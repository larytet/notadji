import math
import os
import random

import cocotb
import numpy as np

from dfts_cal import csi_eff, make_gain_lut
from dfts_model import MS, N_TO_MSEL, R, dfts_rx, dfts_tx, used_bins
from dm_model import llrs, point
from stream_tb import reset, run_stream, start_clock
from test_dft import pack, unpack
from test_txrx import write_lut
from tx_model import SH, mask_for, ofdm_symbol

NBITS = {0: 1, 1: 2, 2: 4}


async def setup_tx(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "fft_log2", "cp_sel", "mod", "shift_mask", "ref_boost"):
        getattr(dut, n).value = 0
    dut.m_axis_ready.value = 1
    start_clock(dut.clk)
    await reset(dut)


@cocotb.test()
async def t31_09a_tx_chain(dut):
    """T31-09 mapper -> dfts_tx -> IFFT -> cyclic prefix equals the chain of the models (several N, modulations, prefixes)"""
    if os.environ.get("DUT") != "tx":
        return
    await setup_tx(dut)
    rng = random.Random(3109)
    for (n, mod, cp), bst in zip(((64, 1, 1), (128, 2, 2), (256, 0, 1), (512, 1, 1), (256, 2, 0)), (0, 1, 0, 1, 0)):
        l = n.bit_length() - 1
        m = MS[N_TO_MSEL[n]]
        words = []
        pts = []
        for _ in range(2):                                   # two symbols back to back
            ws = [rng.getrandbits(NBITS[mod]) for _ in range(m - R)]
            words += [(w, i == m - R - 1) for i, w in enumerate(ws)]
            pts.append([point(mod, w) for w in ws])
        exp = []
        for p in pts:
            bins, _ = dfts_tx(p, n, bst)
            s = ofdm_symbol(bins, l, mask_for(l), cp)
            exp += [(pack(a, b), False) for a, b in s]
        dut.fft_log2.value = l
        dut.cp_sel.value = cp
        dut.mod.value = mod
        dut.ref_boost.value = bst
        dut.shift_mask.value = mask_for(l)
        r = await run_stream(dut, words, 0.8, 0.8, 8, rng, expect_out=len(exp), max_cycles=400000)
        assert not r.violations
        got = [w for w, _ in r.out]
        assert got == [w for w, _ in exp], f"samples differ (N={n}, mod={mod})"
        dut._log.info(f"ds_tx_top N={n} {mod} cp {cp}: {len(got)} samples equal the chain of models")


async def setup_rx(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "s_csi", "fft_log2", "mod", "llr_shift", "ref_boost", "lut_we", "lut_addr", "lut_data", "csi_out"):
        getattr(dut, n).value = 0
    dut.m_axis_ready.value = 1
    start_clock(dut.clk)
    await reset(dut)
    from cocotb.triggers import FallingEdge
    for _ in range(300):
        await FallingEdge(dut.clk)


@cocotb.test()
async def t31_09b_rx_chain(dut):
    """T31-09 dfts_rx -> demapper equals the chain of models; transmit, numpy channel (multipath, noise, rotation), receive: bits"""
    if os.environ.get("DUT") != "rx":
        return
    await setup_rx(dut)
    rng = random.Random(31091)
    nprng = np.random.default_rng(7)
    total_err = 0
    for (n, mod), bst in zip(((64, 1), (256, 1), (128, 2), (512, 0)), (1, 0, 1, 0)):
        l = n.bit_length() - 1
        m = MS[N_TO_MSEL[n]]
        nb = NBITS[mod]
        ub = used_bins(n)
        # frequency-selective channel: 2 taps, normalised
        kk = np.array([b if b < n // 2 else b - n for b in range(n)])
        H = 1 + 0.4 * np.exp(1j * 1.0) * np.exp(-2j * np.pi * kk * 3 / n)
        H = H / math.sqrt(np.mean(np.abs(H[ub]) ** 2))
        snr = 10 ** (25 / 10)
        sigma = 4096 / math.sqrt(snr)
        nv = 128 / snr
        words_in, csis, exp_llr, all_bits = [], [], [], []
        lut = make_gain_lut(nv)
        for s in range(3):
            ws = [rng.getrandbits(nb) for _ in range(m - R)]
            pts = [point(mod, w) for w in ws]
            bins, _ = dfts_tx(pts, n, bst)
            Y = np.zeros(n, complex)
            rot = np.exp(1j * rng.uniform(-0.5, 0.5))
            for b in ub:
                Y[b] = H[b] * complex(*bins[b]) * rot + complex(nprng.normal(0, sigma / math.sqrt(2)), nprng.normal(0, sigma / math.sqrt(2)))
            Z = [(0, 0)] * n
            csi = [0] * n
            for b in ub:
                z = Y[b] / H[b]
                Z[b] = (int(round(z.real)), int(round(z.imag)))
                csi[b] = min(255, int(128 * abs(H[b]) ** 2))
            cout = csi_eff([csi[b] for b in ub], nv)
            out, _, _ = dfts_rx(Z, csi, n, lut, cout, bst)
            sym_llrs = [llrs(mod, i, q, cout, 12) for (i, q) in out]
            words_in += [(pack(*Z[b]), b == n - 1) for b in range(n)]
            csis += csi
            exp_llr += sym_llrs
            all_bits += [(w >> j) & 1 for w in ws for j in range(nb)]
            last_cout = cout
        # the same LUT and csi_out apply to the whole run in the DUT (quasi-static channel)
        await write_lut(dut, lut)
        dut.csi_out.value = last_cout
        # csi_out differs by symbol in the model only if csi changed; the channel is the same, so it is the same
        dut.mod.value = mod
        dut.ref_boost.value = bst
        dut.llr_shift.value = 12

        def pre(d, cyc, idx):
            d.fft_log2.value = l if (idx % n == 0) else rng.randrange(16)
            d.s_csi.value = csis[idx] if idx < len(csis) else 0

        nout = 3 * (m - R)
        r = await run_stream(dut, words_in, 0.9, 0.8, 32, rng, expect_out=nout, pre=pre, max_cycles=4000000)
        assert not r.violations
        for k, (w, _) in enumerate(r.out):
            got = [signed8((w >> (8 * j)) & 0xFF) for j in range(nb)]
            assert got == exp_llr[k][:nb] or got == exp_llr[k], (n, k, got, exp_llr[k])
        err = sum(1 for k, (w, _) in enumerate(r.out) for j in range(nb)
                  if (signed8((w >> (8 * j)) & 0xFF) < 0) != bool(all_bits[k * nb + j]))
        total_err += err
        dut._log.info(f"ds_rx_top N={n} mod {mod}: {nout} symbols equal the model; hard-decision bit errors over the channel (25 dB, 2 taps, rotation): {err} of {nout * nb}")
    assert total_err == 0, total_err


def signed8(v):
    return v - 256 if v >= 128 else v
