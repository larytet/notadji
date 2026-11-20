import random

import cocotb

from stream_tb import reset, run_stream, start_clock

W = 32


def make_words(n, rng, w=W):
    return [(rng.getrandbits(w), rng.random() < 0.1) for _ in range(n)]


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    start_clock(dut.clk)
    await reset(dut)


@cocotb.test()
async def t1_01_random_backpressure(dut):
    """T1-01 skid: random back-pressure, 5000 words, in order, no loss"""
    await setup(dut)
    rng = random.Random(1)
    words = make_words(5000, rng)
    for pv, pr in ((0.5, 0.5), (0.9, 0.3), (0.3, 0.9), (1.0, 0.5)):
        res = await run_stream(dut, words, pv, pr, W, rng)
        assert res.out == words, f"mismatch at p_valid={pv} p_ready={pr}"
        assert not res.violations, res.violations[:3]


@cocotb.test()
async def t1_02_full_throughput(dut):
    """T1-02 skid: always valid, always ready: one word per clock, no bubbles"""
    await setup(dut)
    rng = random.Random(2)
    words = make_words(1000, rng)
    res = await run_stream(dut, words, 1.0, 1.0, W, rng)
    assert res.out == words
    oc = res.out_cycles
    gaps = [b - a for a, b in zip(oc, oc[1:])]
    assert all(g == 1 for g in gaps), f"bubbles: {sorted(set(gaps))}"
    assert res.in_cycles[0] + 1 == oc[0], "latency should be 1 clock"


@cocotb.test()
async def t1_03_stall(dut):
    """T1-03 skid: sink stalls 50 clocks with source valid; ready falls; nothing lost"""
    await setup(dut)
    rng = random.Random(3)
    words = make_words(200, rng)
    seen_not_ready = []

    def extra(d, cyc):
        if 20 <= cyc <= 69 and int(d.s_axis_ready.value) == 0:
            seen_not_ready.append(cyc)

    res = await run_stream(dut, words, 1.0, 1.0, W, rng, stall_window=(20, 69), extra=extra)
    assert res.out == words
    assert seen_not_ready, "s_axis_ready never fell during the stall"
    assert not res.violations
