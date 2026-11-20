import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

NTAPS = int(os.environ["NTAPS"])
DEPTH = int(os.environ["TRACE_DEPTH"])
ID_W = (NTAPS - 1).bit_length()
M64 = (1 << 64) - 1


class TB:
    """Python model of timestamp_unit, advanced one clock per call to cycle()."""

    def __init__(self, dut):
        self.dut = dut
        self.reset_model()

    def reset_model(self):
        self.cnt = 0
        self.tap_ts = [0] * NTAPS
        self.tap_cnt = [0] * NTAPS
        self.snap = 0
        self.queue = []
        self.drop = 0

    async def cycle(self, evt=0, load=None, adj=None, snap=False, ready=1, rst=True, check=True):
        d = self.dut
        await FallingEdge(d.clk)
        d.rst_n.value = int(rst)
        d.tap_evt.value = evt
        d.load_valid.value = int(load is not None)
        d.load_value.value = load if load is not None else 0
        d.adj_valid.value = int(adj is not None)
        d.adj_delta.value = (adj & 0xFFFFFFFF) if adj is not None else 0
        d.snap_req.value = int(snap)
        d.m_axis_ready.value = ready
        await Timer(1, unit="ns")
        got = {}
        if check:
            assert int(d.ts_now.value) == self.cnt, f"ts_now {int(d.ts_now.value):#x} model {self.cnt:#x}"
            ts = int(d.tap_ts_flat.value)
            tc = int(d.tap_cnt_flat.value)
            for i in range(NTAPS):
                assert (ts >> (64 * i)) & M64 == self.tap_ts[i], f"tap_ts[{i}]"
                assert (tc >> (16 * i)) & 0xFFFF == self.tap_cnt[i], f"tap_cnt[{i}]"
            assert int(d.snap_ts.value) == self.snap, "snap_ts"
            assert int(d.trace_drop.value) == self.drop, f"trace_drop {int(d.trace_drop.value)} model {self.drop}"
            mv = int(d.m_axis_valid.value)
            assert mv == int(len(self.queue) > 0), "m_axis_valid"
            if mv:
                assert int(d.m_axis_data.value) == self.queue[0], "trace data"
                assert int(d.m_axis_last.value) == 1
        # --- model next state ---
        if not rst:
            self.reset_model()
            return
        was_empty_or_full = len(self.queue)
        popped = ready and len(self.queue) > 0
        n_evt = bin(evt).count("1")
        accepted = 0
        if n_evt:
            if was_empty_or_full < DEPTH:
                first = (evt & -evt).bit_length() - 1
                self.queue_push = (first << 64) | self.cnt
                accepted = 1
        if popped:
            self.queue.pop(0)
        if accepted:
            self.queue.append(self.queue_push)
        self.drop = min(0xFFFF, self.drop + n_evt - accepted)
        for i in range(NTAPS):
            if (evt >> i) & 1:
                self.tap_ts[i] = self.cnt
                self.tap_cnt[i] = (self.tap_cnt[i] + 1) & 0xFFFF
        if snap:
            self.snap = self.cnt
        if load is not None:
            self.cnt = load
        elif adj is not None:
            self.cnt = (self.cnt + 1 + adj) & M64
        else:
            self.cnt = (self.cnt + 1) & M64


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    tb = TB(dut)
    for s in ("tap_evt", "load_valid", "adj_valid", "snap_req", "m_axis_ready"):
        getattr(dut, s).value = 0
    dut.load_value.value = 0
    dut.adj_delta.value = 0
    for _ in range(3):
        await tb.cycle(rst=False, check=False)
    return tb


@cocotb.test()
async def t2_01_free_run(dut):
    """T2-01 free run: 0 after reset, +1 every clock for 10000 clocks"""
    tb = await start(dut)
    for _ in range(10000):
        await tb.cycle()


@cocotb.test()
async def t2_02_single_taps(dut):
    """T2-02 single events latch the model timestamp, event counters increment"""
    tb = await start(dut)
    rng = random.Random(2)
    for _ in range(400):
        evt = (1 << rng.randrange(NTAPS)) if rng.random() < 0.5 else 0
        await tb.cycle(evt=evt, ready=1)
    for _ in range(3):
        await tb.cycle()


