"""T30-05: frame error rate with combining and with more iterations (bit-exact model of module 20).
Usage: python3 stats_combining.py   (about 10 minutes on 12 cores). Prints the table and checks R30-08 and R30-09."""
import math
import random
import sys
from multiprocessing import Pool

from rxsim import CODES, combine, decode, encode, reception

# Eb/N0 grids per number of combined receptions (the combined curves sit about 3 dB to the left)
POINTS = {0: {1: [1.0, 1.5, 2.0, 2.5, 3.0, 3.5], 2: [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0], 3: [-3.5, -3.0, -2.5, -2.0, -1.5, -1.0]},
          4: {1: [1.0, 1.4, 1.8, 2.2, 2.6, 3.0], 2: [-2.0, -1.6, -1.2, -0.8, -0.4, 0.0, 0.4], 3: [-3.2, -2.8, -2.4, -2.0, -1.6, -1.2]}}
FRAMES = {0: 240, 4: 96}
NREC = 3


def one(args):
    ci, ebn0, seed, kmax = args
    rng = random.Random(seed)
    c = CODES[ci]
    msg = [rng.getrandbits(1) for _ in range(c["K"])]
    cw = encode(ci, msg)
    rx = [reception(ci, cw, ebn0, rng) for _ in range(kmax)]
    comb = rx[0]
    for k in range(1, kmax):
        comb = combine(comb, rx[k])
    res = {}
    for mi in (10, 20):
        bits, ok, it = decode(ci, comb, mi)
        res[mi] = int(not (ok and bits == msg))
    return res


def crossing(snr, fer, target):
    """Eb/N0 at which the FER curve crosses `target` (log-linear interpolation)"""
    pts = [(s, f) for s, f in zip(snr, fer)]
    for (s0, f0), (s1, f1) in zip(pts, pts[1:]):
        if f0 >= target >= f1 and f0 > f1:
            if f1 == 0:
                f1 = 0.5 / FRAMES_USED
            return s0 + (s1 - s0) * (math.log(f0) - math.log(target)) / (math.log(f0) - math.log(f1))
    return None


if __name__ == "__main__":
    ok = True
    with Pool(12) as pool:
        for ci in (0, 4):
            c = CODES[ci]
            FRAMES_USED = FRAMES[ci]
            fer = {}          # (iterations, receptions) -> list of (Eb/N0, FER)
            for k in (1, 2, 3):
                for ebn0 in POINTS[ci][k]:
                    rs = pool.map(one, [(ci, ebn0, 1000 * ci + 7 * i + int((ebn0 + 10) * 100), k) for i in range(FRAMES[ci])])
                    for mi in (10, 20):
                        fer.setdefault((mi, k), []).append((ebn0, sum(r[mi] for r in rs) / FRAMES[ci]))
            print(f"\nN = {c['N']} R = {c['rate']} ({FRAMES[ci]} frames per point); Eb/N0 per reception; FER")
            for mi in (10, 20):
                for k in (1, 2, 3):
                    print(f"  {mi} it, {k} rx: " + "  ".join(f"{e:+.1f}:{f:.3f}" for e, f in fer[(mi, k)]))
            cross = {}
            for mi in (10, 20):
                for k in (1, 2, 3):
                    snr = [e for e, f in fer[(mi, k)]]
                    cross[(mi, k)] = crossing(snr, [f for e, f in fer[(mi, k)]], 0.1)
                c1, c2, c3 = cross[(mi, 1)], cross[(mi, 2)], cross[(mi, 3)]
                if None in (c1, c2, c3):
                    print(f"  {mi} iterations: no crossing in the grid {cross}")
                    ok = False
                    continue
                print(f"  {mi} iterations: Eb/N0 at FER 10%: 1 rx {c1:.2f} dB, 2 rx {c2:.2f} dB (gain {c1 - c2:.2f} dB), 3 rx {c3:.2f} dB (gain {c1 - c3:.2f} dB)")
                if mi == 10 and c1 - c2 < 2.0:
                    print("  FAIL: combining gain below 2.0 dB (R30-08)")
                    ok = False
            if cross[(10, 1)] and cross[(20, 1)]:
                print(f"  20 against 10 iterations (1 rx): {cross[(10, 1)] - cross[(20, 1)]:.2f} dB at FER 10%")
            # R30-09: FER(20) <= FER(10) within 3 sigma at every point
            for k in (1, 2, 3):
                for (e, f10), (e2, f20) in zip(fer[(10, k)], fer[(20, k)]):
                    sd = math.sqrt(max(f10 * (1 - f10), 0.01) / FRAMES[ci])
                    if f20 > f10 + 3 * sd:
                        print(f"  FAIL: FER(20) {f20:.3f} above FER(10) {f10:.3f} at {e} dB, {k} rx")
                        ok = False
    print("\nSTATS", "PASSED" if ok else "FAILED")
    sys.exit(0 if ok else 1)
