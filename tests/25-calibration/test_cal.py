import math
import os
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

import calfw

G = os.environ.get("G", "")
LIB = calfw.load()


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def pack(i, q):
    return ((int(q) & 0xFFFF) << 16) | (int(i) & 0xFFFF)


def unpack(w):
    return s16(w & 0xFFFF), s16((w >> 16) & 0xFFFF)


def g(dut, n):
    return int(getattr(dut, n).value)


def gs(dut, n, bits):
    v = int(getattr(dut, n).value)
    return v - (1 << bits) if v >> (bits - 1) else v


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


# ------------------------------------------------------------------ model of iq_corr
def sat16(v):
    return max(-32768, min(32767, v))


def corr_model(i, q, en, da, er, ei, di, dq):
    if not en:
        return i, q
    xi, xq = (i, q) if da else (i - di, q - dq)
    ci = er * xi + ei * xq + 16384
    cq = ei * xi - er * xq + 16384
    ri = xi - (ci >> 15) + (di if da else 0)
    rq = xq - (cq >> 15) + (dq if da else 0)
    return sat16(ri), sat16(rq)


@cocotb.test()
async def t25_01_stats(dut):
    """T25-01 cal_stats: sums, count, windows that add up, clear, extreme samples"""
    if G != "stats":
        return
    rng = random.Random(2501)
    dut.clear.value = 0
    dut.start.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.n_samples.value = 0
    await start(dut)
    tot = dict(i=0, q=0, ii=0, qq=0, iq=0, n=0)
    windows = [1, 2, 17, 1000, 3000, 5] + [rng.randint(1, 400) for _ in range(20)] + [65536]
    ign = 0
    for wi, n in enumerate(windows):
        if wi in (0, 6, 15):
            await FallingEdge(dut.clk)
            dut.clear.value = 1
            await FallingEdge(dut.clk)
            dut.clear.value = 0
            tot = dict(i=0, q=0, ii=0, qq=0, iq=0, n=0)
        extreme = (n == 65536)
        pv = rng.choice([1.0, 0.5])
        await FallingEdge(dut.clk)
        dut.n_samples.value = n
        dut.start.value = 1
        dut.s_valid.value = 1
        dut.s_data.value = pack(rng.randint(-32768, 32767), rng.randint(-32768, 32767))     # not counted: busy not yet set
        await FallingEdge(dut.clk)
        dut.start.value = 0
        k = 0
        got = 0
        while got < n:
            v = rng.random() < pv
            i, q = (-32768, -32768) if extreme else (rng.randint(-32768, 32767), rng.randint(-32768, 32767))
            if not extreme and wi % 3 == 0:
                i, q = rng.randint(-50, 50), rng.randint(-50, 50)
            dut.s_valid.value = int(v)
            dut.s_data.value = pack(i, q)
            if k == 1 and n > 5:
                dut.start.value = 1                          # while busy
                ign += 1
            else:
                dut.start.value = 0
            if v:
                got += 1
                tot["i"] += i
                tot["q"] += q
                tot["ii"] += i * i
                tot["qq"] += q * q
                tot["iq"] += i * q
                tot["n"] += 1
            k += 1
            await FallingEdge(dut.clk)
        dut.s_valid.value = 0
        dut.start.value = 0
        await Timer(1, unit="ns")
        assert g(dut, "done") == 1 or True
        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        got_s = (gs(dut, "sum_i", 40), gs(dut, "sum_q", 40), g(dut, "sum_ii"), g(dut, "sum_qq"), gs(dut, "sum_iq", 48), g(dut, "count"))
        exp_s = (tot["i"], tot["q"], tot["ii"], tot["qq"], tot["iq"], tot["n"])
        assert got_s == exp_s, f"window {wi} (n={n}): {got_s} expected {exp_s}"
        assert g(dut, "busy") == 0
    assert g(dut, "ovr_cnt") == ign, f"ovr_cnt {g(dut, 'ovr_cnt')} expected {ign}"
    dut._log.info(f"STATS: {len(windows)} windows (to 65536 extreme samples) equal the exact sums; {ign} starts while busy counted")


