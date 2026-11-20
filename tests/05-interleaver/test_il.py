import random

import cocotb

from il_common import *
from stream_tb import run_stream


@cocotb.test()
async def t5_01_model_selfcheck(dut):
    """T5-01 pos() is a bijection for n = 1..4096 and equals the 802.11 formula for multiples of 16"""
    for n in range(1, 4097):
        seen = bytearray(n)
        for k in range(n):
            p = pos(k, n)
            assert 0 <= p < n and not seen[p], f"n={n} k={k} p={p}"
            seen[p] = 1
        if n % 16 == 0:
            assert all(pos(k, n) == (n // 16) * (k % 16) + k // 16 for k in range(n))


@cocotb.test()
async def t5_02_03_many_n(dut):
    """T5-02/03 many block lengths at full speed equal the model"""
    await setup(dut)
    rng = random.Random(52)
    for n in n_list():
        dut.n.value = n
        blocks = [rand_block(rng, n) for _ in range(3)]
        exp = flat([model(b) for b in blocks])
        res = await run_stream(dut, flat(blocks), 1.0, 1.0, W, rng, expect_out=len(exp))
        assert res.out == exp, f"n={n}"
        assert not res.violations


@cocotb.test()
async def t5_05_random_handshakes(dut):
    """T5-05 random valid and ready patterns"""
    await setup(dut)
    rng = random.Random(55)
    for n in [17, 100, 242, 484]:
        if n > MAXN:
            continue
        dut.n.value = n
        blocks = [rand_block(rng, n) for _ in range(4)]
        exp = flat([model(b) for b in blocks])
        for pv, pr in ((0.5, 0.5), (0.9, 0.3), (0.3, 0.9)):
            res = await run_stream(dut, flat(blocks), pv, pr, W, rng, expect_out=len(exp))
            assert res.out == exp, f"n={n} pv={pv} pr={pr}"
            assert not res.violations


@cocotb.test()
async def t5_06_n_per_block(dut):
    """T5-06 block length changes at every block, aligned with its first element"""
    await setup(dut)
    rng = random.Random(56)
    ns = [rng.choice(n_list()) for _ in range(30)]
    blocks = [rand_block(rng, n) for n in ns]
    exp = flat([model(b) for b in blocks])
    pre = n_hook(dut, ns)
    for pv, pr in ((1.0, 1.0), (0.7, 0.5)):
        res = await run_stream(dut, flat(blocks), pv, pr, W, rng, expect_out=len(exp), pre=pre)
        assert res.out == exp, f"pv={pv} pr={pr}"


@cocotb.test()
async def t5_07_throughput(dut):
    """T5-07 steady input period equals n clocks per block"""
    await setup(dut)
    rng = random.Random(57)
    for n in [16, 17, 100, 242, MAXN]:
        if n > MAXN:
            continue
        dut.n.value = n
        nb = 12
        blocks = [rand_block(rng, n) for _ in range(nb)]
        exp = flat([model(b) for b in blocks])
        res = await run_stream(dut, flat(blocks), 1.0, 1.0, W, rng, expect_out=len(exp))
        starts = [res.in_cycles[i * n] for i in range(nb)]
        period = (starts[-1] - starts[nb // 2]) / (nb - 1 - nb // 2)
        assert abs(period - n) <= 1.0, f"n={n}: period {period}"


@cocotb.test()
async def t5_08_bad_last(dut):
    """T5-08 wrong last position: err_len pulses, blocks still closed by the count"""
    await setup(dut)
    rng = random.Random(58)
    n = 32
    dut.n.value = n
    blocks = [rand_block(rng, n) for _ in range(5)]
    words = []
    for k, b in enumerate(blocks):
        for i, x in enumerate(b):
            last = (i == n - 1)
            if k == 1:
                last = (i == n - 4)
            if k == 3:
                last = False
            words.append((x, last))
    exp = flat([model(b) for b in blocks])
    errs = []

    def extra(d, cyc):
        if int(d.err_len.value):
            errs.append(cyc)

    res = await run_stream(dut, words, 1.0, 1.0, W, rng, expect_out=len(exp), extra=extra)
    assert res.out == exp
    assert len(errs) == 3, f"err_len pulses {errs}"


@cocotb.test()
async def t5_09_clamping(dut):
    """T5-09 n = 0 acts as 1; n above MAX_N acts as MAX_N"""
    await setup(dut)
    rng = random.Random(59)
    dut.n.value = 0
    blocks = [rand_block(rng, 1) for _ in range(4)]
    exp = flat([model(b) for b in blocks])
    res = await run_stream(dut, flat(blocks), 1.0, 1.0, W, rng, expect_out=len(exp))
    assert res.out == exp, "n=0"
    nbits = (MAXN).bit_length()
    dut.n.value = (1 << nbits) - 1 if (1 << nbits) - 1 > MAXN else MAXN
    blocks = [rand_block(rng, MAXN) for _ in range(2)]
    exp = flat([model(b) for b in blocks])
    res = await run_stream(dut, flat(blocks), 1.0, 1.0, W, rng, expect_out=len(exp))
    assert res.out == exp, "n above MAX_N"
