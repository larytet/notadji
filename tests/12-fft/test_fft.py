import os
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from fft_model import fft_fixed
from stream_tb import reset, run_stream, start_clock

MAXL = int(os.environ.get("MAXL", "9"))
ALL = (1 << 10) - 1


def pack(re, im):
    return ((im & 0xFFFF) << 16) | (re & 0xFFFF)


def unpack(w):
    def s(x):
        return x - 0x10000 if x & 0x8000 else x
    return s(w & 0xFFFF), s((w >> 16) & 0xFFFF)


def rand_sym(rng, n, amp=20000):
    return [(rng.randint(-amp, amp), rng.randint(-amp, amp)) for _ in range(n)]


def words_of(syms):
    out = []
    for s in syms:
        for i, (re, im) in enumerate(s):
            out.append((pack(re, im), i == len(s) - 1))
    return out


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.fft_log2.value = 6
    dut.inverse.value = 0
    dut.shift_mask.value = 0
    start_clock(dut.clk)
    await reset(dut)


def cfg_pre(dut, cfgs, lens):
    bounds, acc = [], 0
    for n in lens:
        bounds.append(acc)
        acc += n

    def pre(d, cyc, idx):
        s = 0
        for i, b in enumerate(bounds):
            if idx >= b:
                s = i
        c = cfgs[min(s, len(cfgs) - 1)]
        d.fft_log2.value = c[0]
        d.inverse.value = int(c[1])
        d.shift_mask.value = c[2]

    return pre


async def run_syms(dut, syms, cfgs, pv=1.0, pr=1.0, seed=0):
    rng = random.Random(seed)
    words = words_of(syms)
    pre = cfg_pre(dut, cfgs, [len(s) for s in syms])
    res = await run_stream(dut, words, pv, pr, 32, rng, expect_out=len(words), pre=pre)
    outs, cur = [], []
    for w, last in res.out:
        cur.append(unpack(w))
        if last:
            outs.append(cur)
            cur = []
    return res, outs


@cocotb.test()
async def t12_01_bit_exact(dut):
    """T12-01 forward and inverse, several shift masks, every N: equal to the bit-exact model incl. saturation count"""
    await setup(dut)
    rng = random.Random(121)
    total_ovf = 0
    for l in range(6, MAXL + 1):
        n = 1 << l
        cfgs = [(l, False, ALL), (l, True, 0b11111), (l, False, 0), (l, True, ALL), (l, True, 0)]
        syms = [rand_sym(rng, n) for _ in cfgs]
        res, outs = await run_syms(dut, syms, cfgs, seed=l)
        for s, c, o in zip(syms, cfgs, outs):
            exp, ovf = fft_fixed(s, c[0], c[1], c[2])
            total_ovf += ovf
            assert o == exp, f"L={l} inverse={c[1]} mask={c[2]:#x}"
    await ClockCycles(dut.clk, 3)
    assert int(dut.ovf_cnt.value) == total_ovf, f"ovf_cnt {int(dut.ovf_cnt.value)} model {total_ovf}"
    assert total_ovf > 0


@cocotb.test()
async def t12_02_accuracy(dut):
    """T12-02 error against floating point (forward with all stages shifted, and inverse)"""
    await setup(dut)
    rng = random.Random(122)
    for l in range(6, MAXL + 1):
        n = 1 << l
        syms = [rand_sym(rng, n, 32000), rand_sym(rng, n, 32000)]
        cfgs = [(l, False, ALL), (l, True, ALL)]
        res, outs = await run_syms(dut, syms, cfgs, seed=l)
        for s, o, inv in zip(syms, outs, (False, True)):
            x = np.array([complex(a, b) for a, b in s])
            ref = np.fft.ifft(x) if inv else np.fft.fft(x) / n
            y = np.array([complex(a, b) for a, b in o])
            err = np.sqrt(np.mean(np.abs(y - ref) ** 2) / np.mean(np.abs(ref) ** 2))
            assert err < 3e-3, f"L={l} inverse={inv}: relative error {err:.2e}"


@cocotb.test()
async def t12_03_known_signals(dut):
    """T12-03 impulse gives a flat spectrum; a complex exponential gives a single peak"""
    await setup(dut)
    for l in range(6, MAXL + 1):
        n = 1 << l
        imp = [(20000, 0)] + [(0, 0)] * (n - 1)
        k0 = 5 + l
        a = 20000
        tone = [(int(round(a * np.cos(2 * np.pi * k0 * i / n))), int(round(a * np.sin(2 * np.pi * k0 * i / n)))) for i in range(n)]
        cfgs = [(l, False, 0), (l, False, ALL)]
        res, outs = await run_syms(dut, [imp, tone], cfgs, seed=1)
        assert all(abs(re - 20000) <= 3 and abs(im) <= 3 for re, im in outs[0]), f"L={l}: impulse spectrum not flat"
        y = outs[1]
        mags = [abs(complex(re, im)) for re, im in y]
        assert int(np.argmax(mags)) == k0 and abs(mags[k0] - a) < 60, f"L={l}: peak at {int(np.argmax(mags))}, {mags[k0]}"
        others = [m for k, m in enumerate(mags) if k != k0]
        assert max(others) < 12, f"L={l}: leakage {max(others):.1f}"


