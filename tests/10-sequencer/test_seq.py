import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

DEPTH = int(os.environ.get("DEPTH", "64"))
SAFE_PERIOD = 1000
SAFE_LINES = 0x0000
MIN_FRAME = 16
A_NOP, A_SET, A_CLR, A_PULSE, A_GAIN, A_PLL, A_END = 0, 1, 2, 3, 4, 5, 15
M16 = 0xFFFF


def entry(t, act, arg=0):
    return ((t & 0xFFFFFF) << 24) | (act << 16) | (arg & 0xFFFF)


class Model:
    def __init__(self):
        self.banks = [[0] * DEPTH, [0] * DEPTH]
        self.active = 0
        self.pending = 0
        self.safe = 1
        self.rp = 0
        self.exhausted = 0
        self.tick = 0
        self.lines = 0
        self.pulses = 0
        self.gain = 0
        self.pll = 0
        self.evt = 0
        self.fs = 1
        self.frame_cnt = 1
        self.missed = 0

    def outputs(self, force):
        return dict(lines=SAFE_LINES if force else self.lines, pulses=0 if force else self.pulses, gain_val=self.gain, pll_val=self.pll,
                    evt_pulse=self.evt, frame_start=self.fs, frame_cnt=self.frame_cnt, missed=self.missed, active_bank=self.active,
                    pending=self.pending, tick=self.tick, forced=int(force))

    def cur_entry(self):
        if self.safe:
            return entry(SAFE_PERIOD, A_END)
        return self.banks[self.active][self.rp]

    def step(self, run, force, wr_en, wr_addr, wr_data, commit):
        e = self.cur_entry()
        t, act, arg = e >> 24, (e >> 16) & 0xFF, e & 0xFFFF
        is_end = act == A_END
        t_eff = MIN_FRAME if (is_end and t < MIN_FRAME) else t
        t_cmp = t_eff - 1 if is_end else t_eff
        fire = run and not self.exhausted and self.tick >= t_cmp
        # write (uses the active bank value before this edge)
        if wr_en:
            self.banks[1 - self.active][wr_addr] = wr_data
        pending_n = 1 if commit else self.pending
        tick_n = (self.tick + 1) & 0xFFFFFF if run else self.tick
        rp_n, exh_n, lines_n = self.rp, self.exhausted, self.lines
        pulses_n, evt_n, fs_n = 0, 0, 0
        gain_n, pll_n = self.gain, self.pll
        active_n, safe_n, missed_n, fc_n = self.active, self.safe, self.missed, self.frame_cnt
        if fire:
            if is_end:
                tick_n, rp_n, exh_n, lines_n, fs_n = 0, 0, 0, 0, 1
                fc_n = (self.frame_cnt + 1) & 0xFFFFFFFF
                if self.pending:
                    active_n = 1 - self.active
                    safe_n = 0
                    pending_n = 1 if commit else 0
                    missed_n = 0
                elif self.missed != M16:
                    missed_n = self.missed + 1
            else:
                evt_n = 1
                if self.rp == DEPTH - 1:
                    exh_n = 1
                else:
                    rp_n = self.rp + 1
                if act == A_SET:
                    lines_n = self.lines | arg
                elif act == A_CLR:
                    lines_n = self.lines & ~arg & M16
                elif act == A_PULSE:
                    pulses_n = 1 << (arg & 0xF)
                elif act == A_GAIN:
                    gain_n = arg
                elif act == A_PLL:
                    pll_n = arg
        (self.pending, self.tick, self.rp, self.exhausted, self.lines, self.pulses, self.evt, self.fs) = (
            pending_n, tick_n, rp_n, exh_n, lines_n, pulses_n, evt_n, fs_n)
        self.gain, self.pll, self.active, self.safe, self.missed, self.frame_cnt = gain_n, pll_n, active_n, safe_n, missed_n, fc_n


