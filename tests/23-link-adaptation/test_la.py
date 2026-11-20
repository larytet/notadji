import math
import random
import subprocess
import sys
import traceback

import numpy as np

from la import Ctl, FW, HERE, load, p_loss

LIB = load()
TESTS = []


def test(f):
    TESTS.append(f)
    return f


def closed_loop(ctl, snr_fn, n_msgs, rng, sigma=0.0, bias=0.0, t0=0, power_effect=True, rec=255, record=None):
    """1 ms messages, 8 slices each; the slice losses come from the controller's MCS and the true SNR."""
    lost_tot = sent_tot = 0
    t = t0
    hist = []
    for k in range(n_msgs):
        t += 1000
        true = snr_fn(k)
        if power_effect:
            true -= (ctl.cfg.pwr_max_x4 - ctl.s.pwr_x4) / 4.0
        thr = ctl.thr[ctl.s.mcs]
        pl = p_loss(thr, true)
        n_lost = int(rng.binomial(8, pl))
        meas = true + bias + (rng.normal(0, sigma) if sigma else 0.0)
        o = ctl.feed(t, int(round(meas * 10)), 8, n_lost, rec)
        lost_tot += n_lost
        sent_tot += 8
        hist.append((t, o.mcs, o.pwr_x4, n_lost, true))
    return dict(lost=lost_tot, sent=sent_tot, hist=hist, t=t)


@test
def t23_01_table_and_budget():
    c = Ctl(LIB)
    thr, rate = c.thr, c.rate
    assert all(thr[i] < thr[i + 1] for i in range(len(thr) - 1)), "threshold not monotonic"
    assert all(rate[i] < rate[i + 1] for i in range(len(rate) - 1)), "rate not monotonic"
    rungs = [c.cfg.mcs[i].rung for i in range(c.cfg.n_mcs)]
    assert all(rungs[i] >= rungs[i + 1] for i in range(len(rungs) - 1)), "rung not monotonic"
    for dl, tones, spf, share in ((40, 234, 8, 218), (30, 108, 4, 200), (100, 468, 12, 128), (17, 58, 1, 256)):
        for kw in (dict(dl_sym_per_frame=dl, data_tones=tones, slices_per_frame=spf, video_share_x256=share),):
            c2 = Ctl(LIB, kw)
            for m in range(c2.cfg.n_mcs):
                exact = dl * tones * (c2.rate[m] / 256) * (share / 256) / spf / 8
                got = LIB.la_slice_budget(__import__("ctypes").byref(c2.cfg), m)
                assert abs(got - exact) <= 2, f"mcs {m}: {got} vs {exact:.1f}"
    assert LIB.la_slice_budget(__import__("ctypes").byref(c.cfg), 99) == 0
    return f"{len(thr)} MCS, budget within 2 bytes of the exact value for 4 configurations"


@test
def t23_02_static_channel():
    rng = np.random.default_rng(2302)
    rows = []
    for snr10 in range(0, 301, 15):
        snr = snr10 / 10
        c = Ctl(LIB)
        r = closed_loop(c, lambda k: snr, 20000, rng)
        last = r["hist"][-10000:]
        mcs = [h[1] for h in last]
        sw = sum(1 for a, b in zip(mcs, mcs[1:]) if a != b)
        ideal = max([m for m, t in enumerate(c.thr) if t / 10 <= snr], default=0)
        loss = sum(h[3] for h in last) / (8 * len(last))
        at_ideal = sum(1 for m in mcs if m == ideal) / len(mcs)
        assert ideal - 2 <= min(mcs) and max(mcs) <= ideal + 1 and at_ideal >= 0.75, f"snr {snr}: mcs {min(mcs)}..{max(mcs)} ideal {ideal}, {at_ideal:.2f} of the time at the ideal"
        assert sw <= 10, f"snr {snr}: {sw} switches in 10 s"
        if snr >= c.thr[0] / 10:
            assert loss <= 0.01, f"snr {snr}: loss {loss}"
        rows.append((snr, ideal, max(mcs), sw, loss, at_ideal))
    worst_sw = max(r[3] for r in rows)
    mean_at = sum(r[5] for r in rows) / len(rows)
    return f"21 SNR values (mean {mean_at:.2f} of the time at the ideal MCS): MCS at the ideal at least 75% of the time and never above it by more than one index (a failed probe can cost up to two below), at most {worst_sw} switches in 10 s, loss <= 1%"


