import math
import os
import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from dfts_model import MS, N_TO_MSEL, R, REFAMP_OF, dfts_rx, dfts_tx, ref_pos, unity_lut, used_bins
from stream_tb import reset, run_stream, start_clock
from test_dft import pack, unpack

N_LIST = [64, 128, 256, 512]


def mapper_like(rng, count, amp=2896):
    return [(rng.choice([-amp, amp]), rng.choice([-amp, amp])) for _ in range(count)]


# ======================= dfts_tx =======================
async def setup_tx(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "fft_log2", "ref_boost"):
        getattr(dut, n).value = 0
    dut.m_axis_ready.value = 1
    start_clock(dut.clk)
    await reset(dut)


@cocotb.test()
async def t31_03_tx(dut):
    """T31-03 dfts_tx bit-exact for N = 64..512, random handshakes, back-to-back symbols with changing N"""
    if os.environ.get("DUT") != "tx":
        return
    await setup_tx(dut)
    rng = random.Random(3103)
    order = [64, 128, 256, 512, 512, 64, 256, 128, 512, 256]
    words, starts, exp, ovf = [], {}, [], 0
    for n in order:
        m = MS[N_TO_MSEL[n]]
        data = mapper_like(rng, m - R, amp=rng.choice([2896, 1295, 4096]))
        bst = rng.getrandbits(1)
        bins, o = dfts_tx(data, n, bst)
        ovf += o
        starts[len(words)] = (n, bst)
        words += [(pack(a, b), i == m - R - 1) for i, (a, b) in enumerate(data)]
        exp += [(pack(a, b), i == n - 1) for i, (a, b) in enumerate(bins)]

    def pre(d, cyc, idx):
        if idx in starts:
            d.fft_log2.value = starts[idx][0].bit_length() - 1
            d.ref_boost.value = starts[idx][1]
        else:
            d.fft_log2.value = rng.randrange(16)      # sampled with the first sample only
            d.ref_boost.value = rng.getrandbits(1)

    r = await run_stream(dut, words, 0.85, 0.7, 32, rng, expect_out=len(exp), pre=pre, max_cycles=4000000)
    assert not r.violations, r.violations
    assert r.out == exp, "bins differ from the model"
    assert int(dut.ovf_cnt.value) == ovf
    # structure: zero outside the used set, reference symbols where defined
    pos = 0
    for n in order:
        m = MS[N_TO_MSEL[n]]
        sym = [unpack(w) for w, _ in r.out[pos:pos + n]]
        ub = set(used_bins(n))
        assert all(sym[b] == (0, 0) for b in range(n) if b not in ub)
        pos += n
    dut._log.info("dfts_tx: 10 symbols equal the model")


