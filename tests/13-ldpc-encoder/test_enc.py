import random

import cocotb
from cocotb.triggers import ClockCycles

from ldpc_py import *
from stream_tb import reset, run_stream, start_clock

ROWS = [h_rows(c) for c in CODES]


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.code.value = 0
    start_clock(dut.clk)
    await reset(dut)


def frames_in(msgs):
    """msgs: list of (code_index, K-bit int) -> list of (word, last)"""
    out = []
    for ci, m in msgs:
        w = to_words(m, CODES[ci]["K"])
        out += [(x, i == len(w) - 1) for i, x in enumerate(w)]
    return out


def code_hook(dut, msgs):
    bounds, acc = [], 0
    for ci, m in msgs:
        bounds.append(acc)
        acc += (CODES[ci]["K"] + 31) // 32

    def pre(d, cyc, idx):
        s = 0
        for i, b in enumerate(bounds):
            if idx >= b:
                s = i
        d.code.value = msgs[min(s, len(msgs) - 1)][0]

    return pre


async def encode(dut, msgs, pv=1.0, pr=1.0, seed=0):
    rng = random.Random(seed)
    words = frames_in(msgs)
    exp_out = sum((CODES[ci]["N"] + 31) // 32 for ci, _ in msgs)
    res = await run_stream(dut, words, pv, pr, 32, rng, expect_out=exp_out, pre=code_hook(dut, msgs))
    cws, cur = [], []
    for w, last in res.out:
        cur.append(w)
        if last:
            cws.append(cur)
            cur = []
    return res, cws


def rand_msg(rng, ci):
    return rng.getrandbits(CODES[ci]["K"])


@cocotb.test()
async def t13_01_02_parity_and_framing(dut):
    """T13-01/02 H c = 0 for all codes; systematic; framing"""
    await setup(dut)
    rng = random.Random(131)
    for ci, c in enumerate(CODES):
        msgs = [(ci, rand_msg(rng, ci)) for _ in range(20)]
        res, cws = await encode(dut, msgs, seed=ci)
        assert len(cws) == 20
        for (_, m), words in zip(msgs, cws):
            n, k = c["N"], c["K"]
            assert len(words) == (n + 31) // 32
            cw = from_words(words)
            assert cw >> n == 0, "bits above N must be zero"
            assert cw & ((1 << k) - 1) == m, f"code {ci}: not systematic"
            assert check(ROWS[ci], cw), f"code {ci} (N={n}, rate {c['rate']}): parity check failed"


@cocotb.test()
async def t13_03_standard_code_alist(dut):
    """T13-03 the 802.11n N=648 rate 5/6 codewords satisfy the matrix read from the AFF3CT alist"""
    await setup(dut)
    rng = random.Random(133)
    n, arows = alist_rows()
    assert n == 648 and len(arows) == 108
    msgs = [(3, rand_msg(rng, 3)) for _ in range(40)]
    res, cws = await encode(dut, msgs)
    for (_, m), words in zip(msgs, cws):
        cw = from_words(words)
        assert check(arows, cw), "codeword does not satisfy the alist parity-check matrix"
        assert cw & ((1 << 540) - 1) == m


@cocotb.test()
async def t13_04_linearity(dut):
    """T13-04 enc(a) ^ enc(b) = enc(a ^ b); zero message gives the zero codeword"""
    await setup(dut)
    rng = random.Random(134)
    for ci in range(len(CODES)):
        a, b = rand_msg(rng, ci), rand_msg(rng, ci)
        res, cws = await encode(dut, [(ci, a), (ci, b), (ci, a ^ b), (ci, 0)])
        ca, cb, cab, cz = (from_words(w) for w in cws)
        assert ca ^ cb == cab, f"code {ci}: not linear"
        assert cz == 0


@cocotb.test()
async def t13_05_mixed_and_handshakes(dut):
    """T13-05 different code per codeword, random handshakes, back to back"""
    await setup(dut)
    rng = random.Random(135)
    msgs = [(ci, rand_msg(rng, ci)) for ci in [rng.randrange(8) for _ in range(24)]]
    for pv, pr in ((1.0, 1.0), (0.6, 0.5), (0.9, 0.2)):
        res, cws = await encode(dut, msgs, pv, pr, seed=7)
        assert len(cws) == len(msgs)
        for (ci, m), words in zip(msgs, cws):
            cw = from_words(words)
            assert cw & ((1 << CODES[ci]["K"]) - 1) == m and check(ROWS[ci], cw), f"pv={pv} pr={pr} code {ci}"
        assert not res.violations


@cocotb.test()
async def t13_06_cycles(dut):
    """T13-06 clocks per codeword with an always-ready sink"""
    await setup(dut)
    rng = random.Random(136)
    worst = 0
    for ci, c in enumerate(CODES):
        msgs = [(ci, rand_msg(rng, ci)) for _ in range(8)]
        res, cws = await encode(dut, msgs)
        nin = (c["K"] + 31) // 32
        nout = (c["N"] + 31) // 32
        starts = [res.in_cycles[i * nin] for i in range(8)]
        period = (starts[-1] - starts[2]) / 5
        dut._log.info(f"CYCLES code {ci} N={c['N']} rate {c['rate']}: {period:.1f} clocks per codeword, {c['K'] / period * 200:.0f} Mbit/s at 200 MHz")
        worst = max(worst, period)
        assert period <= 300, f"code {ci}: {period} clocks per codeword"


@cocotb.test()
async def t13_07_bad_last(dut):
    """T13-07 wrong last position: err_len pulses, codeword closed by the count, next one correct"""
    await setup(dut)
    rng = random.Random(137)
    ci = 3
    k = CODES[ci]["K"]
    nin = (k + 31) // 32
    a = rand_msg(rng, ci)
    b = rand_msg(rng, ci)
    wa = to_words(a, k)
    wb = to_words(b, k)
    words = [(w, i == nin - 4) for i, w in enumerate(wa)] + [(w, i == nin - 1) for i, w in enumerate(wb)]
    errs = []

    def extra(d, cyc):
        if int(d.err_len.value):
            errs.append(cyc)

    dut.code.value = ci
    res = await run_stream(dut, words, 1.0, 1.0, 32, rng, expect_out=2 * ((CODES[ci]["N"] + 31) // 32), extra=extra)
    n = CODES[ci]["N"]
    nout = (n + 31) // 32
    cw_a = from_words([w for w, _ in res.out[:nout]])
    cw_b = from_words([w for w, _ in res.out[nout:]])
    assert len(errs) == 2, f"err_len pulses {errs}"
    assert cw_a & ((1 << k) - 1) == a and check(ROWS[ci], cw_a)
    assert cw_b & ((1 << k) - 1) == b and check(ROWS[ci], cw_b)


@cocotb.test()
async def t13_08_code_properties(dut):
    """T13-08 base matrices: dimensions, rate, no 4-cycles, dual-diagonal parity; 648/5/6 equals the alist extraction"""
    from ldpc_py import ALIST, CODES
    rates = {0: (1, 2), 1: (2, 3), 2: (3, 4), 3: (5, 6)}
    for c in CODES:
        z, mb, kb = c["Z"], c["mb"], c["kb"]
        assert len(c["base"]) == mb and all(len(r) == 24 for r in c["base"])
        assert c["N"] == 24 * z and c["K"] == kb * z
        num, den = rates[c["code"] & 3]
        assert c["K"] * den == c["N"] * num, f"code {c['code']}: rate"
        b = c["base"]
        x = b[0][kb]
        assert b[mb - 1][kb] == x and b[mb // 2][kb] == 0 and x is not None
        for i in range(mb):
            assert (b[i][kb] is not None) == (i in (0, mb // 2, mb - 1))
        for cc in range(1, mb):
            for i in range(mb):
                want = 0 if i in (cc - 1, cc) else None
                assert b[i][kb + cc] == want, f"code {c['code']}: parity structure at ({i},{kb + cc})"
        for i1 in range(mb):
            for i2 in range(i1 + 1, mb):
                seen = set()
                for j in range(24):
                    a_, b_ = b[i1][j], b[i2][j]
                    if a_ is None or b_ is None:
                        continue
                    d = (a_ - b_) % z
                    assert d not in seen, f"code {c['code']}: 4-cycle between rows {i1},{i2}"
                    seen.add(d)
    # standard code: independent extraction from the alist
    n, arows = alist_rows()
    z = 27
    std = CODES[3]
    for i in range(4):
        for j in range(24):
            s = std["base"][i][j]
            sub = [(arows[z * i + r] >> (z * j)) & ((1 << z) - 1) for r in range(z)]
            if s is None:
                assert all(v == 0 for v in sub)
            else:
                assert all(sub[r] == 1 << ((r + s) % z) for r in range(z)), f"block ({i},{j})"
