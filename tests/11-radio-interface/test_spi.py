import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge, Timer


async def setup(dut, div, nbits):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.div.value = div
    dut.nbits.value = nbits
    dut.s_axis_valid.value = 0
    dut.s_axis_data.value = 0
    dut.m_axis_ready.value = 1
    dut.miso.value = 0
    dut.rst_n.value = 0
    for _ in range(4):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


class Slave:
    """SPI mode 0 slave: shifts out the reply words (MSB first) and records the bits seen on MOSI at rising SCLK edges."""

    def __init__(self, dut, nbits, replies):
        self.dut, self.nbits, self.replies = dut, nbits, list(replies)
        self.frames = []
        self.task = cocotb.start_soon(self.run())

    async def run(self):
        d = self.dut
        k = 0
        prev_sclk, prev_cs = 0, 1
        bits, reply = [], 0
        while True:
            await Timer(1, unit="ns")
            sclk, cs = int(d.sclk.value), int(d.cs_n.value)
            if prev_cs == 1 and cs == 0:                      # frame start
                reply = self.replies[k % len(self.replies)]
                k += 1
                bits = []
                d.miso.value = (reply >> (self.nbits - 1)) & 1
            elif cs == 0 and prev_sclk == 0 and sclk == 1:     # rising edge: sample MOSI
                bits.append(int(d.mosi.value))
            elif cs == 0 and prev_sclk == 1 and sclk == 0:     # falling edge: next MISO bit
                n = len(bits)
                if n < self.nbits:
                    d.miso.value = (reply >> (self.nbits - 1 - n)) & 1
            if prev_cs == 0 and cs == 1:
                self.frames.append(bits)
            prev_sclk, prev_cs = sclk, cs
            await Timer(1, unit="ns")

    def stop(self):
        self.task.cancel()


@cocotb.test()
async def t11_01_02_spi(dut):
    """T11-01/02 SPI waveform, MSB first, frame length, read-back, queueing, chip-select gap"""
    rng = random.Random(111)
    for div in (1, 2, 5):
        for nbits in (8, 16, 24, 32):
            await setup(dut, div, nbits)
            cmds = [rng.getrandbits(32) & ((1 << nbits) - 1) for _ in range(6)]
            replies = [rng.getrandbits(32) & ((1 << nbits) - 1) for _ in range(6)]
            slave = Slave(dut, nbits, replies)
            sclk_rises, cs_trace, sclk_trace = [], [], []

            async def mon():
                n = 0
                while True:
                    await FallingEdge(dut.clk)
                    cs_trace.append(int(dut.cs_n.value))
                    sclk_trace.append(int(dut.sclk.value))

            m = cocotb.start_soon(mon())
            got = []

            async def collect():
                while True:
                    await FallingEdge(dut.clk)
                    if int(dut.m_axis_valid.value) and int(dut.m_axis_ready.value):
                        got.append(int(dut.m_axis_data.value))

            c = cocotb.start_soon(collect())
            # queue the commands (the command FIFO holds 8)
            for w in cmds:
                dut.s_axis_valid.value = 1
                dut.s_axis_data.value = w
                while True:
                    await Timer(1, unit="ns")
                    ok = int(dut.s_axis_ready.value)
                    await FallingEdge(dut.clk)
                    if ok:
                        break
            dut.s_axis_valid.value = 0
            await ClockCycles(dut.clk, 6 * (nbits * 2 * div + 8 * div + 20))
            m.cancel(); c.cancel(); slave.stop()
            assert [int("".join(map(str, f)), 2) for f in slave.frames] == cmds, f"div={div} nbits={nbits}: MOSI frames"
            assert all(len(f) == nbits for f in slave.frames)
            assert got == replies, f"div={div} nbits={nbits}: read-back {got} vs {replies}"
            # SCLK idle low while CS is high; SCLK period 2*div clocks inside a frame
            assert all(s == 0 for s, c_ in zip(sclk_trace, cs_trace) if c_ == 1)
            rises = [i for i in range(1, len(sclk_trace)) if sclk_trace[i] == 1 and sclk_trace[i - 1] == 0]
            periods = {b - a for a, b in zip(rises, rises[1:]) if b - a < 4 * div + 2}
            assert periods <= {2 * div}, f"SCLK periods {periods}"
            # chip select high for at least two half periods between frames
            falls = [i for i in range(1, len(cs_trace)) if cs_trace[i] == 0 and cs_trace[i - 1] == 1]
            highs = [i for i in range(1, len(cs_trace)) if cs_trace[i] == 1 and cs_trace[i - 1] == 0]
            for hi, nxt in zip(highs, falls[1:]):
                assert nxt - hi >= 2 * div, f"CS high gap {nxt - hi} clocks"
