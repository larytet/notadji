import ctypes as C
import math
import subprocess
import sys
import traceback
from pathlib import Path

import numpy as np

import dmodel as D

HERE = Path(__file__).resolve().parent
FW = HERE.parent.parent / "fw" / "27-display"
TESTS = []
CLK = 200e6
PERIOD = round(CLK / 60)            # 60 Hz frame in system clocks
KP = 3277                            # Q16: 0.05 x 0.1 ppm per clock
KI = 6711                            # Q24: 0.0004 x 0.1 ppm per clock per update


def test(f):
    TESTS.append(f)
    return f


def flight(seed, e0_ppm, jitter="gauss", sigma=20.0, drift_ppm_min=1.0, minutes=10, hold_at=None, hold_s=0, preset=0, outage_s=0, kp=KP, ki=KI):
    """frame-by-frame loop with the bit-exact PI model; returns the lateness history in clocks"""
    rng = np.random.default_rng(seed)
    n = int(minutes * 60 * 60)
    pi = D.PI()
    pi.step(1, 0, 0, 0, 0, 0, 500, 2, 1 if preset else 0, preset)
    phi = 0.0
    ctl_applied = pi.ctl
    hist = np.zeros(n)
    ctls = np.zeros(n)
    for k in range(n):
        e = e0_ppm + drift_ppm_min * k / 3600.0
        hist[k] = phi
        ctls[k] = pi.ctl
        # the display marker is measured one frame after the control was applied
        if jitter == "gauss":
            j = rng.normal(0, sigma)
        else:
            j = rng.uniform(-200, 200)
        err = int(round(phi + j))
        hold = 1 if (hold_at is not None and hold_at <= k < hold_at + hold_s * 60) else 0
        pi.step(1, hold, 1, err, kp, ki, 500, 2, 0, 0)
        # plant: the control word written now acts on the next frame
        phi = phi - PERIOD * 1e-6 * (e + ctl_applied * 0.1)
        ctl_applied = pi.ctl
    return hist, ctls


@test
def t27_05_steering_loop():
    rows = []
    for e0 in (40.0, -40.0, 25.0, 0.0):
        h, c = flight(5, e0)
        us = h * 5e-3
        lock = int(np.argmax(np.abs(h[:]) < 20 * 5)) if np.any(np.abs(h) < 100) else None
        # lock time: first frame after which |phase| stays below 1 us (200 clocks) for 10 s
        win = 600
        ok = np.abs(h) < 200
        lock_frame = next((i for i in range(len(h) - win) if ok[i:i + win].all()), None)
        after = h[lock_frame:] if lock_frame is not None else h
        rows.append((e0, np.abs(us).max(), np.abs(after * 5e-3).max(), lock_frame / 60.0 if lock_frame is not None else None, np.abs(c).max() / 10, np.abs(np.diff(c)).max() / 10))
        assert np.abs(us).max() < 1000, f"initial offset {e0}: deviation {np.abs(us).max():.0f} us"
        assert np.abs(c).max() <= 500 and np.abs(np.diff(c)).max() <= 2
    # uniform +/-1 us reference jitter (the MAC-003 bound)
    h, c = flight(6, 25.0, jitter="uniform")
    dev_u = np.abs(h * 5e-3).max()
    lock_frame = next(i for i in range(len(h) - 600) if (np.abs(h[i:i + 600]) < 400).all())
    dev_u_after = np.abs(h[lock_frame:] * 5e-3).max()
    assert dev_u < 1000
    # gaussian 0.1 us: tight after lock
    hg, cg = flight(7, 25.0)
    lf = next(i for i in range(len(hg) - 600) if (np.abs(hg[i:i + 600]) < 200).all())
    dev_g = np.abs(hg[lf:] * 5e-3).max()
    assert dev_g < 50, f"{dev_g} us"
    # the 1 ppm residual figure of 07: 0.6 ms over 10 minutes
    resid = 1e-6 * 600 * 1e6
    # reference outage of 10 s (holdover) after lock
    ho, co = flight(8, 25.0, hold_at=60 * 120, hold_s=10)
    seg = ho[60 * 120: 60 * 130 + 5]
    ho_dev = np.abs(seg * 5e-3).max()
    ho_after = np.abs(ho[60 * 135:] * 5e-3).max()
    assert ho_dev < 1000
    # preset integrator (value of the last flight): starts locked
    hp, cp = flight(9, 25.0, preset=-250)
    dev_p = np.abs(hp * 5e-3).max()
    s = "; ".join(f"offset {r[0]:+.0f} ppm: peak deviation {r[1]:.0f} us, after lock (at {r[3]:.1f} s) {r[2]:.1f} us, steering up to {r[4]:.1f} ppm, largest step {r[5]:.1f} ppm" for r in rows)
    return (s + f". Reference jitter uniform +/-1 us: peak {dev_u:.0f} us, after lock {dev_u_after:.0f} us. Gaussian 0.1 us: after lock {dev_g:.1f} us. "
            f"A fixed 1 ppm residual would give {resid:.0f} us over 10 minutes. Reference outage of 10 s: deviation {ho_dev:.0f} us during it, {ho_after:.1f} us afterwards. "
            f"With the integrator preset to the true offset: peak {dev_p:.0f} us")


