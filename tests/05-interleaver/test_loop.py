import random

import cocotb

from il_common import *
from stream_tb import run_stream


@cocotb.test()
async def t5_04_round_trip(dut):
    """T5-04 interleave then de-interleave returns the original blocks (random n, random handshakes)"""
    await setup(dut)
    rng = random.Random(54)
    ns = [rng.choice(n_list()) for _ in range(25)]
    blocks = [rand_block(rng, n) for n in ns]
    exp = flat(blocks)
    pre = n_hook(dut, ns)
    for pv, pr in ((1.0, 1.0), (0.6, 0.6)):
        res = await run_stream(dut, exp, pv, pr, W, rng, expect_out=len(exp), pre=pre)
        assert res.out == exp, f"pv={pv} pr={pr}"
        assert not res.violations
