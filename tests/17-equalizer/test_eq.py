import math
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

from eq_model import EqModel, used_bins, Preamble, point
from stream_tb import reset, run_stream, start_clock


def pack(i, q):
    return ((q & 0xFFFF) << 16) | (i & 0xFFFF)


def unpack(w):
    def s(x):
        return x - 0x10000 if x & 0x8000 else x
    return s(w & 0xFFFF), s((w >> 16) & 0xFFFF)


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 1
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.fft_log2.value = 6
    dut.kind.value = 0
    start_clock(dut.clk)
    await reset(dut)


def channel(l, rng, gains=(0.3, 0.2)):
    n = 1 << l
    th = [rng.uniform(0, 2 * math.pi) for _ in gains]
    delays = [2, 5][:len(gains)]
    H = np.zeros(n, complex)
    for b in range(n):
        k = b if b < n // 2 else b - n
        H[b] = 1.0 + sum(g * np.exp(1j * t) * np.exp(-2j * np.pi * k * d / n) for g, t, d in zip(gains, th, delays))
    return H


def quant(c):
    return (int(np.clip(round(c.real), -32768, 32767)), int(np.clip(round(c.imag), -32768, 32767)))


def make_frame(l, rng, H, nsym=3, phases=None, noise=0.0, mod=2):
    """returns (ys list per symbol with kinds, ideal X per data symbol (data tones), data tone bins)"""
    n = 1 << l
    pre = Preamble()
    ltf = pre.symbol(1, l)
    xs_ltf = np.array([complex(i, q) for t, i, q in ltf])
    nz = lambda: noise * (rng.normalvariate(0, 1) + 1j * rng.normalvariate(0, 1)) / math.sqrt(2)   # noqa: E731
    def ys_of(x, ph=0.0, gain=1.0):
        out = []
        for b in range(n):
            if x[b] == 0:
                out.append((0, 0))
            else:
                out.append(quant(H[b] * np.exp(1j * ph) * gain * x[b] + nz()))
        return out
    syms = [(0, ys_of(xs_ltf)), (1, ys_of(xs_ltf))]
    ideal = []
    for s in range(nsym):
        tpl = pre.symbol(2, l, frame_start=(s == 0))
        x = np.zeros(n, complex)
        data_bins = []
        for b, (t, i, q) in enumerate(tpl):
            if t == 2:
                x[b] = complex(i, q)
            elif t == 1:
                w = rng.randrange(1 << 4)
                p = point(mod, w)
                x[b] = complex(*p)
                data_bins.append(b)
        ph = phases[s] if phases else 0.0
        syms.append((2 if s == 0 else 3, ys_of(x, ph)))
        ideal.append([x[b] for b in data_bins])
    return syms, ideal


async def run_symbol(dut, l, kind, ys, expect_out, pv=1.0, pr=1.0, seed=0, extra_last=None):
    dut.fft_log2.value = l
    dut.kind.value = kind
    n = 1 << l
    words = [(pack(*y), i == n - 1) for i, y in enumerate(ys)]
    csis = []

    def extra(d, cyc):
        if int(d.m_axis_valid.value) and int(d.m_axis_ready.value):
            csis.append(int(d.m_csi.value))

    res = await run_stream(dut, words, pv, pr, 32, random.Random(seed), expect_out=expect_out, extra=extra, max_cycles=200000)
    return [unpack(w) for w, _ in res.out], [l_ for _, l_ in res.out], csis, res


async def run_frame(dut, l, syms, pv=1.0, pr=1.0, seed=0):
    results = []
    n_data = len(Preamble().symbol(2, l)) and sum(1 for t, _, _ in Preamble().symbol(2, l) if t == 1)
    for k, (kind, ys) in enumerate(syms):
        exp = n_data if kind >= 2 else 0
        out, lasts, csis, res = await run_symbol(dut, l, kind, ys, exp, pv, pr, seed + k)
        results.append((out, lasts, csis, res))
    return results


def model_frame(l, syms):
    m = EqModel(l)
    outs = []
    for kind, ys in syms:
        if kind == 0:
            m.ltf1(ys)
        elif kind == 1:
            m.ltf2(ys)
        else:
            outs.append(m.data(ys, first=(kind == 2)))
    return outs