class TB:
    def __init__(self, dut):
        self.dut = dut
        self.m = Model()
        self.cycles = 0

    async def cycle(self, run=1, force=0, wr=None, commit=0, check=True):
        d = self.dut
        await FallingEdge(d.clk)
        d.run.value = run
        d.force_safe.value = force
        d.wr_en.value = int(wr is not None)
        d.wr_addr.value = wr[0] if wr else 0
        d.wr_data.value = wr[1] if wr else 0
        d.commit.value = commit
        await Timer(1, unit="ns")
        if check:
            exp = self.m.outputs(force)
            for k, v in exp.items():
                got = int(getattr(d, k).value)
                assert got == v, f"cycle {self.cycles}: {k} = {got:#x}, model {v:#x}"
        self.m.step(run, force, wr is not None, wr[0] if wr else 0, wr[1] if wr else 0, commit)
        self.cycles += 1

    async def load(self, table, commit=True, run=1):
        """write the table into the inactive bank, one entry per clock, then commit"""
        for i, e in enumerate(table):
            await self.cycle(run=run, wr=(i, e))
        if commit:
            await self.cycle(run=run, commit=1)

    async def idle(self, n, **kw):
        for _ in range(n):
            await self.cycle(**kw)


def rand_table(rng, nev=12, frame_len=None, extra_end=True):
    t = 0
    tbl = []
    for _ in range(nev):
        t += rng.randint(0, 40)
        act = rng.choice([A_NOP, A_SET, A_CLR, A_PULSE, A_GAIN, A_PLL])
        tbl.append(entry(t, act, rng.getrandbits(16)))
    end_t = (frame_len if frame_len else t + rng.randint(20, 60))
    if extra_end:
        tbl.append(entry(end_t, A_END))
    return tbl


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for s in ("run", "force_safe", "wr_en", "commit"):
        getattr(dut, s).value = 0
    dut.wr_addr.value = 0
    dut.wr_data.value = 0
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    tb = TB(dut)
    tb.m.step(0, 0, 0, 0, 0, 0)      # the DUT takes one clock (run low) before the first sample
    return tb


@cocotb.test()
async def t10_04_reset_state(dut):
    """T10-04 reset state: lines 0, safe frames of SAFE_PERIOD clocks, frame_cnt increments"""
    tb = await start(dut)
    await tb.idle(2 * SAFE_PERIOD + 20)
    assert tb.m.frame_cnt >= 3 and tb.m.lines == 0 and tb.m.safe == 1


@cocotb.test()
async def t10_01_playback(dut):
    """T10-01 random sorted tables, all actions, three frames each, compared every clock"""
    tb = await start(dut)
    rng = random.Random(101)
    for _ in range(12):
        tbl = rand_table(rng, nev=rng.randint(1, min(20, DEPTH - 2)))
        await tb.load(tbl)
        await tb.idle(SAFE_PERIOD + 3 * (tbl[-1] >> 24) + 50)


@cocotb.test()
async def t10_02_cpu_stall(dut):
    """T10-02 after one commit nothing more is written: the frame repeats; missed counts the replays"""
    tb = await start(dut)
    rng = random.Random(102)
    tbl = [entry(10, A_SET, 0x0005), entry(20, A_PULSE, 3), entry(30, A_GAIN, 0x1234), entry(50, A_CLR, 0x0004), entry(80, A_END)]
    await tb.load(tbl)
    await tb.idle(SAFE_PERIOD + 100)             # the commit takes effect at the end of the safe frame
    frames_before = tb.m.frame_cnt
    seen = []
    for _ in range(50 * 80 + 40):
        await tb.cycle()
        if tb.m.fs:
            seen.append(tb.m.frame_cnt)
    assert tb.m.frame_cnt - frames_before >= 49
    assert tb.m.missed >= 48, f"missed {tb.m.missed}"
    assert tb.m.lines in (0x0001, 0x0005, 0x0000)


