"""Rate-distortion helpers shared by the module 32 tests."""
import math
import sys
from pathlib import Path

import numpy as np

T = Path(__file__).resolve().parents[1]
import os
sys.path.insert(0, os.environ.get("SL2_DIR", str(T.parent / "fw" / "32-codec")))
sys.path.insert(0, str(T / "29-custom-codec"))
import seqgen        # noqa: E402
import sl2           # noqa: E402

W, H, SH = 320, 256, 32
NF = 12
BPP = W * H


def psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return 99.0 if mse == 0 else 10 * np.log10(255 ** 2 / mse)


def get_seq(i=0, n=NF):
    return [f.astype(np.uint8) for f in seqgen.sequence(i, n)]


def run_sl2(args):
    """args: (tools, qp, seq index, frames). Returns (bits per pixel averaged over frames, mean PSNR, stats)"""
    tools, qp, si, nf = args
    seq = get_seq(si, nf)
    c = sl2.Codec(W, H, SH, tools)
    c.stats_reset()
    ref, bits, ps = None, 0, []
    for f in seq:
        sl, rec, _ = c.encode_frame(f, ref, qp=qp)
        bits += sum(len(b) for b in sl) * 8
        ps.append(psnr(f, rec))
        ref = rec
    return bits / nf / BPP, float(np.mean(ps)), c.stats()


def bits_at(curve, target):
    """bpp at the PSNR target by log-linear interpolation of (bpp, psnr) points; None outside the measured range"""
    pts = sorted(curve, key=lambda p: p[1])
    for (b0, p0), (b1, p1) in zip(pts, pts[1:]):
        if p0 <= target <= p1 and p1 > p0:
            t = (target - p0) / (p1 - p0)
            return math.exp(math.log(b0) + t * (math.log(b1) - math.log(b0)))
    return None
