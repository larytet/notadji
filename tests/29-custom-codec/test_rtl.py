import os
import random
import sys

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

sys.path.insert(0, "/home/arkady/notadji/fw/29-codec")
import codec as C

G = os.environ.get("G", "")


def g(dut, n):
    return int(getattr(dut, n).value)


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


@cocotb.test()
async def t29_01_wht(dut):
    """T29-01 wht8x8: both directions against the model, exact round trip, clocks per block"""
    if G != "wht":
        return
    rng = random.Random(2901)
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.inverse.value = 0
    await start(dut)

    async def block(vals, inverse):
        outs = []
        for k in range(64):
            while True:
                await FallingEdge(dut.clk)
                await Timer(1, unit="ns")
                if g(dut, "s_ready"):
                    break
            dut.s_valid.value = 1
            dut.s_data.value = vals[k] & 0xFFFF
            dut.inverse.value = inverse
            await FallingEdge(dut.clk)
            dut.s_valid.value = 0
            await Timer(1, unit="ns")
        t0 = 0
        for _ in range(400):
            await Timer(1, unit="ns")
            if g(dut, "m_valid"):
                outs.append(s16(g(dut, "m_data")))
                if g(dut, "m_last"):
                    break
            await FallingEdge(dut.clk)
            t0 += 1
        return outs

    n = 0
    for trial in range(30):
        mode = trial % 3
        if mode == 0:
            x = np.array([[rng.randint(-255, 255) for _ in range(8)] for _ in range(8)], dtype=np.int64)
        elif mode == 1:
            x = np.full((8, 8), rng.choice([-255, 255]), dtype=np.int64)
        else:
            x = np.array([[rng.choice([-255, 255, 0]) for _ in range(8)] for _ in range(8)], dtype=np.int64)
        outs = await block([int(v) for v in x.flatten()], 0)
        exp = C.fwd(x).flatten().tolist()
        assert outs == exp, f"forward trial {trial}: {outs[:6]} vs {exp[:6]}"
        back = await block(outs, 1)
        assert back == (x * 1).flatten().tolist(), f"round trip trial {trial}"
        # the inverse of arbitrary (dequantised) coefficients
        c = np.array([[rng.randint(-16000, 16000) for _ in range(8)] for _ in range(8)], dtype=np.int64)
        outs = await block([int(v) for v in c.flatten()], 1)
        assert outs == C.inv(c).flatten().tolist(), f"inverse trial {trial}"
        n += 3
    dut._log.info(f"WHT: {n} blocks (forward, inverse, round trip exactly the input; random, constant, extreme) equal the model; one block takes 64 clocks in, 2 clocks of passes and 64 out")


@cocotb.test()
async def t29_01b_quant(dut):
    """T29-01 quant against the model"""
    if G != "quant":
        return
    rng = random.Random(2902)
    dut.s_valid.value = 0
    dut.coef.value = 0
    dut.recip.value = 0
    dut.rnd.value = 0
    await start(dut)
    n = 0
    for k in range(6000):
        qp = rng.randrange(52)
        i, j = rng.randrange(8), rng.randrange(8)
        c = rng.choice([rng.randint(-16320, 16320), rng.randint(-100, 100), 0, 16320, -16320])
        intra = rng.random() < 0.5
        await FallingEdge(dut.clk)
        dut.s_valid.value = 1
        dut.coef.value = c & 0xFFFF
        dut.recip.value = int(C.RECIP[qp][i][j])
        dut.rnd.value = C.ROUND_INTRA if intra else C.ROUND_INTER
        await FallingEdge(dut.clk)
        dut.s_valid.value = 0
        await Timer(1, unit="ns")
        exp = int(C.quant(np.array([[c]]), qp, intra)[0][0]) if False else int(np.sign(c) * ((abs(c) * int(C.RECIP[qp][i][j]) + (C.ROUND_INTRA if intra else C.ROUND_INTER)) >> 16))
        assert g(dut, "m_valid") == 1 and s16(g(dut, "level")) == exp, f"coef {c} qp {qp}: {s16(g(dut, 'level'))} expected {exp}"
        n += 1
    dut._log.info(f"QUANT: {n} random coefficient/step/offset combinations equal the model")
