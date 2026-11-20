import math
import os
import random
import sys
from pathlib import Path

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "16-tx-chain"))
from stream_tb import reset, run_stream  # noqa: E402
from tx_model import CODES, mask_for, SH, ND, NB  # noqa: E402

G = os.environ.get("G", "")
SPS = 4          # clocks per input sample
BACKOFF = None   # a quarter of the prefix


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def s24(x):
    return x - (1 << 24) if x & (1 << 23) else x


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for n in ("tx_s_valid", "tx_s_data", "tx_s_last", "tx_fft_log2", "tx_cp_sel", "tx_mod", "tx_code", "tx_shift_mask",
              "rx_fft_log2", "rx_cp_sel", "rx_mod", "rx_code", "rx_nsym", "rx_ncw", "rx_nbytes", "rx_backoff", "rx_thr_sel",
              "rx_min_power", "rx_s_valid", "rx_s_data"):
        getattr(dut, n).value = 0
    dut.tx_m_ready.value = 1
    dut.rx_m_ready.value = 1
    dut.rx_min_power.value = 1000
    await reset(dut)




async def tx_frame_samples(dut, data, l, cp, mod, ci):
    from tx_model import tx_frame
    exp, nblk = tx_frame(data, l, cp, mod, ci, mask_for(l))
    dut.tx_fft_log2.value = l
    dut.tx_cp_sel.value = cp
    dut.tx_mod.value = mod
    dut.tx_code.value = ci
    dut.tx_shift_mask.value = mask_for(l)
    words = [(b, i == len(data) - 1) for i, b in enumerate(data)]
    res = await run_stream(dut, words, 1.0, 1.0, 8, random.Random(1), expect_out=len(exp), max_cycles=4000000, sp="tx_s", mp="tx_m")
    got = [(s16(w & 0xFFFF), s16((w >> 16) & 0xFFFF)) for w, _ in res.out]
    assert got == exp, "transmit chain output differs from its model"
    return np.array([complex(i, q) for i, q in got]), nblk


def channel(x, l, rng, snr_db, cfo_sc, taps=None, lead=None, tail=300):
    n = 1 << l
    if taps:
        h = np.zeros(max(d for d, _ in taps) + 1, complex)
        for d, g in taps:
            h[d] += g
        x = np.convolve(x, h)[:len(x)]
    lead = lead if lead is not None else rng.randint(60, 300)
    p_sig = float(np.mean(np.abs(x[:n]) ** 2))
    y = np.concatenate([np.zeros(lead, complex), x, np.zeros(tail, complex)])
    k = np.arange(len(y))
    y = y * np.exp(2j * np.pi * cfo_sc * k / n)
    sig2 = p_sig / (10 ** (snr_db / 10))
    y = y + (np.array([rng.gauss(0, 1) for _ in y]) + 1j * np.array([rng.gauss(0, 1) for _ in y])) * math.sqrt(sig2 / 2)
    return [(int(np.clip(round(v.real), -32768, 32767)), int(np.clip(round(v.imag), -32768, 32767))) for v in y], lead


async def rx_run(dut, samples, nbytes, wait_clocks=100000, SPS=4):
    """feed samples one per SPS clocks, collect bytes; returns dict"""
    out, lasts = [], []
    clk_n = 0
    first_clk = last_clk = None
    end_feed = None
    ok = None
    snap = dict(fifo=0, iters=0)
    err_any = 0
    dec = []
    inc_seen = 0
    il = []
    ev = []
    nin = 0
    dfirst = True
    n = len(samples)
    done = False
    while not done:
        for ph in range(SPS):
            await FallingEdge(dut.clk)
            idx = clk_n // SPS
            if ph == 0 and idx < n:
                i, q = samples[idx]
                dut.rx_s_valid.value = 1
                dut.rx_s_data.value = ((q & 0xFFFF) << 16) | (i & 0xFFFF)
            else:
                dut.rx_s_valid.value = 0
            if idx == n and end_feed is None:
                end_feed = clk_n
            await Timer(1, unit="ns")
            err_any |= int(dut.rx_err.value)
            if int(dut.rx_det.value) or int(dut.rx_cfo_inc.value):
                inc_seen = s24(int(dut.rx_cfo_inc.value))
            u = dut.u_rx
            if int(u.il_v.value) and int(u.il_r.value):
                v = int(u.il_d.value)
                il.append(v - 256 if v > 127 else v)
            if int(u.sy_v.value):
                nin += 1
            if int(u.det.value):
                ev.append(('det', nin))
            if int(u.sy_fall.value):
                ev.append(('fall', nin))
            if int(u.fr_v.value) and not any(e[0] == 'fr' for e in ev):
                ev.append(('fr', nin))
            if int(u.dc_v.value) and int(u.dc_r.value):
                if dfirst:
                    dec.append((int(u.dc_ok.value), int(u.dc_it.value)))
                dfirst = bool(int(u.dc_l.value))
            snap["fifo"] = max(snap["fifo"], int(dut.rx_fifo_max.value))
            snap["iters"] = max(snap["iters"], int(dut.rx_iters_max.value))
            if int(dut.rx_m_valid.value) and int(dut.rx_m_ready.value):
                out.append(int(dut.rx_m_data.value))
                lasts.append(int(dut.rx_m_last.value))
                if first_clk is None:
                    first_clk = clk_n
                last_clk = clk_n
                if int(dut.rx_m_last.value):
                    ok = int(dut.rx_frame_ok.value)
            clk_n += 1
            if len(out) >= nbytes and int(dut.rx_m_last.value) and int(dut.rx_m_valid.value):
                done = True
            if clk_n > n * SPS + wait_clocks:
                done = True
        if done:
            break
    dut.rx_s_valid.value = 0
    await ClockCycles(dut.clk, 400)
    return dict(out=out, lasts=lasts, first=first_clk, last=last_clk, end_feed=end_feed, ok=ok,
                inc=inc_seen, fifo=snap["fifo"], iters=snap["iters"],
                err=err_any, nsamp=n, dec=dec, il=il, ev=ev)


