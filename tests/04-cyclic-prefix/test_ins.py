import random

import cocotb

from cp_common import *
from stream_tb import run_stream


@cocotb.test()
async def t4_01_all_sizes(dut):
    """T4-01 every N and cp_sel at full speed equals the model"""
    await setup(dut)
    rng = random.Random(41)
    for n in sizes():
        for sel in (0, 1, 2):
            dut.fft_log2.value = n.bit_length() - 1
            dut.cp_sel.value = sel
            syms = [rand_symbol(rng, n) for _ in range(20)]
            exp = flat([insert_model(s, sel) for s in syms])
            res = await run_stream(dut, flat(syms), 1.0, 1.0, W, rng, expect_out=len(exp))
            assert res.out == exp, f"N={n} sel={sel}"
            assert not res.violations


@cocotb.test()
async def t4_02_random_handshakes(dut):
    """T4-02 random valid and ready patterns"""
    await setup(dut)
    rng = random.Random(42)
    for n in sizes():
        for sel in (0, 1, 2):
            dut.fft_log2.value = n.bit_length() - 1
            dut.cp_sel.value = sel
            syms = [rand_symbol(rng, n) for _ in range(6)]
            exp = flat([insert_model(s, sel) for s in syms])
            for pv, pr in ((0.5, 0.5), (0.9, 0.3), (0.3, 0.9)):
                res = await run_stream(dut, flat(syms), pv, pr, W, rng, expect_out=len(exp))
                assert res.out == exp, f"N={n} sel={sel} pv={pv} pr={pr}"
                assert not res.violations


@cocotb.test()
async def t4_03_config_per_symbol(dut):
    """T4-03 the configuration present at the first sample of each symbol is the one used"""
    await setup(dut)
    rng = random.Random(43)
    cfgs = []
    syms = []
    for _ in range(40):
        n = rng.choice(sizes())
        sel = rng.choice((0, 1, 2))
        cfgs.append((n.bit_length() - 1, sel))
        syms.append((rand_symbol(rng, n), sel))
    exp = flat([insert_model(s, sel) for s, sel in syms])
    pre = cfg_hook(dut, cfgs, [len(s) for s, _ in syms])
    for pv, pr in ((1.0, 1.0), (0.7, 0.5)):
        res = await run_stream(dut, flat([s for s, _ in syms]), pv, pr, W, rng, expect_out=len(exp), pre=pre)
        assert res.out == exp, f"pv={pv} pr={pr}"


@cocotb.test()
async def t4_04_throughput(dut):
    """T4-04 sustained input period equals N+L clocks (output-limited), no deadlock"""
    await setup(dut)
    rng = random.Random(44)
    for n in sizes():
        for sel in (0, 1, 2):
            dut.fft_log2.value = n.bit_length() - 1
            dut.cp_sel.value = sel
            nsym = 24
            syms = [rand_symbol(rng, n) for _ in range(nsym)]
            exp = flat([insert_model(s, sel) for s in syms])
            res = await run_stream(dut, flat(syms), 1.0, 1.0, W, rng, expect_out=len(exp))
            starts = [res.in_cycles[i * n] for i in range(nsym)]
            period = (starts[-1] - starts[nsym // 2]) / (nsym - 1 - nsym // 2)
            want = n + cp_len(n, sel)
            assert abs(period - want) <= 1.0, f"N={n} sel={sel}: period {period}, expected {want}"


@cocotb.test()
async def t4_05_bad_last(dut):
    """T4-05 wrong last position: err_len pulses, symbols still closed by the count"""
    await setup(dut)
    rng = random.Random(45)
    n = sizes()[0]
    dut.fft_log2.value = n.bit_length() - 1
    dut.cp_sel.value = 1
    good = [rand_symbol(rng, n) for _ in range(3)]
    bad_early = rand_symbol(rng, n)
    bad_missing = rand_symbol(rng, n)
    syms = [good[0], bad_early, good[1], bad_missing, good[2]]
    words = []
    for k, s in enumerate(syms):
        for i, w in enumerate(s):
            last = (i == n - 1)
            if s is bad_early:
                last = (i == n - 4)
            if s is bad_missing:
                last = False
            words.append((w, last))
    exp = flat([insert_model(s, 1) for s in syms])
    errs = []

    def extra(d, cyc):
        if int(d.err_len.value):
            errs.append(cyc)

    res = await run_stream(dut, words, 1.0, 1.0, W, rng, expect_out=len(exp), extra=extra)
    assert res.out == exp
    # early last: mismatch at the early beat and at the closing beat; missing last: one mismatch
    assert len(errs) == 3, f"err_len pulses {errs}"
