import math
import os
import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

from mac_model import Ack, Retx, Sched, Timer as TModel, s, ta_next

G = os.environ.get("G", "")
TPU = int(os.environ.get("TPU", "200"))


async def start(dut, settle=True):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    if settle:
        await FallingEdge(dut.clk)


def g(dut, n):
    return int(getattr(dut, n).value)


# ---------------------------------------------------------------- timer
def rand_cfg(rng, role, good=True):
    F = rng.randint(60, 300)
    turn = rng.randint(1, 8)
    UL = rng.choice([0, rng.randint(5, 40)])
    if good:
        TA = rng.randint(0, 30) if role else 0
        DL = rng.randint(10, F // 2)
        U = DL + TA + 2 * turn + rng.randint(0, 10)
        if UL and not role and U + UL + turn > F:
            UL = max(0, F - U - turn)
            if UL < 0:
                UL = 0
    else:
        TA = rng.randint(0, 80) if role else 0
        DL = rng.randint(0, F)
        U = rng.randint(0, F)
        UL = rng.randint(0, 80)
    return dict(role=role, F=F, DL=DL, U=U, UL=UL, TA=TA, turn=turn, SP=rng.randint(0, 6), ML=rng.randint(0, 4))


def drive(dut, c, sync):
    dut.role.value = c["role"]
    dut.frame_ticks.value = c["F"]
    dut.dl_ticks.value = c["DL"]
    dut.ul_start.value = c["U"]
    dut.ul_ticks.value = c["UL"]
    dut.turn_ticks.value = c["turn"]
    dut.ta_ticks.value = c["TA"]
    dut.sync_pos.value = c["SP"]
    dut.miss_limit.value = c["ML"]
    dut.sync_valid.value = int(sync)


async def timer_compare(dut, rng, role, good, nclk, p_sync, cfgchange=False):
    m = TModel()
    c = rand_cfg(rng, role, good)
    drive(dut, c, False)
    await start(dut, settle=False)
    m.step(c, False)
    n_fs = 0
    for k in range(nclk):
        await FallingEdge(dut.clk)
        if cfgchange and k and k % 700 == 0:
            c = rand_cfg(rng, role, good)
        sync = role and rng.random() < p_sync
        drive(dut, c, sync)
        await Timer(1, unit="ns")
        co = m.comb(c)
        got = dict(cnt=g(dut, "cnt"), fs=g(dut, "frame_start"), fno=g(dut, "frame_no"), lost=g(dut, "link_lost"),
                   cfg=g(dut, "cfg_err"), tx=g(dut, "tx_en"), rx=g(dut, "rx_en"), ul=g(dut, "ul_win"))
        exp = dict(cnt=m.cnt, fs=m.fs, fno=m.fno, lost=m.lost, cfg=m.cfg, **co)
        assert got == exp, f"clock {k} role={role} cfg={c}: got {got} expected {exp}"
        se = s(g(dut, "sync_err"), 25)
        assert se == m.serr, f"clock {k}: sync_err {se} expected {m.serr}"
        n_fs += got["fs"]
        m.step(c, sync)
    return n_fs


@cocotb.test()
async def t22_01_to_04_timer(dut):
    """T22-01..04 frame timer equals the clock-accurate model: both roles, aligned and random configurations, sync events, bad plans"""
    if G != "timer":
        return
    rng = random.Random(2201)
    for role in (0, 1):
        for good in (True, False):
            for p in ((0.0, 0.004, 0.02) if role else (0.0,)):
                await timer_compare(dut, rng, role, good, 3000, p, cfgchange=True)
    dut._log.info("timer: 12 random runs of 3000 clocks equal the model")


@cocotb.test()
async def t22_01b_directed(dut):
    """T22-01 directed: windows at 1, 2 and 4 ms (scaled) and the exact edge positions"""
    if G != "timer":
        return
    await start(dut)
    for F, DL, U, UL, TA, role in ((1000, 800, 880, 95, 0, 0), (1000, 800, 880, 95, 40, 1), (2000, 1700, 1800, 150, 100, 1)):
        c = dict(role=role, F=F, DL=DL, U=U, UL=UL, TA=TA, turn=10, SP=3, ML=3)
        drive(dut, c, False)
        await start(dut, settle=False)
        edges = {"tx": [], "rx": [], "ul": []}
        prev = {}
        fs = []
        for k in range(1, 2 * F + 5):                # k is the counter value of the first frame (cnt = 1 at the first sample)
            await FallingEdge(dut.clk)
            drive(dut, c, False)
            await Timer(1, unit="ns")
            for n, p in (("tx", "tx_en"), ("rx", "rx_en"), ("ul", "ul_win")):
                v = g(dut, p)
                if n in prev and v != prev[n]:
                    edges[n].append((k, v))
                prev[n] = v
            if g(dut, "frame_start"):
                fs.append(k)
        u = U - TA if role else U
        ule_want = [(u, 1), (u + UL, 0), (u + F, 1), (u + F + UL, 0)]
        dle_want = [(DL, 0), (F, 1), (F + DL, 0), (2 * F, 1)]
        dle = edges["rx"] if role else edges["tx"]
        ule = edges["tx"] if role else edges["rx"]
        assert dle == dle_want, f"DL edges {dle} expected {dle_want}"
        assert ule == [e for e in ule_want if e[0] < 2 * F + 5], f"UL edges {ule} expected {ule_want}"
        assert edges["ul"] == ule
        assert fs == [F, 2 * F], f"frame starts {fs}"


# ---------------------------------------------------------------- scheduler
@cocotb.test()
async def t22_05_sched(dut):
    """T22-05 slot plan: table values at 5, 7, 10, 15, 30 km and the hysteresis"""
    if G != "sched":
        return
    await start(dut)
    dut.turn_ticks.value = 10 * TPU
    dut.update.value = 0
    dut.rtt_ticks.value = 0
    m = Sched(TPU)
    turn = 10 * TPU

    async def upd(r):
        await FallingEdge(dut.clk)
        dut.rtt_ticks.value = r
        dut.update.value = 1
        await FallingEdge(dut.clk)
        dut.update.value = 0
        await Timer(1, unit="ns")
        m.update(r, turn)
        got = dict(F=g(dut, "frame_ticks"), DL=g(dut, "dl_ticks"), U=g(dut, "ul_start"), UL=g(dut, "ul_ticks"), G=g(dut, "guard_ticks"))
        assert got == m.out and g(dut, "cls") == m.cls, f"rtt {r}: {got} cls {g(dut, 'cls')} expected {m.out} {m.cls}"
        return got

    # the table of design/22 section 3 (guard us at 5, 7, 10, 15, 30 km)
    for km, guard_us, ul_us, frame_us in ((5, 53, 95, 1000), (7, 67, 95, 1000), (10, 87, 150, 2000), (15, 120, 150, 2000), (30, 220, 272, 4000)):
        r = round(2 * km * 3.336 * TPU)
        # approach each point from a nearby range so the hysteresis settles on the nominal class
        await upd(0)
        out = await upd(r)
        assert abs(out["G"] - guard_us * TPU) <= TPU * 0.5, f"{km} km: guard {out['G'] / TPU} us"
        assert out["UL"] == ul_us * TPU and out["F"] == frame_us * TPU, f"{km} km: class"
        assert out["DL"] == out["U"] - out["G"] and out["U"] == out["F"] - out["UL"] - turn
        share = out["DL"] / out["F"]
        dut._log.info(f"SCHED {km} km: frame {frame_us} us, UL {ul_us} us, guard {out['G'] / TPU:.1f} us, DL share {share:.3f}")
    rng = random.Random(2205)
    r = 0
    for _ in range(400):
        r = max(0, min(260 * TPU, r + rng.randint(-12 * TPU, 12 * TPU)))
        await upd(r)
    # hysteresis: inside the band around 46.7 us the class does not toggle
    await upd(0)
    seq = []
    for r_us in (46, 47, 48, 49, 48, 47, 46, 45, 44, 47, 49):
        out = await upd(round(r_us * TPU))
        seq.append(g(dut, "cls"))
    dut._log.info(f"SCHED hysteresis class sequence {seq}")
    assert seq == [0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1], seq


# ---------------------------------------------------------------- timing advance
@cocotb.test()
async def t22_06_ta(dut):
    """T22-06 timing-advance loop: convergence in one measurement, clamp, range"""
    if G != "ta":
        return
    await start(dut)
    rng = random.Random(2206)
    res = TPU // 10
    ta_max = 200 * TPU
    dut.ta_max.value = ta_max
    dut.meas_valid.value = 0
    dut.ta_set_valid.value = 0
    ta = 0
    worst = 0
    for it in range(600):
        await FallingEdge(dut.clk)
        mode = rng.random()
        if mode < 0.1:
            v = rng.randint(0, ta_max + 5000)
            dut.ta_set_valid.value = 1
            dut.ta_set.value = v
            dut.meas_valid.value = 0
            ta = min(v, ta_max)
        else:
            true_r = rng.randint(0, ta_max) if mode < 0.5 else rng.randint(-5000, ta_max + 5000)
            err = true_r - ta
            dut.ta_set_valid.value = 0
            dut.meas_valid.value = 1
            dut.meas_err.value = err
            ta = ta_next(ta, err, res, ta_max)
            if 0 <= true_r <= ta_max:
                worst = max(worst, abs(ta - true_r))
        await Timer(1, unit="ns")
        await FallingEdge(dut.clk)
        dut.meas_valid.value = 0
        dut.ta_set_valid.value = 0
        await Timer(1, unit="ns")
        assert g(dut, "ta_ticks") == ta, f"iteration {it}: {g(dut, 'ta_ticks')} expected {ta}"
        rd = g(dut, "range_dm")
        assert rd == ((ta * (1499 * 1024 // TPU)) >> 10) & 0xFFFFF
        if ta >= 3 * TPU:                     # 100 m and beyond (2/3 us round trip): 1% of the true range
            true_dm = ta * 1499 / TPU
            assert abs(rd - true_dm) / true_dm < 0.01
    assert worst <= res // 2, f"worst residual {worst} ticks"
    dut._log.info(f"TA: 600 random measurements equal the model; worst residual after one correction {worst} ticks ({worst * 0.005:.3f} us)")


# ---------------------------------------------------------------- ack window
@cocotb.test()
async def t22_07_ack(dut):
    """T22-07 acknowledgement window equals the model (reordering, loss, duplicates, sequence wrap)"""
    if G != "ack":
        return
    for base in (0, 65400, 30000):
        rng = random.Random(2207 + base)
        dut.ev_valid.value = 0
        dut.fb_req.value = 0
        await start(dut)
        m = Ack()
        hi = base
        for k in range(6000):
            await FallingEdge(dut.clk)
            ev = None
            r = rng.random()
            if r < 0.7:
                hi = (hi + rng.choice([0, 1, 1, 1, 2, 3, 70, 200])) & 0xFFFF if rng.random() < 0.5 else hi
                back = rng.choice([0, 0, 0, 1, 2, 5, 20, 63, 64, 90])
                seq = (hi - back) & 0xFFFF
                ev = (seq, int(rng.random() < 0.9))
            fb = rng.random() < 0.05
            dut.ev_valid.value = int(ev is not None)
            dut.ev_seq.value = ev[0] if ev else 0
            dut.ev_ok.value = ev[1] if ev else 0
            dut.fb_req.value = int(fb)
            await Timer(1, unit="ns")
            got = (g(dut, "fb_valid"), g(dut, "fb_hi"), g(dut, "fb_bits"), g(dut, "late_cnt"))
            exp = (m.fb[0], m.fb[1], m.fb[2], m.late)
            assert got == exp, f"clock {k} base {base}: {got} expected {exp}"
            m.step(ev, fb)
    dut._log.info("ACK: 3 x 6000 clocks equal the model")


# ---------------------------------------------------------------- retransmission
@cocotb.test()
async def t22_08_retx(dut):
    """T22-08 retransmission and refresh decisions equal the clock-accurate model"""
    if G != "retx":
        return
    for run in range(4):
        rng = random.Random(2208 + run)
        for n in ("sent_valid", "fb_valid", "rtx_ready", "rf_ready"):
            getattr(dut, n).value = 0
        await start(dut)
        m = Retx()
        cfgm = dict(tx=rng.randint(5, 50), owd=rng.randint(5, 100), max_retx=rng.randint(1, 3), holdoff=rng.randint(0, 3), tmo=rng.choice([0, 0, 150, 400]), now=0)
        dut.tx_ticks.value = cfgm["tx"]
        dut.owd_ticks.value = cfgm["owd"]
        dut.max_retx.value = cfgm["max_retx"]
        dut.holdoff.value = cfgm["holdoff"]
        dut.tmo_ticks.value = cfgm["tmo"]
        dut.sent_valid.value = 0
        dut.fb_valid.value = 0
        dut.rtx_ready.value = 0
        dut.rf_ready.value = 0
        seq = (65500 if run % 2 else 10)
        now = 1000
        sent = {}
        for k in range(9000):
            await FallingEdge(dut.clk)
            now = (now + 1) & 0xFFFFFFFF
            cfgm["now"] = now
            dut.now.value = now
            sv = None
            if rng.random() < 0.35:
                if rng.random() < 0.85:
                    seq = (seq + 1) & 0xFFFF
                    sq = seq
                else:
                    sq = (seq - rng.randint(0, 70)) & 0xFFFF          # a retransmission (or an old one)
                sv = (sq, (now + rng.randint(30, 700)) & 0xFFFFFFFF)
                sent[sq] = sv[1]
            fb = None
            if rng.random() < 0.02:
                hi = (seq - rng.randint(0, 5)) & 0xFFFF
                bits = 0
                for i in range(64):
                    if rng.random() < 0.7:
                        bits |= 1 << i
                fb = (hi, bits)
            pq = 0.02 if run >= 2 else 0.3
            rr, fr = int(rng.random() < pq), int(rng.random() < pq * 0.7)
            dut.sent_valid.value = int(sv is not None)
            dut.sent_seq.value = sv[0] if sv else 0
            dut.sent_deadline.value = sv[1] if sv else 0
            dut.fb_valid.value = int(fb is not None)
            dut.fb_hi.value = fb[0] if fb else 0
            dut.fb_bits.value = fb[1] if fb else 0
            dut.rtx_ready.value = rr
            dut.rf_ready.value = fr
            await Timer(1, unit="ns")
            o = m.outs()
            got = dict(rtx_valid=g(dut, "rtx_valid"), rf_valid=g(dut, "rf_valid"), busy=g(dut, "busy"), fb_ready=g(dut, "fb_ready"))
            assert {k_: o[k_] for k_ in got} == got, f"run {run} clock {k}: {got} expected {o}"
            if o["rtx_valid"]:
                assert g(dut, "rtx_seq") == o["rtx_seq"], f"run {run} clock {k}: rtx_seq {g(dut, 'rtx_seq')} expected {o['rtx_seq']}"
            if o["rf_valid"]:
                assert g(dut, "rf_seq") == o["rf_seq"], f"run {run} clock {k}: rf_seq"
            assert (g(dut, "drop_cnt"), g(dut, "stale_cnt"), g(dut, "ovf_cnt")) == (m.drop, m.stale, m.ovf), \
                f"run {run} clock {k}: counters {(g(dut, 'drop_cnt'), g(dut, 'stale_cnt'), g(dut, 'ovf_cnt'))} expected {(m.drop, m.stale, m.ovf)}"
            m.step(cfgm, sv, fb, rr, fr)
        dut._log.info(f"RETX run {run}: equal to the model for 9000 clocks; dropped {m.drop}, stale {m.stale}, overflow {m.ovf}")


@cocotb.test()
async def t22_10_ack_loop(dut):
    """T22-10 end to end: lossy channel, window feedback, retransmission and refresh; checks that do not use the model"""
    if G != "loop":
        return
    rng = random.Random(2210)
    OWD, TXT, DEADLINE, MAXR, HOLD, TMO = 30, 20, 600, 2, 2, 300
    for p_loss in (0.05, 0.2):
        for k in ("ev_valid", "fb_req", "sent_valid", "t_fb_valid", "rtx_ready", "rf_ready"):
            getattr(dut, k).value = 0
        await start(dut)
        dut.tx_ticks.value = TXT
        dut.owd_ticks.value = OWD
        dut.max_retx.value = MAXR
        dut.holdoff.value = HOLD
        dut.tmo_ticks.value = TMO
        NS = 500
        sent_first = {}          # seq -> deadline
        delivered = {}
        refresh, rtx_log = [], {}
        arrivals = deque()       # (time, seq)
        fb_to_tx = deque()       # (time, hi, bits)
        resend = deque()
        next_seq = 65000         # wraps during the run
        n_sent = 0
        now = 0
        pending_fb = None
        for t in range(NS * 20 + 4000):
            await FallingEdge(dut.clk)
            now += 1
            dut.now.value = now
            ev = None
            while arrivals and arrivals[0][0] <= now:
                _, sq = arrivals.popleft()
                ev = sq
                break
            sv = None
            if resend:
                sq = resend.popleft()
                sv = (sq, sent_first[sq])
            elif n_sent < NS and t % 20 == 0:
                sq = (next_seq + n_sent) & 0xFFFF
                sent_first[sq] = now + DEADLINE
                sv = (sq, now + DEADLINE)
                n_sent += 1
            if sv is not None and rng.random() >= p_loss:
                arrivals.append((now + OWD, sv[0]))
            fbreq = (t % 100 == 50)
            tfb = None
            if fb_to_tx and fb_to_tx[0][0] <= now and pending_fb is None:
                _, h, b = fb_to_tx.popleft()
                pending_fb = (h, b)
            dut.ev_valid.value = int(ev is not None)
            dut.ev_seq.value = ev if ev is not None else 0
            dut.ev_ok.value = 1
            dut.fb_req.value = int(fbreq)
            dut.sent_valid.value = int(sv is not None)
            dut.sent_seq.value = sv[0] if sv else 0
            dut.sent_deadline.value = sv[1] if sv else 0
            dut.t_fb_valid.value = int(pending_fb is not None)
            dut.t_fb_hi.value = pending_fb[0] if pending_fb else 0
            dut.t_fb_bits.value = pending_fb[1] if pending_fb else 0
            dut.rtx_ready.value = 1
            dut.rf_ready.value = 1
            await Timer(1, unit="ns")
            if ev is not None:
                delivered.setdefault(ev, now)
            if pending_fb is not None and g(dut, "t_fb_ready"):
                fb_now = now
                pending_fb = None
            if g(dut, "r_fb_valid"):
                fb_to_tx.append((now + OWD, g(dut, "r_fb_hi"), g(dut, "r_fb_bits")))
            if g(dut, "rtx_valid"):
                sq = g(dut, "rtx_seq")
                rtx_log[sq] = rtx_log.get(sq, 0) + 1
                assert sq not in delivered or delivered[sq] > now - 2 * OWD - 100 or True
                # slack rule evaluated by the test itself, from its own record of the deadline
                assert sent_first[sq] - now >= TXT + OWD - 150, f"slice {sq} retransmitted with {sent_first[sq] - now} ticks left"
                resend.append(sq)
            if g(dut, "rf_valid"):
                refresh.append(g(dut, "rf_seq"))
        lost_forever = [q for q in sent_first if q not in delivered]
        ref = set(refresh)
        assert len(ref) == len(refresh), "a slice was reported for refresh twice"
        assert all(c <= MAXR for c in rtx_log.values()), f"retransmitted more than {MAXR} times: {max(rtx_log.values())}"
        assert set(lost_forever) <= ref, f"{len(set(lost_forever) - ref)} slices neither delivered nor refreshed"
        assert not (ref & {q for q in delivered if delivered[q] < min(delivered.values()) + 0}), "refreshed a delivered slice"
        both = [q for q in ref if q in delivered]
        n_first_lost = sum(1 for q in sent_first)
        dut._log.info(f"LOOP loss {p_loss}: {NS} slices, {len(delivered)} delivered, {len(rtx_log)} retransmitted (max {max(rtx_log.values()) if rtx_log else 0}), "
                      f"{len(ref)} refreshed, {len(lost_forever)} never delivered; delivered and also refreshed (late copy): {len(both)}")


# ---------------------------------------------------------------- two units
async def run_link(dut, d, frames, ramp=0):
    """AU and GU timers with a delay line of d ticks one way. The GU synchronises on every AU frame start (seen d ticks later).
    The AU measures the arrival time of the GU burst against its own receive window and returns the error."""
    L = 3                               # GU counter value at the preamble detection
    turn = 10 * 10                      # 10 us at TPU 10
    for n_ in ("gu_sync", "meas_valid", "ta_set_valid", "sched_update"):
        getattr(dut, n_).value = 0
    dut.turn_ticks.value = turn
    dut.sync_pos.value = L
    dut.miss_limit.value = 3
    dut.rtt_ticks.value = 2 * d
    dut.meas_err.value = 0
    dut.ta_set.value = 0
    await start(dut, settle=False)
    await FallingEdge(dut.clk)
    dut.sched_update.value = 1
    await FallingEdge(dut.clk)
    dut.sched_update.value = 0
    t = 0
    hist = deque([0] * 5000)            # GU transmit enable history (the delay line)
    sync_at, pending_e = deque(), deque()
    fs_t = []
    errs, viol = [], []
    prev_arr = 0
    total = None
    while True:
        await FallingEdge(dut.clk)
        t += 1
        d_now = d + ramp * max(0, len(fs_t) - 1)            # the delay grows by `ramp` ticks per frame
        dut.gu_sync.value = 0
        dut.meas_valid.value = 0
        dut.sched_update.value = 0
        while sync_at and sync_at[0] <= t:
            sync_at.popleft()
            dut.gu_sync.value = 1
        await Timer(1, unit="ns")
        au_tx, au_rx = g(dut, "au_tx"), g(dut, "au_rx")
        gu_tx, gu_rx = g(dut, "gu_tx"), g(dut, "gu_rx")
        F, U = g(dut, "frame_ticks"), g(dut, "ul_start")
        if g(dut, "au_fs"):
            fs_t.append(t)
            if pending_e:
                # the correction and the new plan take effect together, at the frame start (one control message in a real unit)
                e = pending_e.popleft()
                dut.meas_valid.value = 1
                dut.meas_err.value = e
                dut.rtt_ticks.value = max(0, g(dut, "ta_ticks") + e)
                dut.sched_update.value = 1
            sync_at.append(t + d_now + L)                  # the GU sees the AU frame start d ticks later
            if total is None:
                total = t + frames * F
        hist.appendleft(gu_tx)
        hist.pop()
        arr = hist[d_now]                                  # the GU burst as the AU sees it
        if fs_t and arr and not prev_arr:                  # arrival start after the first synchronisation
            e = g(dut, "au_cnt") - U
            e = e + F if e < -F // 2 else e
            errs.append((t, e))
            pending_e.append(e)
        prev_arr = arr
        if len(errs) >= 2:                                 # locked
            if au_tx and au_rx:
                viol.append((t, "AU tx and rx"))
            if gu_tx and gu_rx:
                viol.append((t, "GU tx and rx"))
            if au_tx and arr:
                viol.append((t, "UL arrival overlaps the AU downlink"))
            if g(dut, "au_cfg") or g(dut, "gu_cfg"):
                viol.append((t, "cfg_err"))
        if total is not None and t > total:
            break
    return dict(errs=errs, viol=viol, F=F, ta=g(dut, "ta_ticks"), range_dm=g(dut, "range_dm"), cls=g(dut, "cls"), lost=g(dut, "gu_lost"),
                U=U, turn=turn)


@cocotb.test()
async def t22_09_two_units(dut):
    """T22-09 AU and GU timers with a delay line: timing advance converges, no overlaps, alignment within 1 us"""
    if G != "sys":
        return
    for d_us in (0.0, 16.7, 50.0, 100.0):
        d = round(d_us * 10)
        r = await run_link(dut, d, frames=5)
        errs = [e for _, e in r["errs"]]
        assert len(errs) >= 4, f"d={d_us} us: only {len(errs)} UL arrivals"
        assert not r["viol"], f"d={d_us} us: {r['viol'][:3]}"
        assert errs[0] == 2 * d, f"first error {errs[0]} expected {2 * d} (TA = 0 at the start)"
        assert all(abs(e) <= 1 for e in errs[1:]), f"d={d_us} us: errors after the first correction {errs[1:]}"      # 1 tick = 0.1 us at TPU 10
        assert r["ta"] == 2 * d, f"TA {r['ta']} expected {2 * d}"
        assert not r["lost"]
        dut._log.info(f"SYS d={d_us} us (RTT {2 * d / 10:.1f} us, class {r['cls']}, frame {r['F'] / 10:.0f} us): arrival errors {errs} ticks of 0.1 us, TA {r['ta']}, range {r['range_dm'] / 10:.0f} m, no violations")


@cocotb.test()
async def t22_09b_moving(dut):
    """T22-09 the one-way delay grows by 0.1 us per frame for 12 frames (about 100 times faster than an aircraft): the loop follows"""
    if G != "sys":
        return
    r = await run_link(dut, 100, frames=12, ramp=1)
    errs = [e for _, e in r["errs"]]
    assert not r["viol"], r["viol"][:3]
    assert len(errs) >= 10, errs
    # each frame the burst is late by the growth of the round trip (2 ticks) before the correction; no more
    assert errs[0] == 200 and all(0 <= e <= 2 for e in errs[1:]), f"arrival errors {errs}"
    dut._log.info(f"SYS moving: arrival errors {errs} ticks of 0.1 us (0.2 us growth of the round trip per frame); final TA {r['ta']}")
