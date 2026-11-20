import random

import cocotb

from stream_tb import reset, run_stream, start_clock


@cocotb.test()
async def t14_07_serializer(dut):
    """T14-07 LLR stream order, counts, last flag, back-pressure"""
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 1
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.s_nbits.value = 1
    start_clock(dut.clk)
    await reset(dut)
    rng = random.Random(147)
    beats = []
    for _ in range(300):
        nb = rng.choice([1, 2, 4, 6, 8])
        data = [rng.randrange(256) for _ in range(8)]
        beats.append((nb, data, rng.random() < 0.2))
    words = [(sum(d << (8 * k) for k, d in enumerate(data)), last) for nb, data, last in beats]
    exp = []
    for nb, data, last in beats:
        for k in range(nb):
            exp.append((data[k], int(last and k == nb - 1)))

    def pre(d, cyc, idx):
        d.s_nbits.value = beats[min(idx, len(beats) - 1)][0]

    for pv, pr in ((1.0, 1.0), (0.6, 0.5), (0.9, 0.2)):
        res = await run_stream(dut, words, pv, pr, 64, rng, expect_out=len(exp), pre=pre)
        assert res.out == exp, f"pv={pv} pr={pr}"
        assert not res.violations
