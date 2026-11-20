import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer


async def setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for s in ("lines", "pulses", "pll_val", "sel", "inv", "hop_sel", "safe_val", "force_safe"):
        getattr(dut, s).value = 0
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


def model(lines, pulses, pll, sel, inv, hop_sel, safe, force):
    pins = 0
    for k in range(6):
        s = (sel >> (4 * k)) & 0xF
        v = safe >> k & 1 if force else ((lines >> s) & 1) ^ ((inv >> k) & 1)
        pins |= v << k
    return pins, 0 if force else (pulses >> hop_sel) & 1, pll & 0xF


@cocotb.test()
async def t11_03_04_pins_and_override(dut):
    """T11-03/04 pin mapping with inversion, hop trigger and profile; fault override within one clock"""
    await setup(dut)
    rng = random.Random(113)
    prev = None
    for n in range(2000):
        args = (rng.getrandbits(16), rng.getrandbits(16), rng.getrandbits(16), rng.getrandbits(24), rng.getrandbits(6),
                rng.getrandbits(4), rng.getrandbits(6), int(rng.random() < 0.3))
        names = ("lines", "pulses", "pll_val", "sel", "inv", "hop_sel", "safe_val", "force_safe")
        for nme, v in zip(names, args):
            getattr(dut, nme).value = v
        await Timer(1, unit="ns")
        # outputs show the previous inputs (one clock of latency)
        if prev is not None:
            exp = model(*prev)
            got = (int(dut.pin.value), int(dut.hop_trig.value), int(dut.profile.value))
            assert got == exp, f"step {n}: got {got} expected {exp}"
        prev = args
        await FallingEdge(dut.clk)
    # override: pins go to safe_val one clock after force_safe rises, whatever the lines are
    dut.lines.value = 0xFFFF
    dut.sel.value = 0x543210
    dut.inv.value = 0
    dut.safe_val.value = 0b101010
    dut.force_safe.value = 0
    dut.pulses.value = 0xFFFF
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert int(dut.pin.value) == 0b111111
    dut.force_safe.value = 1
    await FallingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.pin.value) == 0b101010 and int(dut.hop_trig.value) == 0
