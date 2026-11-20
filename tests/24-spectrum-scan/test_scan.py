import os
import random

import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

G = os.environ.get("G", "")


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def pack(i, q):
    return ((q & 0xFFFF) << 16) | (i & 0xFFFF)


def power(w):
    i, q = s16(w & 0xFFFF), s16((w >> 16) & 0xFFFF)
    return i * i + q * q


def lg_model(x):
    if x == 0:
        return 0
    p = x.bit_length() - 1
    m = ((x << (47 - p)) >> 43) & 15
    return 16 * p + m


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1


def g(dut, n):
    return int(getattr(dut, n).value)


def rand_sample(rng, mode):
    if mode == 0:
        return pack(rng.randint(-32768, 32767), rng.randint(-32768, 32767))
    if mode == 1:
        return pack(-32768, -32768)
    return pack(rng.randint(-300, 300), rng.randint(-300, 300))


@cocotb.test()
async def t24_01_meas(dut):
    """T24-01 one dwell: exact energy sum, logarithm, timing, start while busy"""
    if G != "meas":
        return
    rng = random.Random(2401)
    dut.start.value = 0
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.settle_ticks.value = 0
    dut.dwell_ticks.value = 1
    await start(dut)
    cases = [(0, 1), (3, 1), (0, 5), (200, 2000), (7, 64)] + [(rng.randint(0, 200), rng.randint(1, 600)) for _ in range(25)]
    for n, (settle, dwell) in enumerate(cases):
        mode = 1 if n == 4 else rng.choice([0, 2])
        pv = rng.choice([1.0, 0.5, 0.2])
        await FallingEdge(dut.clk)
        dut.settle_ticks.value = settle
        dut.dwell_ticks.value = dwell
        dut.start.value = 1
        dut.s_valid.value = 1                       # a strobe in the start clock is not part of the measurement
        dut.s_data.value = rand_sample(rng, 0)
        stream = []
        await FallingEdge(dut.clk)
        dut.start.value = 0
        k = 0
        done_seen = None
        counted = 0
        busy_low_early = False
        while done_seen is None:
            v = rng.random() < pv
            w = rand_sample(rng, mode)
            dut.s_valid.value = int(v)
            dut.s_data.value = w
            if k == 3 and settle > 5:
                dut.start.value = 1                 # ignored: busy
            else:
                dut.start.value = 0
            await Timer(1, unit="ns")
            if g(dut, "done"):
                done_seen = k
                break
            stream.append((v, w))
            k += 1
            await FallingEdge(dut.clk)
            if k > 400000:
                assert False, "no done"
        # model: the strobes after start; the settle strobes are skipped
        strobes = [w for v, w in stream if v]
        # done appears one iteration after the last counted strobe was driven: the last iteration's data is not part of it
        win = strobes[settle:settle + dwell]
        exp = sum(power(w) for w in win)
        assert len(strobes) == settle + dwell, f"case {n}: {len(strobes)} strobes before done, expected {settle + dwell}"
        assert g(dut, "sum") == exp, f"case {n}: sum {g(dut, 'sum')} expected {exp}"
        assert g(dut, "lg") == lg_model(exp), f"case {n}: lg {g(dut, 'lg')} expected {lg_model(exp)}"
        assert g(dut, "sat") == 0
        # the numpy value
        arr = np.array([[s16(w & 0xFFFF), s16((w >> 16) & 0xFFFF)] for w in win], dtype=np.int64)
        assert int((arr ** 2).sum()) == exp
        if exp > 0:
            assert abs(lg_model(exp) / 16 - np.log2(exp)) < 0.0861 + 1 / 16, f"log error at {exp}"
        await FallingEdge(dut.clk)
        dut.s_valid.value = 0
        await Timer(1, unit="ns")
        assert g(dut, "busy") == 0
    n_ign = sum(1 for (settle, dwell) in cases if settle > 5)
    assert g(dut, "ovr_cnt") == n_ign, f"ovr_cnt {g(dut, 'ovr_cnt')} expected {n_ign}"
    dut._log.info(f"MEAS: {len(cases)} dwells equal the exact sum and the integer logarithm, {n_ign} starts while busy ignored and counted")


def next_ch(ptr, have, mask, n_ch, home):
    for k in range(1, 33):
        c = (ptr + k) % 32
        if c < n_ch and (mask >> c) & 1 and c != home:
            return c
    return None