def evm(out, ideal):
    z = np.array([complex(i, q) for (i, q) in out])
    x = np.array(ideal)
    return math.sqrt(np.mean(np.abs(z - x) ** 2) / np.mean(np.abs(x) ** 2))


@cocotb.test()
async def t17_02_bit_exact(dut):
    """T17-02 equal to the bit-exact model for every N, random channels and phases"""
    await setup(dut)
    rng = random.Random(172)
    for l in range(6, 10):
        for trial in range(2):
            H = channel(l, rng)
            phases = [rng.uniform(-1.0, 1.0) for _ in range(3)]
            syms, ideal = make_frame(l, rng, H, 3, phases, noise=30.0 * trial)
            res = await run_frame(dut, l, syms, seed=l)
            exp = model_frame(l, syms)
            dsyms = [r for r, (k, _) in zip(res, syms) if k >= 2]
            for s, (r, e) in enumerate(zip(dsyms, exp)):
                got = list(zip(r[0], r[2]))
                assert got == e, f"L={l} trial={trial} symbol {s}: first difference at {next(i for i, (a, b) in enumerate(zip(got, e)) if a != b)}"
                assert r[1] == [0] * (len(e) - 1) + [1], "last only on the final data tone"
                assert not r[3].violations


@cocotb.test()
async def t17_03_04_accuracy(dut):
    """T17-03/04 equalisation accuracy, noiseless and at 25 dB per-tone SNR"""
    await setup(dut)
    rng = random.Random(173)
    for l in (6, 8, 9):
        H = channel(l, rng)
        phases = [math.radians(a) for a in (50, -60, 20)]
        syms, ideal = make_frame(l, rng, H, 3, phases, noise=0.0)
        res = await run_frame(dut, l, syms)
        dsyms = [r for r, (k, _) in zip(res, syms) if k >= 2]
        for s, (r, x) in enumerate(zip(dsyms, ideal)):
            e = evm(r[0], x)
            dut._log.info(f"EVM L={l} noiseless symbol {s}: {20 * math.log10(e):.1f} dB")
            assert e < 0.02, f"L={l} symbol {s}: EVM {e:.4f}"
    # noisy: compare with a floating point equaliser of the same structure
    for l in (7, 8):
        H = channel(l, rng)
        sigma = 4096 / (10 ** (25 / 20))
        syms, ideal = make_frame(l, rng, H, 3, [0.3, -0.2, 0.1], noise=sigma)
        res = await run_frame(dut, l, syms)
        dsyms = [r for r, (k, _) in zip(res, syms) if k >= 2]
        ltf = Preamble().symbol(1, l)
        used = [b for b, (t, _, _) in enumerate(ltf) if t]
        sgn = {b: (-1 if ltf[b][1] < 0 else 1) for b in used}
        Y1 = {b: complex(*syms[0][1][b]) for b in used}
        Y2 = {b: complex(*syms[1][1][b]) for b in used}
        Hest = {b: (Y1[b] + Y2[b]) / 2 * sgn[b] / 4096 for b in used}
        pre = Preamble()
        for s in range(3):
            tpl = pre.symbol(2, l, frame_start=(s == 0))
            ys = {b: complex(*syms[2 + s][1][b]) for b in used}
            W = {b: ys[b] / Hest[b] for b in used}
            pil = [(b, 1 if tpl[b][1] > 0 else -1) for b in used if tpl[b][0] == 2]
            c = np.mean([W[b] * sg / 4096 for b, sg in pil])
            zf = [W[b] / c for b in used if tpl[b][0] == 1]
            ef = math.sqrt(np.mean(np.abs(np.array(zf) - np.array(ideal[s])) ** 2) / np.mean(np.abs(np.array(ideal[s])) ** 2))
            ed = evm(dsyms[s][0], ideal[s])
            dut._log.info(f"EVMNOISY L={l} symbol {s}: DUT {20 * math.log10(ed):.2f} dB, float reference {20 * math.log10(ef):.2f} dB")
            assert abs(20 * math.log10(ed / ef)) < 1.0, f"L={l} symbol {s}: DUT EVM differs from the float reference by more than 1 dB"


