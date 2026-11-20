import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

G = os.environ.get("G", "")
SH = {0: 4, 1: 3, 2: 2}
BIAS = 2


async def start(dut, rst=True):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


@cocotb.test()
async def t21_01a_framer(dut):
    """T21-01 rx_framer: skip, windows and last pattern"""
    if G != "frm":
        return
    for l in (7, 8, 9):
        for cp in (1, 2):
            for backoff in (0, 2, 4):
                n = 1 << l
                lc = n >> SH[cp]
                kb = n >> 6                         # k_back = P/4 = N/16
                skip = lc - backoff - kb - 1 - BIAS
                if skip < 0:
                    continue
                nwin = 4
                await start(dut)
                dut.fft_log2.value = l
                dut.cp_sel.value = cp
                dut.backoff.value = backoff
                dut.k_back.value = kb
                dut.nwin.value = nwin
                dut.fall.value = 0
                dut.rearm.value = 0
                dut.s_valid.value = 0
                dut.s_data.value = 0
                fall_at = 50
                got, lasts = [], []
                total = fall_at + 1 + skip + nwin * n + (nwin - 1) * lc + 40
                for idx in range(total):
                    await FallingEdge(dut.clk)
                    dut.s_valid.value = 1
                    dut.s_data.value = idx
                    dut.fall.value = 0
                    await Timer(1, unit="ns")
                    if int(dut.m_valid.value):
                        got.append(int(dut.m_data.value))
                        lasts.append(int(dut.m_last.value))
                    await FallingEdge(dut.clk)
                    dut.s_valid.value = 0
                    # the fall pulse arrives between samples, referring to the sample just presented
                    dut.fall.value = 1 if idx == fall_at else 0
                first = fall_at + 1 + skip
                exp = []
                for w in range(nwin):
                    st = first + w * (n + lc)
                    exp += list(range(st, st + n))
                assert got == exp, f"l={l} cp={cp} backoff={backoff}: first window sample {got[:1]} expected {exp[:1]}"
                assert sum(lasts) == nwin and all(lasts[(w + 1) * n - 1] for w in range(nwin))
    await start(dut)
    # negative skip is flagged
    dut.fft_log2.value = 7
    dut.cp_sel.value = 0
    dut.backoff.value = 4
    dut.k_back.value = 8
    dut.nwin.value = 2
    dut.rearm.value = 0
    dut.s_valid.value = 0
    dut.fall.value = 0
    await FallingEdge(dut.clk)
    dut.fall.value = 1
    await FallingEdge(dut.clk)
    dut.fall.value = 0
    await ClockCycles(dut.clk, 3)
    assert int(dut.err_skip.value) == 1


@cocotb.test()
async def t21_01b_trim(dut):
    """T21-01 llr_trim: only the first total LLRs pass, last every N, restart after frame_llr inputs"""
    if G != "trim":
        return
    rng = random.Random(2102)
    await start(dut)
    n = 648
    total = 3 * n
    dut.total.value = total
    dut.n_cw.value = n
    dut.clr.value = 0
    dut.frame_llr.value = total + 400
    dut.m_ready.value = 1
    dut.s_valid.value = 0
    for rep in range(2):
        sent = [rng.randint(-127, 127) for _ in range(total + 400)]
        got, lasts = [], []
        for v in sent:
            await FallingEdge(dut.clk)
            dut.s_valid.value = 1
            dut.s_data.value = v & 0xFF
            dut.m_ready.value = rng.randint(0, 1) if rep else 1
            await Timer(1, unit="ns")
            if int(dut.m_valid.value) and int(dut.m_ready.value):
                got.append(int(dut.m_data.value))
                lasts.append(int(dut.m_last.value))
            while not int(dut.s_ready.value):
                await FallingEdge(dut.clk)
                dut.m_ready.value = rng.randint(0, 1)
                await Timer(1, unit="ns")
                if int(dut.m_valid.value) and int(dut.m_ready.value):
                    got.append(int(dut.m_data.value))
                    lasts.append(int(dut.m_last.value))
        await FallingEdge(dut.clk)
        dut.s_valid.value = 0
        assert [g if g < 128 else g - 256 for g in got] == sent[:total], f"rep {rep}"
        assert lasts == [int(i % n == n - 1) for i in range(total)]


@cocotb.test()
async def t21_01c_bytes(dut):
    """T21-01 msg_to_bytes: bytes from message bits, trimmed to nbytes, frame_done"""
    if G != "m2b":
        return
    rng = random.Random(2103)
    await start(dut)
    for (k, ncw, nbytes) in ((324, 2, 70), (540, 3, 200), (972, 2, 243)):
        dut.nbytes.value = nbytes
        dut.ncw.value = ncw
        dut.m_ready.value = 1
        dut.s_valid.value = 0
        bits = [rng.getrandbits(1) for _ in range(k * ncw)]
        exp = [sum(bits[8 * i + b] << b for b in range(8)) for i in range(nbytes)]
        got, lasts, done = [], [], 0
        for i, b in enumerate(bits):
            await FallingEdge(dut.clk)
            dut.s_valid.value = 1
            dut.s_data.value = b
            dut.s_last.value = int(i % k == k - 1)
            dut.m_ready.value = rng.randint(0, 1)
            await Timer(1, unit="ns")
            while not int(dut.s_ready.value):
                if int(dut.m_valid.value) and int(dut.m_ready.value):
                    got.append(int(dut.m_data.value)); lasts.append(int(dut.m_last.value))
                await FallingEdge(dut.clk)
                dut.m_ready.value = rng.randint(0, 1)
                await Timer(1, unit="ns")
            if int(dut.m_valid.value) and int(dut.m_ready.value):
                got.append(int(dut.m_data.value)); lasts.append(int(dut.m_last.value))
            done += int(dut.frame_done.value)
        for _ in range(6):
            await FallingEdge(dut.clk)
            dut.s_valid.value = 0
            dut.m_ready.value = 1
            await Timer(1, unit="ns")
            if int(dut.m_valid.value):
                got.append(int(dut.m_data.value)); lasts.append(int(dut.m_last.value))
            done += int(dut.frame_done.value)
        assert got == exp, f"k={k} ncw={ncw} nbytes={nbytes}: {len(got)} bytes"
        assert lasts == [0] * (nbytes - 1) + [1]
        assert done == 1
