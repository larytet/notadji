import os
import random

import cocotb

from stream_tb import reset, run_stream, start_clock

IN_W = int(os.environ["IN_W"])
OUT_W = int(os.environ["OUT_W"])


def pack_up(frames):
    """frames: list of lists of input words (multiple of ratio) -> list of (outword, last)"""
    r = OUT_W // IN_W
    out = []
    for f in frames:
        for i in range(0, len(f), r):
            word = 0
            for k in range(r):
                word |= f[i + k] << (k * IN_W)
            out.append((word, i + r == len(f)))
    return out


def pack_down(frames):
    r = IN_W // OUT_W
    out = []
    mask = (1 << OUT_W) - 1
    for f in frames:
        for wi, w in enumerate(f):
            for k in range(r):
                out.append(((w >> (k * OUT_W)) & mask, wi == len(f) - 1 and k == r - 1))
    return out


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    start_clock(dut.clk)
    await reset(dut)


def make_frames(rng, nframes, mult):
    frames = []
    for _ in range(nframes):
        n = rng.randint(1, 8) * mult
        frames.append([rng.getrandbits(IN_W) for _ in range(n)])
    return frames


@cocotb.test()
async def t1_06_conversion(dut):
    """T1-06 width conv: packed and unpacked output equals the model, last on the right beat"""
    await setup(dut)
    rng = random.Random(6)
    ratio = max(OUT_W // IN_W, 1)
    frames = make_frames(rng, 300, ratio if OUT_W > IN_W else 1)
    in_words = [(w, i == len(f) - 1) for f in frames for i, w in enumerate(f)]
    if OUT_W > IN_W:
        expect = pack_up(frames)
    elif OUT_W < IN_W:
        expect = pack_down(frames)
    else:
        expect = in_words
    for pv, pr in ((1.0, 1.0), (0.5, 0.5), (0.9, 0.2)):
        res = await run_stream(dut, in_words, pv, pr, IN_W, rng, expect_out=len(expect))
        assert res.out == expect, f"mismatch p_valid={pv} p_ready={pr}"
        assert not res.violations, res.violations[:3]


@cocotb.test()
async def t1_06b_throughput(dut):
    """T1-06 width conv: full-rate throughput, one output word per ratio input beats"""
    await setup(dut)
    rng = random.Random(7)
    ratio = max(OUT_W // IN_W, IN_W // OUT_W)
    if ratio == 1:
        return
    frames = make_frames(rng, 100, ratio if OUT_W > IN_W else 1)
    in_words = [(w, i == len(f) - 1) for f in frames for i, w in enumerate(f)]
    expect = pack_up(frames) if OUT_W > IN_W else pack_down(frames)
    res = await run_stream(dut, in_words, 1.0, 1.0, IN_W, rng, expect_out=len(expect))
    assert res.out == expect
    # the wide side is busy 1 beat in `ratio`; the narrow side must never stall
    narrow = res.in_cycles if OUT_W > IN_W else res.out_cycles
    span = narrow[-1] - narrow[0] + 1
    assert span <= len(narrow) + len(frames) * 2, f"narrow side stalled: span {span} for {len(narrow)} beats"


@cocotb.test()
async def t1_07_bad_frame(dut):
    """T1-07 width conv: up-conversion frame of non-multiple length raises err_frame once and recovers"""
    if OUT_W <= IN_W:
        return
    await setup(dut)
    rng = random.Random(8)
    ratio = OUT_W // IN_W
    if ratio < 2:
        return
    good = [rng.getrandbits(IN_W) for _ in range(ratio * 2)]
    bad = [rng.getrandbits(IN_W) for _ in range(ratio + 1)]   # one beat over a word boundary
    good2 = [rng.getrandbits(IN_W) for _ in range(ratio)]
    frames = [good, bad, good2]
    in_words = [(w, i == len(f) - 1) for f in frames for i, w in enumerate(f)]
    errs = []

    def extra(d, cyc):
        if int(d.err_frame.value):
            errs.append(cyc)

    # expected: good as 2 words; bad as one full word plus a zero-filled partial word flagged last; good2
    exp = pack_up([good])
    w0 = pack_up([bad[:ratio]])[0][0]
    exp += [(w0, False), (bad[ratio], True)]
    exp += pack_up([good2])
    res = await run_stream(dut, in_words, 1.0, 1.0, IN_W, rng, expect_out=len(exp), extra=extra)
    assert res.out == exp, f"got {res.out} expected {exp}"
    assert len(errs) == 1, f"err_frame pulses: {errs}"
