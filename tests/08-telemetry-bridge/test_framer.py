import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from tb_common import *

DIV = 8
IDLE_BITS = 10
TIMEOUT = IDLE_BITS * DIV          # clocks of silence that end a frame
FRAMES_START = (0xFE, 0xFD, 0x24)


async def setup(dut, proto, max_len=511, idle=IDLE_BITS):
    dut.s_axis_valid.value = 0
    dut.s_axis_data.value = 0
    dut.m_axis_ready.value = 1
    dut.div.value = DIV
    dut.proto.value = proto
    dut.idle_bits.value = idle
    dut.max_len.value = max_len
    await start(dut)


class Run:
    def __init__(self, dut, ready_p=1.0, seed=0):
        self.dut = dut
        self.out = []
        self.drops = 0
        self.rng = random.Random(seed)
        self.ready_p = ready_p
        self.cycles = 0
        self.first_out = None
        self.task = cocotb.start_soon(self.mon())

    async def mon(self):
        d = self.dut
        while True:
            await FallingEdge(d.clk)
            r = 1 if self.rng.random() < self.ready_p else 0
            d.m_axis_ready.value = r
            await Timer(1, unit="ns")
            if int(d.drop.value):
                self.drops += 1
            if int(d.m_axis_valid.value) and r:
                self.out.append((int(d.m_axis_data.value), int(d.m_axis_last.value), int(d.m_axis_err.value)))
            self.cycles += 1

    async def feed(self, items):
        """items: list of bytes or ('gap', clocks). Bytes are offered with valid held until ready."""
        d = self.dut
        await FallingEdge(d.clk)
        for it in items:
            if isinstance(it, tuple):
                d.s_axis_valid.value = 0
                for _ in range(it[1]):
                    await FallingEdge(d.clk)
                continue
            d.s_axis_valid.value = 1
            d.s_axis_data.value = it
            while True:
                await Timer(1, unit="ns")
                ok = int(d.s_axis_ready.value)
                await FallingEdge(d.clk)
                if ok:
                    break
        d.s_axis_valid.value = 0

    async def settle(self, clocks=TIMEOUT + 40):
        await ClockCycles(self.dut.clk, clocks)

    def stop(self):
        self.task.cancel()


def with_gaps(frames, rng, small=2):
    items = []
    for f in frames:
        for b in f:
            items.append(b)
            if rng.random() < 0.2:
                items.append(("gap", rng.randint(1, small)))
        items.append(("gap", rng.randint(0, 6)))
    return items


@cocotb.test()
async def t8_05_mavlink(dut):
    """T8-05 MAVLink v1/v2, unsigned and signed, payload 0..255, back to back"""
    await setup(dut, 1)
    rng = random.Random(85)
    frames = []
    for n in [0, 1, 9, 33, 255, 100]:
        frames.append(mav1(rng, n))
        frames.append(mav2(rng, n))
        frames.append(mav2(rng, n, signed=True))
    rng.shuffle(frames)
    for ready_p in (1.0, 0.4):
        r = Run(dut, ready_p, seed=1)
        await r.feed(with_gaps(frames, rng))
        await r.settle()
        r.stop()
        exp = [x for f in frames for x in as_out(f)]
        assert r.out == exp
        assert r.drops == 0


@cocotb.test()
async def t8_06_msp(dut):
    """T8-06 MSP v1/v2 including a 300-byte v2 payload"""
    await setup(dut, 2)
    rng = random.Random(86)
    frames = []
    for n in [0, 1, 9, 33, 255]:
        frames.append(msp1(rng, n))
        frames.append(msp2(rng, n))
    frames.append(msp2(rng, 300))
    rng.shuffle(frames)
    r = Run(dut, 1.0)
    await r.feed(with_gaps(frames, rng))
    await r.settle()
    r.stop()
    assert r.out == [x for f in frames for x in as_out(f)]
    assert r.drops == 0


@cocotb.test()
async def t8_07_garbage(dut):
    """T8-07 garbage between frames is dropped and counted"""
    await setup(dut, 3)      # auto mode accepts both protocols; garbage here must avoid the start bytes
    await ClockCycles(dut.clk, 2)
    dut.proto.value = 1      # MAVLink only: '$' and everything else is garbage
    rng = random.Random(87)
    frames = [mav1(rng, 5), mav2(rng, 12), mav1(rng, 0)]
    items, nbad = [], 0
    for f in frames:
        for _ in range(rng.randint(1, 4)):
            items.append(rng.choice([0x00, 0x11, 0x24, 0x7F, 0xAA]))
            nbad += 1
        items += f
    r = Run(dut)
    await r.feed(items)
    await r.settle()
    r.stop()
    assert r.out == [x for f in frames for x in as_out(f)]
    assert r.drops == nbad, f"drops {r.drops} expected {nbad}"


