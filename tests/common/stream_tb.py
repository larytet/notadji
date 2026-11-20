"""Cycle-based stream testbench helper (cocotb 2, Verilator).

Every clock cycle: at the falling edge the testbench drives the source and the sink, waits 1 ns
for combinational outputs to settle, samples, and records the transfers that the next rising edge
will perform. The protocol rule (valid, data, last stable while valid and not ready) is checked
on both interfaces.
"""
import random

from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer


def start_clock(sig, period_ns=10):
    import cocotb
    cocotb.start_soon(Clock(sig, period_ns, unit="ns").start())


async def reset(dut, clk="clk", rst="rst_n", cycles=4):
    getattr(dut, rst).value = 0
    for _ in range(cycles):
        await FallingEdge(getattr(dut, clk))
    getattr(dut, rst).value = 1
    await FallingEdge(getattr(dut, clk))


class StreamResult:
    def __init__(self):
        self.out = []          # (data, last) words received
        self.in_cycles = []    # cycle numbers of accepted input transfers
        self.out_cycles = []   # cycle numbers of output transfers
        self.cycles = 0
        self.violations = []


async def run_stream(dut, words, p_valid, p_ready, in_w, rng, clk="clk", max_cycles=200000,
                     expect_out=None, stall_window=None, extra=None, pre=None):
    """Drive `words` (list of (data, last)) through dut.s_axis_* and collect dut.m_axis_*.

    stall_window: optional (first_cycle, last_cycle) during which the sink is not ready.
    extra: optional callback(dut, cycle) invoked each cycle after sampling.
    pre: optional callback(dut, cycle, idx) invoked at the falling edge before driving; idx is the index of the
         word currently presented (or about to be) by the source, so a test can change a configuration input
         exactly at a word boundary.
    Returns a StreamResult. Stops when expect_out words were received (default: len(words)) and every input word was accepted.
    """
    clk_sig = getattr(dut, clk)
    res = StreamResult()
    idx = 0
    active = False
    prev_m = None  # (valid, ready, data, last) of the previous cycle
    prev_s = None
    if expect_out is None:
        expect_out = len(words)
    cyc = 0
    while (len(res.out) < expect_out or idx < len(words)) and cyc < max_cycles:
        await FallingEdge(clk_sig)
        if pre:
            pre(dut, cyc, idx)
        # source decision: once valid is raised it is held until the transfer
        if not active and idx < len(words) and rng.random() < p_valid:
            active = True
        if active:
            d, l = words[idx]
            dut.s_axis_valid.value = 1
            dut.s_axis_data.value = d
            dut.s_axis_last.value = int(l)
        else:
            dut.s_axis_valid.value = 0
            dut.s_axis_data.value = rng.getrandbits(in_w)
            dut.s_axis_last.value = rng.getrandbits(1)
        # sink decision
        if stall_window and stall_window[0] <= cyc <= stall_window[1]:
            mr = 0
        else:
            mr = 1 if rng.random() < p_ready else 0
        dut.m_axis_ready.value = mr
        await Timer(1, unit="ns")
        sv = int(dut.s_axis_valid.value)
        sr = int(dut.s_axis_ready.value)
        mv = int(dut.m_axis_valid.value)
        md = int(dut.m_axis_data.value) if mv else None
        ml = int(dut.m_axis_last.value) if mv else None
        # protocol checks
        if prev_m is not None and prev_m[0] and not prev_m[1]:
            if not mv or md != prev_m[2] or ml != prev_m[3]:
                res.violations.append((cyc, "master changed while stalled"))
        if sv and sr:
            res.in_cycles.append(cyc)
            idx += 1
            active = False
        if mv and mr:
            res.out.append((md, ml))
            res.out_cycles.append(cyc)
        prev_m = (mv, mr, md, ml)
        prev_s = (sv, sr)
        if extra:
            extra(dut, cyc)
        cyc += 1
    # the last accepted word transfers at the coming rising edge; release the source afterwards
    await FallingEdge(clk_sig)
    dut.s_axis_valid.value = 0
    res.cycles = cyc
    res.idx_in = idx
    return res
