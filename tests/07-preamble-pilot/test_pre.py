import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

from stream_tb import reset, start_clock

PLAN = {   # log2: (kmin, kmax, pilot |k| list)
    6: (1, 26, [7, 21]),
    7: (2, 58, [11, 25, 53]),
    8: (2, 122, [11, 39, 75, 103]),
    9: (3, 244, [12, 42, 72, 102, 132, 162, 192, 222]),
    10: (3, 500, [12, 72, 132, 192, 252, 312, 372, 432]),
}
EXPECT = {6: (52, 48, 4), 7: (114, 108, 6), 8: (242, 234, 8), 9: (484, 468, 16), 10: (996, 980, 16)}


def clamp_log2(l):
    return min(max(l, 6), 10)


class Model:
    def __init__(self):
        self.pol_state = 0x7F

    def pn_gen(self):
        s = 0x1FF
        while True:
            fb = ((s >> 8) ^ (s >> 4)) & 1
            s = ((s << 1) & 0x1FF) | fb
            yield fb

    def symbol(self, kind, log2, frame_start=False):
        log2 = clamp_log2(log2)
        n = 1 << log2
        kmin, kmax, pil = PLAN[log2]
        kind = kind if kind in (0, 1) else 2
        pn = self.pn_gen()
        pol = 0
        if kind == 2:
            st = 0x7F if frame_start else self.pol_state
            pol = bin(st & 0b1001000).count("1") & 1
            self.pol_state = ((st << 1) & 0x7F) | pol
        pos = [p for p in pil]
        # pilot index list in increasing-k order: negative (largest |k| first) then positive
        order = [-p for p in reversed(pos)] + pos
        out = []
        for b in range(n):
            k = b if b < n // 2 else b - n
            ak = abs(k)
            used = kmin <= ak <= kmax and k != 0
            t, i, q = 0, 0, 0
            if kind == 2:
                if used and k in order:
                    j = order.index(k)
                    neg = pol ^ (1 if j % 4 == 3 else 0)
                    t, i = 2, (-4096 if neg else 4096)
                elif used:
                    t = 1
            elif kind == 0:
                if used and ak % 4 == 0:
                    t = 2
                    i = 5793 if next(pn) else -5793
                    q = 5793 if next(pn) else -5793
            else:
                if used:
                    t = 2
                    i = 4096 if next(pn) else -4096
            out.append((t, i, q))
        return out


def pack(t, i, q):
    return (t << 32) | ((q & 0xFFFF) << 16) | (i & 0xFFFF)


def unpack(w):
    def s(x):
        return x - 0x10000 if x & 0x8000 else x
    return (w >> 32) & 3, s(w & 0xFFFF), s((w >> 16) & 0xFFFF)


async def setup(dut):
    dut.cmd_valid.value = 0
    dut.cmd_kind.value = 0
    dut.cmd_log2.value = 8
    dut.cmd_frame_start.value = 0
    dut.m_axis_ready.value = 0
    start_clock(dut.clk)
    await reset(dut)


async def run_cmds(dut, cmds, p_cmd=1.0, p_ready=1.0, seed=0):
    """cmds: list of (kind, log2, frame_start). Returns (symbols, total_cycles, ready_violations)."""
    rng = random.Random(seed)
    idx = 0
    active = False
    symbols = []
    cur = []
    expect_total = None
    cyc = 0
    bad_ready = 0
    accepted = 0
    # number of beats expected: computed from the commands (clamped N)
    total_beats = sum(1 << clamp_log2(c[1]) for c in cmds)
    got = 0
    while (got < total_beats or idx < len(cmds)) and cyc < 400000:
        await FallingEdge(dut.clk)
        if not active and idx < len(cmds) and rng.random() < p_cmd:
            active = True
        if active:
            k, l, fs = cmds[idx]
            dut.cmd_valid.value = 1
            dut.cmd_kind.value = k
            dut.cmd_log2.value = l
            dut.cmd_frame_start.value = int(fs)
        else:
            dut.cmd_valid.value = 0
        mr = 1 if rng.random() < p_ready else 0
        dut.m_axis_ready.value = mr
        await Timer(1, unit="ns")
        cr = int(dut.cmd_ready.value)
        mv = int(dut.m_axis_valid.value)
        ml = int(dut.m_axis_last.value)
        # cmd_ready must be low while a symbol is in progress unless its last beat is being accepted
        if mv and not (mr and ml) and cr:
            bad_ready += 1
        if active and cr:
            idx += 1
            active = False
        if mv and mr:
            cur.append(int(dut.m_axis_data.value))
            got += 1
            if ml:
                symbols.append(cur)
                cur = []
        cyc += 1
    # let the last symbol finish if the loop ended on command acceptance
    return symbols, cyc, bad_ready


def expected(cmds):
    m = Model()
    return [[pack(*x) for x in m.symbol(k, l, fs)] for k, l, fs in cmds]


