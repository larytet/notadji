import random

import cocotb

from cp_common import *
from stream_tb import run_stream


def make_in(rng, n, sel):
    return rand_symbol(rng, n + cp_len(n, sel))


@cocotb.test()
async def t4_06_backoff0(dut):
    """T4-06 every N and cp_sel, backoff 0: useful samples only"""
    await setup(dut, with_backoff=True)
    rng = random.Random(46)
    for n in sizes():
        for sel in (0, 1, 2):
            dut.fft_log2.value = n.bit_length() - 1
            dut.cp_sel.value = sel
            dut.backoff.value = 0
            ins = [make_in(rng, n, sel) for _ in range(20)]
            exp = flat([remove_model(s, n, sel) for s in ins])
            res = await run_stream(dut, flat(ins), 1.0, 1.0, W, rng, expect_out=len(exp))
            assert res.out == exp, f"N={n} sel={sel}"
            assert not res.violations


@cocotb.test()
async def t4_07_backoff(dut):
    """T4-07 backoff 1..L and above L (clamped)"""
    await setup(dut, with_backoff=True)
    rng = random.Random(47)
    maxb = (1 << (MAXL - 1)) - 1
    for n in sizes():
        for sel in (0, 1, 2):
            l = cp_len(n, sel)
            dut.fft_log2.value = n.bit_length() - 1
            dut.cp_sel.value = sel
            for back in sorted({1, max(1, l // 2), l, min(l + 1, maxb), maxb}):
                dut.backoff.value = back
                ins = [make_in(rng, n, sel) for _ in range(5)]
                exp = flat([remove_model(s, n, sel, back) for s in ins])
                res = await run_stream(dut, flat(ins), 1.0, 1.0, W, rng, expect_out=len(exp))
                assert res.out == exp, f"N={n} sel={sel} back={back}"


@cocotb.test()
async def t4_08_random_and_config(dut):
    """T4-08 random handshakes with per-symbol configuration and backoff changes"""
    await setup(dut, with_backoff=True)
    rng = random.Random(48)
    maxb = (1 << (MAXL - 1)) - 1
    cfgs, ins, exp_syms = [], [], []
    for _ in range(40):
        n = rng.choice(sizes())
        sel = rng.choice((0, 1, 2))
        back = rng.choice([0, 1, rng.randint(0, cp_len(n, sel)), maxb])
        cfgs.append((n.bit_length() - 1, sel, back))
        s = make_in(rng, n, sel)
        ins.append(s)
        exp_syms.append(remove_model(s, n, sel, back))
    exp = flat(exp_syms)
    pre = cfg_hook(dut, cfgs, [len(s) for s in ins], with_backoff=True)
    for pv, pr in ((1.0, 1.0), (0.6, 0.5), (0.9, 0.2)):
        res = await run_stream(dut, flat(ins), pv, pr, W, rng, expect_out=len(exp), pre=pre)
        assert res.out == exp, f"pv={pv} pr={pr}"
        assert not res.violations


@cocotb.test()
async def t4_09_bad_last(dut):
    """T4-09 wrong last position: err_len pulses, symbols still closed by the count"""
    await setup(dut, with_backoff=True)
    rng = random.Random(49)
    n = sizes()[0]
    sel = 2
    dut.fft_log2.value = n.bit_length() - 1
    dut.cp_sel.value = sel
    total = n + cp_len(n, sel)
    syms = [make_in(rng, n, sel) for _ in range(5)]
    words = []
    for k, s in enumerate(syms):
        for i, w in enumerate(s):
            last = (i == total - 1)
            if k == 1:
                last = (i == total - 4)
            if k == 3:
                last = False
            words.append((w, last))
    exp = flat([remove_model(s, n, sel) for s in syms])
    errs = []

    def extra(d, cyc):
        if int(d.err_len.value):
            errs.append(cyc)

    res = await run_stream(dut, words, 1.0, 1.0, W, rng, expect_out=len(exp), extra=extra)
    assert res.out == exp
    assert len(errs) == 3, f"err_len pulses {errs}"
