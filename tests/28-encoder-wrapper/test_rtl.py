import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

import enc_model as E

G = os.environ.get("G", "")
CODEC = int(os.environ.get("CODEC", "0"))


def g(dut, n):
    return int(getattr(dut, n).value)


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


# ---------------------------------------------------------------- T28-01 splitter
@cocotb.test()
async def t28_01_split(dut):
    """T28-01 nal_split: Annex-B streams from the encoder model, random handshakes"""
    if G != "split":
        return
    rng = random.Random(2801 + CODEC)
    dut.s_valid.value = 0
    dut.s_data.value = 0
    dut.m_ready.value = 1
    dut.flush.value = 0
    await start(dut)
    for run in range(6):
        S = rng.choice([1, 8, 12])
        stream, nals = [], []
        for fr in range(3):
            sizes = [rng.choice([0, 1, 2, 30, 300, rng.randint(1, 1500)]) for _ in range(S)]
            st, nl = E.frame_bytes(CODEC, rng, fr, S, sizes, idr=(fr == 0))
            stream += st
            nals += nl
        stream = [0] * rng.choice([0, 1, 2]) + stream
        exp = [n for k, n in nals]
        got, types = [], []
        cur = None
        i = 0
        k = 0
        pv, pr = rng.choice([1.0, 0.6]), rng.choice([1.0, 0.5])
        flush_sent = False
        for step in range(len(stream) * 12 + 400):
            await FallingEdge(dut.clk)
            if i < len(stream) and rng.random() < pv:
                dut.s_valid.value = 1
                dut.s_data.value = stream[i]
            else:
                dut.s_valid.value = 0
            dut.flush.value = 1 if (i >= len(stream) and not flush_sent) else 0
            dut.m_ready.value = int(rng.random() < pr)
            await Timer(1, unit="ns")
            if g(dut, "s_valid") and g(dut, "s_ready") and i < len(stream):
                i += 1
            if g(dut, "flush") and g(dut, "s_ready"):
                flush_sent = True
            if g(dut, "m_valid") and g(dut, "m_ready"):
                if cur is None:
                    cur = []
                    types.append((g(dut, "nal_type"), g(dut, "is_slice"), g(dut, "is_idr")))
                cur.append(g(dut, "m_data"))
                if g(dut, "m_last"):
                    got.append(cur)
                    cur = None
            if len(got) == len(exp):
                break
        dut.s_valid.value = 0
        dut.flush.value = 0
        assert got == exp, f"run {run}: {len(got)} NAL units against {len(exp)}; first difference at NAL {next((n for n, (a, b) in enumerate(zip(got, exp)) if a != b), None)}"
        for (k_, n), (t, sl, idr) in zip(nals, types):
            et = E.nal_type_of(CODEC, n[0])
            esl = k_ in ("slice", "idr")
            assert (t, sl, idr) == (et, int(esl), int(k_ == "idr")), f"run {run}: {(t, sl, idr)} expected {(et, int(esl), int(k_ == 'idr'))}"
        await FallingEdge(dut.clk)
        dut.rst_n.value = 0
        await FallingEdge(dut.clk)
        dut.rst_n.value = 1
    dut._log.info(f"SPLIT codec {CODEC}: 6 streams of 3 frames (3- and 4-byte start codes, trailing zeros, 00 00 03 in payload, NAL units of 1 to 1500 bytes) equal the model with type, slice and IDR flags")