@test
def t23_03_step_down():
    rng = np.random.default_rng(2303)
    worst = 0
    for drop_to in (2.0, 8.0, 13.0, 19.0):
        c = Ctl(LIB)
        r = closed_loop(c, lambda k: 28.0, 12000, rng)
        t = r["t"]
        res = []
        true0 = drop_to - (c.cfg.pwr_max_x4 - c.s.pwr_x4) / 4.0
        for k in range(30):
            t += 1000
            true = drop_to - (c.cfg.pwr_max_x4 - c.s.pwr_x4) / 4.0
            pl = p_loss(c.thr[c.s.mcs], true)
            nl = int(rng.binomial(8, pl))
            o = c.feed(t, int(round(true * 10)), 8, nl)
            res.append(o.mcs)
        ideal = max([m for m, th in enumerate(c.thr) if th / 10 <= true0 + c.cfg.down_hys_x10 / 10], default=0)
        assert res[0] == ideal, f"drop to {drop_to}: first message gives MCS {res[0]}, expected {ideal}"
        assert res[-1] in (ideal, ideal + 1) or drop_to < 2.0
        worst = max(worst, next((i for i, m in enumerate(res) if m <= ideal), 99))
    return "a 28 dB -> 2/8/13/19 dB drop is followed in the very first feedback message (<= 1 ms of the 2 ms of MAC-005)"


@test
def t23_04_climb_and_rate():
    rng = np.random.default_rng(2304)
    c = Ctl(LIB)
    r = closed_loop(c, lambda k: 5.0, 3000, rng)
    t0 = r["t"]
    ups = []
    prev = c.s.mcs
    t = t0
    for k in range(3000):
        t += 1000
        true = 28.0 - (c.cfg.pwr_max_x4 - c.s.pwr_x4) / 4.0
        nl = int(rng.binomial(8, p_loss(c.thr[c.s.mcs], true)))
        o = c.feed(t, int(round(true * 10)), 8, nl)
        if o.mcs > prev:
            ups.append(t - t0)
        assert o.mcs - prev <= 1, "more than one index per step up"
        prev = o.mcs
    gaps = [b - a for a, b in zip(ups, ups[1:])]
    assert all(g >= c.cfg.up_dwell_us for g in gaps), f"steps closer than one frame: {gaps}"
    top = c.s.mcs
    n_in_1s = sum(1 for u in ups if u <= 1_000_000)
    assert n_in_1s >= 4, f"only {n_in_1s} steps in the first second"
    assert top >= 8
    return f"{len(ups)} steps up, {n_in_1s} within the first second (>= 4 per second), never more than one index per frame; end at MCS {top}"


@test
def t23_05_noisy_measurement():
    rng = np.random.default_rng(2305)
    snr = 16.0
    c = Ctl(LIB)
    r = closed_loop(c, lambda k: snr, 30000, rng, sigma=1.5)
    mcs = [h[1] for h in r["hist"][10000:]]
    sw = sum(1 for a, b in zip(mcs, mcs[1:]) if a != b)
    # naive controller: the highest MCS whose threshold is met by each single measurement
    thr = c.thr
    meas = snr + rng.normal(0, 1.5, 20000)
    naive = [max([m for m, t in enumerate(thr) if t / 10 <= x], default=0) for x in meas]
    sw_naive = sum(1 for a, b in zip(naive, naive[1:]) if a != b)
    assert sw <= 20, f"{sw} switches in 20 s"
    assert sw_naive > 5 * max(sw, 1), f"naive {sw_naive} vs {sw}"
    loss = sum(h[3] for h in r["hist"][10000:]) / (8 * 20000)
    return f"sigma 1.5 dB: {sw} switches in 20 s ({sw / 20:.2f} per second) against {sw_naive / 20:.0f} per second without filter and hysteresis; slice loss {loss:.4f}"


