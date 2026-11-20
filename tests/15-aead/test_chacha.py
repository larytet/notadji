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
async def t15_01_chacha(dut):
    """T15-01 keystream block equals the reference ChaCha20 stream"""
    dut.start.value = 0
    await start(dut)
    rng = random.Random(151)
    for k in range(30):
        key = [rng.getrandbits(8) for _ in range(32)]
        nonce = [rng.getrandbits(8) for _ in range(12)]
        counter = rng.choice([0, 1, 2, rng.getrandbits(32), 0xFFFFFFFE])
        await FallingEdge(dut.clk)
        dut.key.value = le(key)
        dut.nonce.value = le(nonce)
        dut.counter.value = counter
        dut.start.value = 1
        await FallingEdge(dut.clk)
        dut.start.value = 0
        for _ in range(200):
            await Timer(1, unit="ns")
            if int(dut.done.value):
                break
            await FallingEdge(dut.clk)
        assert int(dut.done.value) == 1, "no done pulse"
        ks = int(dut.ks.value).to_bytes(64, "little")
        assert ks == keystream(key, nonce, counter), f"block {k}"
        await ClockCycles(dut.clk, 2)