@cocotb.test()
async def t31_03b_tx_float(dut):
    """T31-03 the used bins equal the floating-point DFT of the symbol vector; clocks per symbol"""
    if os.environ.get("DUT") != "tx":
        return
    import numpy as np
    await setup_tx(dut)
    rng = random.Random(31031)
    for n, bst in [(n, b) for n in N_LIST for b in (0, 1)]:
        m = MS[N_TO_MSEL[n]]
        syms = [mapper_like(rng, m - R) for _ in range(4)]
        words = []
        for data in syms:
            words += [(pack(a, b), i == m - R - 1) for i, (a, b) in enumerate(data)]

        def pre(d, cyc, idx):
            d.fft_log2.value = n.bit_length() - 1
            d.ref_boost.value = bst

        r = await run_stream(dut, words, 1.0, 1.0, 32, rng, expect_out=4 * n, pre=pre, max_cycles=400000)
        for s, data in enumerate(syms):
            bins = [complex(*unpack(w)) for w, _ in r.out[s * n:(s + 1) * n]]
            d = []
            it = iter(data)
            pos = set(ref_pos(m))
            for k in range(m):
                if k in pos:
                    j = ref_pos(m).index(k)
                    d.append(complex(REFAMP_OF[bst] * (-1 if (0b11010010 >> j) & 1 else 1), 0))
                else:
                    d.append(complex(*next(it)))
            S = np.fft.fft(np.array(d)) / math.sqrt(m)             # p = 0..M-1 frequency order
            got = np.array([bins[b] for b in used_bins(n)])        # bin order: k = 1..M/2 then -M/2..-1
            ref = np.concatenate([S[m // 2:], S[:m // 2]])
            err = np.sqrt(np.mean(np.abs(got - ref) ** 2) / np.mean(np.abs(ref) ** 2))
            assert err < 0.005, (n, err)
        firsts = [r.out_cycles[s * n] for s in range(4)]
        dut._log.info(f"CLOCKS dfts_tx N={n} boost {bst}: symbol period {(firsts[-1] - firsts[1]) / 2:.0f} clocks (budget 2880), error vs float DFT {err:.4%}")


# ======================= dfts_rx =======================
async def setup_rx(dut):
    for n in ("s_axis_valid", "s_axis_data", "s_axis_last", "s_csi", "fft_log2", "ref_boost", "lut_we", "lut_addr", "lut_data"):
        getattr(dut, n).value = 0
    dut.csi_out.value = 0
    dut.m_axis_ready.value = 1
    start_clock(dut.clk)
    await reset(dut)
    for _ in range(300):                                 # gain table initialisation (256 clocks)
        await FallingEdge(dut.clk)


async def write_lut(dut, lut):
    for i, v in enumerate(lut):
        dut.lut_we.value = 1
        dut.lut_addr.value = i
        dut.lut_data.value = v
        await FallingEdge(dut.clk)
    dut.lut_we.value = 0
    await FallingEdge(dut.clk)


def rx_words(bins, csi, n):
    return [(pack(*bins[b]), b == n - 1) for b in range(n)], csi


async def run_rx(dut, syms, rng, pv, pr):
    """syms: list of (n, bins, csi, boost). Returns the run result"""
    words, csis, starts = [], [], {}
    for n, bins, csi, bst in syms:
        starts[len(words)] = (n, bst)
        for b in range(n):
            words.append((pack(*bins[b]), b == n - 1))
            csis.append(csi[b])
    exp_out = sum(MS[N_TO_MSEL[n]] - R for n, _, _, _ in syms)

    def pre(d, cyc, idx):
        if idx in starts:
            d.fft_log2.value = starts[idx][0].bit_length() - 1
            d.ref_boost.value = starts[idx][1]
        else:
            d.fft_log2.value = rng.randrange(16)
            d.ref_boost.value = rng.getrandbits(1)
        d.s_csi.value = csis[idx] if idx < len(csis) else 0

    r = await run_stream(dut, words, pv, pr, 32, rng, expect_out=exp_out, pre=pre, max_cycles=6000000)
    assert not r.violations, r.violations
    return r


def rotate(bins, phase, gain):
    c, s = math.cos(phase) * gain, math.sin(phase) * gain
    return [(int(round(a * c - b * s)), int(round(a * s + b * c))) for a, b in bins]


@cocotb.test()
async def t31_04_rx(dut):
    """T31-04 dfts_rx bit-exact (random weights, csi, rotations); transmit then receive returns the data"""
    if os.environ.get("DUT") != "rx":
        return
    import numpy as np
    await setup_rx(dut)
    rng = random.Random(3104)
    lut = [min(511, int(256 * c / (c + 40))) if c else 0 for c in range(256)]
    await write_lut(dut, lut)
    dut.csi_out.value = 77
    syms, exp, outs = [], [], []
    for n in [64, 256, 128, 512, 64, 512]:
        m = MS[N_TO_MSEL[n]]
        data = mapper_like(rng, m - R)
        bst = rng.getrandbits(1)
        bins, _ = dfts_tx(data, n, bst)
        bins = rotate(bins, rng.uniform(-1.0, 1.0), rng.uniform(0.5, 1.5))
        bins = [(a + rng.randint(-30, 30), b + rng.randint(-30, 30)) for a, b in bins]
        csi = [rng.randint(0, 255) for _ in range(n)]
        syms.append((n, bins, csi, bst))
        out, c_out, _ = dfts_rx(bins, csi, n, lut, 77, bst)
        exp += [(pack(a, b), i == len(out) - 1) for i, (a, b) in enumerate(out)]
        outs.append((data, out))
    r = await run_rx(dut, syms, rng, 0.9, 0.8)
    assert r.out == exp, "dfts_rx output differs from the model"
    # transmit then receive over an ideal channel with common rotation and gain, flat csi 128 and unity table
    await write_lut(dut, unity_lut())
    dut.csi_out.value = 128
    syms2, evm = [], []
    for n, bst in [(n, b) for n in N_LIST for b in (0, 1)]:
        m = MS[N_TO_MSEL[n]]
        data = mapper_like(rng, m - R)
        bins, _ = dfts_tx(data, n, bst)
        bins = rotate(bins, rng.uniform(-1.0, 1.0), rng.uniform(0.5, 1.5))
        syms2.append((n, bins, [128] * n, data, bst))
    r2 = await run_rx(dut, [(n, b, c, bst) for n, b, c, _, bst in syms2], rng, 1.0, 1.0)
    pos = 0
    for n, b, c, data, bst in syms2:
        k = len(data)
        got = np.array([complex(*unpack(w)) for w, _ in r2.out[pos:pos + k]])
        ref = np.array([complex(*a) for a in data])
        e = 20 * math.log10(math.sqrt(np.mean(np.abs(got - ref) ** 2)) / 4096)
        evm.append(round(e, 1))
        assert e < -35, (n, e)
        pos += k
    assert int(dut.m_csi.value) == 128
    dut._log.info(f"dfts_rx: bit-exact; ideal-channel EVM per N (dB): {evm}")
