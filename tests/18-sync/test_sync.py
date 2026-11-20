import math
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from sync_sig import make_burst, noise_only, stf_ltf


async def setup(dut, l=8):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.fft_log2.value = l
    dut.thr_sel.value = 0
    dut.min_power.value = 1000
    dut.agc_lo.value = 0
    dut.agc_hi.value = 0xFFFFFFFF
    dut.rearm.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.rst_n.value = 0
    for _ in range(4):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


def pack(i, q):
    return ((q & 0xFFFF) << 16) | (i & 0xFFFF)


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def s24(x):
    return x - (1 << 24) if x & (1 << 23) else x


async def run_samples(dut, samples, rearm=True, tail_clocks=40):
    """stream samples one per clock; returns dict with det_n, fall_n, inc, angle, outs, agc events"""
    ev = dict(det=[], fall=[], outs=[], up=[], down=[])
    if rearm:
        await FallingEdge(dut.clk)
        dut.rearm.value = 1
        dut.s_valid.value = 0
        await FallingEdge(dut.clk)
        dut.rearm.value = 0
    k = 0
    n = len(samples) + tail_clocks
    for step in range(n):
        await FallingEdge(dut.clk)
        if step < len(samples):
            dut.s_valid.value = 1
            dut.s_data.value = pack(*samples[step])
        else:
            dut.s_valid.value = 0
        await Timer(1, unit="ns")
        # pulses are registered: they belong to the sample presented one clock earlier
        if int(dut.det.value):
            ev["det"].append(step - 1)
        if int(dut.fall.value):
            ev["fall"].append(step - 1)
        if int(dut.agc_up.value):
            ev["up"].append(step - 1)
        if int(dut.agc_down.value):
            ev["down"].append(step - 1)
        if int(dut.m_valid.value):
            w = int(dut.m_data.value)
            ev["outs"].append((s16(w & 0xFFFF), s16((w >> 16) & 0xFFFF)))
    ev["inc"] = s24(int(dut.cfo_inc.value))
    ev["angle"] = int(dut.cfo_angle.value)
    ev["k_back"] = int(dut.k_back.value)
    return ev


@cocotb.test()
async def t18_01_detection(dut):
    """T18-01 detection rate and acquisition time"""
    rng = random.Random(181)
    for l in (6, 7, 8, 9):
        await setup(dut, l)
        n = 1 << l
        p = n // 4
        for snr, need in ((20, 1.0), (10, 1.0), (5, 0.9)):
            nb = 12 if l == 9 else 20
            ok, acq = 0, []
            for b in range(nb):
                gap = rng.randint(100, 300)
                samples, tr = make_burst(l, rng, snr, rng.uniform(-1.9, 1.9), gap)
                ev = await run_samples(dut, samples)
                if len(ev["det"]) == 1 and tr["gap"] <= ev["det"][0] <= tr["stf_end"]:
                    ok += 1
                    acq.append(ev["det"][0] - tr["gap"])
            rate = ok / nb
            dut._log.info(f"DETECT N={n} SNR={snr} dB: {ok}/{nb} bursts, detection after {np.mean(acq) if acq else float('nan'):.1f} samples ({np.mean(acq) / p if acq else float('nan'):.2f} P) from the start of the STF")
            assert rate >= need, f"N={n} SNR={snr}: detection rate {rate}"


@cocotb.test()
async def t18_02_false_alarm(dut):
    """T18-02 no detection in noise only or in silence"""
    rng = random.Random(182)
    await setup(dut, 8)
    for power in (50, 2000, 40000):
        ev = await run_samples(dut, noise_only(8, rng, 40000, power))
        assert ev["det"] == [], f"false detection in noise of power {power}: {ev['det'][:3]}"
        assert not dut.locked.value
    ev = await run_samples(dut, [(0, 0)] * 5000)
    assert ev["det"] == [], "silence must not trigger"


