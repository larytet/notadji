import itertools
import math
import random

import cocotb
from cocotb.triggers import Timer

from stream_tb import reset, run_stream, start_clock

S = 4096
NBITS = {0: 1, 1: 2, 2: 4, 3: 6, 4: 8, 5: 1, 6: 1, 7: 1}   # reserved values act as BPSK


def mag(m, j):
    M = 1 << m
    unit = S / math.sqrt(2 * (M * M - 1) / 3)
    return int(math.floor((2 * j + 1) * unit + 0.5))


def axis_level(gbits):
    """gbits: Gray bits, most significant first -> signed amplitude (rounded, RMS 4096)"""
    m = len(gbits)
    b = 0
    prev = 0
    for g in gbits:
        prev ^= g
        b = (b << 1) | prev
    level = 2 * b - ((1 << m) - 1)
    j = (abs(level) - 1) // 2
    return mag(m, j) if level > 0 else -mag(m, j)


def model_point(mod, word):
    if mod not in (1, 2, 3, 4):
        return (S if word & 1 else -S), 0
    nb = NBITS[mod]
    m = nb // 2
    bits = [(word >> i) & 1 for i in range(nb)]       # bit 0 first in time
    return axis_level(bits[:m]), axis_level(bits[m:])


def pack(i, q):
    return ((q & 0xFFFF) << 16) | (i & 0xFFFF)


def unpack(w):
    def s(x):
        return x - 0x10000 if x & 0x8000 else x
    return s(w & 0xFFFF), s((w >> 16) & 0xFFFF)


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.mod.value = 0
    start_clock(dut.clk)
    await reset(dut)


async def poke(dut, mod, word):
    dut.mod.value = mod
    dut.s_axis_data.value = word
    dut.s_axis_valid.value = 1
    dut.m_axis_ready.value = 1
    await Timer(1, unit="ns")
    return unpack(int(dut.m_axis_data.value))


@cocotb.test()
async def t6_01_exhaustive(dut):
    """T6-01 every input word 0..255 for every mod 0..7 equals the model"""
    await setup(dut)
    for mod in range(8):
        for word in range(256):
            got = await poke(dut, mod, word)
            assert got == model_point(mod, word), f"mod={mod} word={word:#04x} got {got} want {model_point(mod, word)}"


@cocotb.test()
async def t6_02_gray(dut):
    """T6-02 nearest neighbours differ in exactly one bit (checked on the DUT output)"""
    await setup(dut)
    for mod in (1, 2, 3, 4):
        nb = NBITS[mod]
        pts = {}
        for word in range(1 << nb):
            pts[word] = await poke(dut, mod, word)
        dmin = min(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in itertools.combinations(pts.values(), 2))
        for wa, wb in itertools.combinations(pts, 2):
            a, b = pts[wa], pts[wb]
            if abs(a[0] - b[0]) + abs(a[1] - b[1]) <= dmin * 1.02 and (a[0] == b[0] or a[1] == b[1]):
                assert bin(wa ^ wb).count("1") == 1, f"mod={mod}: {wa:#x} and {wb:#x} are neighbours but differ in several bits"
        assert len(set(pts.values())) == len(pts), "constellation points must be distinct"


@cocotb.test()
async def t6_03_power(dut):
    """T6-03 mean power equals 4096^2 within 1% for every modulation"""
    await setup(dut)
    for mod in (0, 1, 2, 3, 4):
        nb = NBITS[mod]
        tot = 0
        for word in range(1 << nb):
            i, q = await poke(dut, mod, word)
            tot += i * i + q * q
        mean = tot / (1 << nb)
        assert abs(mean / (S * S) - 1) < 0.01, f"mod={mod}: mean power {mean / (S * S):.4f}"


@cocotb.test()
async def t6_04_05_stream(dut):
    """T6-04/05 per-beat modulation changes, random handshakes, last pass-through"""
    await setup(dut)
    rng = random.Random(64)
    n = 3000
    mods = [rng.randrange(8) for _ in range(n)]
    datas = [rng.getrandbits(8) for _ in range(n)]
    lasts = [rng.random() < 0.1 for _ in range(n)]
    words = list(zip(datas, lasts))
    exp = [(pack(*model_point(m, d)), l) for m, d, l in zip(mods, datas, lasts)]

    def pre(d, cyc, idx):
        d.mod.value = mods[min(idx, n - 1)]

    for pv, pr in ((1.0, 1.0), (0.5, 0.5), (0.9, 0.2)):
        res = await run_stream(dut, words, pv, pr, 8, rng, expect_out=n, pre=pre)
        assert res.out == exp, f"pv={pv} pr={pr}"
        assert not res.violations


@cocotb.test()
async def t6_05b_zero_latency(dut):
    """T6-05 valid and ready are combinational pass-through"""
    await setup(dut)
    for v, r in itertools.product((0, 1), (0, 1)):
        dut.s_axis_valid.value = v
        dut.m_axis_ready.value = r
        await Timer(1, unit="ns")
        assert int(dut.m_axis_valid.value) == v and int(dut.s_axis_ready.value) == r


@cocotb.test()
async def t6_06_tables(dut):
    """T6-06 amplitude magnitudes equal round((2j+1) x 4096 / sqrt(2(M^2-1)/3))"""
    await setup(dut)
    for mod, m in ((1, 1), (2, 2), (3, 3), (4, 4)):
        seen = set()
        for word in range(1 << (2 * m)):
            i, q = await poke(dut, mod, word)
            seen.add(abs(i))
            seen.add(abs(q))
        want = {mag(m, j) for j in range(1 << (m - 1))}
        assert seen == want, f"mod={mod}: {sorted(seen)} vs {sorted(want)}"
