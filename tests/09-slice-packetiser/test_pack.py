import random

import cocotb
from cocotb.triggers import ClockCycles

from sl_common import *
from stream_tb import run_stream


@cocotb.test()
async def t9_01_02_random(dut):
    """T9-01/02 random slices, full speed and random handshakes, equal to the model"""
    await setup(dut)
    rng = random.Random(91)
    slices = [rand_slice(rng, rng.randint(1, min(600, MAXB))) for _ in range(40)]
    metas = [rand_meta(rng) for _ in slices]
    frames = [frame_bytes(p, *m) for p, m in zip(slices, metas)]
    exp = flat(frames)
    words = [(b, i == len(p) - 1) for p in slices for i, b in enumerate(p)]
    pre = meta_hook(dut, metas, [len(p) for p in slices])
    for pv, pr in ((1.0, 1.0), (0.6, 0.5), (0.9, 0.2)):
        res = await run_stream(dut, words, pv, pr, 8, rng, expect_out=len(exp), pre=pre)
        assert res.out == exp, f"pv={pv} pr={pr}"
        assert not res.violations


@cocotb.test()
async def t9_03_sizes(dut):
    """T9-03 payloads of 1 byte and of exactly MAX_BYTES"""
    await setup(dut)
    rng = random.Random(93)
    slices = [rand_slice(rng, 1), rand_slice(rng, MAXB), rand_slice(rng, 2), rand_slice(rng, MAXB)]
    metas = [rand_meta(rng) for _ in slices]
    frames = [frame_bytes(p, *m) for p, m in zip(slices, metas)]
    exp = flat(frames)
    words = [(b, i == len(p) - 1) for p in slices for i, b in enumerate(p)]
    pre = meta_hook(dut, metas, [len(p) for p in slices])
    res = await run_stream(dut, words, 1.0, 1.0, 8, rng, expect_out=len(exp), pre=pre)
    assert res.out == exp


@cocotb.test()
async def t9_04_throughput(dut):
    """T9-04 no idle clock inside a frame; at most 2 clocks between frames while data is queued"""
    await setup(dut)
    rng = random.Random(94)
    slices = [rand_slice(rng, 40) for _ in range(20)]
    metas = [rand_meta(rng) for _ in slices]
    frames = [frame_bytes(p, *m) for p, m in zip(slices, metas)]
    exp = flat(frames)
    words = [(b, i == len(p) - 1) for p in slices for i, b in enumerate(p)]
    pre = meta_hook(dut, metas, [len(p) for p in slices])
    res = await run_stream(dut, words, 1.0, 1.0, 8, rng, expect_out=len(exp), pre=pre)
    assert res.out == exp
    pos = 0
    gaps_in, gaps_between = [], []
    for f in frames:
        cyc = res.out_cycles[pos:pos + len(f)]
        gaps_in += [b - a for a, b in zip(cyc, cyc[1:])]
        if pos:
            gaps_between.append(cyc[0] - res.out_cycles[pos - 1])
        pos += len(f)
    assert set(gaps_in) == {1}, f"idle clocks inside a frame: {sorted(set(gaps_in))}"
    assert max(gaps_between[1:]) <= 2, f"gap between frames {sorted(set(gaps_between))}"