@test
def t23_06_outer_loop():
    rng = np.random.default_rng(2306)
    out = []
    for bias in (3.0, -3.0):
        for snr in (16.5, 18.0):
            res = {}
            for label, step in (("olla", 200000), ("off", 0)):
                c = Ctl(LIB, dict(per_target_ppm=10000, olla_step_udb=step))
                r = closed_loop(c, lambda k: snr, 60000, rng, bias=bias)
                tail = r["hist"][30000:]
                loss = sum(h[3] for h in tail) / (8 * len(tail))
                rate = float(np.mean([c.rate[h[1]] * (1 - h[3] / 8) for h in tail]))
                res[label] = (loss, rate, c.s.offset_udb / 1e6)
            ideal = max([m for m, t in enumerate(c.thr) if t / 10 <= snr], default=0)
            out.append((bias, snr, res))
            if bias > 0:
                assert res["olla"][0] < 0.03, f"bias {bias} snr {snr}: loss {res['olla'][0]:.3f}"
                assert res["olla"][0] < res["off"][0] or res["off"][0] < 0.03
            elif snr == 18.0:
                assert res["olla"][1] >= res["off"][1] * 1.05, f"bias {bias} snr {snr}: rate {res['olla'][1]:.0f} vs {res['off'][1]:.0f}"
    s = "; ".join(f"bias {b:+.0f} dB snr {sn}: loss {r['olla'][0]:.4f} (off {r['off'][0]:.3f}), good rate {r['olla'][1]:.0f} (off {r['off'][1]:.0f}), offset {r['olla'][2]:+.1f} dB" for b, sn, r in out)
    return s


@test
def t23_07_power_loop():
    rng = np.random.default_rng(2307)
    c = Ctl(LIB)
    r = closed_loop(c, lambda k: 38.0, 8000, rng)
    p = [h[2] for h in r["hist"]]
    assert p[0] >= p[-1] and all(a >= b for a, b in zip(p, p[1:])), "power not monotonic on a constant channel"
    assert p[-1] < p[0]
    final_true = 38.0 - (c.cfg.pwr_max_x4 - p[-1]) / 4
    assert c.cfg.pwr_min_x4 <= p[-1] <= c.cfg.pwr_max_x4
    assert c.s.mcs == c.cfg.mcs_max
    steps = [a - b for a, b in zip(p, p[1:]) if a != b]
    assert all(s_ == 4 for s_ in steps), steps
    # the SNR falls by 10 dB: power comes back up
    r2 = closed_loop(c, lambda k: 28.0, 8000, rng, t0=r["t"])
    p2 = [h[2] for h in r2["hist"]]
    assert max(p2) > p[-1], "power did not rise after the fall"
    dirs = sum(1 for a, b, d in zip(p2, p2[1:], p2[2:]) if (b - a) * (d - b) < 0)
    # limits and a channel at the very top
    c3 = Ctl(LIB, dict(pwr_min_x4=100))
    r3 = closed_loop(c3, lambda k: 45.0, 6000, rng)
    assert min(h[2] for h in r3["hist"]) >= 100
    # constant channel at a level inside the band: few direction changes
    c4 = Ctl(LIB)
    r4 = closed_loop(c4, lambda k: 30.0, 20000, rng)
    p4 = [h[2] for h in r4["hist"]]
    ch = [b - a for a, b in zip(p4, p4[1:]) if a != b]
    dc = sum(1 for a, b in zip(ch, ch[1:]) if a * b < 0)
    assert dc <= 2, f"{dc} direction changes"
    return (f"constant 38 dB: power from {p[0]} to {p[-1]} (units of 0.25 dB), true SNR {final_true:.1f} dB, one 1 dB step at a time; "
            f"after a 10 dB fall power rises again (max {max(p2)}); floor respected; {dc} direction changes at 30 dB")