@test
def t27_06_early_scanout():
    so = HERE / "build" / "libsr.so"
    so.parent.mkdir(exist_ok=True)
    subprocess.check_call(["gcc", "-std=c99", "-O2", "-shared", "-fPIC", str(FW / "start_rule.c"), "-I", str(FW), "-o", str(so)])
    lib = C.CDLL(str(so))
    class St(C.Structure):
        _fields_ = [("mean", C.c_int32 * 64), ("var", C.c_uint32 * 64), ("seen", C.c_uint8 * 64), ("n", C.c_uint8)]
    lib.sr_init.argtypes = [C.POINTER(St), C.c_uint8]
    lib.sr_report.argtypes = [C.POINTER(St), C.c_uint8, C.c_int32, C.c_int32]
    lib.sr_start.argtypes = [C.POINTER(St), C.c_int32, C.c_int32]
    lib.sr_start.restype = C.c_int32
    rng = np.random.default_rng(2706)
    t_line = 1e6 / 60 / 1125                    # us
    out = []
    for name, d_dec, jit in (("fast decoder (0.2 ms per slice)", 200.0, 150.0), ("slower decoder (0.5 ms per slice, 36 lines scan in 0.53 ms)", 500.0, 150.0),
                              ("too slow decoder (0.7 ms per slice)", 700.0, 150.0)):
        ns, h = 30, 36
        st = St()
        lib.sr_init(C.byref(st), ns)
        base = 1000.0
        late = 0
        lines = 0
        Ls = []
        for frame in range(2600):
            T = base + np.arange(ns) * d_dec + rng.lognormal(math.log(jit), 0.5, ns) - jit
            a = np.arange(ns) * h * t_line
            L = lib.sr_start(C.byref(st), 794, 150)
            if frame >= 600:                     # after the statistics have settled
                Ls.append(L)
                late += int(np.sum(T > L + a)) * h
                lines += ns * h
            for k in range(ns):
                lib.sr_report(C.byref(st), k, int(round(T[k])), int(round(a[k])))
        L = float(np.mean(Ls))
        full = base + (ns - 1) * d_dec + 150          # wait for the last slice
        frac = late / lines
        out.append((name, L, full, frac))
        assert frac < 3e-3, f"{name}: late fraction {frac:.4f}"
        assert L <= full + 1
    # line_sel model over frames with the same arrivals: late slices appear as stale lines
    ln = D.Lines()
    stale = 0
    for frame in range(30):
        ln.step(1, 0, 0, 0, 0, 0)
        stale += ln.stale
        ns, h = 30, 36
        T = 1000.0 + np.arange(ns) * 200 + rng.lognormal(math.log(150), 0.5, ns) - 150
        Lstart = 1450.0
        for k in range(ns):
            ln.step(0, 1, k * h, h, 0, 0) if T[k] <= Lstart + k * h * t_line else None
        for y in range(1080):
            ln.step(0, 0, 0, 0, 1, y)
    ln.step(1, 0, 0, 0, 0, 0)
    assert stale / (29 * 1080) < 0.01, stale
    return "; ".join(f"{n}: start offset {L / 1000:.2f} ms against {f / 1000:.2f} ms for waiting for the whole frame (saves {(f - L) / 1000:.2f} ms), late-line fraction {fr:.1e}" for n, L, f, fr in out)


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
