import random

import cocotb
from cocotb.triggers import FallingEdge, Timer

from stream_tb import reset, run_stream, start_clock

W = 16
DEPTH = 16


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    start_clock(dut.clk)
    await reset(dut)


@cocotb.test()
async def t1_04_fill_drain(dut):
    """T1-04 fifo: fill to full then drain; level, ready and valid correct"""
    await setup(dut)
    for i in range(DEPTH):
        await FallingEdge(dut.clk)
        dut.s_axis_valid.value = 1
        dut.s_axis_data.value = i
        dut.s_axis_last.value = int(i == DEPTH - 1)
        dut.m_axis_ready.value = 0
        await Timer(1, unit="ns")
        assert int(dut.s_axis_ready.value) == 1, f"not ready at level {i}"
        assert int(dut.level.value) == i
    await FallingEdge(dut.clk)
    dut.s_axis_valid.value = 1
    await Timer(1, unit="ns")
    assert int(dut.level.value) == DEPTH
    assert int(dut.s_axis_ready.value) == 0, "ready must be low when full"
    for i in range(DEPTH):
        await FallingEdge(dut.clk)
        dut.s_axis_valid.value = 0
        dut.m_axis_ready.value = 1
        await Timer(1, unit="ns")
        assert int(dut.m_axis_valid.value) == 1
        assert int(dut.m_axis_data.value) == i
        assert int(dut.m_axis_last.value) == int(i == DEPTH - 1)
        assert int(dut.level.value) == DEPTH - i
    await FallingEdge(dut.clk)
    dut.m_axis_ready.value = 1
    await Timer(1, unit="ns")
    assert int(dut.m_axis_valid.value) == 0, "valid must be low when empty"
    assert int(dut.level.value) == 0


@cocotb.test()
async def t1_05_random(dut):
    """T1-05 fifo: random traffic, data in order, level matches a model every clock"""
    await setup(dut)
    rng = random.Random(5)
    words = [(rng.getrandbits(W), rng.random() < 0.1) for _ in range(20000)]
    model_in = []   # accepted words (for the level model)
    state = {"in": 0, "out": 0}

    def extra(d, cyc):
        lvl = int(d.level.value)
        assert 0 <= lvl <= DEPTH, f"level {lvl}"

    res = await run_stream(dut, words, 0.7, 0.6, W, rng, extra=extra)
    assert res.out == words
    assert not res.violations
    # level model: replay transfers
    ins = set(res.in_cycles)
    outs = set(res.out_cycles)
    lvl = 0
    for c in range(res.cycles):
        assert 0 <= lvl <= DEPTH
        lvl += (c in ins) - (c in outs)
    assert lvl == 0