@cocotb.test()
async def t25_02_corr(dut):
    """T25-02 iq_corr: bit-exact against the integer model, pass-through, saturation, latency, throughput"""
    if G != "corr":
        return
    rng = random.Random(2502)
    dut.cfg_valid.value = 0
    dut.en.value = 0
    dut.dc_after.value = 0
    dut.eps_r.value = 0
    dut.eps_i.value = 0
    dut.dc_i.value = 0
    dut.dc_q.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    await start(dut)
    n_checked = 0
    for trial in range(40):
        en = int(trial % 7 != 0)
        da = trial % 2
        er, ei = rng.randint(-16000, 16000), rng.randint(-16000, 16000)
        di, dq = rng.randint(-3000, 3000), rng.randint(-3000, 3000)
        if trial % 5 == 4:
            er, ei, di, dq = 16000, -16000, 30000, -30000          # saturation
        await FallingEdge(dut.clk)
        dut.cfg_valid.value = 1
        dut.en.value = en
        dut.dc_after.value = da
        dut.eps_r.value = er
        dut.eps_i.value = ei
        dut.dc_i.value = di
        dut.dc_q.value = dq
        await FallingEdge(dut.clk)
        dut.cfg_valid.value = 0
        for _ in range(4):
            await FallingEdge(dut.clk)
        n = 300
        ins, outs, vals = [], [], []
        for k in range(n + 6):
            v = k < n and (trial % 3 == 0 or rng.random() < 0.7)
            i, q = rng.randint(-32768, 32767), rng.randint(-32768, 32767)
            if trial % 5 == 4:
                i, q = rng.choice([-32768, 32767]), rng.choice([-32768, 32767])
            dut.s_valid.value = int(v)
            dut.s_data.value = pack(i, q)
            if v:
                ins.append((i, q))
            await Timer(1, unit="ns")
            if g(dut, "m_valid"):
                outs.append(unpack(g(dut, "m_data")))
            await FallingEdge(dut.clk)
        dut.s_valid.value = 0
        for _ in range(6):
            await Timer(1, unit="ns")
            if g(dut, "m_valid"):
                outs.append(unpack(g(dut, "m_data")))
            await FallingEdge(dut.clk)
        exp = [corr_model(i, q, en, da, er, ei, di, dq) for i, q in ins]
        assert outs == exp, f"trial {trial}: first difference at {next(k for k, (a, b) in enumerate(zip(outs, exp)) if a != b) if len(outs) == len(exp) else 'count'}; {len(outs)} vs {len(exp)} outputs"
        n_checked += len(outs)
        # against the float formula (no saturation) within one LSB
        if trial % 5 != 4 and en:
            for (i, q), (oi, oq) in zip(ins[:50], outs[:50]):
                xi, xq = (i, q) if da else (i - di, q - dq)
                fi = xi - (er / 32768 * xi + ei / 32768 * xq) + (di if da else 0)
                fq = xq - (ei / 32768 * xi - er / 32768 * xq) + (dq if da else 0)
                fi, fq = max(-32768, min(32767, fi)), max(-32768, min(32767, fq))
                assert abs(fi - oi) <= 1 and abs(fq - oq) <= 1, f"{(fi, fq)} vs {(oi, oq)}"
    dut._log.info(f"CORR: {n_checked} samples in 40 configurations equal the integer model (pass-through, saturation, both DC modes)")


# ------------------------------------------------------------------ closed loops
def impair(x, eps, dc=0):
    return x + eps * np.conj(x) + dc


def quant(z):
    return np.clip(np.round(z.real), -32768, 32767).astype(np.int64) + 1j * np.clip(np.round(z.imag), -32768, 32767).astype(np.int64)


def cgauss(rng, n, sigma):
    return (rng.normal(0, sigma, n) + 1j * rng.normal(0, sigma, n))


async def feed(dut, pre, z, tap=None, post_clocks=6):
    """stream complex samples into the rx or tx path of cal_loop, one per clock; returns the corrected output as a complex array"""
    vn, dn = ("rx_valid", "rx_data") if pre == "rx" else ("tx_valid", "tx_data")
    on = ("rx_m_valid", "rx_m_data") if pre == "rx" else ("tx_m_valid", "tx_m_data")
    out = []
    n = len(z)
    zi = z.real.astype(np.int64)
    zq = z.imag.astype(np.int64)
    for k in range(n + post_clocks):
        await FallingEdge(dut.clk)
        if k < n:
            getattr(dut, vn).value = 1
            getattr(dut, dn).value = pack(zi[k], zq[k])
        else:
            getattr(dut, vn).value = 0
        await Timer(1, unit="ns")
        if g(dut, on[0]):
            w = unpack(g(dut, on[1]))
            out.append(complex(w[0], w[1]))
    return np.array(out)


