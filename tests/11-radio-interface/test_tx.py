import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

SYS = 5000
CLOCKS = []


async def setup(dut, tx_ps):
    for t in CLOCKS:
        t.cancel()           # a second setup in the same test must not leave two drivers on one clock
    CLOCKS.clear()
    CLOCKS.append(cocotb.start_soon(Clock(dut.clk, SYS, unit="ps").start()))
    CLOCKS.append(cocotb.start_soon(Clock(dut.tx_clk, tx_ps, unit="ps").start()))
    dut.s_axis_valid.value = 0
    dut.s_axis_data.value = 0
    dut.tx_run.value = 1
    dut.tx_req.value = 0
    dut.rst_n.value = 0
    dut.tx_rst_n.value = 0
    for _ in range(6):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    dut.tx_rst_n.value = 1
    for _ in range(8):
        await FallingEdge(dut.clk)


async def feeder(dut, words, p, rng, state):
    i = 0
    active = False
    while i < len(words):
        await FallingEdge(dut.clk)
        if not active and rng.random() < p:
            active = True
        dut.s_axis_valid.value = int(active)
        if active:
            dut.s_axis_data.value = words[i]
        await Timer(100, unit="ps")
        if active and int(dut.s_axis_ready.value):
            i += 1
            active = False
            state["fed"] = i
    await FallingEdge(dut.clk)
    dut.s_axis_valid.value = 0


async def radio(dut, p, rng, got, stats, tx_req_on):
    """radio model on tx_clk: requests a sample with probability p"""
    while True:
        await FallingEdge(dut.tx_clk)
        req = int(rng.random() < p) if tx_req_on["on"] else 0
        dut.tx_req.value = req
        await Timer(100, unit="ps")
        v = int(dut.tx_valid.value)
        d = int(dut.tx_data.value)
        if v:
            got.append(d)
        elif req and tx_req_on["run"]:
            stats["underruns"] += 1
            assert d == 0, "underrun must send zero"
        if not req:
            assert v == 0


@cocotb.test()
async def t11_07_tx(dut):
    """T11-07 in-order delivery, zero fill and exact underrun count, no count while tx_run is low, back-pressure"""
    rng = random.Random(117)
    for tx_ps in (16276, 4000):
        await setup(dut, tx_ps)
        words = [rng.getrandbits(32) for _ in range(300)]
        got, stats, st = [], {"underruns": 0}, {}
        ctl = {"on": True, "run": True}
        r = cocotb.start_soon(radio(dut, 0.7, rng, got, stats, ctl))
        await feeder(dut, words, 0.3, rng, st)
        await ClockCycles(dut.clk, 120)
        ctl["on"] = False
        await ClockCycles(dut.clk, 30)
        r.cancel()
        assert got == words, f"tx_ps={tx_ps}: {len(got)} of {len(words)}"
        await ClockCycles(dut.clk, 10)
        assert int(dut.tx_underrun_cnt.value) == stats["underruns"], f"counter {int(dut.tx_underrun_cnt.value)} model {stats['underruns']}"
        assert stats["underruns"] > 0
    # no count while tx_run is low
    await setup(dut, 8000)
    dut.tx_run.value = 0
    await ClockCycles(dut.clk, 8)
    got, stats = [], {"underruns": 0}
    ctl = {"on": True, "run": False}
    r = cocotb.start_soon(radio(dut, 1.0, rng, got, stats, ctl))
    await ClockCycles(dut.clk, 100)
    r.cancel()
    assert got == [] and int(dut.tx_underrun_cnt.value) == 0
    # back-pressure: radio not requesting, fill the FIFO
    dut.tx_req.value = 0
    dut.tx_run.value = 1
    await ClockCycles(dut.clk, 8)
    words = [rng.getrandbits(32) for _ in range(40)]
    st = {"fed": 0}
    f = cocotb.start_soon(feeder(dut, words, 1.0, rng, st))
    await ClockCycles(dut.clk, 80)
    assert 1 <= st["fed"] <= 16, f"{st['fed']} words accepted by a depth-16 FIFO"
    assert int(dut.s_axis_ready.value) == 0
    got, stats = [], {"underruns": 0}
    ctl = {"on": True, "run": True}
    r = cocotb.start_soon(radio(dut, 1.0, rng, got, stats, ctl))
    await f
    await ClockCycles(dut.clk, 80)
    r.cancel()
    assert got == words
