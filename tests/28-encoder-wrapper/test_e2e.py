import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

import enc_model as E

G = os.environ.get("G", "")


def g(dut, n):
    return int(getattr(dut, n).value)


@cocotb.test()
async def t28_06_end_to_end(dut):
    """T28-06 encoder model -> enc_wrap -> slice_pack -> slice_unpack with rate control, losses and refresh"""
    if G != "e2e":
        return
    rng = random.Random(2806)
    S = 8
    NF = int(os.environ.get("NF", "120"))
    LAT = 1
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    for n_ in ("enc_valid", "enc_flush", "frame_sync", "budget_valid", "qp_valid", "rf_valid", "cmd_start", "buf_check_en"):
        getattr(dut, n_).value = 0
    dut.frame_src.value = 0
    dut.slices_per_frame.value = S
    dut.wave_period.value = 40
    dut.max_budget.value = 3000
    dut.qp_bias_max.value = 20
    dut.fifo_level.value = 0
    dut.enc_data.value = 0
    dut.budget_in.value = 0
    dut.qp_bias_in.value = 0
    dut.rf_seq.value = 0
    dut.ps_ready.value = 1
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)

    budgets = [600, 450, 300, 520]
    mask_hist = []                 # masks commanded per frame
    enc_q = []                     # frames in the encoder: (stream, nals, budget, mask)
    pending_loss = []              # (frame, idx) reported lost, to be requested
    recv = []                      # (frame, idx, flags, len, payload) from the depacketiser
    exp_slices = {}                # (frame, idx) -> (flags, payload)
    exp_over = 0
    sent_ps = []
    ps_got = []
    cur_p = []
    cur_hdr = None
    expected_masks = []
    pending_bits = 0
    wave = 40
    frame_out = 0                  # bitstream frame counter
    intra_seen = intra_cmd = 0

    async def clock_with_collect(n):
        nonlocal cur_p, cur_hdr
        for _ in range(n):
            await Timer(1, unit="ns")
            collect()
            await FallingEdge(dut.clk)

    def collect():
        nonlocal cur_p, cur_hdr
        if g(dut, "p_valid"):
            cur_p.append(g(dut, "p_data"))
            if g(dut, "p_last"):
                cur_p_ = list(cur_p)
                cur_p.clear()
                pending_payload.append(cur_p_)
        if g(dut, "u_valid") and g(dut, "u_hdr_ok") and g(dut, "u_crc_ok"):
            recv.append((g(dut, "u_frame"), g(dut, "u_idx"), g(dut, "u_flags"), g(dut, "u_len")))
        if g(dut, "ps_valid") and g(dut, "ps_ready"):
            ps_cur.append(g(dut, "ps_data"))
            if g(dut, "ps_last"):
                ps_got.append(list(ps_cur))
                ps_cur.clear()

    pending_payload = []
    ps_cur = []
    cmd_budget = None
    n_lost_total = 0
    for k in range(NF + 2):
        # --- command side for frame k: budget, refresh requests, then the frame marker
        b = budgets[(k // 20) % len(budgets)]
        await FallingEdge(dut.clk)
        dut.budget_valid.value = 1
        dut.budget_in.value = b
        await FallingEdge(dut.clk)
        dut.budget_valid.value = 0
        # lost slices of earlier frames that arrived since: request them now (a few clocks apart)
        for (f_, i_) in pending_loss:
            await FallingEdge(dut.clk)
            dut.rf_valid.value = 1
            dut.rf_seq.value = (f_ * S + i_) & 0xFFFF
            await FallingEdge(dut.clk)
            dut.rf_valid.value = 0
            pending_bits |= (1 << i_)
        pending_loss = []
        await FallingEdge(dut.clk)
        await FallingEdge(dut.clk)
        # expected mask: pending requests plus the rolling wave
        wb = (1 << (k % wave)) if (k % wave) < S else 0
        exp_mask = pending_bits | wb
        pending_bits = 0
        dut.cmd_start.value = 1
        await FallingEdge(dut.clk)
        dut.cmd_start.value = 0
        await Timer(1, unit="ns")
        got_mask = g(dut, "intra_mask")
        assert got_mask == exp_mask, f"frame {k}: intra_mask {got_mask:#x} expected {exp_mask:#x}"
        intra_cmd += bin(got_mask).count("1")
        # the encoder model codes frame k with this budget and mask
        idr = (k == 0)
        sizes = []
        for i in range(S):
            if (got_mask >> i) & 1:
                sizes.append(int(b * rng.uniform(1.7, 2.6)))
            else:
                sizes.append(int(b * rng.uniform(0.6, 0.98)))
        if rng.random() < 0.05:
            sizes[rng.randrange(S)] = int(b * 1.3)                    # an encoder that misses the budget
        stream, nals = E.frame_bytes(0, rng, k, S, sizes, idr=idr)
        enc_q.append((stream, nals, b, got_mask))
        # --- the frame that has been in the encoder for LAT frames leaves now
        if len(enc_q) > LAT:
            stream, nals, bud, mask = enc_q.pop(0)
            slice_nals = [n for kd, n in nals if kd in ("slice", "idr")]
            ps_nals = [n for kd, n in nals if kd not in ("slice", "idr")]
            for i, n in enumerate(slice_nals):
                fl = (int(i == S - 1) << 1) | int(bool((mask >> i) & 1) or (frame_out == 0))
                exp_slices[(frame_out, i)] = (fl, n)
                if len(n) * 100 > bud * 105:
                    exp_over += 1
            # AUD is a PS-port NAL unit too
            sent_ps += ps_nals
            idx = 0
            while idx < len(stream):
                await FallingEdge(dut.clk)
                dut.enc_valid.value = 1
                dut.enc_data.value = stream[idx]
                await Timer(1, unit="ns")
                collect()
                if g(dut, "enc_ready"):
                    idx += 1
            await FallingEdge(dut.clk)
            dut.enc_valid.value = 0
            # drain the packetiser
            for _ in range(60 + 2 * sum(len(n) for n in slice_nals) // 4):
                await Timer(1, unit="ns")
                collect()
                await FallingEdge(dut.clk)
            # channel: 5% of the slices are lost and reported one frame later
            for i in range(S):
                if rng.random() < 0.05:
                    pending_loss.append((frame_out, i))
                    n_lost_total += 1
            frame_out += 1
    # flush the last NAL unit and drain
    await FallingEdge(dut.clk)
    dut.enc_flush.value = 1
    await FallingEdge(dut.clk)
    dut.enc_flush.value = 0
    for _ in range(3000):
        await Timer(1, unit="ns")
        collect()
        await FallingEdge(dut.clk)
    # checks
    got = {}
    for (f_, i_, fl, ln), pl in zip(recv, pending_payload):
        got[(f_, i_)] = (fl, pl)
    missing = [k for k in exp_slices if k not in got]
    # the last frame's final NAL unit needs the flush: allow the last slice of the stream to be missing only if it was never closed
    assert len(missing) == 0, f"{len(missing)} slices missing, first {missing[:3]}"
    bad = [k for k in exp_slices if got[k][0] != exp_slices[k][0] or got[k][1] != exp_slices[k][1]]
    assert not bad, f"{len(bad)} slices differ (flags or payload), first {bad[:3]}: flags {got[bad[0]][0]} vs {exp_slices[bad[0]][0]}"
    assert g(dut, "mon_n_slices") == len(exp_slices), (g(dut, "mon_n_slices"), len(exp_slices))
    assert g(dut, "mon_n_over") == exp_over, f"monitor counted {g(dut, 'mon_n_over')} oversize slices, expected {exp_over}"
    assert g(dut, "err_count") == 0 and g(dut, "err_overflow") == 0 and g(dut, "err_rc") == 0
    # parameter sets and delimiters arrived intact (in order)
    assert ps_got == sent_ps[:len(ps_got)] and len(ps_got) >= len(sent_ps) - 1, (len(ps_got), len(sent_ps))
    maxr = g(dut, "mon_max_ratio_q8")
    dut._log.info(f"E2E: {len(exp_slices)} slices in {frame_out} frames (budgets 300 to 600 bytes, 1-frame encoder latency, {n_lost_total} slices lost and refreshed, rolling wave of 40 frames): "
                  f"payloads, headers and flags equal the model; {intra_cmd} intra commands (size x1.7 to 2.6); monitor n_over = {g(dut, 'mon_n_over')} equals the {exp_over} injected oversize slices; "
                  f"max size/budget {maxr / 256:.2f}; {len(ps_got)} parameter-set/delimiter NAL units routed to the ps port")
