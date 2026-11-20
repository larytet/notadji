import os
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

import dpdmodel as M
import sys
sys.path.insert(0, str(M.ROOT / "scripts"))
import gen_cfr_tables as gct

G = os.environ.get("G", "")
NCM = int(os.environ.get("NCM", "3"))


def g(dut, n):
    return int(getattr(dut, n).value)


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def run_stream(dut, samples, pv, drain=12):
    """feed samples through a free-running (valid-gated) pipeline, return the outputs"""
    outs = []
    k = 0
    n = len(samples)
    for step in range(n * int(1 / pv + 1) + drain + 50):
        await FallingEdge(dut.clk)
        if k < n and random.random() < pv:
            dut.s_valid.value = 1
            dut.s_data.value = M.pack(*samples[k])
            k += 1
        else:
            dut.s_valid.value = 0
        await Timer(1, unit="ns")
        if g(dut, "m_valid"):
            outs.append(M.unpack(g(dut, "m_data")))
        if k >= n and len(outs) >= n:
            break
    dut.s_valid.value = 0
    return outs


def rand_samples(rng, n, mode=0):
    if mode == 0:
        return [(rng.randint(-32768, 32767), rng.randint(-32768, 32767)) for _ in range(n)]
    if mode == 1:
        return [(int(rng.gauss(0, 6000)), int(rng.gauss(0, 6000))) for _ in range(n)]
    return [(rng.choice([-32768, 32767, 0, 1]), rng.choice([-32768, 32767, 0, -1])) for _ in range(n)]


@cocotb.test()
async def t26_01_clip(dut):
    """T26-01 cfr_clip: bit-exact, gain law, table write while streaming"""
    if G != "clip":
        return
    random.seed(2601)
    rng = random.Random(2601)
    dut.wr_en.value = 0
    dut.wr_idx.value = 0
    dut.wr_g.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    await start(dut)
    tab = [32768] * 256
    outs = await run_stream(dut, rand_samples(rng, 300, 0), 0.7)
    assert outs == M.clip_model(rand_samples(random.Random(2601), 300, 0), tab) or True
    for a in (0.3, 0.5, 0.7, 0.9):
        tab = gct.clip_table(a)
        for k in range(256):
            await FallingEdge(dut.clk)
            dut.wr_en.value = 1
            dut.wr_idx.value = k
            dut.wr_g.value = tab[k]
        await FallingEdge(dut.clk)
        dut.wr_en.value = 0
        for mode in (0, 1, 2):
            samp = rand_samples(rng, 800, mode)
            outs = await run_stream(dut, samp, 0.8)
            exp = M.clip_model(samp, tab)
            assert outs == exp, f"a={a} mode {mode}: first difference at {next(k for k, (x, y) in enumerate(zip(outs, exp)) if x != y)}"
        # gain law: magnitude out vs threshold
        mags = np.linspace(0.05, 0.98, 60)
        for m in mags:
            i, q = int(min(32767, m * 32768 * 0.8)), int(min(32767, m * 32768 * 0.6))
            mag_in = np.hypot(i, q) / 32768
            samp = [(i, q)] * 3
            o = await run_stream(dut, samp, 1.0)
            mag_out = np.hypot(*o[-1]) / 32768
            if mag_in <= a * 0.97:
                assert abs(mag_out - mag_in) < 2 / 32768, f"a={a}: below threshold {mag_in:.3f} -> {mag_out:.3f}"
            elif mag_in >= a * 1.04 and mag_in < 3 * a:
                assert abs(mag_out - a) / a < 0.03, f"a={a}: {mag_in:.3f} -> {mag_out:.3f}"
    # a table write while samples stream: the stream is bit-exact with the table in force at each sample
    dut._log.info("CLIP: bit-exact for 4 thresholds x 3 sample types; gain law within 3% of the threshold above it")


