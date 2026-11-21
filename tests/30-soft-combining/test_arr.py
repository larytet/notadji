import os
import random

import cocotb

from rxsim import CODES, decode, encode, reception, words
from stream_tb import reset, run_stream, start_clock

P = int(os.environ.get("P", "2"))


async def setup(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "code", "max_iter"):
        getattr(dut, n).value = 0
    dut.m_axis_ready.value = 1
    start_clock(dut.clk)
    await reset(dut)


def stream_case(ci_list, ebn0, mi, rng):
    wds, starts, frames = [], [], []
    for ci in ci_list:
        c = CODES[ci]
        msg = [rng.getrandbits(1) for _ in range(c["K"])]
        llr = reception(ci, encode(ci, msg), ebn0[ci], rng)
        starts.append((len(wds), ci))
        wds += [(v & 0xFF, i == len(llr) - 1) for i, v in enumerate(llr)]
        frames.append((ci, llr, msg))
    return wds, starts, frames


async def run_case(dut, ci_list, ebn0, mi, rng, pv, pr):
    wds, starts, frames = stream_case(ci_list, ebn0, mi, rng)
    start_at = {s: ci for s, ci in starts}
    nout = sum((CODES[ci]["K"] + 31) // 32 for ci in ci_list)
    infos = []
    state = dict(first=True)

    def pre(d, cyc, idx):
        if idx in start_at:
            d.code.value = start_at[idx]
            d.max_iter.value = mi

    def extra(d, cyc):
        if int(d.m_axis_valid.value) and int(d.m_axis_ready.value):
            if state["first"]:
                infos.append((int(d.m_ok.value), int(d.m_iters.value)))
            state["first"] = bool(int(d.m_axis_last.value))

    r = await run_stream(dut, wds, pv, pr, 8, rng, expect_out=nout, extra=extra, pre=pre, max_cycles=4000000)
    assert not r.violations
    # expected words and results in order
    exp_w, exp_i = [], []
    for ci, llr, msg in frames:
        bits, ok, it = decode(ci, llr, mi)
        exp_w += words(bits)
        exp_i.append((int(ok), it))
    got_w = [w for w, _ in r.out]
    assert got_w == exp_w, "decoded words differ from the model (order or content)"
    assert infos == exp_i, f"ok/iterations {infos} against {exp_i}"
    return r.out_cycles[-1] - r.in_cycles[0], frames


@cocotb.test()
async def t30_06_array_equal_and_throughput(dut):
    """T30-06 ordered results equal the model for mixed codes; clocks and throughput against P"""
    await setup(dut)
    rng = random.Random(3006 + P)
    ebn0 = {0: 1.8, 2: 3.2, 4: 1.5, 7: 3.5}
    # mixed codes, random handshakes
    cyc, frames = await run_case(dut, [0, 2, 4, 7, 4, 0, 7, 2, 0, 4], ebn0, 10, rng, 0.7, 0.6)
    dut._log.info(f"MIXED P={P}: 10 codewords in {cyc} clocks")
    # throughput: same code back-to-back, full-rate source and sink
    for ci, mi in ((4, 10), (4, 20), (7, 10), (7, 20), (0, 10)):
        n = 8
        cyc, frames = await run_case(dut, [ci] * n, {ci: ebn0[ci] + 0.5}, mi, rng, 1.0, 1.0)
        kbits = sum(CODES[c]["K"] for c, _, _ in frames)
        dut._log.info(f"THROUGHPUT P={P} code {ci} (N={CODES[ci]['N']} R={CODES[ci]['rate']}) max_iter {mi}: {n} codewords in {cyc} clocks = {cyc / n:.0f} clocks per codeword, {kbits / cyc * 200:.0f} Mbit/s information at 200 MHz")