@test
def t23_08_timeout_and_safe():
    c = Ctl(LIB)
    rng = np.random.default_rng(2308)
    r = closed_loop(c, lambda k: 25.0, 3000, rng)
    t = r["t"]
    assert c.s.mcs >= 5
    first_safe = None
    for k in range(1, 30):
        o = c.tick(t + k * 1000)
        if o.safe and first_safe is None:
            first_safe = k
            assert o.mcs == c.cfg.mcs_min and o.pwr_x4 == c.cfg.pwr_max_x4
        if not o.safe:
            assert k < 10, "timeout late"
    assert first_safe == 10, f"safe after {first_safe} ms"
    t2 = t + 50000
    o = c.feed(t2, 250, 8, 0)
    assert not o.safe
    assert o.mcs == c.cfg.mcs_min or o.mcs == c.cfg.mcs_min + 1
    return "safe schedule exactly 10 ms after the last message (lowest MCS, maximum power); the next message ends it and the climb restarts from the lowest MCS"


@test
def t23_09_outage():
    c = Ctl(LIB)
    t = 0
    out_at = None
    for k in range(100):
        t += 1000
        o = c.feed(t, 5, 8, 8)           # 0.5 dB: below thr[0] - 1 dB
        if o.outage and out_at is None:
            out_at = k + 1
    assert out_at is not None and 20 <= out_at <= 22, out_at
    cleared = None
    for k in range(400):
        t += 1000
        o = c.feed(t, 150, 8, 0)
        if not o.outage and cleared is None:
            cleared = k + 1
    assert cleared is not None and cleared <= 150, cleared
    return f"outage raised after {out_at} ms below the lowest threshold, cleared {cleared} ms after the SNR returns to 15 dB (rise filter)"


def fading(n, fd=100.0, mean_db=20.0, seed=7, k_db=None):
    """Sum-of-sinusoids fading trace in dB, 1 kHz sampling; k_db: Rician K factor (None: Rayleigh)."""
    rng = np.random.default_rng(seed)
    nsin = 16
    th = rng.uniform(0, 2 * np.pi, nsin)
    ph = rng.uniform(0, 2 * np.pi, nsin)
    ph2 = rng.uniform(0, 2 * np.pi, nsin)
    tt = np.arange(n) / 1000.0
    I = sum(np.cos(2 * np.pi * fd * np.cos(a) * tt + p) for a, p in zip(th, ph)) / math.sqrt(nsin / 2)
    Q = sum(np.cos(2 * np.pi * fd * np.cos(a) * tt + p) for a, p in zip(th, ph2)) / math.sqrt(nsin / 2)
    if k_db is None:
        power = (I ** 2 + Q ** 2) / 2
    else:
        k = 10 ** (k_db / 10)
        power = (math.sqrt(k / (k + 1)) + I / math.sqrt(2 * (k + 1))) ** 2 + (Q / math.sqrt(2 * (k + 1))) ** 2
    return mean_db + 10 * np.log10(np.maximum(power, 1e-3))


def fade_run(trace, seed):
    rng = np.random.default_rng(seed)
    n = len(trace)
    c = Ctl(LIB)
    r = closed_loop(c, lambda k: float(trace[k]), n, rng, sigma=0.5, power_effect=False)
    h = r["hist"]
    loss = r["lost"] / r["sent"]
    good = float(np.mean([c.rate[x[1]] * (1 - x[3] / 8) for x in h]))
    sw = sum(1 for a, b in zip(h, h[1:]) if a[1] != b[1]) / (n / 1000.0)
    best, best_m = 0.0, 0
    for m in range(c.cfg.n_mcs):
        g_ = float(np.mean([c.rate[m] * (1 - p_loss(c.thr[m], float(x))) for x in trace]))
        if g_ > best:
            best, best_m = g_, m
    genie = float(np.mean([c.rate[max([m for m, t in enumerate(c.thr) if t / 10 <= x], default=0)] for x in trace]))
    return loss, good, sw, best, best_m, genie


