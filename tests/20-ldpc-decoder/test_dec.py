import math
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

import json
from pathlib import Path

from dec_model import CODES, decode, float_decode, noisy_llr, words
from stream_tb import reset, run_stream, start_clock

SNR = {0: 1.5, 1: 2.5, 2: 3.2, 3: 3.8, 4: 1.3, 5: 2.2, 6: 2.8, 7: 3.5}      # Eb/N0 giving a moderate frame error rate


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 1
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.code.value = 0
    dut.max_iter.value = 10
    start_clock(dut.clk)
    await reset(dut)


def to_u8(v):
    return v & 0xFF


async def decode_frames(dut, frames, pv=1.0, pr=1.0, seed=0):
    """frames: list of (code, llr list, max_iter). Returns list of (words, ok, iters, cycles)"""
    rng = random.Random(seed)
    results = []
    for k, (ci, llr, mi) in enumerate(frames):
        dut.code.value = ci
        dut.max_iter.value = mi
        n = len(llr)
        wds = [(to_u8(v), i == n - 1) for i, v in enumerate(llr)]
        nout = (CODES[ci]["K"] + 31) // 32
        info = {}

        def extra(d, cyc):
            if int(d.m_axis_valid.value) and int(d.m_axis_ready.value) and "ok" not in info:
                info["ok"] = int(d.m_ok.value)
                info["it"] = int(d.m_iters.value)

        res = await run_stream(dut, wds, pv, pr, 8, rng, expect_out=nout, extra=extra, max_cycles=3000000)
        results.append(([w for w, _ in res.out], info["ok"], info["it"], res.out_cycles[-1] - res.in_cycles[0], res))
    return results


def make_frames(rng, cases, mode="fixed"):
    frames, truth = [], []
    for ci, ebn0, mi in cases:
        c = CODES[ci]
        msg = [rng.getrandbits(1) for _ in range(c["K"])]
        cw, llr = noisy_llr(ci, msg, ebn0, rng, mode)
        frames.append((ci, llr, mi))
        truth.append(msg)
    return frames, truth


@cocotb.test()
async def t20_01_bit_exact(dut):
    """T20-01 equal to the bit-exact model for all codes at moderate and high noise"""
    await setup(dut)
    rng = random.Random(201)
    cases = []
    for ci in range(8):
        cases += [(ci, SNR[ci], 10), (ci, SNR[ci] - 2.0, 6)]
    frames, truth = make_frames(rng, cases)
    f2, t2 = make_frames(rng, [(ci, 9.0, 10) for ci in (0, 3, 4, 7)], mode="sigma")     # saturating inputs (stress)
    frames += f2
    truth += t2
    res = await decode_frames(dut, frames)
    oks = 0
    for (ci, llr, mi), (w, ok, it, cyc, r), msg in zip(frames, res, truth):
        bits, mok, mit = decode(ci, llr, mi)
        assert w == words(bits), f"code {ci}: decoded words differ from the model"
        assert (ok, it) == (int(mok), mit), f"code {ci}: ok/iters {(ok, it)} vs model {(int(mok), mit)}"
        oks += ok
    dut._log.info(f"BITEXACT {len(frames)} frames, {oks} converged")
    assert oks >= 8, f"only {oks} frames converged"


@cocotb.test()
async def t20_02_noise_free(dut):
    """T20-02 full-scale noise-free LLRs decode in at most 2 iterations; low noise decodes correctly"""
    await setup(dut)
    rng = random.Random(202)
    frames, truth = [], []
    for ci in range(8):
        c = CODES[ci]
        msg = [rng.getrandbits(1) for _ in range(c["K"])]
        cw, _ = noisy_llr(ci, msg, 20.0, rng)
        frames.append((ci, [(-127 if b else 127) for b in cw], 5))
        truth.append(msg)
    res = await decode_frames(dut, frames)
    for ci, ((w, ok, it, cyc, r), msg) in enumerate(zip(res, truth)):
        assert w == words(msg), f"code {ci}"
        assert ok == 1 and it <= 2, f"code {ci}: iterations {it}"
    for ci in range(8):
        f, t = make_frames(rng, [(ci, SNR[ci] + 3.0, 10)] * 3)
        res = await decode_frames(dut, f)
        for (w, ok, it, cyc, r), msg in zip(res, t):
            assert w == words(msg) and ok == 1, f"code {ci}: low-noise frame failed"