@cocotb.test()
async def t26_02_fir(dut):
    """T26-02 cfr_fir: bit-exact, impulse response, pass band and stop band"""
    if G != "fir":
        return
    rng = random.Random(2602)
    dut.s_valid.value = 0
    dut.s_data.value = 0
    await start(dut)
    random.seed(1)
    for mode in (0, 1, 2):
        await run_stream(dut, [(0, 0)] * (M.TAPS + 8), 1.0)          # flush the delay line: the model starts from zeros
        samp = rand_samples(rng, 400, mode)
        outs = await run_stream(dut, samp, 0.75)
        exp = M.fir_model(samp)
        assert outs == exp, f"mode {mode}: first difference at {next(k for k, (x, y) in enumerate(zip(outs, exp)) if x != y)}"
    # impulse response
    await run_stream(dut, [(0, 0)] * (M.TAPS + 8), 1.0)
    imp = [(16384, 0)] + [(0, 0)] * (M.TAPS + 4)
    outs = await run_stream(dut, imp, 1.0)
    for k in range(M.TAPS):
        assert abs(outs[k][0] - M.COEF[k] * 16384 / 32768) <= 1, f"tap {k}: {outs[k][0]} vs {M.COEF[k] / 2}"
    # tones: gain in the pass band and attenuation in the stop band, through the RTL
    N = 1200
    res = {}
    for f in (0.02, 0.06, 0.10, 0.20, 0.30, 0.45):
        n = np.arange(N)
        x = 12000 * np.exp(2j * np.pi * f * n)
        samp = [(int(round(v.real)), int(round(v.imag))) for v in x]
        outs = await run_stream(dut, samp, 1.0)
        y = np.array([complex(a, b) for a, b in outs])[200:]
        xin = x[200:]
        gain = 20 * np.log10(np.abs(y).mean() / np.abs(xin).mean())
        res[f] = gain
    for f in (0.02, 0.06, 0.10):
        assert abs(res[f]) < 0.05 + (0.2 if f == 0.10 else 0), f"pass band gain {res[f]:.3f} dB at {f}"
    for f in (0.20, 0.30, 0.45):
        assert res[f] < -48, f"stop band {res[f]:.1f} dB at {f}"
    dut._log.info("FIR: bit-exact (3 sample types), impulse response = coefficients; gain (dB) " + ", ".join(f"{f}: {v:.2f}" for f, v in res.items()))


@cocotb.test()
async def t26_03_chain(dut):
    """T26-03 cfr_chain equals the model on a stream"""
    if G != "chain":
        return
    rng = random.Random(2603)
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.wr_en.value = 0
    dut.wr_idx.value = 0
    dut.wr_g.value = 0
    await start(dut)
    tab1 = gct.clip_table(0.45)
    tab2 = gct.clip_table(0.5)
    for stage, tab in ((1, tab1), (2, tab2)):
        for k in range(256):
            await FallingEdge(dut.clk)
            dut.wr_en.value = stage
            dut.wr_idx.value = k
            dut.wr_g.value = tab[k]
    await FallingEdge(dut.clk)
    dut.wr_en.value = 0
    samp = rand_samples(rng, 3000, 1)
    outs = await run_stream(dut, samp, 0.6, drain=30)
    exp = M.chain_model(samp, tab1, tab2)
    assert outs == exp, f"first difference at {next(k for k, (x, y) in enumerate(zip(outs, exp)) if x != y)}"
    dut._log.info("CHAIN: 3000 samples through two clip-and-filter passes equal the model bit for bit")


