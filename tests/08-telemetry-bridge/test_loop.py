import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge

from tb_common import start
from test_tx import feed


@cocotb.test()
async def t8_04_loopback(dut):
    """T8-04 tx to rx at divisors 4, 8, 66 and 3000"""
    dut.s_axis_valid.value = 0
    dut.s_axis_data.value = 0
    dut.div.value = 8
    await start(dut)
    rng = random.Random(84)
    for div in (4, 8, 66, 3000):
        dut.div.value = div
        await ClockCycles(dut.clk, 4)
        n = 40 if div < 1000 else 4
        data = [rng.getrandbits(8) for _ in range(n)]
        got = []
        errs = []

        async def mon():
            while True:
                await FallingEdge(dut.clk)
                if int(dut.m_axis_valid.value):
                    got.append(int(dut.m_axis_data.value))
                    errs.append(int(dut.frame_err.value))

        m = cocotb.start_soon(mon())
        await feed(dut, data)
        await ClockCycles(dut.clk, 12 * div)
        m.cancel()
        assert got == data, f"div={div}"
        assert not any(errs)
