import random

import cocotb

from dfts_model import MS, dft_mixed, dft_ref, rms_err
from stream_tb import reset, run_stream, start_clock


def pack(re, im):
    return ((im & 0xFFFF) << 16) | (re & 0xFFFF)


def unpack(w):
    re, im = w & 0xFFFF, (w >> 16) & 0xFFFF
    return (re - 65536 if re >= 32768 else re, im - 65536 if im >= 32768 else im)


async def setup(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "m_sel", "inverse", "in_rot", "out_rot"):
        getattr(dut, n).value = 0
    dut.m_axis_ready.value = 1
    start_clock(dut.clk)
    await reset(dut)


def make_symbols(rng, cases):
    """cases: list of (m_sel, inverse, in_rot, out_rot, amp). Returns words, starts {idx: case}, expected model outputs"""
    words, starts, exp, ovf = [], {}, [], 0
    for ms, inv, ir, orot, amp in cases:
        m = MS[ms]
        if amp == "ext":
            x = [(rng.choice([-32768, 32767]), rng.choice([-32768, 32767])) for _ in range(m)]
        else:
            x = [(rng.randint(-amp, amp), rng.randint(-amp, amp)) for _ in range(m)]
        y, o = dft_mixed(x, ms, inv, ir, orot)
        ovf += o
        starts[len(words)] = (ms, inv, ir, orot)
        words += [(pack(a, b), i == m - 1) for i, (a, b) in enumerate(x)]
        exp += [(w, i == m - 1) for i, w in enumerate(pack(a, b) for a, b in y)]
    return words, starts, exp, ovf


async def run_symbols(dut, cases, rng, pv, pr, max_cycles=3000000):
    words, starts, exp, ovf = make_symbols(rng, cases)

    def pre(d, cyc, idx):
        if idx in starts:
            ms, inv, ir, orot = starts[idx]
            d.m_sel.value, d.inverse.value, d.in_rot.value, d.out_rot.value = ms, inv, ir, orot
        else:                                   # configuration is sampled with the first sample only
            d.m_sel.value, d.inverse.value = rng.getrandbits(2), rng.getrandbits(1)
            d.in_rot.value, d.out_rot.value = rng.randrange(512), rng.randrange(512)

    r = await run_stream(dut, words, pv, pr, 32, rng, expect_out=len(exp), pre=pre, max_cycles=max_cycles)
    assert not r.violations, r.violations
    return r, exp, ovf


@cocotb.test()
async def t31_01_bit_exact(dut):
    """T31-01 bit-exact against the model: all M, both directions, rotations, amplitudes, random handshakes"""
    await setup(dut)
    rng = random.Random(3101)
    cases = []
    for ms in range(4):
        m = MS[ms]
        for inv in (0, 1):
            cases.append((ms, inv, 0, 0, 4000))
            cases.append((ms, inv, m // 2, m // 2, 12000))
            cases.append((ms, inv, rng.randrange(m), rng.randrange(m), 30000))
    cases.append((2, 0, 7, 11, "ext"))
    cases.append((3, 1, 100, 300, "ext"))
    rng.shuffle(cases)
    r, exp, ovf = await run_symbols(dut, cases, rng, 0.9, 0.8)
    assert r.out == exp, "output differs from the model"
    assert int(dut.ovf_cnt.value) == ovf, (int(dut.ovf_cnt.value), ovf)
    assert int(dut.err_len.value) == 0
    dut._log.info(f"{len(cases)} symbols equal the model, saturation events {ovf}")


@cocotb.test()
async def t31_02_accuracy_and_clocks(dut):
    """T31-02 accuracy against the unitary floating-point DFT and round trip; T31-10 clocks per symbol"""
    await setup(dut)
    rng = random.Random(3102)
    for ms in range(4):
        m = MS[ms]
        x = [(rng.randint(-8000, 8000), rng.randint(-8000, 8000)) for _ in range(m)]
        sends = []
        for inv in (0, 1):
            r, exp, _ = await run_symbols(dut, [(ms, inv, 0, 0, 8000)] * 1, random.Random(ms * 7 + inv), 1.0, 1.0)
        # explicit accuracy: run the model-checked symbols and compare with numpy
        cases = [(ms, 0, 0, 0, 8000), (ms, 1, 0, 0, 8000)]
        words, starts, exp, ovf = make_symbols(random.Random(99 + ms), cases)
        r, exp2, _ = await run_symbols(dut, cases, random.Random(99 + ms), 1.0, 1.0)
        xs = [unpack(w) for w, _ in words[:m]]
        yd = [unpack(w) for w, _ in r.out[:m]]
        e_f = rms_err(yd, dft_ref(xs, False))
        xs2 = [unpack(w) for w, _ in words[m:]]
        yd2 = [unpack(w) for w, _ in r.out[m:]]
        e_i = rms_err(yd2, dft_ref(xs2, True))
        assert e_f < 0.005 and e_i < 0.005, (m, e_f, e_i)
        # round trip: forward then inverse of the forward output
        fwd = yd
        r3, exp3, _ = await run_symbols(dut, [(ms, 1, 0, 0, 100)], random.Random(5), 1.0, 1.0)
        import numpy as np
        back_words = [(pack(a, b), i == m - 1) for i, (a, b) in enumerate(fwd)]
        # feed the forward output through the inverse
        def pre(d, cyc, idx):
            d.m_sel.value, d.inverse.value, d.in_rot.value, d.out_rot.value = ms, 1, 0, 0
        rr = await run_stream(dut, back_words, 1.0, 1.0, 32, rng, expect_out=m, pre=pre, max_cycles=300000)
        yb = np.array([complex(*unpack(w)) for w, _ in rr.out])
        xr = np.array([complex(a, b) for a, b in xs])
        e_rt = float(np.sqrt(np.mean(np.abs(yb - xr) ** 2) / np.mean(np.abs(xr) ** 2)))
        assert e_rt < 0.005, e_rt
        # clocks: six symbols back to back, always valid, always ready
        r4, exp4, _ = await run_symbols(dut, [(ms, 0, 0, m // 2, 8000)] * 6, random.Random(11), 1.0, 1.0)
        firsts = [r4.out_cycles[i * m] for i in range(6)]
        period = (firsts[-1] - firsts[1]) / 4
        lat = r4.out_cycles[0] - r4.in_cycles[0]
        dut._log.info(f"CLOCKS M={m}: latency first input to first output {lat}, symbol period {period:.0f} clocks (budget 2880); error forward {e_f:.4%} inverse {e_i:.4%} round trip {e_rt:.4%}")
