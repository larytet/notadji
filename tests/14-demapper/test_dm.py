import math
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from dm_model import *
from stream_tb import reset, run_stream, start_clock


def pack(i, q):
    return ((q & 0xFFFF) << 16) | (i & 0xFFFF)


def s8(x):
    return x - 256 if x & 0x80 else x


def unpack_llrs(word, n):
    return [s8((word >> (8 * k)) & 0xFF) for k in range(n)]


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 1
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.s_csi.value = 255
    dut.mod.value = 0
    dut.llr_shift.value = 12
    start_clock(dut.clk)
    await reset(dut)


async def run_points(dut, pts, pv=1.0, pr=1.0, seed=0):
    """pts: list of (mod, i, q, csi, sh). Returns list of LLR lists from the DUT."""
    rng = random.Random(seed)
    words = [(pack(i, q), k % 7 == 0) for k, (mod, i, q, c, sh) in enumerate(pts)]

    def pre(d, cyc, idx):
        mod, i, q, c, sh = pts[min(idx, len(pts) - 1)]
        d.mod.value = mod
        d.s_csi.value = c
        d.llr_shift.value = sh

    nbits_log, last_log = [], []

    def extra(d, cyc):
        if int(d.m_axis_valid.value) and int(d.m_axis_ready.value):
            nbits_log.append(int(d.m_nbits.value))

    res = await run_stream(dut, words, pv, pr, 32, rng, expect_out=len(pts), pre=pre, extra=extra)
    outs = []
    for (w, last), (mod, *_), nb in zip(res.out, pts, nbits_log):
        outs.append(unpack_llrs(w, 8))
    return res, outs, nbits_log


def rand_pts(rng, mod, n, amp=7000):
    return [(mod, rng.randint(-amp, amp), rng.randint(-amp, amp), rng.randrange(256), rng.randrange(0, 15)) for _ in range(n)]


@cocotb.test()
async def t14_01_bit_exact(dut):
    """T14-01 every modulation: structured grid plus random points equal the model"""
    await setup(dut)
    rng = random.Random(141)
    for mod in range(8):
        pts = rand_pts(rng, mod, 3000)
        pts += [(mod, a, b, 255, 10) for a in range(-9000, 9001, 600) for b in range(-9000, 9001, 1500)]
        pts += [(mod, a, 0, 128, 12) for a in (-32768, -32767, 32767, 0, 1, -1)]
        res, outs, nbs = await run_points(dut, pts, seed=mod)
        for (m_, i, q, c, sh), got, nb in zip(pts, outs, nbs):
            exp = llrs(m_, i, q, c, sh)
            assert nb == len(exp), f"mod={m_}: nbits {nb} expected {len(exp)}"
            assert got[:len(exp)] == exp, f"mod={m_} I={i} Q={q} csi={c} sh={sh}: {got[:len(exp)]} vs {exp}"
            assert all(v == 0 for v in got[len(exp):]), "unused LLR slots must be zero"


@cocotb.test()
async def t14_02_ideal_points(dut):
    """T14-02 ideal constellation points give the right bits; csi 0 gives zero LLRs"""
    await setup(dut)
    for mod in (0, 1, 2, 3, 4):
        pts = constellation(mod)
        nb = BITS[mod]
        batch = [(mod, p[0], p[1], 255, 12) for w, p in pts]
        res, outs, nbs = await run_points(dut, batch)
        for (w, p), got in zip(pts, outs):
            for k in range(nb):
                bit = (w >> k) & 1
                assert (got[k] > 0) == (bit == 0) and got[k] != 0, f"mod={mod} pattern {w:#x} bit {k}: LLR {got[k]}"
        zero = [(mod, p[0], p[1], 0, 12) for w, p in pts]
        res, outs, nbs = await run_points(dut, zero)
        assert all(all(v == 0 for v in o) for o in outs)


