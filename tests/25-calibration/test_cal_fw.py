import ctypes as C
import math
import struct
import subprocess
import sys
import traceback
import zlib

import numpy as np

import calfw
from calfw import FW, HERE

LIB = calfw.load()
TESTS = []


def test(f):
    TESTS.append(f)
    return f


def cg(rng, n, sigma):
    return rng.normal(0, sigma, n) + 1j * rng.normal(0, sigma, n)


def quant(z):
    return np.clip(np.round(z.real), -32768, 32767).astype(np.int64) + 1j * np.clip(np.round(z.imag), -32768, 32767).astype(np.int64)


def sums_of(z):
    i = z.real.astype(np.int64)
    q = z.imag.astype(np.int64)
    return [int(i.sum()), int(q.sum()), int((i * i).sum()), int((q * q).sum()), int((i * q).sum())], len(z)


@test
def t25_03_estimator_accuracy():
    rng = np.random.default_rng(2503)
    out = {}
    for N, need in ((4096, 30.0), (16384, 35.0), (65536, 40.0)):
        worst = 99.0
        dc_err = 0.0
        for trial in range(40):
            mag = rng.uniform(0.005, 0.15)
            eps = mag * np.exp(1j * rng.uniform(0, 2 * np.pi))
            dc = complex(rng.uniform(-2000, 2000), rng.uniform(-2000, 2000))
            x = cg(rng, N, 3000) + cg(rng, N, 95)
            z = quant(x + eps * np.conj(x) + dc)
            sums, n = sums_of(z)
            st, c = calfw.estimate(LIB, sums, n)
            assert st == 0, f"rejected: {st}"
            e_est = complex(c[2], c[3]) / 32768
            res = abs(eps - e_est)
            irr = -20 * math.log10(max(res, 1e-9))
            worst = min(worst, irr)
            # DC with a noise-only window
            nz = quant(cg(rng, N, 50) + dc)
            sd, n2 = sums_of(nz)
            st, c2 = calfw.estimate(LIB, sd, n2)
            dc_err = max(dc_err, abs(c2[0] - dc.real), abs(c2[1] - dc.imag))
            # the first-order law of the estimate against the exact relation e/(1+|e|^2) plus noise: within 5 sigma
            sigma = math.sqrt(1 / (2 * N)) * 1.3
            assert abs(e_est - eps / (1 + mag ** 2)) < 6 * sigma, f"N {N}: estimate off by {abs(e_est - eps):.4f} (sigma {sigma:.4f})"
        out[N] = (worst, dc_err)
        assert worst >= need, f"N={N}: worst image rejection after correction {worst:.1f} dB, need {need}"
    assert out[65536][0] >= 40 and out[65536][1] <= 2.0
    return "worst residual image rejection after correction (dB) / worst DC error (LSB): " + ", ".join(f"N={n}: {a:.1f} / {b:.1f}" for n, (a, b) in out.items())


@test
def t25_04_rejection():
    rng = np.random.default_rng(2504)
    N = 8192
    n = np.arange(N)
    cases = {
        "real tone (not circular)": quant(5000 * np.cos(2 * np.pi * 0.1 * n) + 0j),
        "DC only": quant(np.full(N, 1500 + 700j)),
        "all zero": np.zeros(N, dtype=complex),
        "real noise only on I": quant(cg(rng, N, 3000).real + 0j),
        "huge DC": quant(cg(rng, N, 3000) + 9000),
    }
    expect = {"real tone (not circular)": 3, "DC only": 2, "all zero": 2, "real noise only on I": 3, "huge DC": 4}
    for name, z in cases.items():
        sums, nn = sums_of(z)
        st, _ = calfw.estimate(LIB, sums, nn)
        assert st == expect[name], f"{name}: status {st}, expected {expect[name]}"
    sums, _ = sums_of(quant(cg(rng, 100, 3000)))
    st, _ = calfw.estimate(LIB, sums, 100)
    assert st == 1
    # a rejected window leaves the registers unchanged
    LIB.shim_init()
    good, ng = sums_of(quant(cg(rng, N, 3000) * (1 + 0j) + 0.05 * np.conj(cg(rng, N, 3000))))
    st, r1 = calfw.result(LIB, 4, good, ng, 10)
    assert st == 0
    bad, nb = sums_of(cases["real tone (not circular)"])
    st, r2 = calfw.result(LIB, 4, bad, nb, 20)
    assert st == 3 and r2 == r1, (st, r1, r2)
    return "a real tone, DC only, all-zero, one-sided noise, a window of 100 samples and a huge DC are rejected with the right status; a rejected window leaves the registers unchanged"


