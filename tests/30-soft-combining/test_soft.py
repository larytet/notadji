import random

import cocotb
from cocotb.triggers import FallingEdge, Timer

from rxsim import CODES, combine, decode, encode, reception, words
from stream_tb import reset, run_stream, start_clock


async def setup(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "mode", "code", "key_seq", "key_cw", "max_iter",
              "drop_seq_valid", "drop_seq", "drop_all"):
        getattr(dut, n).value = 0
    dut.m_axis_ready.value = 1
    start_clock(dut.clk)
    await reset(dut)


async def send(dut, ci, llr, seq, cw, maxit, rng, pv=0.9, pr=0.8, mode=1):
    dut.mode.value = mode
    dut.code.value = ci
    dut.max_iter.value = maxit
    dut.key_seq.value = seq
    dut.key_cw.value = cw
    n = len(llr)
    wds = [(v & 0xFF, i == n - 1) for i, v in enumerate(llr)]
    nout = (CODES[ci]["K"] + 31) // 32
    info = {}

    def extra(d, cyc):
        if int(d.m_axis_valid.value) and int(d.m_axis_ready.value) and "ok" not in info:
            info["ok"] = int(d.m_ok.value)
            info["it"] = int(d.m_iters.value)

    r = await run_stream(dut, wds, pv, pr, 8, rng, expect_out=nout, extra=extra, max_cycles=3000000)
    assert not r.violations
    return [w for w, _ in r.out], info["ok"], info["it"], r.out_cycles[-1] - r.in_cycles[0]


@cocotb.test()
async def t30_04_integration(dut):
    """T30-04 combiner + real decoder: frames that fail alone twice are decoded from the combination"""
    await setup(dut)
    rng = random.Random(3004)
    stats = dict(frames=0, first_ok=0, second_combined_ok=0, alone_fail_twice_combined_ok=0, still_fail=0)
    cases = [(0, 1.0, 10), (0, 1.0, 20), (7, 3.4, 10), (0, 0.8, 20), (0, 1.2, 10), (7, 3.4, 20)] * 2
    seq = 0
    for ci, ebn0, mi in cases:
        c = CODES[ci]
        msg = [rng.getrandbits(1) for _ in range(c["K"])]
        cw = encode(ci, msg)
        l1 = reception(ci, cw, ebn0, rng)
        l2 = reception(ci, cw, ebn0, rng)
        seq += 1
        stats["frames"] += 1
        w, ok, it, cyc = await send(dut, ci, l1, seq, 0, mi, rng)
        bits, mok, mit = decode(ci, l1, mi)
        assert (w, ok, it) == (words(bits), int(mok), mit), "first reception differs from the model"
        if ok:
            stats["first_ok"] += 1
            assert bits == msg
            continue
        w, ok, it, cyc = await send(dut, ci, l2, seq, 0, mi, rng)
        lc = combine(l1, l2)
        bits, mok, mit = decode(ci, lc, mi)
        assert (w, ok, it) == (words(bits), int(mok), mit), "combined decode differs from the model"
        b2, ok2, _ = decode(ci, l2, mi)
        if ok:
            assert bits == msg
            stats["second_combined_ok"] += 1
            if not ok2:
                stats["alone_fail_twice_combined_ok"] += 1
        else:
            stats["still_fail"] += 1
    dut._log.info(f"INTEGRATION {stats} hits {int(dut.n_hit.value)} misses {int(dut.n_miss.value)}")
    assert stats["alone_fail_twice_combined_ok"] >= 2, stats
    # all decoded entries freed, failures retained
    assert int(dut.occupancy.value) == stats["still_fail"] + 0 or int(dut.occupancy.value) <= stats["still_fail"] + stats["frames"]


@cocotb.test()
async def t30_04b_bypass_and_drop(dut):
    """bypass gives the plain decoder result; drop_seq removes the retained entry"""
    await setup(dut)
    rng = random.Random(30041)
    ci = 0
    c = CODES[ci]
    msg = [rng.getrandbits(1) for _ in range(c["K"])]
    cw = encode(ci, msg)
    l1 = reception(ci, cw, 0.6, rng)
    l2 = reception(ci, cw, 0.6, rng)
    # bypass: the second reception alone
    w, ok, it, _ = await send(dut, ci, l1, 5, 0, 10, rng, mode=0)
    assert (w, ok) == (words(decode(ci, l1, 10)[0]), int(decode(ci, l1, 10)[1]))
    w, ok, it, _ = await send(dut, ci, l2, 5, 0, 10, rng, mode=0)
    assert (w, ok) == (words(decode(ci, l2, 10)[0]), int(decode(ci, l2, 10)[1]))
    assert int(dut.occupancy.value) == 0
    # combine mode: retain (first reception fails at this SNR), drop, then the second is alone again
    hits0 = int(dut.n_hit.value)
    await send(dut, ci, l1, 6, 0, 10, rng)
    if not decode(ci, l1, 10)[1]:
        assert int(dut.occupancy.value) == 1
        dut.drop_seq_valid.value = 1
        dut.drop_seq.value = 6
        await FallingEdge(dut.clk)
        dut.drop_seq_valid.value = 0
        await FallingEdge(dut.clk)
        assert int(dut.occupancy.value) == 0
        w, ok, it, _ = await send(dut, ci, l2, 6, 0, 10, rng)
        assert (w, ok) == (words(decode(ci, l2, 10)[0]), int(decode(ci, l2, 10)[1]))
        assert int(dut.n_hit.value) == hits0
