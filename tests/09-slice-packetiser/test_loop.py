import random

import cocotb
from cocotb.triggers import ClockCycles

from sl_common import *
from stream_tb import run_stream
from test_unpack import split_payload


@cocotb.test()
async def t9_11_loopback(dut):
    """T9-11 pack then unpack recovers payload and metadata under random handshakes"""
    await setup(dut)
    rng = random.Random(101)
    slices = [rand_slice(rng, rng.randint(1, min(300, MAXB))) for _ in range(40)]
    metas = [rand_meta(rng) for _ in slices]
    words = [(b, i == len(p) - 1) for p in slices for i, b in enumerate(p)]
    pre = meta_hook(dut, metas, [len(p) for p in slices])
    for pv, pr in ((1.0, 1.0), (0.6, 0.5)):
        mon = StatusMon(dut)
        res = await run_stream(dut, words, pv, pr, 8, rng, expect_out=len(words), pre=pre)
        await ClockCycles(dut.clk, 10)
        mon.stop()
        assert split_payload(res.out, None) == slices, f"pv={pv} pr={pr}"
        assert len(mon.items) == len(slices)
        for s, p, m in zip(mon.items, slices, metas):
            assert (s["hdr_ok"], s["crc_ok"], s["trunc"]) == (1, 1, 0)
            assert (s["frame"], s["idx"], s["flags"], s["length"]) == (m[0], m[1], m[2], len(p))