def rx_config(dut, l, cp, mod, ci, nblk, nbytes):
    k = CODES[ci]["K"]
    dut.rx_fft_log2.value = l
    dut.rx_cp_sel.value = cp
    dut.rx_mod.value = mod
    dut.rx_code.value = ci
    dut.rx_nsym.value = nblk
    dut.rx_ncw.value = -(-nbytes * 8 // k)
    dut.rx_nbytes.value = nbytes
    dut.rx_backoff.value = min(15, ((1 << l) >> SH[cp]) // 4)
    dut.rx_thr_sel.value = 0


def auto_sps(l, cp, mod):
    n = 1 << l
    return max(4, math.ceil(1.15 * (ND[l] * NB[mod] + 2 * n) / (n + (n >> SH[cp]))))


async def link(dut, rng, l, cp, mod, ci, nbytes, snr, cfo=0.0, taps=None, sps=None):
    data = [rng.getrandbits(8) for _ in range(nbytes)]
    x, nblk = await tx_frame_samples(dut, data, l, cp, mod, ci)
    await ClockCycles(dut.clk, 20)
    rx_config(dut, l, cp, mod, ci, nblk, nbytes)
    samples, lead = channel(x, l, rng, snr, cfo, taps)
    sps = sps or auto_sps(l, cp, mod)
    r = await rx_run(dut, samples, nbytes, SPS=sps)
    r["sps"] = sps
    r["ok"] = int(dut.rx_frame_ok.value)
    r["data"] = data
    r["good"] = r["out"] == data and r["lasts"] == [0] * (nbytes - 1) + [1]
    r["frame_ok"] = r["ok"]
    r["cfo_err"] = abs(r["inc"] - cfo / (1 << l) * (1 << 24)) / ((1 << 24) / (1 << l))
    r["nblk"] = nblk
    r["lead"] = lead
    from tx_model import coded_blocks
    coded = [b for blk in coded_blocks(data, l, mod, ci) for b in blk]
    r["signerr"] = sum(1 for a, b in zip(r["il"], coded) if (a < 0) != bool(b))
    r["nil"] = len(r["il"])
    r["sym_len"] = (1 << l) + ((1 << l) >> SH[cp])
    r["frame_end_clk"] = (lead + len(x)) * sps
    return r


def why(r):
    d = r["data"]
    bad = [i for i, (a, b) in enumerate(zip(r["out"], d)) if a != b]
    return f"received {len(r['out'])} bytes, {len(bad)} differ, first {bad[:5]}, err={r['err']} fifo={r['fifo']} frame_ok={r['ok']} dec={r['dec']}"


def desc(l, cp, mod, ci, n):
    return f"L={l} cp={cp} mod={mod} code={ci} bytes={n}"


@cocotb.test()
async def t21_02_noiseless(dut):
    """T21-02 noiseless loop"""
    if G != "loop":
        return
    await setup(dut)
    rng = random.Random(2102)
    for l, cp, mod, ci, n in ((7, 1, 1, 0, 40), (7, 1, 2, 1, 100), (8, 1, 1, 0, 60), (8, 1, 2, 3, 150), (8, 2, 3, 3, 200), (8, 1, 4, 4, 150)):
        r = await link(dut, rng, l, cp, mod, ci, n, 60)
        dut._log.info(f"NOISELESS {desc(l, cp, mod, ci, n)}: good={r['good']} frame_ok={r['frame_ok']} iters={r['iters']} err={r['err']} bytes={len(r['out'])}")
        assert r["good"], f"{desc(l, cp, mod, ci, n)}: bytes differ ({len(r['out'])} received)"
        assert r["frame_ok"] == 1 and r["err"] == 0, why(r)


@cocotb.test()
async def t21_03_cfo(dut):
    """T21-03 carrier offsets"""
    if G != "loop":
        return
    await setup(dut)
    rng = random.Random(2103)
    for off in (-1.5, -0.5, 0.5, 1.5):
        r = await link(dut, rng, 8, 1, 2, 1, 100, 30, cfo=off)
        dut._log.info(f"CFO offset {off}: good={r['good']} estimate error {r['cfo_err']:.4f} sub-carrier spacings")
        assert r["good"], f"offset {off}: bytes differ"
        assert r["cfo_err"] < 0.05


@cocotb.test()
async def t21_04_noise(dut):
    """T21-04 noise: frame error rate against SNR"""
    if G != "noise":
        return
    await setup(dut)
    rng = random.Random(2104)
    summary = []
    for mod, ci, snrs in ((1, 1, (25, 18, 14, 11)), (2, 1, (25, 21, 18))):
        for snr in snrs:
            good = 0
            runs = 10
            for _ in range(runs):
                r = await link(dut, rng, 8, 1, mod, ci, 100, snr)
                good += int(r["good"])
            summary.append((mod, ci, snr, good, runs))
            dut._log.info(f"NOISE mod={mod} code={ci} SNR={snr} dB: {good} of {runs} frames recovered")
    for mod, ci, snr, good, runs in summary:
        if snr == 25:
            assert good >= 9, f"mod={mod} at 25 dB: {good} of {runs}"


@cocotb.test()
async def t21_05_multipath(dut):
    """T21-05 two-tap channel"""
    if G != "loop":
        return
    await setup(dut)
    rng = random.Random(2105)
    for l, cp, mod, ci, n in ((8, 1, 1, 1, 100), (8, 1, 2, 1, 100)):
        r = await link(dut, rng, l, cp, mod, ci, n, 30, taps=[(0, 1.0), (5, 0.4)])
        dut._log.info(f"MULTIPATH {desc(l, cp, mod, ci, n)}: good={r['good']}")
        assert r["good"]


@cocotb.test()
async def t21_06_in_a_row(dut):
    """T21-06 three frames in a row with different configurations, no reset between"""
    if G != "loop":
        return
    await setup(dut)
    rng = random.Random(2106)
    for l, cp, mod, ci, n in ((8, 1, 1, 1, 80), (7, 1, 2, 0, 60), (8, 2, 2, 3, 120)):
        r = await link(dut, rng, l, cp, mod, ci, n, 30, cfo=0.3)
        dut._log.info(f"IN A ROW {desc(l, cp, mod, ci, n)}: good={r['good']}")
        assert r["good"], desc(l, cp, mod, ci, n) + why(r)


@cocotb.test()
async def t21_07_latency(dut):
    """T21-07 latency, FIFO occupancy and decoder time"""
    if G != "loop":
        return
    await setup(dut)
    rng = random.Random(2107)
    for l, cp, mod, ci, n in ((8, 1, 2, 1, 300), (8, 1, 1, 3, 300)):
        r = await link(dut, rng, l, cp, mod, ci, n, 30)
        assert r["good"], desc(l, cp, mod, ci, n) + why(r)
        lat_first = r["first"] - r["frame_end_clk"]
        lat_last = r["last"] - r["frame_end_clk"]
        dut._log.info(f"LATENCY {desc(l, cp, mod, ci, n)}: {r['nblk']} data symbols of {r['sym_len']} samples ({r['sym_len'] * r['sps']} clocks at {r['sps']} per sample); "
                      f"first byte {lat_first} clocks, last byte {lat_last} clocks after the last sample; FIFO high-water {r['fifo']}; max iterations {r['iters']}")


@cocotb.test()
async def t21_07b_rate(dut):
    """T21-07 smallest sustainable number of clocks per input sample"""
    if G != "rate":
        return
    await setup(dut)
    rng = random.Random(2108)
    for l, cp, mod, ci, n in ((8, 1, 1, 1, 200), (8, 1, 2, 1, 200), (8, 1, 3, 1, 200)):
        found = None
        for sps in (4,):
            r = await link(dut, rng, l, cp, mod, ci, n, 30, sps=sps)
            dut._log.info(f"RATE {desc(l, cp, mod, ci, n)} at {sps} clocks per sample: good={r['good']} {why(r)}")
            if r["good"] and not r["err"]:
                found = sps
                break
        assert found is not None
        dut._log.info(f"RATE SUMMARY {desc(l, cp, mod, ci, n)}: smallest sustainable {found} clocks per sample (symbol {(1 << l) + ((1 << l) >> SH[cp])} samples, {ND[l] * NB[mod]} coded bits per symbol)")


@cocotb.test()
async def t21_08_reconfig_sequence(dut):
    """T21-08 five frames with changing configurations, no reset (regression for the trim restart and the early-detection fixes)"""
    if G != "seq":
        return
    await setup(dut)
    rng = random.Random(2102)
    for l, cp, mod, ci, n in ((7, 1, 1, 0, 40), (7, 1, 2, 1, 100), (8, 1, 1, 0, 60), (8, 1, 2, 3, 150), (8, 2, 3, 3, 200)):
        r = await link(dut, rng, l, cp, mod, ci, n, 60)
        dut._log.info(f"CP2 lead={r['lead']} ev={r['ev']} nil={r['nil']} signerr={r['signerr']} inc={r['inc']} good={r['good']} {why(r)}")
        assert r["good"] and r["frame_ok"] == 1, why(r)