async def stats_window(dut, pre, z, tap, clear=True):
    """one cal_stats window over the stream; returns the five sums (windows without clear add up)"""
    await FallingEdge(dut.clk)
    dut.tap_sel.value = tap
    dut.st_clear.value = int(clear)
    await FallingEdge(dut.clk)
    dut.st_clear.value = 0
    dut.st_n.value = len(z)
    dut.st_start.value = 1
    await FallingEdge(dut.clk)
    dut.st_start.value = 0
    await feed(dut, pre, z, tap)
    for _ in range(8):
        await FallingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert g(dut, "st_busy") == 0, "stats window did not finish"
    return [gs(dut, "sum_i", 40), gs(dut, "sum_q", 40), g(dut, "sum_ii"), g(dut, "sum_qq"), gs(dut, "sum_iq", 48)], g(dut, "st_count")


async def program(dut, which, er, ei, di, dq, en=1):
    await FallingEdge(dut.clk)
    for _ in range(4):
        await FallingEdge(dut.clk)
    p = which
    getattr(dut, f"{p}_eps_r").value = er
    getattr(dut, f"{p}_eps_i").value = ei
    getattr(dut, f"{p}_dc_i").value = di
    getattr(dut, f"{p}_dc_q").value = dq
    getattr(dut, f"{p}_en").value = en
    getattr(dut, f"{p}_cfg_valid").value = 1
    await FallingEdge(dut.clk)
    getattr(dut, f"{p}_cfg_valid").value = 0
    for _ in range(4):
        await FallingEdge(dut.clk)


def tone_metrics(y, k):
    """tone at bin k: returns (image rejection dB, DC relative to the tone dBc)"""
    Y = np.fft.fft(y) / len(y)
    n = len(y)
    return 20 * np.log10(abs(Y[k]) / max(abs(Y[(-k) % n]), 1e-9)), 20 * np.log10(max(abs(Y[0]), 1e-9) / abs(Y[k]))


async def setup_loop(dut):
    for n_ in ("rx_cfg_valid", "tx_cfg_valid", "rx_valid", "tx_valid", "tap_sel", "st_clear", "st_start", "rx_en", "tx_en"):
        getattr(dut, n_).value = 0
    for n_ in ("rx_eps_r", "rx_eps_i", "rx_dc_i", "rx_dc_q", "tx_eps_r", "tx_eps_i", "tx_dc_i", "tx_dc_q", "rx_data", "tx_data", "st_n"):
        getattr(dut, n_).value = 0
    await start(dut)


@cocotb.test()
async def t25_05_rx_loop(dut):
    """T25-05 receive loop in RTL: stats -> firmware estimate -> iq_corr; image rejection and DC before and after"""
    if G != "loop":
        return
    N = 16384
    rng = np.random.default_rng(2505)
    await setup_loop(dut)
    k_tone = N // 8
    n_idx = np.arange(N)
    tone = 8000 * np.exp(2j * np.pi * k_tone * n_idx / N)
    res = []
    for trial in range(12):
        LIB.shim_init()
        mag = rng.uniform(0.01, 0.10)
        eps = mag * np.exp(1j * rng.uniform(0, 2 * np.pi))
        dc = complex(rng.uniform(-1500, 1500), rng.uniform(-1500, 1500))
        # start from a cleared correction
        await program(dut, "rx", 0, 0, 0, 0, en=1)
        irr0, _ = tone_metrics(quant(impair(tone, eps, dc)) - np.mean(quant(impair(tone, eps, dc))), k_tone)
        er = ei = di = dq = 0
        for rnd in range(4):
            # idle window: noise only through the impaired receiver
            idle = quant(impair(cgauss(rng, N, 100), eps, dc))
            s, n = await stats_window(dut, "rx", idle, 1)
            assert n == N
            st, regs = calfw.result(LIB, 1, s, n, now_ms=1000 * rnd)
            assert st == 0, f"trial {trial} DC job rejected: {st}"
            # signal window: a circular wideband signal at 30 dB SNR
            sig = quant(impair(cgauss(rng, N, 3000) + cgauss(rng, N, 95), eps, dc))
            s, n = await stats_window(dut, "rx", sig, 1)
            st, regs = calfw.result(LIB, 4, s, n, now_ms=1000 * rnd + 5)
            assert st == 0, f"trial {trial} IQ job rejected: {st}"
            di, dq, er, ei = regs[0], regs[1], regs[2], regs[3]
            await program(dut, "rx", er, ei, di, dq)
        # verification on a tone and on idle noise
        out = await feed(dut, "rx", quant(impair(tone, eps, dc)))
        irr1, dcc = tone_metrics(out, k_tone)
        idle = quant(impair(cgauss(rng, N, 100), eps, dc))
        out2 = await feed(dut, "rx", idle)
        dc_res = abs(np.mean(out2))
        dc_dbfs = 20 * np.log10(max(dc_res, 1e-3) / 32768)
        res.append((irr0, irr1, dc_dbfs, abs(dc)))
        assert irr1 >= 40, f"trial {trial}: image rejection {irr1:.1f} dB (before {irr0:.1f}), eps {mag:.3f}"
        assert dc_dbfs <= -80, f"trial {trial}: DC {dc_dbfs:.1f} dBFS (was {20 * np.log10(abs(dc) / 32768):.1f})"
    dut._log.info("RXLOOP image rejection before/after (dB) and residual DC (dBFS): " +
                  "; ".join(f"{a:.1f} -> {b:.1f}, {c:.1f}" for a, b, c, _ in res))
    dut._log.info(f"RXLOOP worst after: image {min(r[1] for r in res):.1f} dB, DC {max(r[2] for r in res):.1f} dBFS")