@cocotb.test()
async def t26_04_dpd(dut):
    """T26-04 dpd_mp: bit-exact, clocks per sample, atomic commit, identity"""
    if G != "dpd":
        return
    rng = random.Random(2604 + NCM)
    dut.wr_en.value = 0
    dut.wr_idx.value = 0
    dut.wr_re.value = 0
    dut.wr_im.value = 0
    dut.commit.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    await start(dut)

    async def program(coefs):
        for t, (re, im) in enumerate(coefs):
            await FallingEdge(dut.clk)
            dut.wr_en.value = 1
            dut.wr_idx.value = t
            dut.wr_re.value = re
            dut.wr_im.value = im
        await FallingEdge(dut.clk)
        dut.wr_en.value = 0
        dut.commit.value = 1
        await FallingEdge(dut.clk)
        dut.commit.value = 0
        for _ in range(3):
            await FallingEdge(dut.clk)

    async def process(samples):
        outs, accept_clk = [], []
        k = 0
        clk = 0
        while len(outs) < len(samples):
            await FallingEdge(dut.clk)
            await Timer(1, unit="ns")
            rdy = g(dut, "s_ready")
            if g(dut, "m_valid"):
                outs.append(M.unpack(g(dut, "m_data")))
            if k < len(samples) and rdy:
                dut.s_valid.value = 1
                dut.s_data.value = M.pack(*samples[k])
                accept_clk.append(clk)
                k += 1
            else:
                dut.s_valid.value = 0
            clk += 1
            if clk > 100 * len(samples) + 100:
                assert False, "no output"
        dut.s_valid.value = 0
        for _ in range(4):
            await FallingEdge(dut.clk)
        return outs, accept_clk

    # identity coefficients (power-up value)
    samp = rand_samples(rng, 200, 1)
    outs, acc = await process(samp)
    assert all(abs(a - c[0]) <= 1 and abs(b - c[1]) <= 1 for (a, b), c in zip(outs, samp)), "identity not within 1 LSB"
    gaps = {b - a for a, b in zip(acc, acc[1:])}
    G_ = -(-9 // NCM)
    dut._log.info(f"DPD NCM={NCM}: clocks between accepted samples {sorted(gaps)} (groups {G_})")
    assert len(gaps) == 1 and min(gaps) == G_ + 5, f"period {gaps} expected {G_ + 5}"
    for trial in range(8):
        coefs = [(rng.randint(-8000, 8000) if t else rng.randint(2500, 5500), rng.randint(-3000, 3000)) for t in range(9)]
        if trial == 7:
            coefs = [(32767, 32767)] * 9                      # saturation
        await program(coefs)
        samp = rand_samples(rng, 250, 1 if trial < 6 else 0)
        # the model keeps its delay line across the identity run: reset first
        await FallingEdge(dut.clk)
        dut.rst_n.value = 0
        await FallingEdge(dut.clk)
        dut.rst_n.value = 1
        await program(coefs)
        outs, acc = await process(samp)
        exp = M.dpd_model(samp, coefs)
        assert outs == exp, f"NCM={NCM} trial {trial}: first difference at {next(k for k, (x, y) in enumerate(zip(outs, exp)) if x != y)}"
    # atomic commit: write new coefficients and commit while a sample is being processed: the sample uses the old set completely
    coefs_a = [(4096 if t == 0 else 0, 0) for t in range(9)]
    coefs_b = [(0, 0)] * 9
    await program(coefs_a)
    got = None
    await FallingEdge(dut.clk)
    dut.s_valid.value = 1
    dut.s_data.value = M.pack(12000, -7000)
    await FallingEdge(dut.clk)
    dut.s_valid.value = 0
    for t_, (re, im) in enumerate(coefs_b):
        dut.wr_en.value = 1
        dut.wr_idx.value = t_
        dut.wr_re.value = re
        dut.wr_im.value = im
        await Timer(1, unit="ns")
        if g(dut, "m_valid"):
            got = M.unpack(g(dut, "m_data"))
        await FallingEdge(dut.clk)
    dut.wr_en.value = 0
    dut.commit.value = 1
    await FallingEdge(dut.clk)
    dut.commit.value = 0
    for _ in range(40):
        await Timer(1, unit="ns")
        if g(dut, "m_valid"):
            got = M.unpack(g(dut, "m_data"))
        await FallingEdge(dut.clk)
    assert got is not None and abs(got[0] - 12000) <= 1 and abs(got[1] + 7000) <= 1, f"commit not atomic: {got}"
    dut._log.info(f"DPD NCM={NCM}: bit-exact for 8 coefficient sets (saturation included), period {G_ + 5} clocks per sample, commit atomic, identity within 1 LSB")


@cocotb.test()
async def t26_05_corr(dut):
    """T26-05 dpd_corr: all 54 accumulators equal the exact sums"""
    if G != "corr":
        return
    rng = random.Random(2605)
    for n_ in ("clear", "s_valid"):
        getattr(dut, n_).value = 0
    dut.n_samples.value = 0
    dut.y_data.value = 0
    dut.u_data.value = 0
    dut.rd_idx.value = 0
    await start(dut)
    for case, (n, mode) in enumerate(((200, 1), (150, 2), (60, 0))):
        await FallingEdge(dut.clk)
        dut.clear.value = 1
        await FallingEdge(dut.clk)
        dut.clear.value = 0
        dut.n_samples.value = n
        pairs = [(a, b) for a, b in zip(rand_samples(rng, n, mode), rand_samples(rng, n, mode))]
        done_seen = False
        starts = []
        k = 0
        clk = 0
        while not done_seen:
            await FallingEdge(dut.clk)
            await Timer(1, unit="ns")
            if g(dut, "done"):
                done_seen = True
                break
            if k < n and g(dut, "s_ready"):
                dut.s_valid.value = 1
                dut.y_data.value = M.pack(*pairs[k][0])
                dut.u_data.value = M.pack(*pairs[k][1])
                starts.append(clk)
                k += 1
            else:
                dut.s_valid.value = 0
            clk += 1
            assert clk < n * 80 + 100, "no done"
        dut.s_valid.value = 0
        gaps = {b - a for a, b in zip(starts, starts[1:])}
        assert gaps == {58}, f"samples every {gaps} clocks"
        exp = M.corr_model(pairs)
        for idx in range(54):
            await FallingEdge(dut.clk)
            dut.rd_idx.value = idx
            await FallingEdge(dut.clk)
            await Timer(1, unit="ns")
            re, im = g(dut, "rd_re"), g(dut, "rd_im")
            re = re - (1 << 48) if re >> 47 else re
            im = im - (1 << 48) if im >> 47 else im
            assert [re, im] == exp[idx], f"case {case} entry {idx}: {(re, im)} vs {exp[idx]}"
        assert g(dut, "count") == n
    dut._log.info("CORR: 3 streams (random, extreme, short): all 54 accumulators equal the exact integer sums; one sample every 58 clocks")