@cocotb.test()
async def t8_08_raw(dut):
    """T8-08 raw framing by idle timeout and by max_len"""
    await setup(dut, 0, max_len=16)
    rng = random.Random(88)
    frames = [[rng.getrandbits(8) for _ in range(n)] for n in (1, 5, 16, 3)]
    items = []
    for f in frames:
        items += f
        items.append(("gap", TIMEOUT + 30))
    r = Run(dut)
    await r.feed(items)
    await r.settle()
    exp = [x for f in frames for x in as_out(f)]
    assert r.out == exp
    # long burst: split by max_len into 16, 16, 8
    burst = [rng.getrandbits(8) for _ in range(40)]
    r.out.clear()
    await r.feed(burst)
    await r.settle()
    r.stop()
    exp = as_out(burst[:16]) + as_out(burst[16:32]) + as_out(burst[32:])
    assert r.out == exp


@cocotb.test()
async def t8_09_truncated(dut):
    """T8-09 truncated protocol frame ends with 0x00, last, err after the timeout; next frame fine"""
    await setup(dut, 1)
    rng = random.Random(89)
    f1 = mav2(rng, 20)
    f2 = mav1(rng, 7)
    r = Run(dut)
    await r.feed(f1[:-3] + [("gap", TIMEOUT + 40)] + f2)
    await r.settle()
    r.stop()
    exp = [(b, 0, 0) for b in f1[:-3]] + [(0x00, 1, 1)] + as_out(f2)
    assert r.out == exp


@cocotb.test()
async def t8_10_invalid_and_too_long(dut):
    """T8-10 invalid MSP header and over-long frames terminate with err and resynchronise"""
    await setup(dut, 2, max_len=32)
    rng = random.Random(90)
    good = msp1(rng, 4, avoid=FRAMES_START)
    r = Run(dut)
    # '$' then 'Q' (not M or X): abort at 'Q'; following bytes up to the next '$' are dropped
    await r.feed([0x24, 0x51, 0x01, 0x02] + [("gap", 10)] + good)
    await r.settle()
    exp = [(0x24, 0, 0), (0x51, 1, 1)] + as_out(good)
    assert r.out == exp, f"invalid header: {r.out[:6]}"
    r.out.clear()
    # bad direction byte
    await r.feed([0x24, 0x4D, 0x3F, 0x00, 0x00] + [("gap", 10)] + good)
    await r.settle()
    assert r.out == [(0x24, 0, 0), (0x4D, 0, 0), (0x3F, 1, 1)] + as_out(good), f"bad direction: {r.out[:6]}"
    r.out.clear()
    # length above max_len (v1, size 100 -> total 106 > 32): abort at the size byte
    big = [0x24, 0x4D, 0x3C, 100, 0x01] + rnd_payload(rng, 100, avoid=FRAMES_START) + [0x00]
    await r.feed(big + [("gap", 10)] + good)
    await r.settle()
    r.stop()
    assert r.out == [(0x24, 0, 0), (0x4D, 0, 0), (0x3C, 0, 0), (100, 1, 1)] + as_out(good), f"too long: {r.out[:8]}"


@cocotb.test()
async def t8_11_auto(dut):
    """T8-11 auto mode: MAVLink, MSP and raw data mixed"""
    await setup(dut, 3)
    rng = random.Random(91)
    m = mav2(rng, 15)
    s = msp1(rng, 6)
    raw = [0x55, 0x01, 0x02, 0x03, 0x04]
    m2 = mav1(rng, 3)
    r = Run(dut)
    await r.feed(m + [("gap", 3)] + s + [("gap", 3)] + raw + [("gap", TIMEOUT + 40)] + m2)
    await r.settle()
    r.stop()
    exp = as_out(m) + as_out(s) + as_out(raw) + as_out(m2)
    assert r.out == exp


@cocotb.test()
async def t8_13_latency(dut):
    """T8-13 protocol mode: output byte one clock after the input byte is accepted"""
    await setup(dut, 1)
    rng = random.Random(93)
    f = mav1(rng, 4)
    lat = []
    d = dut
    for b in f:
        d.s_axis_valid.value = 1
        d.s_axis_data.value = b
        await Timer(1, unit="ns")
        assert int(d.s_axis_ready.value) == 1
        await FallingEdge(d.clk)
        d.s_axis_valid.value = 0
        await Timer(1, unit="ns")
        assert int(d.m_axis_valid.value) == 1 and int(d.m_axis_data.value) == b, "byte must be at the output one clock after it was accepted"
        await FallingEdge(d.clk)
