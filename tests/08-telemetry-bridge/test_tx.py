import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from tb_common import start


async def record(dut, wave, busy):
    while True:
        await FallingEdge(dut.clk)
        wave.append(int(dut.txd.value))
        busy.append(int(dut.busy.value))


async def feed(dut, data, gap=0):
    """Present bytes, holding valid until ready; `gap` idle clocks between bytes (aligned to the falling edge)."""
    await FallingEdge(dut.clk)
    for b in data:
        for _ in range(gap):
            dut.s_axis_valid.value = 0
            await FallingEdge(dut.clk)
        dut.s_axis_valid.value = 1
        dut.s_axis_data.value = b
        while True:
            await Timer(1, unit="ns")
            ok = int(dut.s_axis_ready.value)
            await FallingEdge(dut.clk)
            if ok:
                break
    dut.s_axis_valid.value = 0


def decode(wave, div):
    """Decode a recorded txd waveform into bytes, checking exact bit timing. Returns (bytes, start_indices)."""
    out, starts = [], []
    i = 0
    while i < len(wave):
        if wave[i] == 0:
            starts.append(i)
            assert all(w == 0 for w in wave[i:i + div]), f"start bit not {div} clocks at {i}"
            byte = 0
            for k in range(8):
                seg = wave[i + div * (1 + k): i + div * (2 + k)]
                assert len(set(seg)) == 1, f"data bit {k} not stable for {div} clocks at {i}"
                byte |= seg[0] << k
            stop = wave[i + 9 * div: i + 10 * div]
            assert stop == [1] * div, f"stop bit not high for {div} clocks at {i}"
            out.append(byte)
            i += 10 * div
        else:
            i += 1
    return out, starts


@cocotb.test()
async def t8_03_waveform(dut):
    """T8-03 start, 8 data LSB first, stop, each exactly div clocks; back-to-back without a gap; busy"""
    dut.s_axis_valid.value = 0
    dut.s_axis_data.value = 0
    dut.div.value = 8
    await start(dut)
    rng = random.Random(83)
    for div in (4, 8, 66):
        dut.div.value = div
        await ClockCycles(dut.clk, 4)
        for gap in (0, 3 * div):
            wave, busy = [], []
            t = cocotb.start_soon(record(dut, wave, busy))
            data = [rng.getrandbits(8) for _ in range(12)]
            await feed(dut, data, gap)
            await ClockCycles(dut.clk, 12 * div)
            t.cancel()
            out, starts = decode(wave, div)
            assert out == data, f"div={div} gap={gap}"
            if gap == 0:
                spacing = [b - a for a, b in zip(starts, starts[1:])]
                assert all(s == 10 * div for s in spacing), f"gaps between back-to-back bytes: {sorted(set(spacing))}"
            # busy is high exactly while the frame is on the line
            assert sum(busy) >= 10 * div * len(data) - len(data) * 2
            assert busy[-1] == 0
