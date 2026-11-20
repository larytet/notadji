import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from tb_common import start, uart_send


async def monitor(dut, got, errs):
    while True:
        await FallingEdge(dut.clk)
        if int(dut.m_axis_valid.value):
            got.append(int(dut.m_axis_data.value))
            errs.append(int(dut.frame_err.value))


@cocotb.test()
async def t8_01_random_and_back_to_back(dut):
    """T8-01 random bytes with random gaps, then back to back; divisors 4, 8, 66"""
    dut.rxd.value = 1
    dut.div.value = 8
    await start(dut)
    rng = random.Random(81)
    got, errs = [], []
    cocotb.start_soon(monitor(dut, got, errs))
    for div in (4, 8, 66):
        dut.div.value = div
        await ClockCycles(dut.clk, 3 * div)
        for gap_mode in ("random", "b2b"):
            sent = [rng.getrandbits(8) for _ in range(60)]
            got.clear(); errs.clear()
            for b in sent:
                await uart_send(dut, dut.rxd, b, div, idle_bits=(rng.randint(0, 3) if gap_mode == "random" else 0))
            await ClockCycles(dut.clk, 3 * div)
            assert got == sent, f"div={div} {gap_mode}"
            assert not any(errs)


@cocotb.test()
async def t8_02_bad_stop_and_glitch(dut):
    """T8-02 bad stop bit raises frame_err (byte still delivered); a short start glitch gives no byte"""
    dut.rxd.value = 1
    dut.div.value = 16
    await start(dut)
    got, errs = [], []
    cocotb.start_soon(monitor(dut, got, errs))
    div = 16
    await ClockCycles(dut.clk, 3 * div)
    await uart_send(dut, dut.rxd, 0xA5, div, stop=0)
    await ClockCycles(dut.clk, 3 * div)
    assert got == [0xA5] and errs == [1], (got, errs)
    got.clear(); errs.clear()
    # glitch: low for a quarter of a bit
    dut.rxd.value = 0
    await ClockCycles(dut.clk, div // 4)
    dut.rxd.value = 1
    await ClockCycles(dut.clk, 5 * div)
    assert got == [], f"glitch produced {got}"
    # a good byte still works afterwards
    await uart_send(dut, dut.rxd, 0x3C, div, idle_bits=2)
    await ClockCycles(dut.clk, 2 * div)
    assert got == [0x3C] and errs == [0]
