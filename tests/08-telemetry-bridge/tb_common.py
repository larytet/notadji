import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

CLK_NS = 10


async def start(dut, rst_n="rst_n"):
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    getattr(dut, rst_n).value = 0
    for _ in range(4):
        await FallingEdge(dut.clk)
    getattr(dut, rst_n).value = 1
    await FallingEdge(dut.clk)


async def uart_send(dut, sig, byte, div, stop=1, idle_bits=0):
    """Drive one 8N1 byte on `sig` with `div` clocks per bit, then `idle_bits` idle bit times."""
    for b in [0] + [(byte >> i) & 1 for i in range(8)] + [stop]:
        sig.value = b
        await ClockCycles(dut.clk, div)
    if stop == 0:
        sig.value = 1
    if idle_bits:
        sig.value = 1
        await ClockCycles(dut.clk, idle_bits * div)


# ---------------- frame builders ----------------
def rnd_payload(rng, n, avoid=()):
    out = []
    while len(out) < n:
        b = rng.getrandbits(8)
        if b not in avoid:
            out.append(b)
    return out


def mav1(rng, n, avoid=()):
    return [0xFE, n, rng.getrandbits(8), 1, 1, rng.getrandbits(8)] + rnd_payload(rng, n, avoid) + [rng.getrandbits(8), rng.getrandbits(8)]


def mav2(rng, n, signed=False, avoid=()):
    inc = 1 if signed else 0
    f = [0xFD, n, inc, 0, rng.getrandbits(8), 1, 1, rng.getrandbits(8), 0, 0] + rnd_payload(rng, n, avoid) + [rng.getrandbits(8), rng.getrandbits(8)]
    if signed:
        f += rnd_payload(rng, 13, avoid)
    return f


def msp1(rng, n, avoid=()):
    return [0x24, 0x4D, rng.choice([0x3C, 0x3E, 0x21]), n, rng.getrandbits(8)] + rnd_payload(rng, n, avoid) + [rng.getrandbits(8)]


def msp2(rng, n, avoid=()):
    return [0x24, 0x58, rng.choice([0x3C, 0x3E, 0x21]), 0, rng.getrandbits(8), rng.getrandbits(8), n & 0xFF, n >> 8] + rnd_payload(rng, n, avoid) + [rng.getrandbits(8)]


def as_out(frame, err=0):
    return [(b, int(i == len(frame) - 1), err if i == len(frame) - 1 else 0) for i, b in enumerate(frame)]
