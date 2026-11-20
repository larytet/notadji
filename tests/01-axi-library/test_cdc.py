import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

W = 16
AW = 4
DEPTH = 2 ** AW


async def producer(dut, words, p, rng, state):
    idx = 0
    active = False
    while idx < len(words):
        await FallingEdge(dut.s_clk)
        if not active and rng.random() < p:
            active = True
        if active:
            d, l = words[idx]
            dut.s_axis_valid.value = 1
            dut.s_axis_data.value = d
            dut.s_axis_last.value = int(l)
        else:
            dut.s_axis_valid.value = 0
        await Timer(1, unit="ns")
        if active and int(dut.s_axis_ready.value):
            idx += 1
            active = False
            state["written"] = idx
        if not int(dut.s_axis_ready.value):
            state["full_seen"] = True
    await FallingEdge(dut.s_clk)
    dut.s_axis_valid.value = 0


async def consumer(dut, n, p, rng, out, state):
    while len(out) < n and state["cycles"] < 400000:
        await FallingEdge(dut.m_clk)
        state["cycles"] += 1
        dut.m_axis_ready.value = 1 if rng.random() < p else 0
        await Timer(1, unit="ns")
        if int(dut.m_axis_valid.value):
            # model check: never read more than was written
            assert len(out) < state["written"], "read from empty FIFO"
            if int(dut.m_axis_ready.value):
                out.append((int(dut.m_axis_data.value), int(dut.m_axis_last.value)))
        else:
            state["empty_seen"] = True


async def setup(dut, s_per_ps, m_per_ps):
    cocotb.start_soon(Clock(dut.s_clk, s_per_ps, unit="ps").start())
    cocotb.start_soon(Clock(dut.m_clk, m_per_ps, unit="ps").start())
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.s_rst_n.value = 0
    dut.m_rst_n.value = 0
    for _ in range(6):
        await FallingEdge(dut.s_clk)
    dut.s_rst_n.value = 1
    dut.m_rst_n.value = 1
    for _ in range(6):
        await FallingEdge(dut.s_clk)


async def run(dut, s_per, m_per, ps, pm, n, seed):
    await setup(dut, s_per, m_per)
    rng = random.Random(seed)
    words = [(rng.getrandbits(W), rng.random() < 0.1) for _ in range(n)]
    out = []
    state = {"written": 0, "cycles": 0, "full_seen": False, "empty_seen": False}
    c = cocotb.start_soon(consumer(dut, n, pm, random.Random(seed + 1), out, state))
    cocotb.start_soon(producer(dut, words, ps, random.Random(seed + 2), state))
    await c
    assert out == words, f"mismatch: got {len(out)} of {n} words"
    return state


@cocotb.test()
async def t1_08a_write_faster(dut):
    """T1-08 cdc fifo: write 200 MHz, read 150 MHz, 20000 words, random enables"""
    await run(dut, 5000, 6666, 0.8, 0.8, 20000, 11)


@cocotb.test()
async def t1_08b_read_faster(dut):
    """T1-08 cdc fifo: write 150 MHz, read 200 MHz, 20000 words, random enables"""
    st = await run(dut, 6666, 5000, 0.8, 0.8, 20000, 12)
    assert st["empty_seen"], "reader never saw the FIFO empty"


@cocotb.test()
async def t1_09_slow_reader(dut):
    """T1-09 cdc fifo: reader 10x slower than the writer; writer stalls through ready; nothing lost"""
    st = await run(dut, 5000, 50000, 1.0, 1.0, 3000, 21)
    assert st["full_seen"], "writer never saw the FIFO full (ready low)"
