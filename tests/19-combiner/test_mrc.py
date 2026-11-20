import math
import os
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from mrc_model import combine

B = int(os.environ.get("B", "2"))


def pack(i, q):
    return ((q & 0xFFFF) << 16) | (i & 0xFFFF)


def unpack(w):
    def s(x):
        return x - 0x10000 if x & 0x8000 else x
    return s(w & 0xFFFF), s((w >> 16) & 0xFFFF)


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.s_csi.value = 0
    dut.s_last.value = 0
    dut.m_ready.value = 1
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def run(dut, tones, p_valid=(1.0,), p_ready=1.0, seed=0, lasts=None):
    """tones: list over time of (list of (z) per branch, list of csi per branch). Returns [(z, csi, last)]."""
    rng = random.Random(seed)
    n = len(tones)
    idx = [0] * B
    active = [False] * B
    out = []
    pv = list(p_valid) * B if len(p_valid) == 1 else list(p_valid)
    errs = 0
    prev = None
    cyc = 0
    while len(out) < n and cyc < 400000:
        await FallingEdge(dut.clk)
        vv, dd, cc, ll = 0, 0, 0, 0
        for b in range(B):
            if not active[b] and idx[b] < n and rng.random() < pv[b]:
                active[b] = True
            if active[b]:
                z, c = tones[idx[b]][0][b], tones[idx[b]][1][b]
                vv |= 1 << b
                dd |= pack(*z) << (32 * b)
                cc |= c << (8 * b)
                last = (idx[b] == n - 1) if lasts is None else lasts[b][idx[b]]
                ll |= int(last) << b
        dut.s_valid.value = vv
        dut.s_data.value = dd
        dut.s_csi.value = cc
        dut.s_last.value = ll
        mr = 1 if rng.random() < p_ready else 0
        dut.m_ready.value = mr
        await Timer(1, unit="ns")
        rdy = int(dut.s_ready.value)
        for b in range(B):
            if (vv >> b) & 1 and (rdy >> b) & 1:
                idx[b] += 1
                active[b] = False
        if int(dut.m_valid.value):
            cur = (int(dut.m_data.value), int(dut.m_csi.value), int(dut.m_last.value))
            if prev is not None and prev[0] and not prev[1] and cur != prev[2]:
                errs += 1
            if mr:
                out.append(cur)
            prev = (1, mr, cur)
        else:
            prev = None
        if int(dut.err_len.value):
            errs += 0
        cyc += 1
    await FallingEdge(dut.clk)
    dut.s_valid.value = 0
    return out, errs


def rand_tones(rng, n, zero_p=0.05):
    tones = []
    for _ in range(n):
        zs = [(rng.randint(-32768, 32767), rng.randint(-32768, 32767)) if rng.random() < 0.3 else (rng.randint(-5000, 5000), rng.randint(-5000, 5000)) for _ in range(B)]
        cs = [0 if rng.random() < zero_p else rng.choice([rng.randrange(256), 255, 1, 128]) for _ in range(B)]
        tones.append((zs, cs))
    return tones


@cocotb.test()
async def t19_01_02_bit_exact_and_accuracy(dut):
    """T19-01/02 bit-exact against the model; 0.5% accuracy against the exact weighted mean"""
    await setup(dut)
    rng = random.Random(191)
    tones = rand_tones(rng, 12000)
    # a few all-zero csi sets
    tones[10] = ([(100, 200)] * B, [0] * B)
    tones[11] = ([(-5, 7)] * B, [1] + [0] * (B - 1))
    out, errs = await run(dut, tones)
    assert len(out) == len(tones)
    for (zs, cs), (w, c, l) in zip(tones, out):
        (ei, eq), ec = combine(zs, cs)
        assert (unpack(w), c) == ((ei, eq), ec), f"zs={zs} cs={cs}: got {unpack(w)}, {c}; model {(ei, eq)}, {ec}"
        s = sum(cs)
        if s:
            ex_i = sum(z[0] * x for z, x in zip(zs, cs)) / s
            ex_q = sum(z[1] * x for z, x in zip(zs, cs)) / s
            ex_i, ex_q = max(-32768, min(32767, ex_i)), max(-32768, min(32767, ex_q))
            assert abs(unpack(w)[0] - ex_i) <= 0.005 * abs(ex_i) + 1.5 and abs(unpack(w)[1] - ex_q) <= 0.005 * abs(ex_q) + 1.5, f"accuracy zs={zs} cs={cs}"


