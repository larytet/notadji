import binascii
import os
import random
import zlib

import cocotb
from cocotb.triggers import FallingEdge, Timer

from stream_tb import reset, run_stream, start_clock

KIND = os.environ["KIND"]
DW = int(os.environ["DW"])
NB = DW // 8
if KIND == "crc32":
    CRC_BYTES = 4
    RESIDUE = 0x2144DF1C

    def ref(data):
        return zlib.crc32(bytes(data))

    def append(crc):
        return crc.to_bytes(4, "little")
else:
    CRC_BYTES = 2
    RESIDUE = 0

    def ref(data):
        return binascii.crc_hqx(bytes(data), 0xFFFF)

    def append(crc):
        return crc.to_bytes(2, "big")


def words_of(data):
    assert len(data) % NB == 0
    return [int.from_bytes(bytes(data[i:i + NB]), "little") for i in range(0, len(data), NB)]


def frame_words(data):
    w = words_of(data)
    return [(x, i == len(w) - 1) for i, x in enumerate(w)]


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    start_clock(dut.clk)
    await reset(dut)


async def send(dut, frames, rng, pv, pr):
    """Send frames (list of byte lists), return the list of (crc_value, crc_ok) at every crc_valid pulse."""
    words = [fw for f in frames for fw in frame_words(f)]
    pulses = []

    def extra(d, cyc):
        if int(d.crc_valid.value):
            pulses.append((int(d.crc_value.value), int(d.crc_ok.value)))

    res = await run_stream(dut, words, pv, pr, DW, rng, extra=extra)
    # the pulse for the last frame comes one clock after its last transfer
    await FallingEdge(dut.clk)
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 1
    await Timer(1, unit="ns")
    if int(dut.crc_valid.value):
        pulses.append((int(dut.crc_value.value), int(dut.crc_ok.value)))
    assert [w for w in res.out] == words
    assert not res.violations
    return pulses


def rand_data(rng, nbytes):
    return [rng.getrandbits(8) for _ in range(nbytes)]


@cocotb.test()
async def t3_06_07_random_frames(dut):
    """T3-06/07 CRC of random frames equals zlib.crc32 or crc_hqx, one pulse per frame"""
    await setup(dut)
    rng = random.Random(36)
    frames = [rand_data(rng, NB * rng.randint(1, 12)) for _ in range(300)]
    for pv, pr in ((1.0, 1.0), (0.5, 0.5), (0.9, 0.2)):
        pulses = await send(dut, frames, rng, pv, pr)
        assert len(pulses) == len(frames), f"{len(pulses)} pulses for {len(frames)} frames"
        for (v, _), f in zip(pulses, frames):
            assert v == ref(f), f"crc {v:#x} expected {ref(f):#x}"


@cocotb.test()
async def t3_08_check_vector(dut):
    """T3-08 check value of the ASCII string 123456789"""
    await setup(dut)
    rng = random.Random(38)
    s = list(b"123456789")
    # pad the string to a whole number of words by choosing the data width: use a frame of repeated check strings
    if len(s) % NB == 0:
        pulses = await send(dut, [s], rng, 1.0, 1.0)
        want = 0xCBF43926 if KIND == "crc32" else 0x29B1
        assert pulses[0][0] == want
    else:
        # DW does not divide 9 bytes: check the library-equivalent value of a 9*NB byte frame instead
        f = s * NB
        pulses = await send(dut, [f], rng, 1.0, 1.0)
        assert pulses[0][0] == ref(f)


@cocotb.test()
async def t3_09_running_value(dut):
    """T3-09 crc_value after every accepted word equals the library CRC of the bytes so far"""
    await setup(dut)
    rng = random.Random(39)
    data = rand_data(rng, NB * 10)
    words = words_of(data)
    dut.m_axis_ready.value = 1
    for j, w in enumerate(words):
        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        if j > 0:
            got = int(dut.crc_value.value)
            assert got == ref(data[: NB * j]), f"after word {j}: {got:#x}"
        dut.s_axis_valid.value = 1
        dut.s_axis_data.value = w
        dut.s_axis_last.value = int(j == len(words) - 1)
        dut.m_axis_ready.value = 1
    await FallingEdge(dut.clk)
    dut.s_axis_valid.value = 0
    await Timer(1, unit="ns")
    assert int(dut.crc_value.value) == ref(data)
    assert int(dut.crc_valid.value) == 1


@cocotb.test()
async def t3_10_residue_and_errors(dut):
    """T3-10 frame plus appended CRC gives crc_ok; any single flipped bit does not"""
    await setup(dut)
    rng = random.Random(40)
    frames = []
    for _ in range(40):
        k = rng.randint(2, 10)
        n = NB * k - CRC_BYTES
        if n < 1:
            n += NB
        d = rand_data(rng, n)
        total = d + list(append(ref(d)))
        if len(total) % NB:
            continue
        frames.append(total)
    assert len(frames) >= 10
    pulses = await send(dut, frames, rng, 0.8, 0.8)
    assert len(pulses) == len(frames)
    assert all(ok == 1 and v == RESIDUE for v, ok in pulses), "good frames must pass"
    bad_frames = []
    for _ in range(500):
        f = list(rng.choice(frames))
        bit = rng.randrange(len(f) * 8)
        f[bit // 8] ^= 1 << (bit % 8)
        bad_frames.append(f)
    pulses = await send(dut, bad_frames, rng, 1.0, 1.0)
    assert len(pulses) == len(bad_frames)
    assert not any(ok for _, ok in pulses), "a single-bit error went undetected"


@cocotb.test()
async def t3_11_back_to_back(dut):
    """T3-11 one-word frames back to back with stalls: one pulse per frame, correct values"""
    await setup(dut)
    rng = random.Random(41)
    frames = [rand_data(rng, NB) for _ in range(500)]
    for pv, pr in ((1.0, 1.0), (0.7, 0.3)):
        pulses = await send(dut, frames, rng, pv, pr)
        assert len(pulses) == len(frames)
        assert [v for v, _ in pulses] == [ref(f) for f in frames]
