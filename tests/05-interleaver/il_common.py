import os
import random

from stream_tb import reset, start_clock

W = int(os.environ.get("W", "1"))
MAXN = int(os.environ.get("MAXN", "1024"))
DEINT = int(os.environ.get("DEINT", "0"))


def pos(k, n):
    R = (n + 15) // 16
    full = ((n - 1) % 16) + 1
    r, c = divmod(k, 16)
    base = c * R if c < full else full * R + (c - full) * (R - 1)
    return base + r


def interleave(block):
    n = len(block)
    out = [0] * n
    for k, x in enumerate(block):
        out[pos(k, n)] = x
    return out


def deinterleave(block):
    n = len(block)
    return [block[pos(k, n)] for k in range(n)]


def model(block):
    return deinterleave(block) if DEINT else interleave(block)


def rand_block(rng, n):
    return [rng.getrandbits(W) for _ in range(n)]


def flat(blocks):
    return [(x, i == len(b) - 1) for b in blocks for i, x in enumerate(b)]


def n_list():
    base = [1, 2, 3, 15, 16, 17, 31, 32, 33, 47, 48, 64, 100, 242, 255, 256, 257, 484, 968, 1000, 1024, MAXN]
    return sorted({n for n in base if 1 <= n <= MAXN})


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.n.value = 16
    start_clock(dut.clk)
    await reset(dut)


def n_hook(dut, ns):
    bounds = []
    acc = 0
    for n in ns:
        bounds.append(acc)
        acc += n

    def pre(d, cyc, idx):
        s = 0
        for i, b in enumerate(bounds):
            if idx >= b:
                s = i
        d.n.value = ns[min(s, len(ns) - 1)]

    return pre
