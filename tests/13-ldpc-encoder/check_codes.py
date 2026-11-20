#!/usr/bin/env python3
"""T13-09: waterfall check of the LDPC codes with AFF3CT (layered normalised min-sum, 20 iterations, BPSK over AWGN).

Usage: python3 tests/13-ldpc-encoder/check_codes.py [--frames N] [--errors E]
Writes the parity-check matrix of every code as an alist file in a temporary directory, runs AFF3CT at a few Eb/N0 points
and prints the frame error rate. Also runs an own-design 648/5/6 code next to the real 802.11n 648/5/6 code to measure
the cost of the own design.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
AFF3CT = "/home/arkady/tools/aff3ct/bin/aff3ct"

CODES = json.loads((HERE / "ldpc_codes.json").read_text())
RANGE = {"1/2": (1.0, 2.5), "2/3": (2.0, 3.5), "3/4": (2.5, 4.0), "5/6": (3.0, 4.5)}


def alist_text(base, z, kb, mb):
    n, m = 24 * z, mb * z
    cols = [[] for _ in range(n)]
    rows = [[] for _ in range(m)]
    for i in range(mb):
        for j in range(24):
            s = base[i][j]
            if s is None:
                continue
            for r in range(z):
                c = j * z + ((r + s) % z)
                rr = i * z + r
                cols[c].append(rr + 1)
                rows[rr].append(c + 1)
    cmax, rmax = max(map(len, cols)), max(map(len, rows))
    out = [f"{n} {m}", f"{cmax} {rmax}", " ".join(str(len(c)) for c in cols), " ".join(str(len(r)) for r in rows)]
    for c in cols:
        out.append(" ".join(map(str, c + [0] * (cmax - len(c)))))
    for r in rows:
        out.append(" ".join(map(str, r + [0] * (rmax - len(r)))))
    return "\n".join(out) + "\n"


def run(alist, k, n, lo, hi, frames, errors):
    cmd = [AFF3CT, "-C", "LDPC", "-K", str(k), "-N", str(n), "--enc-type", "LDPC_H", "--enc-g-method", "IDENTITY",
           "--dec-type", "BP_HORIZONTAL_LAYERED", "--dec-implem", "NMS", "--dec-ite", "20", "--dec-h-path", str(alist),
           "-m", str(lo), "-M", str(hi + 0.01), "-s", "0.5", "--mdm-type", "BPSK", "--chn-type", "AWGN", "-e", str(errors), "-n", str(frames)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    res = []
    for line in p.stdout.splitlines():
        f = line.replace("|", " ").split()
        if len(f) >= 9 and re.match(r"^-?\d+\.\d+$", f[0]):
            try:
                res.append((float(f[1]), int(f[2]), int(f[4]), float(f[6])))   # Eb/N0, frames, frame errors, FER
            except ValueError:
                pass
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=20000)
    ap.add_argument("--errors", type=int, default=30)
    a = ap.parse_args()
    import gen_ldpc_codes as g
    tmp = Path(tempfile.mkdtemp(prefix="ldpc_codes_"))
    jobs = []
    for c in CODES:
        jobs.append((f"code {c['code']} N={c['N']} R={c['rate']} ({c['source']})", c["base"], c["Z"], c["kb"], c["mb"], c["rate"]))
    own = g.design(4, 27, seed=1003)
    jobs.append(("own design N=648 R=5/6 (for comparison)", own, 27, 20, 4, "5/6"))
    allres = {}
    for name, base, z, kb, mb, rate in jobs:
        path = tmp / (re.sub(r"\W+", "_", name) + ".alist")
        path.write_text(alist_text(base, z, kb, mb))
        lo, hi = RANGE[rate]
        res = run(path, kb * z, 24 * z, lo, hi, a.frames, a.errors)
        allres[name] = res
        print(f"{name}: " + "  ".join(f"{eb:.1f} dB: FER {fer:.2e} ({fe}/{fr})" for eb, fr, fe, fer in res), flush=True)
    bad = [n for n, r in allres.items() if len(r) < 3 or not (r[0][3] > r[-1][3] or r[-1][3] == 0)]
    print("WATERFALL OK" if not bad else f"NO WATERFALL: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
