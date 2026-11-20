import random

import cocotb
from cocotb.triggers import ClockCycles

from sl_common import *
from stream_tb import run_stream


async def run_frames(dut, frames, pv=1.0, pr=1.0, seed=0, expect_out=None):
    rng = random.Random(seed)
    mon = StatusMon(dut)
    words = flat(frames)
    res = await run_stream(dut, words, pv, pr, 8, rng, expect_out=expect_out if expect_out is not None else 0)
    await ClockCycles(dut.clk, 8)
    mon.stop()
    return res, mon.items


def split_payload(out, lens):
    """split the output byte list into per-frame payloads by `last`"""
    res, cur = [], []
    for b, l in out:
        cur.append(b)
        if l:
            res.append(cur)
            cur = []
    return res


@cocotb.test()
async def t9_05_good_frames(dut):
    """T9-05 payload and status of good frames"""
    await setup(dut)
    rng = random.Random(95)
    for pv, pr in ((1.0, 1.0), (0.6, 0.5), (0.9, 0.2)):
        slices = [rand_slice(rng, rng.choice([0, 1, 5, 60, 200])) for _ in range(30)]
        slices = [s[:MAXB] for s in slices]
        metas = [rand_meta(rng) for _ in slices]
        frames = [frame_bytes(p, *m) for p, m in zip(slices, metas)]
        total = sum(len(p) for p in slices)
        res, st = await run_frames(dut, frames, pv, pr, seed=2, expect_out=total)
        got = split_payload(res.out, None)
        assert got == [p for p in slices if p], f"pv={pv} pr={pr}"
        assert len(st) == len(frames)
        for s, p, m in zip(st, slices, metas):
            assert (s["hdr_ok"], s["crc_ok"], s["trunc"]) == (1, 1, 0)
            assert (s["frame"], s["idx"], s["flags"], s["length"]) == (m[0], m[1], m[2], len(p))
        assert not res.violations


@cocotb.test()
async def t9_06_padding(dut):
    """T9-06 bytes after the CRC are ignored"""
    await setup(dut)
    rng = random.Random(96)
    slices = [rand_slice(rng, rng.randint(1, 50)) for _ in range(20)]
    metas = [rand_meta(rng) for _ in slices]
    frames = [frame_bytes(p, *m) + [rng.getrandbits(8) for _ in range(rng.randint(0, 40))] for p, m in zip(slices, metas)]
    total = sum(len(p) for p in slices)
    res, st = await run_frames(dut, frames, 0.8, 0.8, seed=3, expect_out=total)
    assert split_payload(res.out, None) == slices
    assert len(st) == len(frames) and all((s["hdr_ok"], s["crc_ok"], s["trunc"]) == (1, 1, 0) for s in st)


@cocotb.test()
async def t9_07_header_errors(dut):
    """T9-07 every single-bit error in the 8 header bytes is detected, no payload forwarded"""
    await setup(dut)
    rng = random.Random(97)
    p = rand_slice(rng, 20)
    base = frame_bytes(p, 0x1234, 7, 0b0101)
    frames = []
    for bit in range(64):
        f = list(base)
        f[bit // 8] ^= 1 << (bit % 8)
        frames.append(f)
    res, st = await run_frames(dut, frames, 1.0, 1.0, seed=4, expect_out=0)
    assert res.out == [], "payload of a frame with a bad header must not be forwarded"
    assert len(st) == 64
    assert all(s["hdr_ok"] == 0 and s["crc_ok"] == 0 for s in st), [i for i, s in enumerate(st) if s["hdr_ok"]]
    # a good frame after all of them is still received
    res, st = await run_frames(dut, [base], expect_out=len(p))
    assert split_payload(res.out, None) == [p] and st[0]["crc_ok"] == 1


@cocotb.test()
async def t9_08_payload_errors(dut):
    """T9-08 single-bit errors in payload and CRC: header ok, crc_ok = 0"""
    await setup(dut)
    rng = random.Random(98)
    frames, pays = [], []
    for _ in range(200):
        p = rand_slice(rng, rng.randint(1, 40))
        f = frame_bytes(p, *rand_meta(rng))
        bit = rng.randrange(8 * (len(f) - 8))
        f[8 + bit // 8] ^= 1 << (bit % 8)
        frames.append(f)
        pays.append(f[8:8 + len(p)])
    total = sum(len(p) for p in pays)
    res, st = await run_frames(dut, frames, 0.9, 0.9, seed=5, expect_out=total)
    assert split_payload(res.out, None) == pays
    assert len(st) == 200
    assert all(s["hdr_ok"] == 1 and s["crc_ok"] == 0 and s["trunc"] == 0 for s in st)


@cocotb.test()
async def t9_09_truncated(dut):
    """T9-09 frames cut inside the header, the payload and the CRC; next frame still fine"""
    await setup(dut)
    rng = random.Random(99)
    p = rand_slice(rng, 30)
    full = frame_bytes(p, 0x0102, 3, 0b0011)
    good_p = rand_slice(rng, 12)
    good = frame_bytes(good_p, 9, 1, 0)
    # cut inside the header (keep 3 bytes)
    res, st = await run_frames(dut, [full[:3], good], expect_out=len(good_p))
    assert st[0]["trunc"] == 1 and st[0]["hdr_ok"] == 0
    assert split_payload(res.out, None) == [good_p] and st[1]["crc_ok"] == 1
    # cut inside the payload (keep header + 10 payload bytes)
    cut = full[:8 + 10]
    res, st = await run_frames(dut, [cut, good], expect_out=11 + len(good_p))
    assert st[0]["trunc"] == 1 and st[0]["crc_ok"] == 0 and st[0]["hdr_ok"] == 1
    parts = split_payload(res.out, None)
    assert parts[0][:10] == p[:10] and parts[0][-1] == 0 and len(parts[0]) == 11, "closed with a dummy last byte"
    assert parts[1] == good_p and st[1]["crc_ok"] == 1
    # cut inside the CRC (keep header + payload + 2 CRC bytes)
    cut = full[:8 + 30 + 2]
    res, st = await run_frames(dut, [cut, good], expect_out=len(p) + len(good_p))
    assert st[0]["trunc"] == 1 and st[0]["crc_ok"] == 0 and st[0]["hdr_ok"] == 1
    parts = split_payload(res.out, None)
    assert parts == [p, good_p] and st[1]["crc_ok"] == 1


@cocotb.test()
async def t9_10_len_too_big(dut):
    """T9-10 len above MAX_BYTES with a valid header CRC is rejected"""
    await setup(dut)
    rng = random.Random(100)
    p = rand_slice(rng, 20)
    bad = frame_bytes(p, 5, 2, 1, bad_len=MAXB + 1)
    res, st = await run_frames(dut, [bad], expect_out=0)
    assert res.out == [] and st[0]["hdr_ok"] == 0
    ok = frame_bytes(p, 5, 2, 1)
    res, st = await run_frames(dut, [ok], expect_out=len(p))
    assert st[0]["hdr_ok"] == 1 and st[0]["crc_ok"] == 1
    # a payload of exactly MAX_BYTES is accepted
    big = rand_slice(rng, MAXB)
    res, st = await run_frames(dut, [frame_bytes(big, 6, 3, 0)], expect_out=MAXB)
    assert st[0]["hdr_ok"] == 1 and st[0]["crc_ok"] == 1 and st[0]["length"] == MAXB
