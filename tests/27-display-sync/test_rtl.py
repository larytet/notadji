import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

import dmodel as D

G = os.environ.get("G", "")


def g(dut, n):
    return int(getattr(dut, n).value)


def gs(dut, n, bits):
    return D.s(g(dut, n), bits)


async def start(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1


MODES = {
    "1080p60": dict(h_active=1920, h_fp=88, h_sync=44, h_bp=148, v_active=1080, v_fp=4, v_sync=5, v_bp=36, hs_pol=1, vs_pol=1),
    "720p60": dict(h_active=1280, h_fp=110, h_sync=40, h_bp=220, v_active=720, v_fp=5, v_sync=5, v_bp=20, hs_pol=1, vs_pol=1),
    "1080p30": dict(h_active=1920, h_fp=88, h_sync=44, h_bp=148, v_active=1080, v_fp=4, v_sync=5, v_bp=36, hs_pol=0, vs_pol=0),
    "mid": dict(h_active=64, h_fp=8, h_sync=8, h_bp=16, v_active=40, v_fp=2, v_sync=3, v_bp=5, hs_pol=1, vs_pol=1),
    "tiny": dict(h_active=12, h_fp=3, h_sync=4, h_bp=5, v_active=6, v_fp=2, v_sync=3, v_bp=4, hs_pol=1, vs_pol=0),
}


@cocotb.test()
async def t27_01_timing(dut):
    """T27-01 scan_timing: cycle-accurate against the model, standard modes, slip"""
    if G != "timing":
        return
    rng = random.Random(2701)
    dut.en.value = 0
    dut.slip.value = 0
    for n_ in ("h_active", "h_fp", "h_sync", "h_bp", "v_active", "v_fp", "v_sync", "v_bp", "hs_pol", "vs_pol"):
        getattr(dut, n_).value = 1
    await start(dut)

    def apply(c):
        for k in ("h_active", "h_fp", "h_sync", "h_bp", "v_active", "v_fp", "v_sync", "v_bp", "hs_pol", "vs_pol"):
            getattr(dut, k).value = c[k]
        dut.en.value = c["en"]
        dut.slip.value = c["slip"]

    # tiny modes: every clock for many frames with random slip changes; the standard modes: sampled windows
    for name, nframes in (("tiny", 6), ("mid", 4), ("720p60", 1), ("1080p60", 0)):
        c = dict(MODES[name], en=1, slip=0)
        await FallingEdge(dut.clk)
        apply(dict(c, en=0))
        await FallingEdge(dut.clk)
        await FallingEdge(dut.clk)
        m = D.Timing()
        ht, vt = m.tot(c)
        total = ht * vt * nframes + 100 if nframes else 3 * ht + 50          # 1080p60: three lines (a full frame is 2.5 million clocks)
        fs_seen = []
        for k in range(total):
            await FallingEdge(dut.clk)
            if name == "tiny" and k % 150 == 0:
                c["slip"] = rng.choice([-9, -4, -1, 0, 0, 3, 8])
            apply(c)
            await Timer(1, unit="ns")
            exp = m.comb(c)
            got = dict(hs=g(dut, "hs"), vs=g(dut, "vs"), de=g(dut, "de"), x=g(dut, "x"), y=g(dut, "y"), ls=g(dut, "line_start"),
                       vss=g(dut, "vs_start"), fc=g(dut, "frame_cnt"))
            assert got == exp, f"{name} clock {k}: {got} expected {exp}"
            if exp["vss"]:
                fs_seen.append(k)
            m.step(c)
        if name == "mid":
            gaps = {b - a for a, b in zip(fs_seen, fs_seen[1:])}
            assert gaps == {ht * vt}, f"{name}: frame period {gaps}, expected {ht * vt}"
        dut._log.info(f"TIMING {name}: {ht} x {vt} = {ht * vt} clocks per frame; {total} clocks equal the model on every output")
    # slip: an extra k clocks in the next frame
    base = dict(MODES["tiny"], en=1, slip=0)
    ht, vt = D.Timing.tot(base)
    for slip in (5, -3, 0, 100, -100):
        c = dict(base, slip=slip)
        await FallingEdge(dut.clk)
        c0 = dict(c, en=0)
        apply(c0)
        await FallingEdge(dut.clk)
        apply(c)
        marks = []
        for k in range(ht * vt * 3 + 400):
            await Timer(1, unit="ns")
            if g(dut, "vs_start"):
                marks.append(k)
            await FallingEdge(dut.clk)
        gaps = [b - a for a, b in zip(marks, marks[1:])]
        eff = max(slip, -(base["h_bp"] - 1))
        # slip applies to the line after the active area of every frame, and the vs marker is later in the frame
        assert all(gp == ht * vt + eff for gp in gaps), f"slip {slip}: frame periods {gaps}, expected {ht * vt + eff}"
    dut._log.info("TIMING: slip of +5, -3, 0, +100, -100 changes every frame period by exactly the clamped amount")
    # disabled: all outputs inactive
    c = dict(MODES["tiny"], en=0, slip=0)
    await FallingEdge(dut.clk)
    apply(c)
    await Timer(1, unit="ns")
    assert g(dut, "hs") == 0 and g(dut, "vs") == 0 and g(dut, "de") == 0


@cocotb.test()
async def t27_02_phase(dut):
    """T27-02 phase_meas against the model"""
    if G != "phase":
        return
    rng = random.Random(2702)
    dut.rx_fs.value = 0
    dut.disp_vs.value = 0
    dut.period.value = 1000
    dut.target.value = 300
    await start(dut)
    m = D.Phase()
    for run in range(6):
        period = rng.choice([1000, 777, 4000, 32, 1])
        target = rng.randint(0, max(0, period - 1))
        drift = rng.choice([0, 1, -1, 3])
        await FallingEdge(dut.clk)
        dut.period.value = period
        dut.target.value = target
        dut.rx_fs.value = 0
        dut.disp_vs.value = 0
        dut.rst_n.value = 0
        await FallingEdge(dut.clk)
        dut.rst_n.value = 1
        m = D.Phase()
        m.step(period, target, 0, 0)               # the clock in which the reset is released
        t_rx = 0
        t_dp = rng.randint(0, period)
        for k in range(period * 12 + 50):
            await FallingEdge(dut.clk)
            rx = 0
            dp = 0
            if k == t_rx:
                if rng.random() > 0.1:
                    rx = 1
                t_rx += period
            if k == t_dp:
                dp = 1
                t_dp += period + drift + (rng.randint(-2, 2) if period > 10 else 0)
            if rng.random() < 0.02:
                dp = 1
            dut.period.value = period
            dut.target.value = target
            dut.rx_fs.value = rx
            dut.disp_vs.value = dp
            await Timer(1, unit="ns")
            got = (gs(dut, "err", 24), g(dut, "err_valid"), g(dut, "lost"))
            exp = (m.err, m.valid, m.lost)
            assert got == exp, f"run {run} clock {k}: {got} expected {exp}"
            m.step(period, target, rx, dp)
    dut._log.info("PHASE: 6 runs (periods 1 to 4000, drift, missing and spurious pulses) equal the model clock by clock")


@cocotb.test()
async def t27_03_pi(dut):
    """T27-03 pi_steer against the model"""
    if G != "pi":
        return
    rng = random.Random(2703)
    dut.en.value = 1
    dut.hold.value = 0
    dut.err_valid.value = 0
    dut.err.value = 0
    dut.kp.value = 0
    dut.ki.value = 0
    dut.ppm_max.value = 500
    dut.slew_max.value = 2
    dut.preset_valid.value = 0
    dut.preset.value = 0
    await start(dut)
    m = D.PI()
    worst_step = 0
    n_up = 0
    for run in range(8):
        kp = rng.randint(0, 32767)
        ki = rng.randint(0, 32767) // rng.choice([1, 16, 256])
        ppm_max = rng.choice([500, 100, 4095])
        slew = rng.choice([1, 2, 10, 255])
        await FallingEdge(dut.clk)
        dut.en.value = 0
        await FallingEdge(dut.clk)
        m.step(0, 0, 0, 0, 0, 0, ppm_max, slew, 0, 0)
        for k in range(1501):
            ev = rng.random() < 0.3
            err = rng.randint(-3000, 3000) if rng.random() < 0.9 else rng.randint(-2 ** 22, 2 ** 22)
            hold = int(rng.random() < 0.05)
            en = int(rng.random() > 0.002) if k else 1
            pv = rng.random() < 0.003
            pre = rng.randint(-5000, 5000)
            await FallingEdge(dut.clk)
            await Timer(1, unit="ns")
            if k:                                              # the outputs after the edge of the previous clock
                assert (gs(dut, "ctl", 16), g(dut, "ctl_valid")) == (m.ctl, m.valid), \
                    f"run {run} clock {k}: {(gs(dut, 'ctl', 16), g(dut, 'ctl_valid'))} expected {(m.ctl, m.valid)}"
                if m.valid:
                    n_up += 1
                    assert abs(m.ctl) <= last["ppm_max"]
                    if not last["pv"]:
                        worst_step = max(worst_step, abs(m.ctl - last["prev"]))
                        assert abs(m.ctl - last["prev"]) <= slew, f"slew {abs(m.ctl - last['prev'])} > {slew}"
            if k == 1500:
                break
            dut.en.value = en
            dut.hold.value = hold
            dut.err_valid.value = int(ev)
            dut.err.value = err & 0xFFFFFF
            dut.kp.value = kp
            dut.ki.value = ki
            dut.ppm_max.value = ppm_max
            dut.slew_max.value = slew
            dut.preset_valid.value = int(pv)
            dut.preset.value = pre & 0xFFFF
            last = dict(prev=m.ctl, pv=pv, ppm_max=ppm_max)
            m.step(en, hold, int(ev), err, D.s(kp, 16), D.s(ki, 16), ppm_max, slew, int(pv), pre)
    dut._log.info(f"PI: 8 parameter sets, {n_up} updates equal the model; |ctl| within the limit and steps within the slew limit (largest step {worst_step})")


@cocotb.test()
async def t27_04_lines(dut):
    """T27-04 line_sel against the model"""
    if G != "lines":
        return
    rng = random.Random(2704)
    for n_ in ("swap", "wr_valid", "rd_req"):
        getattr(dut, n_).value = 0
    dut.wr_line.value = 0
    dut.wr_n.value = 0
    dut.rd_line.value = 0
    await start(dut)
    m = D.Lines()
    n_lines = 1080
    for frame in range(12):
        await FallingEdge(dut.clk)
        dut.swap.value = 1
        dut.wr_valid.value = 0
        dut.rd_req.value = 0
        await FallingEdge(dut.clk)
        m.step(1, 0, 0, 0, 0, 0)
        dut.swap.value = 0
        await Timer(1, unit="ns")
        # slices of random height arrive in a random order with random delays; lines are scanned in order
        slices = []
        ln = 0
        while ln < n_lines:
            h = rng.choice([8, 16, 30, 45, 135])
            h = min(h, n_lines - ln)
            slices.append((ln, h))
            ln += h
        arrivals = [(rng.randint(0, 3 * n_lines), a, h) for a, h in slices if rng.random() > 0.05]
        arrivals.sort()
        ai = 0
        for t in range(0, 3 * n_lines + 20):
            wr = 0
            wl = wn = 0
            while ai < len(arrivals) and arrivals[ai][0] <= t:
                _, wl, wn = arrivals[ai]
                wr = 1
                ai += 1
                break
            rd = 1 if (t % 3 == 0 and t // 3 < n_lines) else 0
            rl = t // 3 if rd else 0
            await FallingEdge(dut.clk)
            dut.wr_valid.value = wr
            dut.wr_line.value = wl
            dut.wr_n.value = wn
            dut.rd_req.value = rd
            dut.rd_line.value = rl
            m.step(0, wr, wl, wn, rd, rl)
            await FallingEdge(dut.clk)
            dut.wr_valid.value = 0
            dut.rd_req.value = 0
            await Timer(1, unit="ns")
            if rd:
                pass
            got = (g(dut, "use_cur"), g(dut, "buf_sel"), g(dut, "rd_valid"), g(dut, "late_wr_cnt"))
            if m.rd_valid:
                assert got[:3] == (m.use_cur, m.buf_sel, 1), f"frame {frame} t {t}: {got} vs {(m.use_cur, m.buf_sel)}"
            m.rd_valid = 0
            assert got[3] == m.late
        await FallingEdge(dut.clk)
    # the counters of the last finished frame are latched at swap
    await FallingEdge(dut.clk)
    dut.swap.value = 1
    await FallingEdge(dut.clk)
    dut.swap.value = 0
    m.step(1, 0, 0, 0, 0, 0)
    await Timer(1, unit="ns")
    assert (g(dut, "stale_cnt"), g(dut, "cur_cnt"), g(dut, "cur_buf")) == (m.stale, m.cur, m.cur_buf), (g(dut, "stale_cnt"), g(dut, "cur_cnt"), m.stale, m.cur)
    assert m.stale + m.cur == n_lines
    dut._log.info(f"LINES: 12 frames of random slice arrivals equal the model; last frame {m.cur} lines fresh, {m.stale} from the previous frame, {m.late} late slices in total")
