import random

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from tb_common import *
from test_tx import decode, feed


async def setup_top(dut, proto=1, div=8):
    dut.rxd.value = 1
    dut.s_axis_valid.value = 0
    dut.s_axis_data.value = 0
    dut.m_axis_ready.value = 1
    dut.div.value = div
    dut.proto.value = proto
    dut.idle_bits.value = 20
    dut.max_len.value = 511
    await start(dut)


@cocotb.test()
async def t8_12_top(dut):
    """T8-12 uplink frames, downlink bytes, and overflow with a stalled sink"""
    div = 8
    await setup_top(dut, 1, div)
    rng = random.Random(92)
    frames = [mav1(rng, 9), mav2(rng, 30), mav2(rng, 4, signed=True)]
    got = []
    ovf = []
    ferr = []

    async def mon():
        while True:
            await FallingEdge(dut.clk)
            if int(dut.m_axis_valid.value) and int(dut.m_axis_ready.value):
                got.append((int(dut.m_axis_data.value), int(dut.m_axis_last.value), int(dut.m_axis_err.value)))
            ovf.append(int(dut.rx_overflow.value))
            ferr.append(int(dut.rx_frame_err.value))

    m = cocotb.start_soon(mon())
    await ClockCycles(dut.clk, 5 * div)
    for f in frames:
        for b in f:
            await uart_send(dut, dut.rxd, b, div)
    await ClockCycles(dut.clk, 40 * div)
    assert got == [x for f in frames for x in as_out(f)]
    assert sum(ovf) == 0 and sum(ferr) == 0
    # downlink: bytes into the stream appear on txd
    wave = []

    async def rec():
        while True:
            await FallingEdge(dut.clk)
            wave.append(int(dut.txd.value))

    rc = cocotb.start_soon(rec())
    data = [rng.getrandbits(8) for _ in range(10)]
    await feed(dut, data)
    await ClockCycles(dut.clk, 14 * div)
    rc.cancel()
    out, _ = decode(wave, div)
    assert out == data
    # overflow: sink stalled, a burst of back-to-back bytes bigger than the FIFO plus output register
    dut.proto.value = 0            # raw mode: every byte is kept, so a stalled sink backs up into the FIFO
    dut.m_axis_ready.value = 0
    got.clear()
    ovf.clear()
    for b in rnd_payload(rng, 40):
        await uart_send(dut, dut.rxd, b, div)
    await ClockCycles(dut.clk, 20 * div)
    assert sum(ovf) > 0, "rx_overflow never raised with a stalled sink"
    m.cancel()