@cocotb.test()
async def t19_03_array_gain(dut):
    """T19-03 SNR gain of the combined output over a single branch"""
    await setup(dut)
    rng = np.random.default_rng(193)
    n = 20000
    pts = np.array([complex(a, b) for a in (-3886, -1295, 1295, 3886) for b in (-3886, -1295, 1295, 3886)])
    x = pts[rng.integers(0, 16, n)]
    sigma = 1500.0                                  # noise std per branch (per complex sample), unit gain branches
    noise = (rng.normal(0, sigma / math.sqrt(2), (B, n)) + 1j * rng.normal(0, sigma / math.sqrt(2), (B, n)))
    z = x[None, :] + noise                          # equalised branch values, equal quality
    tones = [([(int(round(z[b, t].real)), int(round(z[b, t].imag))) for b in range(B)], [128] * B) for t in range(n)]
    out, _ = await run(dut, tones)
    zc = np.array([complex(*unpack(w)) for w, c, l in out])
    def evm2(v):
        return np.mean(np.abs(v - x) ** 2) / np.mean(np.abs(x) ** 2)
    single = np.mean([evm2(z[b]) for b in range(B)])
    gain_db = 10 * math.log10(single / evm2(zc))
    want = 10 * math.log10(B)
    dut._log.info(f"ARRAYGAIN B={B}: combined EVM {10 * math.log10(evm2(zc)):.2f} dB, single branch {10 * math.log10(single):.2f} dB, gain {gain_db:.2f} dB (ideal {want:.2f} dB)")
    assert abs(gain_db - want) < 0.7, f"gain {gain_db:.2f} dB, expected {want:.2f}"
    # unequal branches: Rayleigh-like gains, weights follow csi = 128 |g|^2
    g = rng.rayleigh(1 / math.sqrt(2) * 1.0, (B, n)) * np.exp(1j * rng.uniform(0, 2 * np.pi, (B, n)))
    g = np.clip(np.abs(g), 0.2, 1.4)
    noise2 = (rng.normal(0, sigma / math.sqrt(2), (B, n)) + 1j * rng.normal(0, sigma / math.sqrt(2), (B, n)))
    z2 = x[None, :] + noise2 / g
    tones = [([(int(round(z2[b, t].real)), int(round(z2[b, t].imag))) for b in range(B)], [int(min(255, 128 * g[b, t] ** 2)) for b in range(B)]) for t in range(n)]
    out, _ = await run(dut, tones)
    zc2 = np.array([complex(*unpack(w)) for w, c, l in out])
    best = min(evm2(z2[b]) for b in range(B))
    ideal_w = (g ** 2)
    zi = (z2 * ideal_w).sum(0) / ideal_w.sum(0)
    dut._log.info(f"ARRAYGAIN random gains B={B}: combined {10 * math.log10(evm2(zc2)):.2f} dB, ideal float MRC {10 * math.log10(evm2(zi)):.2f} dB, best single {10 * math.log10(best):.2f} dB")
    assert evm2(zc2) < best
    assert abs(10 * math.log10(evm2(zc2) / evm2(zi))) < 0.3


@cocotb.test()
async def t19_04_erased_branch(dut):
    """T19-04 a branch with csi 0 contributes nothing"""
    await setup(dut)
    rng = random.Random(194)
    tones = []
    for _ in range(300):
        zs = [(rng.randint(-5000, 5000), rng.randint(-5000, 5000)) for _ in range(B)]
        cs = [rng.randint(1, 255) for _ in range(B)]
        k = rng.randrange(B)
        cs[k] = 0
        zs[k] = (rng.randint(-32768, 32767), rng.randint(-32768, 32767))       # garbage on the erased branch
        tones.append((zs, cs))
    out, _ = await run(dut, tones)
    for (zs, cs), (w, c, l) in zip(tones, out):
        keep = [i for i in range(B) if cs[i]]
        (ei, eq), ec = combine([zs[i] for i in keep], [cs[i] for i in keep])
        assert (unpack(w), c) == ((ei, eq), ec)


@cocotb.test()
async def t19_05_alignment(dut):
    """T19-05 branches at different times, random sink: no tone lost or mixed; last passes through"""
    await setup(dut)
    rng = random.Random(195)
    tones = rand_tones(rng, 3000)
    pv = [0.9, 0.4, 0.7, 0.3, 0.6, 0.8, 0.5, 0.2][:B]
    out, errs = await run(dut, tones, p_valid=pv, p_ready=0.5, seed=5)
    assert len(out) == len(tones)
    for t, ((zs, cs), (w, c, l)) in enumerate(zip(tones, out)):
        (ei, eq), ec = combine(zs, cs)
        assert (unpack(w), c) == ((ei, eq), ec), f"tone {t}"
        assert l == int(t == len(tones) - 1)
    assert errs == 0, "output changed while stalled"


@cocotb.test()
async def t19_06_last_mismatch(dut):
    """T19-06 err_len pulses when branches disagree on last"""
    await setup(dut)
    rng = random.Random(196)
    tones = rand_tones(rng, 20)
    lasts = [[False] * 20 for _ in range(B)]
    lasts[0][9] = True                         # only branch 0 flags the tone
    seen = []

    async def mon():
        while True:
            await FallingEdge(dut.clk)
            if int(dut.err_len.value):
                seen.append(1)

    m = cocotb.start_soon(mon())
    out, _ = await run(dut, tones, lasts=lasts)
    await ClockCycles(dut.clk, 3)
    m.cancel()
    assert len(out) == 20 and len(seen) >= 1
