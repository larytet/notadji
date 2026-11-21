import random
import sys
from pathlib import Path

import cocotb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fw" / "32-codec"))
import sl2                                    # noqa: E402
from stream_tb import reset, run_stream, start_clock   # noqa: E402


def s16(v):
    return v - 65536 if v >= 32768 else v


async def setup(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "inverse"):
        getattr(dut, n).value = 0
    dut.m_axis_ready.value = 1
    start_clock(dut.clk)
    await reset(dut)


@cocotb.test()
async def t32_08_dct8x8(dut):
    """T32-08 dct8x8 equals the C model: random, constant, extreme blocks, both directions, random handshakes"""
    await setup(dut)
    rng = random.Random(3208)
    nrng = np.random.default_rng(8)
    blocks = []
    for _ in range(40):
        blocks.append((0, nrng.integers(-255, 256, (8, 8))))
    for v in (0, 255, -255, 1, -1):
        blocks.append((0, np.full((8, 8), v)))
    for _ in range(6):
        blocks.append((0, nrng.choice([-255, 255], (8, 8))))
    for _ in range(30):
        blocks.append((1, nrng.integers(-3000, 3001, (8, 8))))
    for _ in range(6):
        blocks.append((1, nrng.integers(-32768, 32768, (8, 8)) // 40))
    blocks.append((1, np.zeros((8, 8), int)))
    blocks.append((1, np.full((8, 8), 20000)))
    # forward results of extreme blocks as inverse inputs (realistic range)
    for _ in range(10):
        blocks.append((1, sl2.fwd(nrng.integers(-255, 256, (8, 8)))))
    rng.shuffle(blocks)
    words, starts, exp = [], {}, []
    for inv, x in blocks:
        x = np.asarray(x, dtype=np.int32)
        y = sl2.inv(x) if inv else sl2.fwd(x)
        starts[len(words)] = inv
        flat = x.reshape(64)
        words += [(int(v) & 0xFFFF, i == 63) for i, v in enumerate(flat)]
        exp += [(int(max(-32768, min(32767, v))) & 0xFFFF, i == 63) for i, v in enumerate(y.reshape(64))]

    def pre(d, cyc, idx):
        d.inverse.value = starts[idx] if idx in starts else rng.getrandbits(1)

    r = await run_stream(dut, words, 0.9, 0.8, 16, rng, expect_out=len(exp), pre=pre, max_cycles=400000)
    assert not r.violations
    assert r.out == exp, "differs from the C model"
    # clocks per block with always-valid source and sink
    n = 6
    ws = []
    for _ in range(n):
        x = nrng.integers(-255, 256, 64)
        ws += [(int(v) & 0xFFFF, i == 63) for i, v in enumerate(x)]
    r2 = await run_stream(dut, ws, 1.0, 1.0, 16, rng, expect_out=64 * n, pre=lambda d, c, i: setattr(d.inverse, "value", 0), max_cycles=100000)
    period = (r2.out_cycles[64 * (n - 1)] - r2.out_cycles[0]) / (n - 1)
    dut._log.info(f"dct8x8: {len(blocks)} blocks equal the C model; {period:.0f} clocks per block (always-ready), latency {r2.out_cycles[0] - r2.in_cycles[0]} clocks")
