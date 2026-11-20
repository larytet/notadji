import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, Timer

from aead_ref import ChaCha20Poly1305, le, seal
from stream_tb import reset, run_stream, start_clock


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 1
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    dut.key.value = 0
    dut.nonce.value = 0
    dut.aad_len.value = 0
    dut.decrypt.value = 0
    start_clock(dut.clk)
    await reset(dut)


class Status:
    def __init__(self, dut):
        self.items = []
        self.dut = dut
        self.task = cocotb.start_soon(self.run())

    async def run(self):
        d = self.dut
        while True:
            await FallingEdge(d.clk)
            if int(d.st_valid.value):
                self.items.append((int(d.st_ok.value), int(d.st_short.value)))

    def stop(self):
        self.task.cancel()


async def run_frame(dut, key, nonce, aad_len, decrypt, frame_in, exp_len, pv=1.0, pr=1.0, seed=0):
    rng = random.Random(seed)
    dut.key.value = le(key)
    dut.nonce.value = le(nonce)
    dut.aad_len.value = aad_len
    dut.decrypt.value = int(decrypt)
    st = Status(dut)
    words = [(b, i == len(frame_in) - 1) for i, b in enumerate(frame_in)]
    res = await run_stream(dut, words, pv, pr, 8, rng, expect_out=exp_len)
    for _ in range(4000):
        if st.items:
            break
        await FallingEdge(dut.clk)
    await ClockCycles(dut.clk, 3)
    st.stop()
    assert len(st.items) == 1, f"status pulses {st.items}"
    return [b for b, _ in res.out], [l for _, l in res.out], st.items[0], res


def rnd(rng, n):
    return [rng.getrandbits(8) for _ in range(n)]


PAYLOADS = [0, 1, 15, 16, 17, 63, 64, 65, 127, 128, 129, 200]
AADS = [0, 1, 8, 13, 16, 20]


@cocotb.test()
async def t15_03_encrypt(dut):
    """T15-03 whole-construction encrypt equals the reference for many AAD and payload lengths"""
    await setup(dut)
    rng = random.Random(153)
    for a in AADS:
        for n in PAYLOADS:
            if a + n == 0:
                continue
            key, nonce = rnd(rng, 32), rnd(rng, 12)
            aad, pt = rnd(rng, a), rnd(rng, n)
            exp = seal(key, nonce, aad, pt)
            out, lasts, st, res = await run_frame(dut, key, nonce, a, False, aad + pt, len(exp), seed=a * 1000 + n)
            assert out == exp, f"aad={a} payload={n}"
            assert lasts == [0] * (len(exp) - 1) + [1], "last must be on the final tag byte"
            assert st == (1, 0)
            assert not res.violations


@cocotb.test()
async def t15_04_decrypt(dut):
    """T15-04 decrypt returns AAD || plaintext with st_ok = 1"""
    await setup(dut)
    rng = random.Random(154)
    for a in AADS:
        for n in PAYLOADS:
            key, nonce = rnd(rng, 32), rnd(rng, 12)
            aad, pt = rnd(rng, a), rnd(rng, n)
            frame = seal(key, nonce, aad, pt)
            exp = aad + pt
            out, lasts, st, res = await run_frame(dut, key, nonce, a, True, frame, len(exp), seed=a * 1000 + n)
            assert out == exp, f"aad={a} payload={n}"
            assert st == (1, 0), f"aad={a} payload={n}: status {st}"
            if exp:
                assert lasts == [0] * (len(exp) - 1) + [1]


