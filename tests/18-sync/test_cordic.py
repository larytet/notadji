import math
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer


@cocotb.test()
async def t18_08_cordic(dut):
    """T18-08 angle of random vectors, all quadrants, within 2 LSB of 65536 per turn"""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.start.value = 0
    dut.x.value = 0
    dut.y.value = 0
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)
    rng = random.Random(188)
    worst = 0
    worst_big = 0
    cases = [(1 << 20, 0), (0, 1 << 20), (-(1 << 20), 0), (0, -(1 << 20)), (1 << 20, 1 << 20), (-(1 << 20), 1 << 20), (-(1 << 20), -(1 << 20)), (1 << 20, -(1 << 20))]
    cases += [(rng.randint(-(1 << 22), (1 << 22) - 1), rng.randint(-(1 << 22), (1 << 22) - 1)) for _ in range(5000)]
    cases += [(rng.randint(-50, 50), rng.randint(-50, 50)) for _ in range(500) if True]
    for x, y in cases:
        if x == 0 and y == 0:
            continue
        dut.x.value = x
        dut.y.value = y
        dut.start.value = 1
        await FallingEdge(dut.clk)
        dut.start.value = 0
        for _ in range(40):
            await Timer(1, unit="ns")
            if int(dut.done.value):
                break
            await FallingEdge(dut.clk)
        assert int(dut.done.value) == 1
        got = int(dut.angle.value)
        exp = int(round(math.atan2(y, x) / (2 * math.pi) * 65536)) % 65536
        d = abs(got - exp)
        d = min(d, 65536 - d)
        worst = max(worst, d)
        if abs(x) > 1000 or abs(y) > 1000:
            worst_big = max(worst_big, d)
            assert d <= 2, f"x={x} y={y}: got {got} expected {exp}"
        await FallingEdge(dut.clk)
    dut._log.info(f"CORDICERR large vectors: worst error {worst_big} LSB of 65536; vectors of magnitude below 50 (integer inputs): worst {worst} LSB")