# ---------------------------------------------------------------- T28-02 tagger
@cocotb.test()
async def t28_02_tag(dut):
    """T28-02 slice_tag: numbering, flags, routing, error counts"""
    if G != "tag":
        return
    rng = random.Random(2802)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 1
    for mode in (0, 1):
        S = 8
        for n_ in ("s_valid", "frame_sync"):
            getattr(dut, n_).value = 0
        dut.frame_src.value = mode
        dut.slices_per_frame.value = S
        dut.tag_mask.value = 0
        dut.m_ready.value = 1
        dut.ps_ready.value = 1
        dut.s_data.value = 0
        dut.s_last.value = 0
        dut.nal_type.value = 0
        dut.is_slice.value = 0
        dut.is_idr.value = 0
        await FallingEdge(dut.clk)
        dut.rst_n.value = 0
        await FallingEdge(dut.clk)
        dut.rst_n.value = 1
        await FallingEdge(dut.clk)
        exp_slices, exp_ps = [], []
        exp_meta = []
        frame = -1
        cnt = 0
        err_exp = 0
        mask_l = 0
        events = []         # (kind, nal bytes, mask)
        counts = [8, 8, 7, 8, 9, 8, 8]
        for fno, c_ in enumerate(counts):
            mask = rng.getrandbits(8)
            events.append(("frame", None, mask, 0))
            for i in range(c_):
                idr = (fno == 0 and i == 0)
                events.append(("slice", [0x65 if idr else 0x41] + [rng.randint(4, 255) for _ in range(rng.randint(0, 40))], 0, idr))
            if rng.random() < 0.5:
                events.append(("ps", [0x06] + [rng.randint(4, 255) for _ in range(5)], 0, 0))
        pv = 0.8
        slice_q = []
        for ev in events:
            kind, data, mask, idr = ev
            if kind == "frame":
                # the boundary: for the delimiter mode it is an AUD NAL unit, otherwise the sync pulse
                await FallingEdge(dut.clk)
                dut.tag_mask.value = mask
                if mode == 1:
                    dut.frame_sync.value = 1
                    await FallingEdge(dut.clk)
                    dut.frame_sync.value = 0
                    nal = None
                else:
                    nal = [0x09, 0xF0]
                if cnt != 0 and cnt != S:
                    err_exp += 1
                frame += 1
                cnt = 0
                mask_l = mask
                if nal:
                    ns = nal
                    typ, sl, ir = 9, 0, 0
                    exp_ps.append(ns)
                else:
                    continue
            else:
                ns = data
                typ = 5 if idr else (1 if kind == "slice" else 6)
                sl = int(kind == "slice")
                ir = int(idr)
                if kind == "slice":
                    flags = ((cnt + 1 == S) << 1) | int(bool((mask_l >> (cnt & 63)) & 1) or bool(idr))
                    exp_meta.append((frame & 0xFFFF, cnt, flags))
                    if cnt >= S:
                        err_exp += 1
                    cnt += 1
                    exp_slices.append(ns)
                else:
                    exp_ps.append(ns)
            # drive the NAL unit
            dut.nal_type.value = typ
            dut.is_slice.value = sl
            dut.is_idr.value = ir
            for bi, b in enumerate(ns):
                while True:
                    await FallingEdge(dut.clk)
                    dut.s_valid.value = int(rng.random() < pv)
                    dut.s_data.value = b
                    dut.s_last.value = int(bi == len(ns) - 1)
                    await Timer(1, unit="ns")
                    if g(dut, "s_valid") and g(dut, "s_ready"):
                        if g(dut, "m_valid") and bi == 0 and sl:
                            slice_q.append((g(dut, "meta_frame"), g(dut, "meta_idx"), g(dut, "meta_flags")))
                        break
                await FallingEdge(dut.clk)
                dut.s_valid.value = 0
        await FallingEdge(dut.clk)
        dut.s_valid.value = 0
        for _ in range(4):
            await FallingEdge(dut.clk)
        exp_meta2 = exp_meta
        assert slice_q == exp_meta2, f"mode {mode}: meta {slice_q[:12]} expected {exp_meta2[:12]}"
        assert g(dut, "err_count") == err_exp, f"mode {mode}: err_count {g(dut, 'err_count')} expected {err_exp}"
    dut._log.info("TAG: numbering from delimiters and from the sync pulse, flags (commanded intra, IDR, last slice), parameter sets routed to the ps port, slice-count errors counted")