@cocotb.test()
async def t24_02_04_engine(dut):
    """T24-02..04 scan engine: sequence, table, timing"""
    if G != "eng":
        return
    rng = random.Random(2402)
    for run in range(5):
        n_ch = rng.choice([6, 12, 24, 32])
        mask = rng.getrandbits(32) | 0x3
        if run == 4:
            mask = 0
        home = rng.randrange(n_ch)
        settle, dwell = rng.randint(0, 30), rng.randint(1, 120)
        pv = rng.choice([1.0, 0.5, 0.25])
        thr = 5_000_000
        for n_ in ("slot", "rx_ready", "clear", "s_valid"):
            getattr(dut, n_).value = 0
        dut.ch_mask.value = mask
        dut.n_ch.value = n_ch
        dut.settle_ticks.value = settle
        dut.dwell_ticks.value = dwell
        dut.strong_thr.value = thr
        dut.home.value = home
        dut.tmo_ticks.value = 0
        dut.rd_ch.value = 0
        await start(dut)
        amp = [rng.choice([5, 50, 500, 3000]) for _ in range(32)]
        tuned = home
        table = {}
        order = []
        ptr, have, sweeps = 31, False, 0
        nslots = 3 * n_ch + 2
        cyc = 0
        for slot_no in range(nslots):
            await FallingEdge(dut.clk)
            dut.s_valid.value = 0
            dut.slot.value = 1
            await FallingEdge(dut.clk)
            dut.slot.value = 0
            # wait for retune_req
            exp_c = next_ch(ptr, have, mask, n_ch, home)
            rt = None
            for _ in range(5):
                await Timer(1, unit="ns")
                if g(dut, "retune_req"):
                    rt = (g(dut, "retune_ch"), g(dut, "back"))
                if g(dut, "slot_done"):
                    break
                await FallingEdge(dut.clk)
            if exp_c is None:
                assert g(dut, "no_ch") or rt is None, "no channel enabled: expected no_ch"
                continue
            assert rt == (exp_c, 0), f"slot {slot_no}: retune {rt} expected {(exp_c, 0)}"
            if have and exp_c <= ptr:
                sweeps += 1
            ptr, have = exp_c, True
            order.append(exp_c)
            tuned = exp_c
            delay = rng.randint(0, 6)
            for _ in range(delay):
                await FallingEdge(dut.clk)
            await FallingEdge(dut.clk)
            dut.rx_ready.value = 1
            kr = 0
            log = []
            await FallingEdge(dut.clk)
            dut.rx_ready.value = 0
            # stream samples
            result_ch = None
            done_at = None
            back_seen = False
            n_str = 0
            for cyc in range(100000):
                v = rng.random() < pv
                w = pack(int(rng.gauss(0, amp[tuned])), int(rng.gauss(0, amp[tuned])))
                dut.s_valid.value = int(v)
                dut.s_data.value = w
                await Timer(1, unit="ns")
                if g(dut, "result_valid"):
                    result_ch = g(dut, "result_ch")
                if g(dut, "retune_req") and g(dut, "back"):
                    back_seen = g(dut, "retune_ch")
                if g(dut, "slot_done"):
                    done_at = cyc
                    break
                log.append((v, w))
                await FallingEdge(dut.clk)
            assert done_at is not None, "slot did not finish"
            assert result_ch == exp_c and back_seen == home, f"slot {slot_no}: result {result_ch}, back {back_seen}"
            # the measurement saw the strobes after the clock in which the engine started it (two clocks after rx_ready, of which
            # the first strobes may already be in the log): find the window by matching the sum
            strobes = [w for v, w in log if v]
            got_sum = None
            dut.rd_ch.value = exp_c
            await FallingEdge(dut.clk)
            dut.s_valid.value = 0
            await Timer(1, unit="ns")
            got_sum = g(dut, "rd_last")
            # candidates: the window may start 0 to 3 strobes after the first logged strobe
            ok = False
            for off in range(0, 4):
                win = strobes[off + settle:off + settle + dwell]
                if len(win) == dwell and sum(power(w) for w in win) == got_sum:
                    ok = True
                    n_str = off + settle + dwell
                    break
            assert ok, f"slot {slot_no} ch {exp_c}: table sum {got_sum} matches no window"
            assert g(dut, "rd_lg") == lg_model(got_sum)
            cnt = table.get(exp_c, (0, 0))[0] + 1
            mx = max(table.get(exp_c, (0, 0))[1], got_sum)
            table[exp_c] = (cnt, mx)
            assert g(dut, "rd_count") == cnt and g(dut, "rd_max") == mx
            assert g(dut, "rd_strong") == int(got_sum > thr)
            # timing: strobes between the start and the end of the slot
            assert settle + dwell <= len(strobes) <= settle + dwell + 6, f"strobes {len(strobes)} for settle {settle} dwell {dwell}"
            tuned = home
        assert g(dut, "scan_cnt") == sweeps, f"sweeps {g(dut, 'scan_cnt')} expected {sweeps}"
        # clear
        await FallingEdge(dut.clk)
        dut.clear.value = 1
        await FallingEdge(dut.clk)
        dut.clear.value = 0
        dut.rd_ch.value = order[0] if order else 0
        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert g(dut, "rd_count") == 0 and g(dut, "scan_cnt") == 0
        dut._log.info(f"ENGINE run {run}: n_ch {n_ch} mask {mask:08x} home {home} settle {settle} dwell {dwell}: {len(order)} slots, {sweeps} sweeps, tables equal")


@cocotb.test()
async def t24_04b_timeout(dut):
    """T24-04 a missing rx_ready is guarded by the timeout"""
    if G != "eng":
        return
    for n_ in ("slot", "rx_ready", "clear", "s_valid"):
        getattr(dut, n_).value = 0
    dut.ch_mask.value = 0xFF
    dut.n_ch.value = 8
    dut.settle_ticks.value = 3
    dut.dwell_ticks.value = 10
    dut.strong_thr.value = 100
    dut.home.value = 0
    dut.tmo_ticks.value = 20
    dut.rd_ch.value = 0
    await start(dut)
    await FallingEdge(dut.clk)
    dut.slot.value = 1
    await FallingEdge(dut.clk)
    dut.slot.value = 0
    seen_back = seen_done = False
    for k in range(60):
        await Timer(1, unit="ns")
        if g(dut, "retune_req") and g(dut, "back"):
            seen_back = k
        if g(dut, "slot_done"):
            seen_done = k
        await FallingEdge(dut.clk)
    assert seen_done and seen_back and g(dut, "err_tmo") == 1
    assert 18 <= seen_done <= 26, f"timeout after {seen_done} clocks"
    assert g(dut, "busy") == 0
    dut._log.info(f"ENGINE: no rx_ready: slot aborted after {seen_done} clocks, retune back, err_tmo set")
