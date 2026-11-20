import random

import cocotb
from cocotb.triggers import ClockCycles

from stream_tb import reset, run_stream, start_clock


@cocotb.test()
async def t15_09_tail_hold(dut):
    """T15-09 stream delayed by 16 bytes; the last 16 bytes arrive as the tail word; short frames flagged"""
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 1
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    start_clock(dut.clk)
    await reset(dut)
    rng = random.Random(159)
    for pv, pr in ((1.0, 1.0), (0.6, 0.5)):
        frames = [[rng.getrandbits(8) for _ in range(n)] for n in (17, 20, 33, 64, 100, 17, 1000)]
        words = [(b, i == len(f) - 1) for f in frames for i, b in enumerate(f)]
        tails = []

        def extra(d, cyc):
            if int(d.m_axis_valid.value) and int(d.m_axis_ready.value) and int(d.m_axis_last.value):
                tails.append(int(d.m_tail.value).to_bytes(16, "little"))

        res = await run_stream(dut, words, pv, pr, 8, rng, expect_out=sum(len(f) - 16 for f in frames), extra=extra)
        exp = [(b, i == len(f) - 17) for f in frames for i, b in enumerate(f[:-16])]
        assert res.out == exp, f"pv={pv} pr={pr}"
        assert tails == [bytes(f[-16:]) for f in frames], "tail words"
        assert not res.violations
    # empty payload (16 bytes) and short frames
    events = []

    async def mon():
        from cocotb.triggers import FallingEdge
        while True:
            await FallingEdge(dut.clk)
            if int(dut.m_empty.value):
                events.append(("empty", int(dut.m_tail.value).to_bytes(16, "little")))
            if int(dut.m_short.value):
                events.append(("short", None))

    from cocotb import start_soon
    m = start_soon(mon())
    f16 = [rng.getrandbits(8) for _ in range(16)]
    f5 = [rng.getrandbits(8) for _ in range(5)]
    words = [(b, i == 15) for i, b in enumerate(f16)] + [(b, i == 4) for i, b in enumerate(f5)]
    res = await run_stream(dut, words, 1.0, 1.0, 8, rng, expect_out=0)
    await ClockCycles(dut.clk, 4)
    m.cancel()
    assert events == [("empty", bytes(f16)), ("short", None)], events
    assert res.out == []