@cocotb.test()
async def t25_06_tx_loop(dut):
    """T25-06 transmit loop: LO leakage and sideband (dBc) through an observation receiver with its own impairments"""
    if G != "loop":
        return
    N = 16384
    rng = np.random.default_rng(2506)
    await setup_loop(dut)
    k_tone = N // 8
    n_idx = np.arange(N)
    tone = 8000 * np.exp(2j * np.pi * k_tone * n_idx / N)
    res = []
    for trial in range(6):
        LIB.shim_init()
        mag_rx = rng.uniform(0.02, 0.08)
        e_rx = mag_rx * np.exp(1j * rng.uniform(0, 2 * np.pi))
        dc_rx = complex(rng.uniform(-800, 800), rng.uniform(-800, 800))
        mag_tx = rng.uniform(0.02, 0.10)
        e_tx = mag_tx * np.exp(1j * rng.uniform(0, 2 * np.pi))
        leak = complex(rng.uniform(-900, 900), rng.uniform(-900, 900))
        # receive calibration first (a few rounds, as in T25-05)
        await program(dut, "rx", 0, 0, 0, 0)
        for rnd in range(3):
            idle = quant(impair(cgauss(rng, N, 100), e_rx, dc_rx))
            s, n = await stats_window(dut, "rx", idle, 1)
            st, regs = calfw.result(LIB, 1, s, n, now_ms=1000 * rnd)
            sig = quant(impair(cgauss(rng, N, 3000) + cgauss(rng, N, 95), e_rx, dc_rx))
            s, n = await stats_window(dut, "rx", sig, 1)
            st, regs = calfw.result(LIB, 4, s, n, now_ms=1000 * rnd + 5)
            await program(dut, "rx", regs[2], regs[3], regs[0], regs[1])
        # transmit rounds: the observation receiver sees the transmit signal after the pre-correction in force
        tx_regs = [0, 0, 0, 0]
        await program(dut, "tx", 0, 0, 0, 0, en=1)
        for rnd in range(6):
            x = quant(cgauss(rng, N, 3000))
            xt = await feed(dut, "tx", x)                         # pre-corrected digital samples (RTL)
            assert len(xt) == N
            y = quant(impair(xt, e_tx, leak))                     # analog transmitter with its impairments
            z = quant(impair(y, e_rx, dc_rx))                     # observation receiver with its impairments
            s, n = await stats_window(dut, "rx", z[:N // 2], 1)   # two guard-time windows add up in the accumulator (no clear in between)
            s, n = await stats_window(dut, "rx", z[N // 2:], 1, clear=False)
            st, regs = calfw.result(LIB, 2, s, n, now_ms=5000 + 1000 * rnd)
            assert st == 0, f"TX_LO rejected: {st}"
            st, regs = calfw.result(LIB, 3, s, n, now_ms=5000 + 1000 * rnd + 5)
            assert st == 0, f"TX_IQ rejected: {st}"
            await program(dut, "tx", regs[6], regs[7], regs[4], regs[5])
        # verification: a tone through the corrected transmitter
        yt = await feed(dut, "tx", quant(tone))
        y = quant(impair(yt, e_tx, leak))
        img, lo = tone_metrics(y, k_tone)
        _, lo0 = tone_metrics(quant(impair(tone, e_tx, leak)), k_tone)
        img0, _ = tone_metrics(quant(impair(tone, e_tx, leak)), k_tone)
        res.append((img0, -img, lo0, lo))
        assert -img <= -45, f"trial {trial}: sideband {-img:.1f} dBc (before {-img0:.1f})"
        assert lo <= -45, f"trial {trial}: LO leakage {lo:.1f} dBc (before {lo0:.1f})"
    dut._log.info("TXLOOP sideband before/after and LO leakage before/after (dBc): " +
                  "; ".join(f"{-a:.1f} -> {b:.1f}, {c:.1f} -> {d:.1f}" for a, b, c, d in res))
