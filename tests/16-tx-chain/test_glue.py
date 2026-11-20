import os
import random

import cocotb
from cocotb.triggers import ClockCycles, Timer

from stream_tb import reset, run_stream, start_clock

G = os.environ.get("G", "")


async def setup(dut, **inputs):
    for k, v in inputs.items():
        getattr(dut, k).value = v
    for sig, val in (("s_valid", 0), ("s_data", 0), ("s_last", 0), ("m_ready", 1)):
        if hasattr(dut, sig):
            getattr(dut, sig).value = val
    start_clock(dut.clk)
    await reset(dut)


@cocotb.test()
async def t16_01a_msg_bits_pack(dut):
    """T16-01 msg_bits_pack: K-bit words, zero padding, frame flag"""
    if G != "pack":
        return
    rng = random.Random(1611)
    for k in (324, 540, 972, 1620):
        await setup(dut, k_bits=k)
        for nbits in (1, 31, 32, 33, k - 1, k, k + 1, 2 * k, 2 * k + 7, 1000):
            bits = [rng.getrandbits(1) for _ in range(nbits)]
            ncw = max(1, -(-nbits // k))
            pad = bits + [0] * (ncw * k - nbits)
            exp, flags = [], []
            for c in range(ncw):
                cw = pad[c * k:(c + 1) * k]
                nw = -(-k // 32)
                for w in range(nw):
                    word = sum(b << i for i, b in enumerate(cw[w * 32:(w + 1) * 32]))
                    exp.append((word, w == nw - 1))
                    flags.append(int(c == ncw - 1 and w == nw - 1))
            got_fl = []

            def extra(d, cyc):
                if int(d.m_valid.value) and int(d.m_ready.value):
                    got_fl.append(int(d.m_frame_last.value))

            words = [(b, i == nbits - 1) for i, b in enumerate(bits)]
            for pv, pr in ((1.0, 1.0), (0.6, 0.5)):
                got_fl.clear()
                res = await run_stream(dut, words, pv, pr, 1, rng, expect_out=len(exp), sp="s", mp="m", extra=extra)
                assert res.out == exp, f"k={k} nbits={nbits} pv={pv}"
                assert [f for (w, l), f in zip(res.out, got_fl) if l] == [f for (w, l), f in zip(exp, flags) if l]
                await ClockCycles(dut.clk, 6)


@cocotb.test()
async def t16_01b_cw_to_bits(dut):
    """T16-01 cw_to_bits: N bits per codeword, frame flag"""
    if G != "cw":
        return
    rng = random.Random(1612)
    for n in (648, 1944):
        await setup(dut, n_bits=n, s_fl=0)
        ncw = 5
        cws = [[rng.getrandbits(1) for _ in range(n)] for _ in range(ncw)]
        nw = -(-n // 32)
        words, widx_cw = [], []
        for c, cw in enumerate(cws):
            pad = cw + [rng.getrandbits(1) for _ in range(nw * 32 - n)]       # garbage above N must be ignored
            for w in range(nw):
                words.append((sum(b << i for i, b in enumerate(pad[w * 32:(w + 1) * 32])), w == nw - 1))
                widx_cw.append(c)
        flags = [int(c == ncw - 1) for c in range(ncw)]
        exp = [(b, int(i == n - 1)) for cw in cws for i, b in enumerate(cw)]
        fl_got = []

        def pre(d, cyc, idx):
            d.s_fl.value = flags[widx_cw[min(idx, len(widx_cw) - 1)]]

        def extra(d, cyc):
            if int(d.m_valid.value) and int(d.m_ready.value) and int(d.m_last.value):
                fl_got.append(int(d.m_fl.value))

        for pv, pr in ((1.0, 1.0), (0.6, 0.5)):
            fl_got.clear()
            res = await run_stream(dut, words, pv, pr, 32, rng, expect_out=len(exp), sp="s", mp="m", pre=pre, extra=extra)
            assert res.out == exp, f"n={n} pv={pv}"
            assert fl_got == flags, f"frame flags {fl_got}"


@cocotb.test()
async def t16_01c_sym_blocker(dut):
    """T16-01 sym_blocker: blocks of Ncbps, zero padding, block pulses and the final flag"""
    if G != "blk":
        return
    rng = random.Random(1613)
    for ncbps in (96, 234, 1404):
        await setup(dut, ncbps=ncbps, s_fl=0)
        ncw, n = 3, 648
        total = ncw * n
        bits = [rng.getrandbits(1) for _ in range(total)]
        nblk = -(-total // ncbps)
        pad = bits + [0] * (nblk * ncbps - total)
        exp = [(b, int(i % ncbps == ncbps - 1)) for i, b in enumerate(pad)]
        words = [(b, i % n == n - 1) for i, b in enumerate(bits)]
        pulses = []

        def pre(d, cyc, idx):
            d.s_fl.value = int(idx == total - 1)

        def extra(d, cyc):
            if int(d.blk_pulse.value):
                pulses.append(int(d.blk_fl.value))

        for pv, pr in ((1.0, 1.0), (0.6, 0.5)):
            pulses.clear()
            res = await run_stream(dut, words, pv, pr, 1, rng, expect_out=len(exp), sp="s", mp="m", pre=pre, extra=extra)
            await ClockCycles(dut.clk, 4)
            assert res.out == exp, f"ncbps={ncbps} pv={pv}"
            assert pulses == [0] * (nblk - 1) + [1], f"block pulses {pulses}"


@cocotb.test()
async def t16_01d_bit_packer(dut):
    """T16-01 bit_packer: nb bits per tone word, bit 0 first, last per block"""
    if G != "bp":
        return
    rng = random.Random(1614)
    for nb in (1, 2, 4, 6, 8):
        await setup(dut, nb=nb)
        ntone = 30
        bits = [rng.getrandbits(1) for _ in range(ntone * nb)]
        exp = [(sum(bits[t * nb + b] << b for b in range(nb)), int(t == ntone - 1)) for t in range(ntone)]
        words = [(b, i == ntone * nb - 1) for i, b in enumerate(bits)]
        for pv, pr in ((1.0, 1.0), (0.6, 0.5)):
            res = await run_stream(dut, words, pv, pr, 1, rng, expect_out=len(exp), sp="s", mp="m")
            assert res.out == exp, f"nb={nb} pv={pv}"


@cocotb.test()
async def t16_01e_assembler(dut):
    """T16-01 tx_assembler: nulls give 0, data bins take mapper samples, pilot bins take the plan value"""
    if G != "asm":
        return
    rng = random.Random(1615)
    for t, expect_map in ((0, False), (1, True), (2, False)):
        for pgv in (0, 1):
            for mpv in (0, 1):
                for mr in (0, 1):
                    dut.pg_valid.value = pgv
                    dut.pg_data.value = (t << 32) | 0x12345678
                    dut.pg_last.value = 1
                    dut.mp_valid.value = mpv
                    dut.mp_data.value = 0xCAFEF00D
                    dut.m_ready.value = mr
                    await Timer(1, unit="ns")
                    ok = pgv and (not expect_map or mpv)
                    assert int(dut.m_valid.value) == int(bool(ok)), f"t={t} pg={pgv} mp={mpv}"
                    assert int(dut.pg_ready.value) == int(bool(mr and (not expect_map or mpv)))
                    assert int(dut.mp_ready.value) == int(bool(mr and pgv and expect_map))
                    if ok:
                        want = 0xCAFEF00D if t == 1 else (0x12345678 if t == 2 else 0)
                        assert int(dut.m_data.value) == want
                        assert int(dut.m_last.value) == 1
