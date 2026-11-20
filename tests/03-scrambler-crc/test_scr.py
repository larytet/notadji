import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

from stream_tb import reset, run_stream, start_clock

W = int(os.environ["W"])
LEN = int(os.environ["LEN"])
TAPS = int(os.environ["TAPS"])
SEED = int(os.environ["SEED"])
MASK = (1 << LEN) - 1


def keystream_bits(n):
    state = SEED
    out = []
    for _ in range(n):
        fb = bin(state & TAPS).count("1") & 1
        out.append(fb)
        state = ((state << 1) & MASK) | fb
    return out


def scramble_frames(frames):
    """frames: list of lists of words -> list of (word, last) as the DUT must emit them"""
    out = []
    for f in frames:
        ks = keystream_bits(len(f) * W)
        for i, w in enumerate(f):
            kw = 0
            for b in range(W):
                kw |= ks[i * W + b] << b
            out.append((w ^ kw, i == len(f) - 1))
    return out


def to_in(frames):
    return [(w, i == len(f) - 1) for f in frames for i, w in enumerate(f)]


def rand_frames(rng, n, maxlen=20):
    return [[rng.getrandbits(W) for _ in range(rng.randint(1, maxlen))] for _ in range(n)]


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    start_clock(dut.clk)
    await reset(dut)


@cocotb.test()
async def t3_01_model(dut):
    """T3-01 random frames and back-pressure equal the bit-serial model"""
    await setup(dut)
    rng = random.Random(31)
    frames = rand_frames(rng, 300)
    expect = scramble_frames(frames)
    for pv, pr in ((1.0, 1.0), (0.5, 0.5), (0.9, 0.2)):
        res = await run_stream(dut, to_in(frames), pv, pr, W, rng)
        assert res.out == expect, f"mismatch p_valid={pv} p_ready={pr}"
        assert not res.violations


@cocotb.test()
async def t3_02_involution(dut):
    """T3-02 scramble then descramble is the identity"""
    await setup(dut)
    rng = random.Random(32)
    frames = rand_frames(rng, 100)
    first = await run_stream(dut, to_in(frames), 0.8, 0.8, W, rng)
    second = await run_stream(dut, first.out, 0.8, 0.8, W, rng)
    assert second.out == to_in(frames)


@cocotb.test()
async def t3_03_restart(dut):
    """T3-03 every frame starts from the seed regardless of the previous frame length"""
    await setup(dut)
    rng = random.Random(33)
    same = [rng.getrandbits(W) for _ in range(3)]
    frames = [same, [rng.getrandbits(W)], same, [rng.getrandbits(W) for _ in range(9)], same]
    res = await run_stream(dut, to_in(frames), 1.0, 1.0, W, rng)
    flat = [w for w, _ in res.out]
    # frames 0, 2 and 4 are identical inputs: their outputs must be identical
    f0 = flat[0:3]
    f2 = flat[4:7]
    f4 = flat[16:19]
    assert f0 == f2 == f4


@cocotb.test()
async def t3_04_period(dut):
    """T3-04 keystream period: 127 bits (LEN 7) or 32767 bits (LEN 15), exactly"""
    await setup(dut)
    rng = random.Random(34)
    period = (1 << LEN) - 1
    nwords = (3 * period + W - 1) // W
    frames = [[0] * nwords]
    res = await run_stream(dut, to_in(frames), 1.0, 1.0, W, rng)
    bits = []
    for w, _ in res.out:
        bits.extend((w >> b) & 1 for b in range(W))
    s = "".join(map(str, bits))
    p = s.find(s[:96], 1)
    assert p == period, f"period {p}, expected {period}"


@cocotb.test()
async def t3_05_stall_and_latency(dut):
    """T3-05 zero-latency pass-through; stalls do not advance the state"""
    await setup(dut)
    rng = random.Random(35)
    frames = rand_frames(rng, 60)
    bad = []

    def extra(d, cyc):
        if int(d.m_axis_valid.value) != int(d.s_axis_valid.value):
            bad.append((cyc, "valid"))
        if int(d.s_axis_ready.value) != int(d.m_axis_ready.value):
            bad.append((cyc, "ready"))

    res = await run_stream(dut, to_in(frames), 0.6, 0.4, W, rng, extra=extra, stall_window=(10, 60))
    assert not bad, bad[:3]
    assert res.out == scramble_frames(frames)