@test
def t23_10_fade_trace():
    n = 30000
    ray = fade_run(fading(n, 100.0, 22.0), 2310)
    ric = fade_run(fading(n, 100.0, 22.0, k_db=10.0), 2311)
    assert ray[0] < 0.08 and ray[1] >= 0.6 * ray[3], f"Rayleigh: {ray}"
    assert ric[0] < 0.03 and ric[1] >= 0.85 * ric[3], f"Rician: {ric}"
    f = lambda tag, r: (f"{tag}: slice loss {r[0]:.4f}, goodput {r[1]:.0f} against best fixed MCS {r[4]} {r[3]:.0f} and a per-millisecond genie {r[5]:.0f} "
                        f"(1/256 bit per tone), {r[2]:.0f} MCS changes per second")
    return "100 Hz Doppler, mean 22 dB, 30 s. " + f("Rayleigh", ray) + ". " + f("Rician K = 10 dB", ric)


@test
def t23_11_portability():
    src = str(FW / "link_adapt.c")
    obj = str(HERE / "build" / "la_strict.o")
    subprocess.check_call(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Wconversion", "-Wshadow", "-Werror", "-mgeneral-regs-only", "-ffreestanding", "-c", src, "-I", str(FW), "-o", obj])
    undefined = subprocess.run(["nm", "-u", obj], capture_output=True, text=True).stdout.strip()
    assert undefined == "", f"undefined symbols: {undefined}"
    size = subprocess.run(["size", obj], capture_output=True, text=True).stdout.splitlines()[-1].split()
    dis = subprocess.run(["objdump", "-d", obj], capture_output=True, text=True).stdout
    fp = [l for l in dis.splitlines() if any(x in l for x in ("xmm", "%st", "fld", "fst"))]
    assert not fp, fp[:3]
    return f"-std=c99 -Wall -Wextra -Wconversion -Wshadow -Werror -mgeneral-regs-only: clean; no undefined symbols; no floating-point instructions; text {size[0]} bytes, data {size[1]}, bss {size[2]} (x86-64 -O2)"


@test
def t23_12_determinism_and_sanitizers():
    def run():
        rng = np.random.default_rng(1)
        c = Ctl(LIB)
        r = closed_loop(c, lambda k: 15 + 10 * math.sin(k / 700), 5000, rng, sigma=1.0)
        return [(h[1], h[2]) for h in r["hist"]]
    assert run() == run()
    exe = str(HERE / "build" / "la_fuzz")
    subprocess.check_call(["gcc", "-std=c99", "-g", "-O1", "-fsanitize=undefined,address", "-fno-sanitize-recover=all", str(HERE / "la_fuzz.c"), str(FW / "link_adapt.c"), "-I", str(FW), "-o", exe])
    res = subprocess.run([exe], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    return "identical outputs on two runs; 2 million random feedback messages under UBSan and ASan with invariant checks: " + res.stdout.strip()


if __name__ == "__main__":
    rc = 0
    only = sys.argv[1:]
    for f in TESTS:
        if only and f.__name__ not in only:
            continue
        try:
            msg = f()
            print(f"  pass  {f.__name__}")
            print(f"        {msg}")
        except Exception:
            rc = 1
            print(f"  FAIL  {f.__name__}")
            traceback.print_exc(limit=3, file=sys.stdout)
    print("ALL TESTS PASSED" if rc == 0 else "SOME TESTS FAILED")
    sys.exit(rc)
