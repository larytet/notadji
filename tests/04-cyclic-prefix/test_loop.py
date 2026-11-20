import random

import cocotb

from cp_common import *
from stream_tb import run_stream


@cocotb.test()
async def t4_10_loopback(dut):
    """T4-10 insert followed by remove returns the original symbols for all N and cp_sel"""
    await setup(dut)
    rng = random.Random(50)
    for n in sizes():
        for sel in (0, 1, 2):
            dut.fft_log2.value = n.bit_length() - 1
            dut.cp_sel.value = sel
            syms = [rand_symbol(rng, n) for _ in range(10)]
            exp = flat(syms)
            for pv, pr in ((1.0, 1.0), (0.6, 0.6)):
                res = await run_stream(dut, exp, pv, pr, W, rng, expect_out=len(exp))
                assert res.out == exp, f"N={n} sel={sel} pv={pv}"