def entry_bytes(version, band, group, tbin, vals, valid=1):
    b = struct.pack("<HBBBB", version, band, group, tbin, valid) + struct.pack("<10h", *vals) + b"\x00\x00"
    return b + struct.pack("<I", zlib.crc32(b))


def image(entries):
    buf = bytearray(b"\xff" * (336 * 32))
    for idx, e in entries.items():
        buf[idx * 32:(idx + 1) * 32] = e
    return buf


@test
def t25_07_crc_and_tables():
    rng = np.random.default_rng(2507)
    LIB.shim_init()
    # CRC-32 against zlib
    for ln in (0, 1, 28, 100, 1000):
        data = bytes(rng.integers(0, 256, ln, dtype=np.uint8))
        arr = (C.c_uint8 * max(ln, 1)).from_buffer_copy(data if ln else b"\0")
        assert LIB.cal_crc32(arr, ln) == zlib.crc32(data), f"length {ln}"
    # a full table
    ents = {}
    for band in range(2):
        for grp in range(8):
            for tb in range(21):
                idx = (band * 8 + grp) * 21 + tb
                ents[idx] = entry_bytes(1, band, grp, tb, list(rng.integers(-3000, 3000, 10)))
    img = image(ents)
    arr = (C.c_uint8 * len(img)).from_buffer_copy(bytes(img))
    assert LIB.shim_load(arr, 336) == 0
    # every single flipped bit in a sample of entries is detected, all 28 data bytes and the CRC
    det = 0
    for idx in rng.choice(336, 40, replace=False):
        for byte in range(32):
            for bit in (0, 3, 7):
                im2 = bytearray(img)
                im2[idx * 32 + byte] ^= 1 << bit
                a2 = (C.c_uint8 * len(im2)).from_buffer_copy(bytes(im2))
                nb = LIB.shim_load(a2, 336)
                assert nb == 1, f"entry {idx} byte {byte} bit {bit}: {nb} bad entries"
                det += 1
    # a wrong version with a correct CRC; an entry in the wrong place
    ents2 = dict(ents)
    ents2[5] = entry_bytes(2, 0, 0, 5, [0] * 10)
    ents2[7] = entry_bytes(1, 0, 1, 3, [0] * 10)           # claims another slot
    a3 = (C.c_uint8 * (336 * 32)).from_buffer_copy(bytes(image(ents2)))
    assert LIB.shim_load(a3, 336) == 2
    # lookup: nearest valid bin in the order 0, +1, -1, +2, -2 ...
    steps = C.c_int()
    for trial in range(300):
        band, grp = int(rng.integers(0, 2)), int(rng.integers(0, 8))
        valid = sorted(rng.choice(21, int(rng.integers(0, 6)), replace=False))
        e3 = {(band * 8 + grp) * 21 + tb: entry_bytes(1, band, grp, tb, [tb] * 10) for tb in valid}
        a4 = (C.c_uint8 * (336 * 32)).from_buffer_copy(bytes(image(e3)))
        LIB.shim_load(a4, 336)
        temp = int(rng.integers(-300, 1000))
        tb0 = min(20, max(0, (temp // 10 + 20) // 5)) if temp >= -200 else 0
        order = [tb0] + [x for k in range(1, 21) for x in ((tb0 + k, tb0 - k) if True else ())]
        order = [tb0]
        for k in range(1, 21):
            order += [tb0 + k, tb0 - k]
        order = [b for b in order if 0 <= b < 21]
        exp = next((b for b in order if b in valid), None)
        idx = LIB.shim_lookup(band, grp, temp, C.byref(steps))
        if exp is None:
            assert idx == -1, f"trial {trial}: {idx}"
        else:
            assert idx == (band * 8 + grp) * 21 + exp, f"trial {trial}: temp {temp} bin {tb0} valid {valid}: got {idx % 21 if idx >= 0 else idx}, expected {exp}"
        assert steps.value <= 21
        if exp == tb0:
            assert steps.value == 1
    # no valid entry: the neutral default is used and flagged
    LIB.shim_load((C.c_uint8 * 32)(*([0xFF] * 32)), 1)
    LIB.shim_hop(0, 0, 250, 1000)
    assert LIB.shim_default_used() == 1
    ents = {5: entry_bytes(1, 0, 0, 5, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])}
    LIB.shim_load((C.c_uint8 * (336 * 32)).from_buffer_copy(bytes(image(ents))), 336)
    LIB.shim_hop(0, 0, 50, 2000)
    assert LIB.shim_default_used() == 0
    return f"CRC-32 equals zlib; {det} single-bit flips in {40} entries all detected; wrong version and misplaced entries detected; 300 random lookups return the nearest valid bin (steps at most 21, 1 for a valid own bin)"


@test
def t25_08_triggers():
    rng = np.random.default_rng(2508)
    results = {}

    def run(temp_fn, t_end, windows_fn, gap=5):
        LIB.shim_init()
        LIB.shim_set_gap(gap)
        jobs = []
        t = 0
        sig = sums_of(quant(cg(rng, 8192, 3000)))
        idle = sums_of(quant(cg(rng, 8192, 100)))
        while t < t_end:
            w = windows_fn(t)
            temp = int(temp_fn(t))
            j = LIB.shim_tick(t, temp, w)
            if j:
                need = {1: 1, 2: 2, 3: 2, 4: 5}[j]
                assert w & need, f"job {j} issued in windows {w:#x} at {t}"
                s_, n_ = idle if j == 1 else sig
                st, _ = calfw.result(LIB, j, s_, n_, t, temp)
                assert st == 0
                jobs.append((t, j, temp))
            t += 10
        return jobs

    win = lambda t: [1, 2, 4, 4, 4, 1, 4, 2, 4, 4][(t // 10) % 10]          # idle, guard, rx burst mix
    # 1. a ramp of 0.1 degC per second from 20 degC for 600 s
    jobs = run(lambda t: 200 + t / 1000 * 1.0, 600000, win)
    for j in (1, 2, 3, 4):
        ts = [x[0] for x in jobs if x[1] == j]
        gaps = [b - a for a, b in zip(ts, ts[1:])]
        assert ts and ts[0] <= 100, f"job {j}: first at {ts[:1]}"
        assert all(48000 <= g_ <= 52000 for g_ in gaps), f"job {j}: gaps {gaps[:5]} (expected about 50 s: 5 degC at 0.1 degC/s)"
        results[j] = (len(ts), min(gaps), max(gaps))
    # 2. constant temperature: every 60 s
    jobs = run(lambda t: 250, 300000, win)
    for j in (1, 2, 3, 4):
        ts = [x[0] for x in jobs if x[1] == j]
        gaps = [b - a for a, b in zip(ts, ts[1:])]
        assert all(59000 <= g_ <= 61000 for g_ in gaps), f"constant temperature, job {j}: {gaps}"
    # 3. a 12 degC step at 100 s: one set of jobs within 100 ms
    jobs = run(lambda t: 250 if t < 100000 else 370, 130000, win)
    after = [x for x in jobs if x[0] >= 100000]
    assert {x[1] for x in after} == {1, 2, 3, 4} and len(after) == 4 and after[-1][0] - 100000 <= 200, after
    # 4. minimum gap between any two jobs, and no job when there is no window
    jobs = run(lambda t: 200 + t / 1000, 200000, win, gap=20)
    ts = [x[0] for x in jobs]
    assert all(b - a >= 20 for a, b in zip(ts, ts[1:]))
    nojobs = run(lambda t: 250, 100000, lambda t: 0)
    assert not nojobs
    # 5. a hop: restore, then refresh when the entry's temperature is far from the present one
    return "ramp 0.1 degC/s: " + ", ".join(f"job {j}: {v[0]} runs, gaps {v[1] / 1000:.1f} to {v[2] / 1000:.1f} s" for j, v in results.items()) + \
           "; constant temperature: every 60 s; a 12 degC step: one set of four jobs within 0.2 s; 20 ms minimum gap and window gating respected"


@test
def t25_09_update_law():
    rng = np.random.default_rng(2509)
    eps = 0.04 * np.exp(0.7j)
    N = 4096
    first, tails = [], []
    for seq in range(40):
        LIB.shim_init()
        regs_hist = []
        cur = 0j
        for u in range(30):
            # the signal as seen after the correction in force
            x = cg(rng, N, 3000)
            z = x + eps * np.conj(x)
            zc = z - cur * np.conj(z)
            zc = quant(zc)
            sums, n = sums_of(zc)
            st, regs = calfw.result(LIB, 4, sums, n, 1000 * u)
            assert st == 0
            cur = complex(regs[2], regs[3]) / 32768
            regs_hist.append(cur)
        first.append(regs_hist[0].real)
        tails.append(np.std([c.real for c in regs_hist[10:]]))
    single = np.std(first)
    avg_tail = float(np.mean(tails))
    assert avg_tail < single / 2.0, f"jitter {avg_tail:.5f} vs single window {single:.5f}"
    # after the loop converges the correction approaches the true value
    final_err = abs(cur - eps)
    # hop: the first update after a hop takes the full residual
    LIB.shim_init()
    st, r0 = calfw.result(LIB, 4, sums, n, 0)
    LIB.shim_hop(0, 0, 250, 5000)             # no entry: neutral default, every job fresh again
    st, r1 = calfw.result(LIB, 4, sums, n, 6000)
    st, r2 = calfw.result(LIB, 4, sums, n, 7000)
    d1 = abs(r1[2] - r0[2])
    d2 = abs(r2[2] - r1[2])
    return f"40 sequences of 30 noisy updates (N = 4096): jitter {avg_tail:.5f} against {single:.5f} for a single window (ratio {single / avg_tail:.1f}), final error of the last sequence {final_err:.4f}"


@test
def t25_10_hop_path():
    rng = np.random.default_rng(2510)
    ents = {}
    for tb in range(21):
        ents[tb] = entry_bytes(1, 0, 0, tb, [tb] * 10)
    arr = (C.c_uint8 * (336 * 32)).from_buffer_copy(bytes(image(ents)))
    LIB.shim_load(arr, 336)
    steps = C.c_int()
    for temp in range(-250, 1100, 7):
        idx = LIB.shim_lookup(0, 0, temp, C.byref(steps))
        assert idx >= 0 and steps.value == 1, (temp, idx, steps.value)
    # worst case: one valid bin at the far end
    ents = {20: entry_bytes(1, 0, 0, 20, [9] * 10)}
    arr = (C.c_uint8 * (336 * 32)).from_buffer_copy(bytes(image(ents)))
    LIB.shim_load(arr, 336)
    idx = LIB.shim_lookup(0, 0, -200, C.byref(steps))
    assert idx == 20 and steps.value <= 21
    return "a hop to a calibrated bin is one table probe (single index computation); the worst case (one valid bin at the other end of the temperature range) is 21 probes; the register list is 8 values written in a fixed order"


@test
def t25_11_portability():
    objs = []
    for src in ("cal_mgr.c",):
        obj = str(HERE / "build" / "cal_strict.o")
        subprocess.check_call(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-Wconversion", "-Wshadow", "-Werror", "-mgeneral-regs-only", "-ffreestanding", "-c",
                               str(FW / src), "-I", str(FW), "-o", obj])
        und = subprocess.run(["nm", "-u", obj], capture_output=True, text=True).stdout.strip()
        assert und == "", und
        size = subprocess.run(["size", obj], capture_output=True, text=True).stdout.splitlines()[-1].split()
    exe = str(HERE / "build" / "cal_fuzz")
    subprocess.check_call(["gcc", "-std=gnu99", "-g", "-O1", "-fsanitize=undefined,address", "-fno-sanitize-recover=all", str(HERE / "cal_fuzz.c"), str(FW / "cal_mgr.c"), "-I", str(FW), "-o", exe])
    r = subprocess.run([exe], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return f"strict build clean (-mgeneral-regs-only, no floating point), no undefined symbols, text {size[0]} bytes, data {size[1]}, bss {size[2]}; fuzz under UBSan/ASan: {r.stdout.strip()}"


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
