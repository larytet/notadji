import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from aead_ref import CLAMP, keystream, le, poly_tag


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(4):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


@cocotb.test()
async def t15_02_poly1305(dut):
    """T15-02 tag equals the reference for random and extreme messages"""
    dut.init.value = 0
    dut.blk_valid.value = 0
    dut.fin.value = 0
    dut.r_in.value = 0
    dut.s_in.value = 0
    dut.blk.value = 0
    await start(dut)
    rng = random.Random(152)
    cases = []
    for _ in range(40):
        n = rng.choice([1, 2, 3, 5, 8, 17])
        cases.append(([rng.getrandbits(8) for _ in range(32)], [rng.getrandbits(8) for _ in range(16 * n)]))
    cases.append(([0xFF] * 32, [0xFF] * 160))
    cases.append(([0xFF] * 16 + [0] * 16, [0xFF] * 16))
    cases.append(([0] * 32, [0] * 48))
    cases.append(([0x55] * 32, [0xFF] * 64))
    for key, msg in cases:
        r = le(key[:16]) & CLAMP
        s = le(key[16:])
        dut.r_in.value = r
        dut.s_in.value = s
        dut.init.value = 1
        await FallingEdge(dut.clk)
        dut.init.value = 0
        for i in range(0, len(msg), 16):
            while True:
                await Timer(1, unit="ns")
                if int(dut.ready.value):
                    break
                await FallingEdge(dut.clk)
            dut.blk.value = le(msg[i:i + 16])
            dut.blk_valid.value = 1
            await FallingEdge(dut.clk)
            dut.blk_valid.value = 0
        while True:
            await Timer(1, unit="ns")
            if int(dut.ready.value):
                break
            await FallingEdge(dut.clk)
        dut.fin.value = 1
        await FallingEdge(dut.clk)
        dut.fin.value = 0
        for _ in range(10):
            await Timer(1, unit="ns")
            if int(dut.tag_valid.value):
                break
            await FallingEdge(dut.clk)
        assert int(dut.tag_valid.value) == 1
        assert int(dut.tag.value).to_bytes(16, "little") == poly_tag(key, msg), f"key {bytes(key).hex()} len {len(msg)}"
        await FallingEdge(dut.clk)