@cocotb.test()
async def t17_05_csi(dut):
    """T17-05 csi is proportional to |H|^2 (128 at unit gain)"""
    await setup(dut)
    rng = random.Random(175)
    l = 6
    for g in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        H = np.full(1 << l, g, complex)
        syms, ideal = make_frame(l, rng, H, 1)
        res = await run_frame(dut, l, syms)
        csis = res[2][2]
        want = min(255, int(g * g * 128))
        assert all(abs(c - want) <= 1 for c in csis), f"gain {g}: csi {sorted(set(csis))}, expected {want}"


@cocotb.test()
async def t17_06_deep_fade(dut):
    """T17-06 a deep fade is clipped by the gain limit and gets csi 0; other tones unaffected"""
    await setup(dut)
    rng = random.Random(176)
    l = 7
    H = channel(l, rng)
    ub = used_bins(l)
    tpl = Preamble().symbol(2, l, frame_start=True)
    data = [b for b in ub if tpl[b][0] == 1]
    fade = data[10]
    H[fade] = 0.02
    syms, ideal = make_frame(l, rng, H, 1)
    res = await run_frame(dut, l, syms)
    out, lasts, csis, _ = res[2]
    exp = model_frame(l, syms)[0]
    assert list(zip(out, csis)) == exp
    assert csis[10] == 0, f"csi of the faded tone {csis[10]}"
    assert max(max(abs(i), abs(q)) for i, q in out) <= 32767
    others = [i for i in range(len(out)) if i != 10]
    z = np.array([complex(*out[i]) for i in others])
    x = np.array([ideal[0][i] for i in others])
    assert math.sqrt(np.mean(np.abs(z - x) ** 2) / np.mean(np.abs(x) ** 2)) < 0.03


@cocotb.test()
async def t17_07_two_frames(dut):
    """T17-07 two frames in a row with random handshakes; no leakage between frames"""
    await setup(dut)
    rng = random.Random(177)
    l = 7
    for k in range(2):
        H = channel(l, rng, gains=(0.5, 0.4) if k else (0.2, 0.1))
        syms, ideal = make_frame(l, rng, H, 3, [0.2, -0.1, 0.3], noise=20.0)
        res = await run_frame(dut, l, syms, pv=0.6, pr=0.5, seed=k)
        exp = model_frame(l, syms)
        dsyms = [r for r, (kk, _) in zip(res, syms) if kk >= 2]
        for r, e in zip(dsyms, exp):
            assert list(zip(r[0], r[2])) == e, f"frame {k}"
            assert not r[3].violations


@cocotb.test()
async def t17_08_bad_last(dut):
    """T17-08 wrong last position: err_len pulses and the next symbol is still processed"""
    await setup(dut)
    rng = random.Random(178)
    l = 6
    H = channel(l, rng)
    syms, ideal = make_frame(l, rng, H, 1)
    errs = []

    def extra(d, cyc):
        if int(d.err_len.value):
            errs.append(cyc)

    n = 1 << l
    dut.fft_log2.value = l
    dut.kind.value = 0
    words = [(pack(*y), i == n - 5) for i, y in enumerate(syms[0][1])]
    await run_stream(dut, words, 1.0, 1.0, 32, rng, expect_out=0, extra=extra)
    await ClockCycles(dut.clk, 5)
    assert len(errs) >= 1
    # a normal frame afterwards (a new LTF1 restarts the estimate)
    res = await run_frame(dut, l, syms)
    exp = model_frame(l, syms)
    assert list(zip(res[2][0], res[2][2])) == exp[0]


@cocotb.test()
async def t17_09_cycles(dut):
    """T17-09 clocks per data symbol for every N"""
    await setup(dut)
    rng = random.Random(179)
    for l in range(6, 10):
        H = channel(l, rng)
        syms, ideal = make_frame(l, rng, H, 3)
        res = await run_frame(dut, l, syms)
        r = res[3][3]
        clocks = r.out_cycles[-1] - r.in_cycles[0]
        dut._log.info(f"CYCLES N={1 << l}: data symbol in {clocks} clocks (symbol period at 200 MHz: 2880)")
        assert clocks < 2880
