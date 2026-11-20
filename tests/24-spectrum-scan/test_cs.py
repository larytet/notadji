import math
import random
import subprocess
import sys
import traceback

import numpy as np

from cs import FLOOR, FW, HERE, Sel, level, load, loss_ppm

LIB = load()
TESTS = []


def test(f):
    TESTS.append(f)
    return f


def make_spectrum(rng, n=12, busy=5):
    """Interference levels (lg) per channel: some busy channels at different strengths, the others at the floor."""
    lv = [FLOOR] * n
    for c in rng.sample(range(n), busy):
        lv[c] = level(FLOOR, [FLOOR + rng.randint(20, 160)])
    return lv


def feed_scans(sel, spec, t, rng=None, sigma=0.0, skip=None):
    for c in range(len(spec)):
        if c != skip:
            sel.scan(c, spec[c] + (rng.gauss(0, sigma) if rng else 0), t)


@test
def t24_05_ranking():
    rng = random.Random(2405)
    n_trials = 300
    for trial in range(n_trials):
        n = rng.choice([8, 12, 20])
        mask = (1 << n) - 1
        # some channels disabled
        for c in rng.sample(range(n), rng.randint(0, 2)):
            mask &= ~(1 << c)
        sel = Sel(LIB, start=rng.randrange(n), n_ch=n, enabled_mask=mask)
        spec = make_spectrum(rng, n, rng.randint(2, n - 2))
        t = 10000
        for c in range(n):
            if rng.random() < 0.9:
                sel.scan(c, spec[c], t - rng.choice([0, 0, 100, 5000]))
        # a blacklisted channel: induce through the API by severe loss right after a switch is complex; use quality memory instead
        for c in rng.sample(range(n), 2):
            sel.s.ch[c].q_valid = 1
            sel.s.ch[c].q_t = t - 100
            sel.s.ch[c].q_loss = 100000
        cfg = sel.cfg
        strong = lambda c: 0 <= c < n and sel.s.ch[c].have and t - sel.s.ch[c].t_scan < cfg.stale_ms and (sel.s.ch[c].lvl_q4 >> 4) >= cfg.strong_lg
        exp = {}
        for c in range(n):
            k = sel.s.ch[c]
            if not (mask >> c) & 1 or not k.have:
                exp[c] = None
                continue
            v = k.lvl_q4 >> 4
            if t - k.t_scan >= cfg.stale_ms:
                v += cfg.unknown_pen
            v += cfg.adj_pen * (int(strong(c - 1)) + int(strong(c + 1)))
            if k.q_valid and t - k.q_t < cfg.memory_ms and k.q_loss >= cfg.loss_trig_ppm:
                v += cfg.qual_pen
            exp[c] = v
        for c in range(n):
            got = sel.score(c, t)
            if exp[c] is None:
                assert got == 0x7FFFFFFF, f"trial {trial} ch {c}: {got} should be unusable"
            else:
                assert got == exp[c], f"trial {trial} ch {c}: {got} expected {exp[c]}"
    return f"{n_trials} random spectra with disabled, unscanned, stale, strong-adjacent and remembered-bad channels: every score equals the independent formula"


