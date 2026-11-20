import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer


@cocotb.test()
async def t11_08_integration_loop(dut):
    """T11-08 TX samples looped back by a behavioural radio into RX return unchanged; SPI and pins run at the same time"""
    rng = random.Random(118)
    cocotb.start_soon(Clock(dut.clk, 5000, unit="ps").start())
    cocotb.start_soon(Clock(dut.rx_clk, 8000, unit="ps").start())
    cocotb.start_soon(Clock(dut.tx_clk, 8000, unit="ps").start())
    for s in ("rx_valid", "tx_req", "rx_m_ready", "tx_s_valid", "tx_run", "spi_c_valid", "spi_r_ready", "miso", "force_safe"):
        getattr(dut, s).value = 0
    for s in ("rx_data", "tx_s_data", "spi_c_data", "lines", "pulses", "pll_val", "pin_sel", "pin_inv", "hop_sel", "safe_val"):
        getattr(dut, s).value = 0
    dut.spi_div.value = 2
    dut.spi_nbits.value = 24
    dut.rst_n.value = 0
    dut.rx_rst_n.value = 0
    dut.tx_rst_n.value = 0
    for _ in range(6):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    dut.rx_rst_n.value = 1
    dut.tx_rst_n.value = 1
    for _ in range(8):
        await FallingEdge(dut.clk)
    dut.tx_run.value = 1
    dut.rx_m_ready.value = 1
    dut.spi_r_ready.value = 1
    dut.pin_sel.value = 0x543210
    words = [rng.getrandbits(32) for _ in range(200)]
    out = []
    pins_seen = set()
    spi_resp = []

    async def radio():
        pipe = [(0, 0)] * 3
        while True:
            await FallingEdge(dut.tx_clk)
            dut.tx_req.value = 1
            await Timer(100, unit="ps")
            pipe = pipe[1:] + [(int(dut.tx_valid.value), int(dut.tx_data.value))]
            v, d = pipe[0]
            dut.rx_valid.value = v
            dut.rx_data.value = d

    async def sink():
        while True:
            await FallingEdge(dut.clk)
            await Timer(100, unit="ps")
            if int(dut.rx_m_valid.value):
                out.append(int(dut.rx_m_data.value))
            pins_seen.add(int(dut.pin.value))
            if int(dut.spi_r_valid.value):
                spi_resp.append(int(dut.spi_r_data.value))

    async def feeder():
        i = 0
        while i < len(words):
            await FallingEdge(dut.clk)
            dut.tx_s_valid.value = 1
            dut.tx_s_data.value = words[i]
            await Timer(100, unit="ps")
            if int(dut.tx_s_ready.value):
                i += 1
        await FallingEdge(dut.clk)
        dut.tx_s_valid.value = 0

    async def spi_and_pins():
        for k in range(6):
            await FallingEdge(dut.clk)
            dut.spi_c_valid.value = 1
            dut.spi_c_data.value = 0xA50000 + k
            await FallingEdge(dut.clk)
            dut.spi_c_valid.value = 0
            dut.lines.value = rng.getrandbits(16)
            await ClockCycles(dut.clk, 200)

    cocotb.start_soon(radio())
    cocotb.start_soon(sink())
    await cocotb.start_soon(feeder())
    await cocotb.start_soon(spi_and_pins())
    await ClockCycles(dut.clk, 200)
    assert out == words, f"{len(out)} of {len(words)} samples returned"
    assert len(spi_resp) == 6
    assert len(pins_seen) > 1
    assert int(dut.rx_overrun_cnt.value) == 0
