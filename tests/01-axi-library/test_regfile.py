import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

N = 16
RO_MASK = 0x00F0          # registers 4..7 are read-only (must match the Makefile)
RO_VALUES = [0xA5A50000 + i for i in range(N)]


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for s in ("awvalid", "wvalid", "arvalid", "bready", "rready"):
        getattr(dut, s).value = 0
    dut.awaddr.value = 0
    dut.araddr.value = 0
    dut.wdata.value = 0
    dut.wstrb.value = 0
    ro = 0
    for i, v in enumerate(RO_VALUES):
        ro |= v << (32 * i)
    dut.ro_data.value = ro
    dut.rst_n.value = 0
    for _ in range(4):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


async def channel(dut, valid, ready, delay=0):
    """Hold `valid` (already set at a falling edge) until the handshake completes."""
    for _ in range(delay):
        await FallingEdge(dut.clk)
    getattr(dut, valid).value = 1
    while True:
        await Timer(1, unit="ns")
        if int(getattr(dut, ready).value):
            await FallingEdge(dut.clk)
            break
        await FallingEdge(dut.clk)
    getattr(dut, valid).value = 0


async def write(dut, addr, data, strb=0xF, aw_delay=0, w_delay=0, b_delay=0):
    """AXI-Lite write; returns bresp. Address and data channels run concurrently with their delays."""
    await FallingEdge(dut.clk)
    dut.awaddr.value = addr
    dut.wdata.value = data
    dut.wstrb.value = strb
    a = cocotb.start_soon(channel(dut, "awvalid", "awready", aw_delay))
    w = cocotb.start_soon(channel(dut, "wvalid", "wready", w_delay))
    await a
    await w
    for _ in range(b_delay):
        await FallingEdge(dut.clk)
    dut.bready.value = 1
    while True:
        await Timer(1, unit="ns")
        if int(dut.bvalid.value):
            resp = int(dut.bresp.value)
            await FallingEdge(dut.clk)
            break
        await FallingEdge(dut.clk)
    dut.bready.value = 0
    return resp


async def read(dut, addr, r_delay=0):
    await FallingEdge(dut.clk)
    dut.araddr.value = addr
    await channel(dut, "arvalid", "arready")
    for _ in range(r_delay):
        await FallingEdge(dut.clk)
    dut.rready.value = 1
    while True:
        await Timer(1, unit="ns")
        if int(dut.rvalid.value):
            data, resp = int(dut.rdata.value), int(dut.rresp.value)
            await FallingEdge(dut.clk)
            break
        await FallingEdge(dut.clk)
    dut.rready.value = 0
    return data, resp


def rw_value(dut, i):
    return (int(dut.rw_data.value) >> (32 * i)) & 0xFFFFFFFF


@cocotb.test()
async def t1_10_write_read_strobes(dut):
    """T1-10 regfile: write and read back every RW register, byte strobes honoured"""
    await setup(dut)
    rng = random.Random(10)
    model = [0] * N
    for i in range(N):
        d, r = await read(dut, i * 4)
        assert r == 0
        assert d == (RO_VALUES[i] if (RO_MASK >> i) & 1 else 0), f"reset value of reg {i}: {d:#x}"
    for _ in range(200):
        i = rng.randrange(N)
        data = rng.getrandbits(32)
        strb = rng.getrandbits(4)
        resp = await write(dut, i * 4, data, strb)
        assert resp == 0
        if not (RO_MASK >> i) & 1:
            for b in range(4):
                if (strb >> b) & 1:
                    model[i] = (model[i] & ~(0xFF << (8 * b))) | (data & (0xFF << (8 * b)))
        d, r = await read(dut, i * 4)
        want = RO_VALUES[i] if (RO_MASK >> i) & 1 else model[i]
        assert d == want, f"reg {i}: got {d:#x} want {want:#x}"
        if not (RO_MASK >> i) & 1:
            assert rw_value(dut, i) == model[i]


@cocotb.test()
async def t1_11_read_only(dut):
    """T1-11 regfile: write to a read-only register is accepted and ignored"""
    await setup(dut)
    for i in range(4, 8):
        assert await write(dut, i * 4, 0xFFFFFFFF) == 0
        d, r = await read(dut, i * 4)
        assert d == RO_VALUES[i] and r == 0


@cocotb.test()
async def t1_12_out_of_range(dut):
    """T1-12 regfile: out-of-range access answers SLVERR, reads return 0, nothing changes"""
    await setup(dut)
    assert await write(dut, 0, 0x1234) == 0
    for addr in (N * 4, N * 4 + 4, 0xFC):
        assert await write(dut, addr, 0xDEADBEEF) == 2, f"write {addr:#x}"
        d, r = await read(dut, addr)
        assert (d, r) == (0, 2), f"read {addr:#x}"
    for i in range(N):
        want = 0x1234 if i == 0 else 0
        if not (RO_MASK >> i) & 1:
            assert rw_value(dut, i) == want, f"reg {i} changed"


@cocotb.test()
async def t1_13_ordering_and_delays(dut):
    """T1-13 regfile: address before data, data before address, random delays, back to back"""
    await setup(dut)
    rng = random.Random(13)
    model = {}
    for k in range(150):
        i = rng.choice([0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15])
        data = rng.getrandbits(32)
        mode = k % 3
        if mode == 0:
            resp = await write(dut, i * 4, data, 0xF, aw_delay=0, w_delay=rng.randint(1, 6))
        elif mode == 1:
            resp = await write(dut, i * 4, data, 0xF, aw_delay=rng.randint(1, 6), w_delay=0)
        else:
            resp = await write(dut, i * 4, data, 0xF, rng.randint(0, 3), rng.randint(0, 3), rng.randint(0, 3))
        assert resp == 0
        model[i] = data
        j = rng.choice(list(model))
        d, r = await read(dut, j * 4, r_delay=rng.randint(0, 3))
        assert (d, r) == (model[j], 0)


@cocotb.test()
async def t1_14_write_pulse(dut):
    """T1-14 regfile: exactly one wr_pulse clock per accepted write to a RW register"""
    await setup(dut)
    pulses = []

    async def watch():
        while True:
            await FallingEdge(dut.clk)
            await Timer(1, unit="ns")
            v = int(dut.wr_pulse.value)
            if v:
                pulses.append(v)

    cocotb.start_soon(watch())
    for i in (0, 3, 8, 15):
        await write(dut, i * 4, (0x11111111 * (i + 1)) & 0xFFFFFFFF)
    await write(dut, 5 * 4, 0xFFFF)      # read-only: no pulse
    await write(dut, N * 4, 0x1)         # out of range: no pulse
    for _ in range(5):
        await FallingEdge(dut.clk)
    assert pulses == [1 << 0, 1 << 3, 1 << 8, 1 << 15], [hex(p) for p in pulses]
