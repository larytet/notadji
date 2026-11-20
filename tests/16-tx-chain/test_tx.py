import math
import random

import cocotb
import numpy as np
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from stream_tb import reset, run_stream, start_clock
from tx_model import *

# (fft_log2, cp_sel, mod, code, nbytes)
CASES = [(6, 0, 1, 0, 40), (6, 1, 2, 1, 100), (7, 2, 3, 3, 200), (8, 1, 4, 4, 150), (8, 0, 0, 2, 60),
         (6, 2, 0, 7, 30), (7, 1, 2, 5, 300), (9, 1, 1, 3, 80), (8, 2, 3, 6, 120)]


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
    dut.cp_sel.value = 0
    dut.mod.value = 0
    dut.code.value = 0
    dut.shift_mask.value = 0
    start_clock(dut.clk)
    await reset(dut)


def set_cfg(dut, l, cp, mod, ci):
    dut.fft_log2.value = l
    dut.cp_sel.value = cp
    dut.mod.value = mod
    dut.code.value = ci
    dut.shift_mask.value = mask_for(l)


async def send_frame(dut, data, l, cp, mod, ci, pv=1.0, pr=1.0, seed=0, extra=None):
    set_cfg(dut, l, cp, mod, ci)
    exp, nblk = tx_frame(data, l, cp, mod, ci, mask_for(l))
    words = [(b, i == len(data) - 1) for i, b in enumerate(data)]
    res = await run_stream(dut, words, pv, pr, 8, random.Random(seed), expect_out=len(exp), extra=extra, max_cycles=3000000)
    got = [unpack(w) for w, _ in res.out]
    return got, exp, nblk, res


@cocotb.test()
async def t16_02_bit_exact(dut):
    """T16-02 whole chain equals the golden model for many configurations"""
    await setup(dut)
    rng = random.Random(162)
    for l, cp, mod, ci, n in CASES:
        data = [rng.getrandbits(8) for _ in range(n)]
        got, exp, nblk, res = await send_frame(dut, data, l, cp, mod, ci, seed=l)
        assert len(got) == len(exp), f"L={l} cp={cp} mod={mod} code={ci}: {len(got)} samples, expected {len(exp)}"
        bad = next((i for i, (a, b) in enumerate(zip(got, exp)) if a != b), None)
        assert bad is None, f"L={l} cp={cp} mod={mod} code={ci} bytes={n}: first difference at sample {bad}: {got[bad]} vs {exp[bad]}"
        lasts = [l_ for _, l_ in res.out]
        assert lasts == [0] * (len(exp) - 1) + [1], "last only on the final sample"
        assert not res.violations
        dut._log.info(f"FRAME L={l} cp={cp} mod={mod} code={ci} bytes={n}: {nblk} data symbols, {len(exp)} samples")
        await ClockCycles(dut.clk, 20)