@cocotb.test()
async def t20_03_05_error_correction_and_limits(dut):
    """T20-03/05 error correction against the model, iteration limit and early termination"""
    await setup(dut)
    rng = random.Random(203)
    ok_dut = errs = float_ok = 0
    n_frames = 0
    for ci in (3, 4):
        frames, truth = make_frames(rng, [(ci, SNR[ci] - 0.4, 12)] * 12)
        res = await decode_frames(dut, frames)
        for (ci_, llr, mi), (w, ok, it, cyc, r), msg in zip(frames, res, truth):
            bits, mok, mit = decode(ci_, llr, mi)
            assert w == words(bits) and ok == int(mok) and it == mit
            fb, fok, fit = float_decode(ci_, llr, mi)
            ok_dut += int(w == words(msg))
            float_ok += int(fb == msg)
            n_frames += 1
            assert it <= mi
    dut._log.info(f"CORRECTION near the waterfall: DUT correct {ok_dut} of {n_frames}, floating-point reference correct {float_ok} of {n_frames}")
    assert ok_dut >= float_ok - 3, f"the fixed-point decoder corrects {ok_dut} frames, the floating-point reference {float_ok}"
    assert ok_dut >= 1
    # heavy noise: stops at the limit, not ok
    frames, truth = make_frames(rng, [(3, 0.0, 4)])
    res = await decode_frames(dut, frames)
    assert res[0][1] == 0 and res[0][2] == 4
    # light noise stops early
    frames, truth = make_frames(rng, [(3, 8.0, 20)])
    res = await decode_frames(dut, frames)
    assert res[0][1] == 1 and res[0][2] <= 3, f"iterations {res[0][2]}"


@cocotb.test()
async def t20_06_sequence_and_handshakes(dut):
    """T20-06 several codewords with different codes and random handshakes; wrong last"""
    await setup(dut)
    rng = random.Random(206)
    cases = [(3, 3.8, 10), (0, 1.8, 10), (7, 3.5, 10), (3, 3.8, 10), (4, 1.5, 8), (1, 3.0, 8)]
    frames, truth = make_frames(rng, cases)
    res = await decode_frames(dut, frames, pv=0.6, pr=0.5, seed=4)
    for (ci, llr, mi), (w, ok, it, cyc, r) in zip(frames, res):
        bits, mok, mit = decode(ci, llr, mi)
        assert w == words(bits) and (ok, it) == (int(mok), mit)
        assert not r.violations
    # wrong last: early last flagged, the decoder still closes by the count
    errs = []

    def extra(d, cyc):
        if int(d.err_len.value):
            errs.append(cyc)

    ci, llr, mi = frames[0]
    n = len(llr)
    dut.code.value = ci
    dut.max_iter.value = 5
    wds = [(to_u8(v), i == n - 5) for i, v in enumerate(llr)]
    r = await run_stream(dut, wds, 1.0, 1.0, 8, rng, expect_out=(CODES[ci]["K"] + 31) // 32, extra=extra, max_cycles=3000000)
    assert len(errs) >= 1
    res = await decode_frames(dut, [frames[1]])
    bits, mok, mit = decode(*frames[1])
    assert res[0][0] == words(bits)


@cocotb.test()
async def t20_07_cycles(dut):
    """T20-07 clocks per codeword and information throughput at 200 MHz"""
    await setup(dut)
    rng = random.Random(207)
    for ci in range(8):
        c = CODES[ci]
        frames, truth = make_frames(rng, [(ci, SNR[ci] + 0.3, 10)] * 2)
        res = await decode_frames(dut, frames)
        for (w, ok, it, cyc, r), (cc, llr, mi) in list(zip(res, frames))[1:]:
            tp = c["K"] / cyc * 200
            dut._log.info(f"CYCLES code {ci} N={c['N']} R={c['rate']}: {cyc} clocks, {it} iterations, {tp:.0f} Mbit/s at 200 MHz (per iteration {(cyc - c['N'] - (c['K'] + 31) // 32) / max(it, 1):.0f} clocks)")


@cocotb.test()
async def t20_08_saturated_frame_regression(dut):
    """T20-08 the frame with saturated channel LLRs that an 8-bit posterior decodes to the complement codeword"""
    await setup(dut)
    d = json.loads((Path(__file__).resolve().parent / "data" / "sat_frame.json").read_text())
    res = await decode_frames(dut, [(d["code"], d["llr"], 20)])
    w, ok, it, cyc, r = res[0]
    assert w == words(d["msg"]), "the saturated-input frame must decode to the sent message"
    assert ok == 1 and it <= 4, f"converged={ok} after {it} iterations"