@cocotb.test()
async def t15_05_tamper(dut):
    """T15-05 any single flipped bit, a wrong nonce or a wrong key is detected"""
    await setup(dut)
    rng = random.Random(155)
    for k in range(200):
        a, n = rng.randint(0, 10), rng.randint(1 if True else 0, 80)
        key, nonce = rnd(rng, 32), rnd(rng, 12)
        aad, pt = rnd(rng, a), rnd(rng, n)
        frame = seal(key, nonce, aad, pt)
        bit = rng.randrange(8 * len(frame))
        bad = list(frame)
        bad[bit // 8] ^= 1 << (bit % 8)
        out, lasts, st, res = await run_frame(dut, key, nonce, a, True, bad, len(frame) - 16, seed=k)
        assert st[0] == 0, f"bit {bit} of a {len(frame)}-byte frame (aad {a}) was not detected"
    for k in range(10):
        key, nonce = rnd(rng, 32), rnd(rng, 12)
        aad, pt = rnd(rng, 8), rnd(rng, 40)
        frame = seal(key, nonce, aad, pt)
        wrong_nonce = list(nonce)
        wrong_nonce[0] ^= 1
        out, _, st, _ = await run_frame(dut, key, wrong_nonce, 8, True, frame, len(frame) - 16)
        assert st[0] == 0
        wrong_key = list(key)
        wrong_key[31] ^= 0x80
        out, _, st, _ = await run_frame(dut, wrong_key, nonce, 8, True, frame, len(frame) - 16)
        assert st[0] == 0


@cocotb.test()
async def t15_06_short(dut):
    """T15-06 frames shorter than aad_len + 16 are flagged; empty payload works; the next frame is fine"""
    await setup(dut)
    rng = random.Random(156)
    key, nonce = rnd(rng, 32), rnd(rng, 12)
    out, _, st, _ = await run_frame(dut, key, nonce, 4, True, rnd(rng, 10), 0)
    assert st == (0, 1) and out == []
    out, _, st, _ = await run_frame(dut, key, nonce, 4, True, rnd(rng, 18), 2)       # 18 bytes with 4 AAD bytes: payload would be negative
    assert st == (0, 1), f"status {st}"
    # 16-byte frame with aad_len 0: empty message, valid tag
    frame = seal(key, nonce, [], [])
    assert len(frame) == 16
    out, _, st, _ = await run_frame(dut, key, nonce, 0, True, frame, 0)
    assert st == (1, 0) and out == []
    # AAD only, encrypt and decrypt
    aad = rnd(rng, 9)
    exp = seal(key, nonce, aad, [])
    out, _, st, _ = await run_frame(dut, key, nonce, 9, False, aad, len(exp))
    assert out == exp and st == (1, 0)
    out, _, st, _ = await run_frame(dut, key, nonce, 9, True, exp, 9)
    assert out == aad and st == (1, 0)
    # a normal frame after the errors
    pt = rnd(rng, 50)
    frame = seal(key, nonce, aad, pt)
    out, _, st, _ = await run_frame(dut, key, nonce, 9, True, frame, 9 + 50)
    assert out == aad + pt and st == (1, 0)


@cocotb.test()
async def t15_07_handshakes_and_sequence(dut):
    """T15-07 random handshakes, frames back to back with different keys, nonces, AAD lengths and modes"""
    await setup(dut)
    rng = random.Random(157)
    for k in range(60):
        key, nonce = rnd(rng, 32), rnd(rng, 12)
        a, n = rng.randint(0, 20), rng.randint(1, 150)
        aad, pt = rnd(rng, a), rnd(rng, n)
        frame = seal(key, nonce, aad, pt)
        pv, pr = rng.choice([(1.0, 1.0), (0.5, 0.5), (0.9, 0.2), (0.3, 0.9)])
        if rng.random() < 0.5:
            out, lasts, st, res = await run_frame(dut, key, nonce, a, False, aad + pt, len(frame), pv, pr, seed=k)
            assert out == frame and st == (1, 0)
        else:
            out, lasts, st, res = await run_frame(dut, key, nonce, a, True, frame, a + n, pv, pr, seed=k)
            assert out == aad + pt and st == (1, 0)
        assert not res.violations


@cocotb.test()
async def t15_08_throughput(dut):
    """T15-08 bytes per clock for a 1200-byte payload"""
    await setup(dut)
    rng = random.Random(158)
    key, nonce = rnd(rng, 32), rnd(rng, 12)
    aad, pt = rnd(rng, 8), rnd(rng, 1200)
    exp = seal(key, nonce, aad, pt)
    out, lasts, st, res = await run_frame(dut, key, nonce, 8, False, aad + pt, len(exp))
    assert out == exp
    clocks = res.out_cycles[-1] - res.in_cycles[0]
    rate = 1208 / clocks
    dut._log.info(f"THROUGHPUT encrypt 1208 bytes in {clocks} clocks: {rate:.3f} byte/clock = {rate * 200 * 8:.0f} Mbit/s at 200 MHz")
    assert rate >= 0.5, f"{rate} byte per clock"