@cocotb.test()
async def t12_04_round_trip(dut):
    """T12-04 forward (all shifted) then inverse restores the input"""
    await setup(dut)
    rng = random.Random(124)
    for l in range(6, MAXL + 1):
        n = 1 << l
        x = rand_sym(rng, n, 30000)
        res, f = await run_syms(dut, [x], [(l, False, ALL)])
        res, y = await run_syms(dut, [f[0]], [(l, True, 0)])
        xa = np.array([complex(a, b) for a, b in x])
        ya = np.array([complex(a, b) for a, b in y[0]])
        err = np.sqrt(np.mean(np.abs(ya - xa) ** 2) / np.mean(np.abs(xa) ** 2))
        dut._log.info(f"ROUNDTRIP L={l} relative error {err:.2e}")
        assert err < 2e-2, f"L={l}: round-trip error {err:.2e}"


@cocotb.test()
async def t12_05_saturation(dut):
    """T12-05 full-scale input without shifting saturates; the counter equals the model"""
    await setup(dut)
    l = 6
    n = 1 << l
    x = [(32767, 32767)] * n
    res, outs = await run_syms(dut, [x], [(l, False, 0)])
    exp, ovf = fft_fixed(x, l, False, 0)
    assert outs[0] == exp and ovf > 0
    await ClockCycles(dut.clk, 3)
    assert int(dut.ovf_cnt.value) == ovf


@cocotb.test()
async def t12_06_mixed_symbols(dut):
    """T12-06 back-to-back symbols of different sizes and modes, random handshakes, config per symbol"""
    await setup(dut)
    rng = random.Random(126)
    cfgs, syms = [], []
    for _ in range(14):
        l = rng.randint(6, MAXL)
        cfgs.append((l, rng.random() < 0.5, rng.choice([0, ALL, 0b10101, 0b1111])))
        syms.append(rand_sym(rng, 1 << l))
    exp = [fft_fixed(s, c[0], c[1], c[2])[0] for s, c in zip(syms, cfgs)]
    for pv, pr in ((1.0, 1.0), (0.6, 0.5), (0.9, 0.2)):
        res, outs = await run_syms(dut, syms, cfgs, pv, pr, seed=3)
        assert outs == exp, f"pv={pv} pr={pr}"
        assert not res.violations


@cocotb.test()
async def t12_07_throughput(dut):
    """T12-07 steady output symbol period at N=256 is at most N/2*L + 40 clocks"""
    await setup(dut)
    rng = random.Random(127)
    l = min(8, MAXL)
    n = 1 << l
    nsym = 10
    syms = [rand_sym(rng, n) for _ in range(nsym)]
    cfgs = [(l, False, ALL)] * nsym
    res, outs = await run_syms(dut, syms, cfgs, seed=7)
    starts = [res.out_cycles[i * n] for i in range(nsym)]
    period = (starts[-1] - starts[nsym // 2]) / (nsym - 1 - nsym // 2)
    limit = n // 2 * l + 40
    dut._log.info(f"PERIOD N={n}: {period:.1f} clocks (limit {limit})")
    assert period <= limit, f"period {period} above {limit}"


@cocotb.test()
async def t12_08_bad_last(dut):
    """T12-08 wrong last position: err_len pulses, symbols still closed by the count"""
    await setup(dut)
    rng = random.Random(128)
    l = 6
    n = 1 << l
    syms = [rand_sym(rng, n) for _ in range(5)]
    words = []
    for k, s in enumerate(syms):
        for i, (re, im) in enumerate(s):
            last = (i == n - 1)
            if k == 1:
                last = (i == n - 4)
            if k == 3:
                last = False
            words.append((pack(re, im), last))
    errs = []

    def extra(d, cyc):
        if int(d.err_len.value):
            errs.append(cyc)

    dut.fft_log2.value = l
    dut.shift_mask.value = ALL
    res = await run_stream(dut, words, 1.0, 1.0, 32, rng, expect_out=len(words), extra=extra)
    outs, cur = [], []
    for w, last in res.out:
        cur.append(unpack(w))
        if last:
            outs.append(cur)
            cur = []
    exp = [fft_fixed(s, l, False, ALL)[0] for s in syms]
    assert outs == exp
    assert len(errs) == 3, f"err_len pulses {errs}"