@cocotb.test()
async def t2_03_simultaneous(dut):
    """T2-03 simultaneous events: all latch; one trace record (lowest index); drops counted"""
    tb = await start(dut)
    await tb.cycle(evt=(1 << NTAPS) - 1, ready=1)
    await tb.cycle(evt=0b101, ready=1)
    await tb.cycle(evt=0, ready=1)
    await tb.cycle(evt=1 << (NTAPS - 1), ready=1)
    for _ in range(6):
        await tb.cycle(ready=1)
    assert tb.drop == (NTAPS - 1) + 1


@cocotb.test()
async def t2_04_trace_order(dut):
    """T2-04 trace stream content and order under random back-pressure"""
    tb = await start(dut)
    rng = random.Random(4)
    for _ in range(3000):
        evt = rng.getrandbits(NTAPS) if rng.random() < 0.3 else 0
        await tb.cycle(evt=evt, ready=int(rng.random() < 0.7))
    for _ in range(DEPTH + 5):
        await tb.cycle(ready=1)
    assert not tb.queue


@cocotb.test()
async def t2_05_overflow(dut):
    """T2-05 trace FIFO overflow: exact drop count, latches intact, stream resumes in order"""
    tb = await start(dut)
    n = DEPTH + 7
    for k in range(n):
        await tb.cycle(evt=1 << (k % NTAPS), ready=0)
    assert tb.drop == 7, f"model drop {tb.drop}"
    assert len(tb.queue) == DEPTH
    for _ in range(DEPTH + 3):
        await tb.cycle(ready=1)
    assert not tb.queue


@cocotb.test()
async def t2_06_load(dut):
    """T2-06 load sets the next value; load beats adjust"""
    tb = await start(dut)
    for _ in range(5):
        await tb.cycle()
    await tb.cycle(load=0x123456789ABC)
    for _ in range(5):
        await tb.cycle()
    await tb.cycle(load=1000, adj=-50)
    for _ in range(3):
        await tb.cycle()


@cocotb.test()
async def t2_07_adjust(dut):
    """T2-07 adjust: next value is ts_now + 1 + delta, positive, negative and zero deltas"""
    tb = await start(dut)
    rng = random.Random(7)
    await tb.cycle(load=1 << 40)
    for _ in range(100):
        await tb.cycle(adj=rng.choice([0, 1, -1, rng.randint(-100000, 100000), 2**31 - 1, -(2**31)]))
        for _ in range(rng.randint(0, 3)):
            await tb.cycle()


@cocotb.test()
async def t2_08_wrap(dut):
    """T2-08 64-bit wrap: counting continues through zero; an event across the wrap latches correctly"""
    tb = await start(dut)
    await tb.cycle(load=(1 << 64) - 5)
    for k in range(12):
        await tb.cycle(evt=1 if k in (2, 6, 7) else 0, ready=1)
    for _ in range(4):
        await tb.cycle(ready=1)
    assert tb.tap_ts[0] < 100


@cocotb.test()
async def t2_09_snapshot(dut):
    """T2-09 snapshot holds the request-clock value until the next request"""
    tb = await start(dut)
    for _ in range(7):
        await tb.cycle()
    await tb.cycle(snap=True)
    for _ in range(10):
        await tb.cycle()
    await tb.cycle(snap=True)
    for _ in range(3):
        await tb.cycle()


@cocotb.test()
async def t2_10_reset_midrun(dut):
    """T2-10 reset in the middle clears counter, latches, counters, trace FIFO and drop count"""
    tb = await start(dut)
    for k in range(40):
        await tb.cycle(evt=(1 << (k % NTAPS)), ready=0)
    assert tb.drop > 0 or DEPTH > 40
    await tb.cycle(rst=False, check=True)
    for _ in range(3):
        await tb.cycle()
    assert tb.cnt == 3 and not tb.queue and tb.drop == 0
