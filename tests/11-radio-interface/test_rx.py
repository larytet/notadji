import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

SYS = 5000          # ps
CLOCKS = []


async def setup(dut, rx_ps):
    for t in CLOCKS:
        t.cancel()           # a second setup in the same test must not leave two drivers on one clock
    CLOCKS.clear()
    CLOCKS.append(cocotb.start_soon(Clock(dut.clk, SYS, unit="ps").start()))
    CLOCKS.append(cocotb.start_soon(Clock(dut.rx_clk, rx_ps, unit="ps").start()))
    dut.rx_valid.value = 0
    dut.rx_data.value = 0
    dut.m_axis_ready.value = 1
    dut.rst_n.value = 0
    dut.rx_rst_n.value = 0
    for _ in range(6):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    dut.rx_rst_n.value = 1
    for _ in range(6):
        await FallingEdge(dut.clk)


async def radio(dut, samples, p, rng, state):
    """radio model: a sample on the radio clock whenever it has one (the radio cannot be stopped)"""
    i = 0
    while i < len(samples):
        await FallingEdge(dut.rx_clk)
        if rng.random() < p:
            dut.rx_valid.value = 1
            dut.rx_data.value = samples[i]
            i += 1
        else:
            dut.rx_valid.value = 0
    await FallingEdge(dut.rx_clk)
    dut.rx_valid.value = 0
    state["sent"] = i


async def sink(dut, out, p, rng, run):
    while True:
        await FallingEdge(dut.clk)
        r = 1 if (run["on"] and rng.random() < p) else 0
        dut.m_axis_ready.value = r
        await Timer(100, unit="ps")
        if int(dut.m_axis_valid.value) and r:
            out.append(int(dut.m_axis_data.value))


@cocotb.test()
async def t11_05_clock_ratios(dut):
    """T11-05 radio slower and faster than the system clock: all samples in order, no drops"""
    rng = random.Random(115)
    for rx_ps in (16276, 4000):
        await setup(dut, rx_ps)
        samples = [rng.getrandbits(32) for _ in range(3000)]
        out, st, run = [], {}, {"on": True}
        s = cocotb.start_soon(sink(dut, out, 0.9, rng, run))
        await radio(dut, samples, 0.5 if rx_ps < SYS else 0.9, rng, st)
        await ClockCycles(dut.clk, 60)
        s.cancel()
        assert out == samples, f"rx_ps={rx_ps}: {len(out)} of {len(samples)}"
        assert int(dut.rx_overrun_cnt.value) == 0


@cocotb.test()
async def t11_06_overrun(dut):
    """T11-06 stalled sink: the extra samples are dropped and counted exactly; the stream resumes in order"""
    rng = random.Random(116)
    await setup(dut, 8000)
    out, st, run = [], {}, {"on": False}
    s = cocotb.start_soon(sink(dut, out, 1.0, rng, run))
    samples = [rng.getrandbits(32) for _ in range(60)]
    await radio(dut, samples, 1.0, rng, st)
    await ClockCycles(dut.clk, 40)
    run["on"] = True
    await ClockCycles(dut.clk, 60)
    first = list(out)
    assert 1 <= len(first) <= 16, f"{len(first)} samples were accepted into a depth-16 FIFO"
    assert first == samples[:len(first)], "accepted samples must be the oldest ones, in order"
    dropped = len(samples) - len(first)
    await ClockCycles(dut.clk, 10)
    assert int(dut.rx_overrun_cnt.value) == dropped, f"counter {int(dut.rx_overrun_cnt.value)} dropped {dropped}"
    # stream resumes: new samples arrive in order
    more = [rng.getrandbits(32) for _ in range(40)]
    out.clear()
    await radio(dut, more, 0.5, rng, st)
    await ClockCycles(dut.clk, 60)
    s.cancel()
    assert out == more