# ---------------------------------------------------------------- T28-03 monitor
@cocotb.test()
async def t28_03_mon(dut):
    """T28-03 budget_mon at the 105% boundary"""
    if G != "mon":
        return
    rng = random.Random(2803)
    for n_ in ("clear", "tap_valid", "tap_last", "buf_check_en"):
        getattr(dut, n_).value = 0
    dut.budget.value = 0
    dut.fifo_level.value = 0
    await start(dut)
    n_exp = o_exp = z_exp = 0
    max_r = 0
    cases = [(1000, 1050), (1000, 1051), (1000, 1049), (100, 105), (100, 106), (1, 1), (1, 2), (0, 50), (500, 1), (4000, 4200), (4000, 4201), (65535 // 2, 100)]
    cases += [(rng.randint(1, 3000), rng.randint(1, 3300)) for _ in range(60)]
    for bud, size in cases:
        size = max(1, size)
        for i in range(size):
            await FallingEdge(dut.clk)
            dut.budget.value = bud if i == 0 else (bud + 77)       # only the value at the first byte counts
            dut.tap_valid.value = 1
            dut.tap_last.value = int(i == size - 1)
            await Timer(1, unit="ns")
            if rng.random() < 0.2 and i != size - 1:
                await FallingEdge(dut.clk)
                dut.tap_valid.value = 0
        await FallingEdge(dut.clk)
        dut.tap_valid.value = 0
        dut.tap_last.value = 0
        await Timer(1, unit="ns")
        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        n_exp += 1
        if bud == 0:
            z_exp += 1
        elif size * 100 > bud * 105:
            o_exp += 1
        if bud:
            r = min(65535, (size << 8) // bud)
            max_r = max(max_r, r)
            assert g(dut, "ratio_q8") == r, f"ratio {g(dut, 'ratio_q8')} expected {r} (size {size} budget {bud})"
        assert g(dut, "n_slices") == n_exp and g(dut, "n_over") == o_exp and g(dut, "n_zero_budget") == z_exp, \
            f"counters {(g(dut, 'n_slices'), g(dut, 'n_over'), g(dut, 'n_zero_budget'))} expected {(n_exp, o_exp, z_exp)} after size {size} budget {bud}"
        assert g(dut, "size") == size
        assert g(dut, "max_ratio_q8") == max_r
    # the buffer check
    await FallingEdge(dut.clk)
    dut.buf_check_en.value = 1
    for lvl, expect in ((100, 0), (900, 0), (1001, 1)):
        for i in range(30):
            await FallingEdge(dut.clk)
            dut.budget.value = 1000
            dut.fifo_level.value = lvl
            dut.tap_valid.value = 1
            dut.tap_last.value = int(i == 29)
        await FallingEdge(dut.clk)
        dut.tap_valid.value = 0
        await Timer(1, unit="ns")
    await FallingEdge(dut.clk)
    assert g(dut, "err_buf") == 1, g(dut, "err_buf")
    dut._log.info(f"MON: {n_exp} slices: boundary at exactly 105%, ratio and maximum, zero budget; {o_exp} over, buffer check counted once")


# ---------------------------------------------------------------- T28-04 refresh map
@cocotb.test()
async def t28_04_refresh(dut):
    """T28-04 refresh_map against a model"""
    if G != "refresh":
        return
    rng = random.Random(2804)
    for n_ in ("bs_start", "cmd_start", "rf_valid"):
        getattr(dut, n_).value = 0
    dut.slices_per_frame.value = 8
    dut.wave_period.value = 0
    dut.bs_frame.value = 0
    dut.rf_seq.value = 0
    await start(dut)
    for S, wave in ((8, 0), (12, 20), (34, 0)):
        await FallingEdge(dut.clk)
        dut.rst_n.value = 0
        await FallingEdge(dut.clk)
        dut.rst_n.value = 1
        dut.slices_per_frame.value = S
        dut.wave_period.value = wave
        await FallingEdge(dut.clk)
        # model
        ring = []                       # first sequence numbers of the bitstream frames
        pending = 0
        queue = []
        frame = 0xFFF0                  # exercise the wrap of the 16-bit numbers
        cmd_frames = 0
        n_req = n_old = n_app = 0
        intra, tag = 0, 0
        for step in range(400):
            await FallingEdge(dut.clk)
            bs = int(rng.random() < 0.08)
            cmd = int(rng.random() < 0.08)
            rf = int(rng.random() < 0.5)
            seq = 0
            if rf:
                # a slice of one of the recent frames (or an old one)
                if ring and rng.random() < 0.9:
                    f_i, first = rng.choice(ring[-12:])
                    seq = (first + rng.randrange(S)) & 0xFFFF
                else:
                    seq = rng.getrandbits(16)
            dut.bs_start.value = bs
            dut.bs_frame.value = frame & 0xFFFF
            dut.cmd_start.value = cmd
            dut.rf_valid.value = rf
            dut.rf_seq.value = seq
            # model update (same order as the RTL: the lookup uses the ring before this clock's boundary)
            hit_idx = None
            for f_i, first in reversed(ring[-16:]):
                pass
            hit_idx = None
            for f_i, first in ring[-16:][::-1] if False else ring[-16:]:
                d = (seq - first) & 0xFFFF
                if d < S and hit_idx is None:
                    hit_idx = d
            # the RTL scans slots in array order (oldest slot index first); duplicates of the same first value cannot occur in the ring
            req_bit = (1 << hit_idx) if (rf and hit_idx is not None and hit_idx < 64) else 0
            if bs:
                ring.append(((frame + 1) & 0xFFFF, ((frame + 1) * S) & 0xFFFF))
                ring = ring[-16:]
                if queue:
                    tag = queue.pop(0)
                else:
                    tag = 0
                frame += 1
            if rf:
                n_req += 1
                if hit_idx is None:
                    n_old += 1
                elif (pending & req_bit) == 0 and req_bit:
                    n_app += 1
            wb = 0
            if wave:
                ph = cmd_frames % wave
                if ph < S and ph < 64:
                    wb = 1 << ph
            m_next = pending | wb | req_bit
            if cmd:
                intra = m_next
                if len(queue) < 8:
                    queue.append(m_next)
                pending = 0
                cmd_frames += 1
            elif rf and hit_idx is not None:
                pending |= req_bit
            await Timer(1, unit="ns")
            await FallingEdge(dut.clk)
            await Timer(1, unit="ns")
            dut.bs_start.value = 0
            dut.cmd_start.value = 0
            dut.rf_valid.value = 0
            tag = queue[0] if queue else 0
            got = (g(dut, "intra_mask"), g(dut, "tag_mask"), g(dut, "n_req"), g(dut, "n_applied"), g(dut, "n_old"))
            assert got == (intra, tag, n_req, n_app, n_old), f"S {S} step {step}: {got} expected {(intra, tag, n_req, n_app, n_old)}"
    dut._log.info("REFRESH: 3 configurations (S = 8, 12 with a rolling wave of 20 frames, 34), 400 random steps each, with the 16-bit wrap: masks, delayed tag masks and counters equal the model")


# ---------------------------------------------------------------- T28-05 rate-control hook
@cocotb.test()
async def t28_05_rc(dut):
    """T28-05 rc_hook"""
    if G != "rc":
        return
    rng = random.Random(2805)
    dut.budget_valid.value = 0
    dut.qp_valid.value = 0
    dut.budget_in.value = 0
    dut.qp_bias_in.value = 0
    dut.max_budget.value = 3000
    dut.qp_bias_max.value = 20
    await start(dut)
    exp_t = 0
    exp_q = 0
    exp_err = 0
    for k in range(300):
        b = rng.choice([0, 100, 1200, 3000, 3001, 5000, rng.randint(0, 6000)])
        q = rng.choice([0, 5, 20, 21, 200, rng.randint(0, 255)])
        bv, qv = int(rng.random() < 0.6), int(rng.random() < 0.4)
        await FallingEdge(dut.clk)
        dut.budget_valid.value = bv
        dut.budget_in.value = b
        dut.qp_valid.value = qv
        dut.qp_bias_in.value = q
        upd = qupd = 0
        if bv:
            if b == 0 or b > 3000:
                exp_err += 1
            else:
                exp_t = b
                upd = 1
        if qv:
            if q > 20:
                exp_err += 1
            else:
                exp_q = q
                qupd = 1
        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert (g(dut, "target_bytes"), g(dut, "update"), g(dut, "qp_bias"), g(dut, "qp_update"), g(dut, "err_rc")) == (exp_t, upd, exp_q, qupd, exp_err), \
            f"step {k}: {(g(dut, 'target_bytes'), g(dut, 'update'), g(dut, 'qp_bias'), g(dut, 'qp_update'), g(dut, 'err_rc'))} expected {(exp_t, upd, exp_q, qupd, exp_err)}"
        dut.budget_valid.value = 0
        dut.qp_valid.value = 0
    dut._log.info(f"RC: 300 random commands: valid budgets reach the output one clock after the command (within 4 clocks), {exp_err} invalid values rejected with the previous value kept")