@cocotb.test()
async def t14_03_04_hard_decisions_and_exact(dut):
    """T14-03/04 LLR signs equal the nearest-point bits and the exact max-log signs"""
    await setup(dut)
    rng = random.Random(143)
    for mod in (1, 2, 3, 4):
        pts_c = constellation(mod)
        nb = BITS[mod]
        d = unit(maxm(mod))
        pts = []
        for _ in range(3000):
            w, p = rng.choice(pts_c)
            pts.append((mod, int(p[0] + rng.gauss(0, 0.45 * d)), int(p[1] + rng.gauss(0, 0.45 * d)), 255, 12))
        res, outs, nbs = await run_points(dut, pts, seed=mod)
        checked = diff_nearest = diff_exact = 0
        for (m_, i, q, c, sh), got in zip(pts, outs):
            near = nearest(mod, i, q, pts_c)
            ex = exact_llrs(mod, i, q, pts_c)
            for k in range(nb):
                if abs(got[k]) < 1 or ex[k] == 0:
                    continue
                checked += 1
                if (got[k] > 0) != (((near >> k) & 1) == 0):
                    diff_nearest += 1
                if (got[k] > 0) != (ex[k] > 0):
                    diff_exact += 1
        dut._log.info(f"AGREE mod={mod}: {checked} bits, differ from nearest point {diff_nearest}, from exact max-log {diff_exact}")
        assert diff_nearest == 0, f"mod={mod}: {diff_nearest} hard decisions differ from the nearest point"
        assert diff_exact == 0, f"mod={mod}: {diff_exact} signs differ from exact max-log"


@cocotb.test()
async def t14_05_saturation_and_csi(dut):
    """T14-05 saturation at +/-127; LLR proportional to csi"""
    await setup(dut)
    pts = [(1, 30000, -30000, 255, 0), (1, -30000, 30000, 255, 0), (2, 5000, 5000, 255, 0)]
    res, outs, nbs = await run_points(dut, pts)
    assert outs[0][:2] == [-127, 127] and outs[1][:2] == [127, -127]
    base = [(1, 1000, 0, c, 10) for c in (20, 40, 80)]
    res, outs, nbs = await run_points(dut, base)
    a, b, c = outs[0][0], outs[1][0], outs[2][0]
    assert abs(b - 2 * a) <= 1 and abs(c - 2 * b) <= 1, f"csi scaling {a} {b} {c}"


@cocotb.test()
async def t14_06_handshakes(dut):
    """T14-06 random handshakes with the configuration changing every beat"""
    await setup(dut)
    rng = random.Random(146)
    pts = []
    for _ in range(4000):
        pts += rand_pts(rng, rng.randrange(8), 1)
    for pv, pr in ((0.6, 0.5), (0.9, 0.2), (1.0, 0.7)):
        res, outs, nbs = await run_points(dut, pts, pv, pr, seed=3)
        assert not res.violations
        for (m_, i, q, c, sh), got, nb in zip(pts, outs, nbs):
            exp = llrs(m_, i, q, c, sh)
            assert got[:len(exp)] == exp and nb == len(exp), f"pv={pv} pr={pr}"
        lasts = [l for _, l in res.out]
        assert lasts == [k % 7 == 0 for k in range(len(pts))], "last must pass through"


@cocotb.test()
async def t14_08_noisy_chain(dut):
    """T14-08 random bits, mapped, with noise: hard decisions equal nearest point; QPSK BER near theory"""
    await setup(dut)
    rng = np.random.default_rng(148)
    # QPSK at Es/N0 = 6 dB
    esn0 = 10 ** (6 / 10)
    sigma = S / math.sqrt(2 * esn0)
    n = 40000
    words = rng.integers(0, 4, n)
    pts = []
    for w in words:
        p = point(1, int(w))
        pts.append((1, int(np.clip(p[0] + rng.normal(0, sigma), -32768, 32767)), int(np.clip(p[1] + rng.normal(0, sigma), -32768, 32767)), 255, 12))
    res, outs, nbs = await run_points(dut, pts)
    errs = 0
    for w, got in zip(words, outs):
        for k in range(2):
            bit = (int(w) >> k) & 1
            if (got[k] > 0) != (bit == 0):
                errs += 1
    ber = errs / (2 * n)
    theory = 0.5 * math.erfc(math.sqrt(esn0) / math.sqrt(2))
    dut._log.info(f"BER QPSK Es/N0=6 dB: measured {ber:.4e}, theory {theory:.4e}")
    assert abs(ber / theory - 1) < 0.2, f"BER {ber:.4e} vs theory {theory:.4e}"
    # 16QAM: DUT hard decisions equal nearest-point decisions on noisy samples
    pts_c = constellation(2)
    sigma = unit(2) * 0.6
    pts = []
    truth = []
    for _ in range(3000):
        w, p = pts_c[int(rng.integers(0, 16))]
        pts.append((2, int(p[0] + rng.normal(0, sigma)), int(p[1] + rng.normal(0, sigma)), 255, 12))
    res, outs, nbs = await run_points(dut, pts)
    bad = 0
    for (m_, i, q, c, sh), got in zip(pts, outs):
        near = nearest(2, i, q, pts_c)
        for k in range(4):
            if abs(got[k]) >= 1 and (got[k] > 0) != (((near >> k) & 1) == 0):
                bad += 1
    assert bad == 0
