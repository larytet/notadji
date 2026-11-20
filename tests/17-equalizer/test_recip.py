import random

import cocotb
from cocotb.triggers import Timer

from eq_model import TAB, recip


@cocotb.test()
async def t17_01_recip(dut):
    """T17-01 table equals round(2^23/(256+i)); the reciprocal is accurate to 0.5%"""
    for i in range(256):
        dut.idx.value = i
        await Timer(1, unit="ns")
        assert int(dut.t.value) == TAB[i] == int(2 ** 23 / (256 + i) + 0.5), f"entry {i}"
    rng = random.Random(171)
    worst = 0.0
    for _ in range(20000):
        e = rng.randint(10, 31)
        x = rng.randint(1 << (e - 1), (1 << e) - 1) if e > 1 else 1
        x = min(x, (1 << 32) - 1)
        r = recip(x)
        exact = 2 ** 40 / x
        if exact < 0x7FFFFFFF:
            err = abs(r - exact) / exact
            worst = max(worst, err)
            assert err < 0.005, f"x={x}: {r} vs {exact:.1f}"
        else:
            assert r == 0x7FFFFFFF
    dut._log.info(f"RECIP worst relative error {worst:.4%}")