def run_link(sel, spec_fn, t_end, step_loss, rng, sigma=0.0, scan_period=1, own_period=10, t0=0, frame_ms=1):
    """One link in a time-stepped model; spec_fn(t) -> list of channel levels; loss follows the level of the link's own channel."""
    n = sel.cfg.n_ch
    switches = []
    rr = 0
    for t in range(t0, t_end):
        spec = spec_fn(t)
        if t % scan_period == 0:
            c = rr % n
            rr += 1
            if c != sel.cur:
                sel.scan(c, spec[c] + (rng.gauss(0, sigma) if sigma else 0), t)
        if t % own_period == 0:
            sel.scan(sel.cur, spec[sel.cur] + (rng.gauss(0, sigma) if sigma else 0), t)
        loss = step_loss(t, sel.cur, spec)
        sel.quality(loss, t)
        d = sel.tick(t, t // frame_ms)
        if d.switch_now:
            switches.append((t, d.target, d.reason, d.effective_frame))
    return switches


@test
def t24_06_hysteresis():
    rng = random.Random(2406)
    n = 12
    # no degradation: scan noise of 2 dB (about 10.6 lg units) on a spectrum with two nearly equal best channels: no switch at all in 5 minutes
    spec = [level(FLOOR, [FLOOR - 20])] * n          # about 4 lg above the floor: no loss
    spec[3] = FLOOR
    spec[7] = FLOOR + 1
    sel = Sel(LIB, start=5, n_ch=n)
    sw = run_link(sel, lambda t: spec, 300000, lambda t, c, s: 0, rng, sigma=10.6)
    assert not sw, f"{len(sw)} switches without any degradation"
    # a real degradation of the current channel at 1 s: one switch to one of the two best, none back in the following 2 minutes
    bad = level(FLOOR, [FLOOR + 120])
    cur = 5

    def spec2(t):
        s2 = list(spec)
        if t >= 1000:
            s2[cur] = bad
        return s2

    sel = Sel(LIB, start=cur, n_ch=n)
    sw = run_link(sel, spec2, 120000, lambda t, c, s: loss_ppm(s[c] - FLOOR), rng, sigma=10.6)
    assert len(sw) == 1 and sw[0][1] in (3, 7), sw
    return f"no switch in 5 minutes with 2 dB scan noise and two equal best channels and no degradation; after a real degradation exactly one switch (to channel {sw[0][1]}, reason {sw[0][2]}, at t = {sw[0][0]} ms) and none in the next 2 minutes"


@test
def t24_07_latency():
    rng = random.Random(2407)
    worst = {"loss": 0, "severe": 0}
    for kind, target in (("loss", 200000), ("severe", 800000)):
        lat = []
        for trial in range(500):
            n = 12
            spec = make_spectrum(rng, n, 5)
            cur = rng.choice([c for c in range(n) if spec[c] == FLOOR])
            sel = Sel(LIB, start=cur, n_ch=n)
            t_step = rng.randint(1500, 4000)
            res = {}

            def loss(t, c, s):
                return target if (t >= t_step and c == cur) else 0

            sw = run_link(sel, lambda t: spec, t_step + 100, loss, rng, sigma=2.0)
            assert sw, f"{kind} trial {trial}: no decision"
            assert sw[0][0] >= t_step
            lat.append(sw[0][0] - t_step)
        worst[kind] = max(lat)
        assert max(lat) <= 20, f"{kind}: latency {max(lat)} ms"
    return f"500 trials each: decision latency after a step of the loss to 20% at most {worst['loss']} ms, to 80% (severe) at most {worst['severe']} ms (ADA-002: 20 ms); 1 ms ticks, det_ms 10"


@test
def t24_08_interferer():
    rng = random.Random(2408)
    ok = 0
    for trial in range(100):
        n = 12
        spec = make_spectrum(rng, n, 4)
        cur = rng.choice([c for c in range(n) if spec[c] == FLOOR])
        t_on = rng.randint(2000, 5000)
        occupied = {cur}

        def spec_fn(t):
            s2 = list(spec)
            if t >= t_on:
                s2[cur] = level(FLOOR, [FLOOR + 110])
            return s2

        sel = Sel(LIB, start=cur, n_ch=n)
        sw = run_link(sel, spec_fn, t_on + 3000, lambda t, c, s: loss_ppm(s[c] - FLOOR), rng, sigma=3.0)
        assert sw, f"trial {trial}: no switch"
        tgt = sw[0][1]
        assert tgt != cur and spec[tgt] <= FLOOR + 1 or spec[tgt] == min(spec), f"trial {trial}: moved to a busy channel {tgt} ({spec[tgt]})"
        assert sw[0][0] - t_on <= 25, f"trial {trial}: latency {sw[0][0] - t_on}"
        assert len(sw) == 1, f"trial {trial}: {len(sw)} switches"
        ok += 1
    return f"{ok} trials: a 110 lg (20 dB) interferer on the current channel: one switch to a clean channel within 25 ms (scan noise 3 lg), never to a busy one"


@test
def t24_09_probation():
    rng = random.Random(2409)
    n = 12
    spec = [FLOOR] * n
    spec[0] = level(FLOOR, [FLOOR + 120])          # current channel is hit at t = 2000
    spec[1] = FLOOR - 4                              # the obvious best candidate
    spec[2] = FLOOR
    spec[3] = FLOOR + 1
    sel = Sel(LIB, start=0, n_ch=n)
    sw_all = []

    def spec_fn(t):
        s2 = list(spec)
        if t < 2000:
            s2[0] = FLOOR
        return s2

    # channel 1 turns bad 5 ms after the link arrives there (a second interferer that the scan does not show)
    arrival = {}

    def loss(t, c, s):
        if t >= 2000 and c == 0:
            return loss_ppm(s[0] - FLOOR)
        if c == 1 and 1 in arrival and t >= arrival[1] + 5:
            return 900000
        return 0

    t = 0
    rr = 0
    for t in range(0, 12000):
        s2 = spec_fn(t)
        c = rr % n
        rr += 1
        if c != sel.cur:
            sel.scan(c, s2[c] + rng.gauss(0, 2), t)
        if t % 10 == 0:
            sel.scan(sel.cur, s2[sel.cur] + rng.gauss(0, 2), t)
        sel.quality(loss(t, sel.cur, s2), t)
        d = sel.tick(t, t)
        if d.switch_now:
            sw_all.append((t, d.target, d.reason))
            arrival[d.target] = t
            if len(sw_all) == 2:
                bl_at_switch = sel.s.ch[1].bl
    targets = [x[1] for x in sw_all]
    assert targets[0] == 1, sw_all
    assert len(sw_all) >= 2 and sw_all[1][1] not in (0, 1) and spec[sw_all[1][1]] <= FLOOR + 1, sw_all
    assert sw_all[1][2] == 4, f"second switch reason {sw_all[1][2]} (probation)"
    gaps = [b[0] - a[0] for a, b in zip(sw_all, sw_all[1:])]
    assert all(g >= 10 for g in gaps)
    assert len(sw_all) == 2, sw_all
    assert bl_at_switch == 1, "the bad channel is not blacklisted"
    return f"degraded channel 0 -> channel 1 at t = {sw_all[0][0]} ms; channel 1 bad 5 ms after arrival -> blacklisted, channel {sw_all[1][1]} at t = {sw_all[1][0]} ms (reason probation); no further switch"


@test
def t24_10_fallback():
    rng = random.Random(2410)
    n = 12
    sel = Sel(LIB, start=4, n_ch=n, fallback=[9, 2, 6])
    sw = []
    t = 0
    sel_loss = lambda c: 900000
    # no scan data at all; the link is dead on every channel: it should walk the fallback list, one entry per probation period
    for t in range(0, 3000):
        sel.quality(sel_loss(sel.cur), t)
        d = sel.tick(t, t)
        if d.switch_now:
            sw.append((t, d.target, d.reason))
    tg = [x[1] for x in sw]
    assert tg[:3] == [9, 2, 6], sw
    assert all(x[2] in (4, 5) for x in sw), sw
    # a blacklisted fallback entry is skipped
    sel = Sel(LIB, start=4, n_ch=n, fallback=[9, 2, 6])
    sel.s.ch[9].bl = 1
    sel.s.ch[9].bl_until = 100000
    d = None
    for t in range(0, 50):
        sel.quality(900000, t)
        d = sel.tick(t, t)
        if d.switch_now:
            break
    assert d.switch_now and d.target == 2, (d.switch_now, d.target)
    return f"no scan data and a dead link: the fallback list is walked in order {tg[:3]} ({len(sw)} switches in 3 s); a blacklisted entry is skipped"


@test
def t24_11_several_links():
    rng = random.Random(2411)
    n, nl, T = 12, 4, 60000
    sels = []
    for i in range(nl):
        sels.append(Sel(LIB, start=0, n_ch=n, link_id=i * 37 + 5, jitter_ms=8, min_stay_ms=500))
    jam = [None]
    jam_t = [0]
    switches = [[] for _ in range(nl)]
    co = 0
    co_by_second = 0
    rr = [i * 3 for i in range(nl)]
    for t in range(T):
        if t % 5000 == 0:
            jam[0] = rng.randrange(n)
        occ = [s.cur for s in sels]
        for i, s in enumerate(sels):
            # level of each channel as seen by link i: its own transmission excluded
            others = [occ[j] for j in range(nl) if j != i]
            spec = []
            for c in range(n):
                itf = [FLOOR + 80 for o in others if o == c]
                if jam[0] == c:
                    itf.append(FLOOR + 100)
                itf += [FLOOR + 80 - 133 for o in others if abs(o - c) == 1]
                spec.append(level(FLOOR, itf))
            c = rr[i] % n
            rr[i] += 1
            if c != s.cur:
                s.scan(c, spec[c] + rng.gauss(0, 2), t)
            if t % 10 == i % 10:
                s.scan(s.cur, spec[s.cur] + rng.gauss(0, 2), t)
            s.quality(loss_ppm(spec[s.cur] - FLOOR), t)
            d = s.tick(t, t)
            if d.switch_now:
                switches[i].append((t, d.target, d.reason))
        if t % 1000 == 999:
            occ2 = [s.cur for s in sels]
            if len(set(occ2)) < nl:
                co += 1
    nsw = [len(x) for x in switches]
    # no link switches more than once per min_stay unless severe
    for i, lst in enumerate(switches):
        for a, b in zip(lst, lst[1:]):
            assert b[0] - a[0] >= 500 or b[2] in (3, 4), f"link {i}: switches {a} {b} closer than the minimum stay"
    final = [s.cur for s in sels]
    cof = co / (T / 1000)
    assert cof <= 0.25, f"{cof:.2f} of the seconds with two links on one channel"
    return f"4 links, 12 channels, jammer moving every 5 s, 60 s: switches per link {nsw}, seconds with a shared channel {co} of {T // 1000} ({cof:.2f}), final channels {final}"


@test
def t24_13_min_stay():
    """T24-13 interference alternates between two channels every 100 ms: switches (not severe) are at least min_stay apart"""
    rng = random.Random(2413)
    n = 8
    sel = Sel(LIB, start=0, n_ch=n)
    hot = level(FLOOR, [FLOOR + 40])        # excess ~ 41 lg: loss about 70000 ppm, above the trigger and below the severe limit

    def spec_fn(t):
        s2 = [FLOOR] * n
        s2[0 if (t // 100) % 2 == 0 else 1] = hot
        s2[2] = s2[3] = s2[4] = s2[5] = s2[6] = s2[7] = FLOOR + 6
        return s2

    sw = run_link(sel, spec_fn, 20000, lambda t, c, s: loss_ppm(s[c] - FLOOR), rng, sigma=2.0)
    gaps = [b[0] - a[0] for a, b in zip(sw, sw[1:]) if b[2] != 3]
    assert len(sw) >= 1
    assert all(g >= 500 for g in gaps), f"switches closer than the minimum stay: {gaps[:5]}"
    return f"{len(sw)} switches in 20 s under alternating interference; the shortest gap between non-severe switches is {min(gaps) if gaps else 'n/a'} ms (minimum stay 500 ms)"


@test
def t24_14_margin():
    """T24-14 a candidate that is not clearly better than the degraded current channel is not taken"""
    rng = random.Random(2414)
    n = 8
    res = {}
    for name, cand_off in (("not clearly better", 48), ("clearly better", 20)):
        cur_lvl = level(FLOOR, [FLOOR + 90])
        spec = [cur_lvl + cand_off] * n
        spec[0] = cur_lvl
        sel = Sel(LIB, start=0, n_ch=n, rise=100000, strong_lg=4000)       # only the loss triggers, no adjacent-channel penalty
        sw = run_link(sel, lambda t: spec, 400, lambda t, c, s: 60000 if c == 0 else 0, rng, sigma=0.0)
        res[name] = len(sw)
    assert res["not clearly better"] == 0 and res["clearly better"] == 1, res
    return f"loss of 6% on the current channel: candidates 48 lg above its level are not taken, candidates 20 lg above it are (the loss penalty of the current channel at 6% is 48 lg, the margin 16)"


@test
def t24_12_portability():
    src = str(FW / "chan_select.c")
    obj = str(HERE / "build" / "cs_strict.o")
    subprocess.check_call(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Wconversion", "-Wshadow", "-Werror", "-mgeneral-regs-only", "-ffreestanding", "-c", src, "-I", str(FW), "-o", obj])
    und = subprocess.run(["nm", "-u", obj], capture_output=True, text=True).stdout.strip()
    assert und == "", und
    size = subprocess.run(["size", obj], capture_output=True, text=True).stdout.splitlines()[-1].split()
    exe = str(HERE / "build" / "cs_fuzz")
    subprocess.check_call(["gcc", "-std=c99", "-g", "-O1", "-fsanitize=undefined,address", "-fno-sanitize-recover=all", str(HERE / "cs_fuzz.c"), src, "-I", str(FW), "-o", exe])
    r = subprocess.run([exe], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return f"strict build clean, no undefined symbols, text {size[0]} bytes, data {size[1]}, bss {size[2]}; random inputs under UBSan/ASan: {r.stdout.strip()}"


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