@cocotb.test()
async def t7_01_tone_plan(dut):
    """T7-01 tone counts, DC and guard bins null, pilot sets"""
    await setup(dut)
    for l in range(6, 11):
        cmds = [(2, l, True)]
        syms, _, _ = await run_cmds(dut, cmds)
        sym = [unpack(w) for w in syms[0]]
        n = 1 << l
        assert len(sym) == n
        used = sum(1 for t, _, _ in sym if t in (1, 2))
        data = sum(1 for t, _, _ in sym if t == 1)
        pil = sum(1 for t, _, _ in sym if t == 2)
        assert (used, data, pil) == EXPECT[l], f"log2={l}: {(used, data, pil)}"
        pil_bins = sorted((b if b < n // 2 else b - n) for b, (t, _, _) in enumerate(sym) if t == 2)
        want = sorted([p for p in PLAN[l][2]] + [-p for p in PLAN[l][2]])
        assert pil_bins == want, f"log2={l}: pilot positions {pil_bins}"
        assert sym[0][0] == 0, "DC bin must be null"
        kmin, kmax, _ = PLAN[l]
        for b, (t, _, _) in enumerate(sym):
            k = b if b < n // 2 else b - n
            if not (kmin <= abs(k) <= kmax):
                assert t == 0, f"guard bin k={k} not null"
        # symmetric in |k|
        for k in range(1, n // 2):
            assert (sym[k][0] == 0) == (sym[n - k][0] == 0)


@cocotb.test()
async def t7_02_stf(dut):
    """T7-02 STF equals the model; its inverse DFT repeats four times"""
    await setup(dut)
    for l in range(6, 11):
        syms, _, _ = await run_cmds(dut, [(0, l, False)])
        assert syms == expected([(0, l, False)]), f"log2={l}"
        n = 1 << l
        x = np.fft.ifft(np.array([complex(unpack(w)[1], unpack(w)[2]) for w in syms[0]]))
        q = n // 4
        scale = np.max(np.abs(x))
        for r in range(1, 4):
            assert np.max(np.abs(x[:q] - x[r * q:(r + 1) * q])) < 1e-9 * scale, f"log2={l} repetition {r}"


@cocotb.test()
async def t7_03_ltf(dut):
    """T7-03 LTF equals the model; two symbols identical; all used tones +/-4096"""
    await setup(dut)
    for l in range(6, 11):
        syms, _, _ = await run_cmds(dut, [(1, l, False), (1, l, False)])
        assert syms == expected([(1, l, False)] * 2), f"log2={l}"
        assert syms[0] == syms[1]
        for w in syms[0]:
            t, i, q = unpack(w)
            if t:
                assert abs(i) == 4096 and q == 0


@cocotb.test()
async def t7_04_pilots(dut):
    """T7-04 pilot template over 300 symbols; polarity period 127; frame_start restarts"""
    await setup(dut)
    cmds = [(2, 8, k == 0 or k == 150) for k in range(300)]
    syms, _, _ = await run_cmds(dut, cmds)
    assert syms == expected(cmds)
    # polarity period: pilot 0 sign repeats every 127 symbols between restarts
    m = Model()
    signs = []
    for k in range(260):
        s = m.symbol(2, 8, k == 0)
        signs.append([i for t, i, _ in s if t == 2][0])
    assert signs[:127] == signs[127:254], "polarity sequence must repeat after 127 symbols"
    # a restart replays the sequence
    cmds = [(2, 8, True)] + [(2, 8, False)] * 9 + [(2, 8, True)]
    syms, _, _ = await run_cmds(dut, cmds)
    assert syms[0] == syms[10]


@cocotb.test()
async def t7_05_power(dut):
    """T7-05 symbol energy: LTF is used x 4096^2 exactly; STF within 10% of the LTF energy"""
    await setup(dut)
    for l in range(6, 11):
        e = {}
        for kind in (0, 1):
            syms, _, _ = await run_cmds(dut, [(kind, l, False)])
            e[kind] = sum(unpack(w)[1] ** 2 + unpack(w)[2] ** 2 for w in syms[0])
        assert e[1] == EXPECT[l][0] * 4096 ** 2, f"log2={l}"
        assert abs(e[0] / e[1] - 1) < 0.10, f"log2={l}: STF/LTF energy {e[0] / e[1]:.3f}"


@cocotb.test()
async def t7_06_07_handshakes_and_mix(dut):
    """T7-06/07 random handshakes, different kind and N per command, back-to-back, cmd_ready"""
    await setup(dut)
    rng = random.Random(76)
    cmds = [(k, l, rng.random() < 0.2) for _ in range(2) for k in (0, 1, 2) for l in range(6, 11)]
    rng.shuffle(cmds)
    first2 = next(i for i, c in enumerate(cmds) if c[0] == 2)
    cmds[first2] = (2, cmds[first2][1], True)   # restart the polarity sequence (the DUT state persists between runs)
    exp = expected(cmds)
    for pc, pr in ((1.0, 1.0), (0.5, 0.5), (0.9, 0.3)):
        syms, cyc, bad = await run_cmds(dut, cmds, pc, pr, seed=3)
        assert syms == exp, f"pc={pc} pr={pr}"
        assert bad == 0, "cmd_ready high while a symbol is in progress"
    # back-to-back: no gap between symbols at full speed
    syms, cyc, _ = await run_cmds(dut, cmds, 1.0, 1.0)
    total = sum(1 << c[1] for c in cmds)
    assert cyc <= total + 4, f"{cyc} cycles for {total} beats"


@cocotb.test()
async def t7_08_clamp_reserved(dut):
    """T7-08 log2 below 6 acts as 6, above 10 as 10; kind 3 acts as kind 2"""
    await setup(dut)
    cmds = [(0, 2, False), (1, 15, False), (3, 7, True), (2, 7, False)]
    syms, _, _ = await run_cmds(dut, cmds)
    assert syms == expected(cmds)
