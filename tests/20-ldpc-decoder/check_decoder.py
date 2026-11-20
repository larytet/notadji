#!/usr/bin/env python3
"""T20-04: frame error rate of the bit-exact decoder model against AFF3CT (layered normalised min-sum, 20 iterations).

Usage: python3 tests/20-ldpc-decoder/check_decoder.py [--frames 100]
Runs the Python model (the same arithmetic as the RTL) over the N = 648 rate 5/6 standard code and one own-design code at three
Eb/N0 points and AFF3CT with the same parity-check matrix at the same points; prints both frame error rates.
"""
import argparse
import math
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
T = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(T / "13-ldpc-encoder"))
from dec_model import CODES, decode, noisy_llr       # noqa: E402
import check_codes                                    # noqa: E402

AFF3CT = "/home/arkady/tools/aff3ct/bin/aff3ct"


def aff3ct_fer(code, points, frames=20000, errors=40):
    path = Path(tempfile.mkdtemp(prefix="dec_cmp_")) / "h.alist"
    path.write_text(check_codes.alist_text(code["base"], code["Z"], code["kb"], code["mb"]))
    lo, hi = points[0], points[-1]
    cmd = [AFF3CT, "-C", "LDPC", "-K", str(code["K"]), "-N", str(code["N"]), "--enc-type", "LDPC_H", "--enc-g-method", "IDENTITY",
           "--dec-type", "BP_HORIZONTAL_LAYERED", "--dec-implem", "NMS", "--dec-ite", "20", "--dec-h-path", str(path),
           "-m", str(lo), "-M", str(hi + 0.01), "-s", str(points[1] - points[0]), "--mdm-type", "BPSK", "--chn-type", "AWGN",
           "-e", str(errors), "-n", str(frames)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    res = {}
    for line in p.stdout.splitlines():
        f = line.replace("|", " ").split()
        if len(f) >= 9 and re.match(r"^-?\d+\.\d+$", f[0]):
            res[round(float(f[1]), 1)] = (float(f[6]), int(f[2]), int(f[4]))
    return res


def model_fer(ci, ebn0, frames, seed):
    rng = random.Random(seed)
    c = CODES[ci]
    bad = 0
    for _ in range(frames):
        msg = [rng.getrandbits(1) for _ in range(c["K"])]
        cw, llr = noisy_llr(ci, msg, ebn0, rng)
        bits, ok, it = decode(ci, llr, 20)
        bad += int(bits != msg)
    return bad / frames, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=100)
    a = ap.parse_args()
    plan = [(3, [3.2, 3.6, 4.0]), (0, [1.8, 2.2, 2.6])]
    for ci, pts in plan:
        c = CODES[ci]
        ref = aff3ct_fer(c, pts)
        print(f"code {ci}: N={c['N']} R={c['rate']} ({c['source']})")
        for eb in pts:
            f, bad = model_fer(ci, eb, a.frames, 1000 + int(eb * 10))
            r = ref.get(round(eb, 1))
            rs = f"AFF3CT FER {r[0]:.3e} ({r[2]}/{r[1]})" if r else "AFF3CT n/a"
            print(f"  Eb/N0 {eb:.1f} dB: model FER {f:.3f} ({bad}/{a.frames})   {rs}", flush=True)


if __name__ == "__main__":
    main()