@cocotb.test()
async def t16_03_closed_loop(dut):
    """T16-03 an ideal floating-point receiver recovers the bytes from the output samples"""
    await setup(dut)
    rng = random.Random(163)
    for l, cp, mod, ci, n in CASES[:7]:
        data = [rng.getrandbits(8) for _ in range(n)]
        got, exp, nblk, res = await send_frame(dut, data, l, cp, mod, ci, seed=3)
        N = 1 << l
        cplen = N >> SH[cp]
        sym_len = N + cplen
        assert len(got) == (3 + nblk) * sym_len
        shifts = bin(mask_for(l)).count("1")
        pre = Preamble()
        tpl = pre.symbol(2, l, frame_start=True)
        data_bins = [b for b, (t, _, _) in enumerate(tpl) if t == 1]
        nb = NB[mod]
        pts = [(w, point(mod, w)) for w in range(1 << nb)]
        rx_blocks = []
        for s in range(3, 3 + nblk):
            seg = got[s * sym_len + cplen:(s + 1) * sym_len]
            y = np.array([complex(i, q) for i, q in seg])
            X = np.fft.fft(y) * (2 ** shifts) / N
            words = []
            for b in data_bins:
                pi, pq = X[b].real, X[b].imag
                w = min(pts, key=lambda wp: (pi - wp[1][0]) ** 2 + (pq - wp[1][1]) ** 2)[0]
                words.append(w)
            bits = [(w >> k) & 1 for w in words for k in range(nb)]
            rx_blocks.append(deinterleave(bits))
        coded = [b for blk in rx_blocks for b in blk]
        c = CODES[ci]
        rows = h_rows(c)
        k, nn = c["K"], c["N"]
        ncw = -(-n * 8 // k)
        msg_bits = []
        for j in range(ncw):
            cw = coded[j * nn:(j + 1) * nn]
            val = sum(b << i for i, b in enumerate(cw))
            assert check(rows, val), f"L={l} mod={mod} code={ci}: codeword {j} fails the parity check"
            msg_bits += cw[:k]
        rx = [sum(msg_bits[8 * i + b] << b for b in range(8)) for i in range(n)]
        assert rx == data, f"L={l} mod={mod} code={ci}: recovered bytes differ"
        # the padding bits are zero
        assert all(b == 0 for b in msg_bits[n * 8:]), "padding of the last message must be zero"
        await ClockCycles(dut.clk, 20)


@cocotb.test()
async def t16_04_structure(dut):
    """T16-04 sample counts, last flag, and the preamble symbols first"""
    await setup(dut)
    rng = random.Random(164)
    for l, cp, mod, ci, n in [(6, 1, 1, 0, 60), (7, 0, 2, 3, 120)]:
        data = [rng.getrandbits(8) for _ in range(n)]
        got, exp, nblk, res = await send_frame(dut, data, l, cp, mod, ci)
        N = 1 << l
        sym_len = N + (N >> SH[cp])
        assert len(got) == (3 + nblk) * sym_len
        pre = Preamble()
        stf = ofdm_symbol([(i, q) if t else (0, 0) for t, i, q in pre.symbol(0, l)], l, mask_for(l), cp)
        assert got[:sym_len] == stf, "the first symbol must be the STF"
        assert got[sym_len:2 * sym_len] == got[2 * sym_len:3 * sym_len], "the two LTF symbols are identical"
        lasts = [l_ for _, l_ in res.out]
        assert sum(lasts) == 1 and lasts[-1] == 1
        await ClockCycles(dut.clk, 20)


@cocotb.test()
async def t16_05_back_to_back(dut):
    """T16-05 several frames in a row with different configurations and random handshakes"""
    await setup(dut)
    rng = random.Random(165)
    for k, (l, cp, mod, ci, n) in enumerate([(6, 0, 1, 0, 30), (7, 1, 2, 3, 90), (6, 2, 3, 1, 50), (8, 0, 0, 4, 40)]):
        data = [rng.getrandbits(8) for _ in range(n)]
        pv, pr = [(0.6, 0.5), (0.9, 0.3), (0.5, 0.9), (1.0, 0.4)][k]
        got, exp, nblk, res = await send_frame(dut, data, l, cp, mod, ci, pv, pr, seed=k)
        assert got == exp, f"frame {k}: L={l} mod={mod} code={ci}"
        assert not res.violations
        # no extra samples after the frame
        await ClockCycles(dut.clk, 300)
        assert int(dut.m_axis_valid.value) == 0, "unexpected samples after the frame"


@cocotb.test()
async def t16_07_throughput(dut):
    """T16-07 latency to the first sample and samples per clock"""
    await setup(dut)
    rng = random.Random(167)
    l, cp, mod, ci, n = 8, 1, 3, 3, 400
    data = [rng.getrandbits(8) for _ in range(n)]
    got, exp, nblk, res = await send_frame(dut, data, l, cp, mod, ci)
    assert got == exp
    first_in, first_out, last_out = res.in_cycles[0], res.out_cycles[0], res.out_cycles[-1]
    spc = len(exp) / (last_out - first_out + 1)
    dut._log.info(f"TXPERF frame of {n} bytes: {nblk} data symbols, first sample {first_out - first_in} clocks after the first byte, {len(exp)} samples in {last_out - first_in + 1} clocks, {spc:.3f} samples per clock over the output interval")