@cocotb.test()
async def t10_03_update_timing(dut):
    """T10-03 writes do not disturb the running frame; commit one clock before END takes effect, in the END clock it does not"""
    tb = await start(dut)
    a = [entry(5, A_SET, 1), entry(100, A_END)]
    b = [entry(7, A_SET, 2), entry(60, A_END)]
    await tb.load(a)
    await tb.idle(SAFE_PERIOD + 10)              # table a is now active
    assert tb.m.active == 1 and not tb.m.pending
    # wait for the start of a frame, then write b into the inactive bank in the middle of the frame
    while not tb.m.fs:
        await tb.cycle()
    await tb.idle(20)
    for i, e in enumerate(b):
        await tb.cycle(wr=(i, e))
    # commit exactly one clock before the END of this frame executes (END time 100 executes at tick 99, commit at tick 98)
    while tb.m.tick < 98:
        await tb.cycle()
    await tb.cycle(commit=1)
    await tb.idle(3)
    assert tb.m.active == 0, "commit one clock before END must swap at this frame end"
    # now a commit in the clock where END executes (END time 60 executes at tick 59) must wait a frame
    while not tb.m.fs:
        await tb.cycle()
    while tb.m.tick < 59:
        await tb.cycle()
    assert tb.m.tick == 59
    await tb.cycle(commit=1)             # END executes in this same clock
    await tb.idle(2)
    assert tb.m.active == 0 and tb.m.pending == 1, "commit in the END clock must wait for the next frame end"
    await tb.idle(80)
    assert tb.m.active == 1


@cocotb.test()
async def t10_05_force_safe(dut):
    """T10-05 force_safe forces SAFE_LINES and suppresses pulses; the timeline continues"""
    tb = await start(dut)
    tbl = [entry(5, A_SET, 0x00FF), entry(10, A_PULSE, 1), entry(15, A_PULSE, 2), entry(20, A_GAIN, 7), entry(60, A_END)]
    await tb.load(tbl)
    await tb.idle(SAFE_PERIOD + 200)
    for k in range(6):
        await tb.idle(13, force=k % 2)
    t0 = tb.m.tick
    await tb.idle(30, force=1)
    assert tb.m.tick != t0 and tb.m.frame_cnt > 3


@cocotb.test()
async def t10_06_same_time_and_late(dut):
    """T10-06 same-time and late entries run one per clock in order"""
    tb = await start(dut)
    tbl = [entry(10, A_SET, 1), entry(10, A_SET, 2), entry(10, A_SET, 4), entry(10, A_PULSE, 0), entry(5, A_SET, 8), entry(40, A_END)]
    await tb.load(tbl)
    await tb.idle(SAFE_PERIOD + 200)


@cocotb.test()
async def t10_07_run_low(dut):
    """T10-07 run low freezes everything; resumes without losing or repeating an event"""
    tb = await start(dut)
    rng = random.Random(107)
    await tb.load(rand_table(rng, min(10, DEPTH - 2)))
    for _ in range(40):
        await tb.idle(rng.randint(1, 30), run=1)
        await tb.idle(rng.randint(1, 15), run=0)


@cocotb.test()
async def t10_08_min_frame(dut):
    """T10-08 END at time 0, 5 or 16 gives 16-clock frames; time 100 gives 100"""
    tb = await start(dut)
    for et, want in ((0, 16), (5, 16), (16, 16), (100, 100)):
        await tb.load([entry(et, A_END)])
        await tb.idle(SAFE_PERIOD + 400)
        starts = []
        for _ in range(want * 6):
            await tb.cycle()
            if tb.m.fs:
                starts.append(tb.cycles)
        gaps = {b - a for a, b in zip(starts, starts[1:])}
        assert gaps == {want}, f"END at {et}: frame lengths {gaps}"


@cocotb.test()
async def t10_09_alternating(dut):
    """T10-09 alternating tables are executed in order; active_bank toggles at each swap"""
    tb = await start(dut)
    rng = random.Random(109)
    last = None
    for k in range(8):
        tbl = rand_table(rng, 6, frame_len=120)
        await tb.load(tbl)
        await tb.idle(SAFE_PERIOD + 260 if k == 0 else 260)
        if last is not None:
            assert tb.m.active != last
        last = tb.m.active


@cocotb.test()
async def t10_10_no_end(dut):
    """T10-10 a table without END never ends the frame; force_safe still works"""
    tb = await start(dut)
    tbl = [entry(i * 3 + 1, A_SET, 1 << (i % 16)) for i in range(DEPTH)]
    await tb.load(tbl)
    await tb.idle(SAFE_PERIOD + 20 + DEPTH * 3 + 200)
    assert tb.m.exhausted == 1
    fc = tb.m.frame_cnt
    await tb.idle(100)
    assert tb.m.frame_cnt == fc
    await tb.idle(10, force=1)