@cocotb.test()
async def t18_03_04_cfo(dut):
    """T18-03/04 carrier-offset estimate error and the residual after derotation"""
    rng = random.Random(183)
    l = 8
    n = 1 << l
    await setup(dut, l)
    unit = (1 << 24) / n            # phase step of one sub-carrier spacing per sample, in 2^24 units
    for snr, tol in ((20, 0.02), (10, 0.05)):
        worst = 0.0
        for off in (-1.9, -1.0, -0.5, -0.1, 0.1, 0.5, 1.0, 1.9):
            samples, tr = make_burst(l, rng, snr, off, 200)
            ev = await run_samples(dut, samples)
            assert len(ev["det"]) == 1, f"no detection at offset {off}, SNR {snr}"
            err = abs(ev["inc"] - tr["inc_true"]) / unit
            worst = max(worst, err)
            assert err < tol, f"SNR {snr} offset {off}: estimate error {err:.4f} sub-carrier spacings"
            if snr == 20:
                # residual offset of the derotated output, from the two identical long-training symbols
                lt = tr["ltf_len"]
                s0 = tr["stf_end"] + 4
                seg = np.array([complex(*ev["outs"][k + 1]) for k in range(s0, s0 + lt - 8)])      # output is one clock late
                seg2 = np.array([complex(*ev["outs"][k + 1]) for k in range(s0 + lt, s0 + lt + lt - 8)])
                ang = np.angle(np.sum(seg2 * np.conj(seg)))
                f_res = ang / (2 * np.pi * lt) * n
                assert abs(f_res) < 0.1, f"offset {off}: residual {f_res:.3f} sub-carrier spacings after derotation"
        dut._log.info(f"CFO SNR={snr} dB: worst estimate error {worst:.4f} sub-carrier spacings")


@cocotb.test()
async def t18_05_timing(dut):
    """T18-05 STF end marker: bias and spread"""
    rng = random.Random(185)
    l = 7
    n = 1 << l
    lc = n >> 3
    await setup(dut, l)
    for snr in (20, 10, 5):
        errs = []
        for b in range(60):
            samples, tr = make_burst(l, rng, snr, rng.uniform(-1.5, 1.5), rng.randint(100, 250))
            ev = await run_samples(dut, samples)
            if len(ev["fall"]) == 1 and len(ev["det"]) == 1:
                errs.append(ev["fall"][0] - ev["k_back"] - tr["stf_end"])
        e = np.array(errs)
        dut._log.info(f"TIMING N={n} SNR={snr} dB: {len(e)}/60 markers, error (fall - k_back - end of STF) mean {e.mean():.2f}, std {e.std():.2f}, max |e| {np.abs(e).max()}, prefix {lc}")
        assert len(e) >= 55
        if snr == 20:
            assert np.percentile(np.abs(e), 99) <= 0.25 * lc + 2, f"99th percentile {np.percentile(np.abs(e), 99)}"


@cocotb.test()
async def t18_06_agc(dut):
    """T18-06 power monitor pulses outside the band only"""
    rng = random.Random(186)
    l = 7
    await setup(dut, l)
    dut.agc_lo.value = 500
    dut.agc_hi.value = 2000
    for power, want in ((1000, "none"), (60, "up"), (9000, "down"), (1000, "none")):
        ev = await run_samples(dut, noise_only(l, rng, 600, power), rearm=False, tail_clocks=5)
        # skip the first window while it fills with the previous level
        up = [t for t in ev["up"] if t > 80]
        down = [t for t in ev["down"] if t > 80]
        if want == "none":
            assert not up and not down, f"power {power}: pulses {up[:3]} {down[:3]}"
        elif want == "up":
            assert up and not down, f"power {power}: expected agc_up"
        else:
            assert down and not up, f"power {power}: expected agc_down"


@cocotb.test()
async def t18_07_bursts_in_a_row(dut):
    """T18-07 three bursts with rearm between them"""
    rng = random.Random(187)
    l = 7
    n = 1 << l
    await setup(dut, l)
    unit = (1 << 24) / n
    for off in (0.7, -1.2, 1.6):
        samples, tr = make_burst(l, rng, 20, off, rng.randint(80, 300))
        ev = await run_samples(dut, samples, rearm=True)
        assert len(ev["det"]) == 1 and len(ev["fall"]) == 1
        assert abs(ev["inc"] - tr["inc_true"]) / unit < 0.03
