import os
import random

from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

from stream_tb import reset, start_clock

W = int(os.environ.get("W", "32"))
MAXL = int(os.environ.get("MAXL", "9"))
SHIFT = {0: 4, 1: 3, 2: 2}


def sizes():
    return [1 << k for k in range(6, MAXL + 1)]


def cp_len(n, sel):
    return n >> SHIFT[sel]


def rand_symbol(rng, n):
    return [rng.getrandbits(W) for _ in range(n)]


def insert_model(sym, sel):
    n = len(sym)
    l = cp_len(n, sel)
    return sym[n - l:] + sym


def remove_model(sym_cp, n, sel, back=0):
    l = cp_len(n, sel)
    back = min(back, l)
    return sym_cp[l - back: l - back + n]


def flat(frames):
    """list of word lists -> list of (word, last)"""
    return [(w, i == len(f) - 1) for f in frames for i, w in enumerate(f)]


async def setup(dut, with_backoff=False):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.fft_log2.value = 6
    dut.cp_sel.value = 0
    if with_backoff:
        dut.backoff.value = 0
    start_clock(dut.clk)
    await reset(dut)


def cfg_hook(dut, cfgs, lens, with_backoff=False):
    """pre-hook: set the configuration of the symbol that contains word idx.
    cfgs: list of (log2, sel[, backoff]) per symbol; lens: input words per symbol."""
    bounds = []
    acc = 0
    for l in lens:
        bounds.append(acc)
        acc += l

    def pre(d, cyc, idx):
        s = 0
        for i, b in enumerate(bounds):
            if idx >= b:
                s = i
        c = cfgs[min(s, len(cfgs) - 1)]
        d.fft_log2.value = c[0]
        d.cp_sel.value = c[1]
        if with_backoff:
            d.backoff.value = c[2]

    return pre
