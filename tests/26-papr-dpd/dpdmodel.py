"""Bit-exact Python models of the module 26 blocks."""
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import gen_cfr_tables as gct  # noqa: E402

def _read_coef():
    txt = (ROOT / "rtl" / "26-papr-dpd" / "cfr_coef_pkg.sv").read_text()
    body = txt[txt.index("CFR_COEF_FLAT = {"):txt.index("  };")]
    vals = [int(v, 16) for v in re.findall(r"16'h([0-9a-fA-F]{4})", body)]
    vals = vals[::-1]
    return [v - 65536 if v >= 32768 else v for v in vals]


COEF = _read_coef()
TAPS = len(COEF)


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def pack(i, q):
    return ((int(q) & 0xFFFF) << 16) | (int(i) & 0xFFFF)


def unpack(w):
    return s16(w & 0xFFFF), s16((w >> 16) & 0xFFFF)


def sat(v, lo=-32768, hi=32767):
    return max(lo, min(hi, v))


def clip_model(samples, table):
    out = []
    for i, q in samples:
        m2 = i * i + q * q
        idx = min(255, m2 >> 22)
        g = table[idx]
        out.append((sat((i * g + 16384) >> 15), sat((q * g + 16384) >> 15)))
    return out


def fir_model(samples, coef=None):
    c = coef or COEF
    t = len(c)
    di = [0] * t
    dq = [0] * t
    out = []
    for i, q in samples:
        di = [i] + di[:-1]
        dq = [q] + dq[:-1]
        si = sum(c[k] * di[k] for k in range(t)) + 16384
        sq = sum(c[k] * dq[k] for k in range(t)) + 16384
        out.append((sat(si >> 15), sat(sq >> 15)))
    return out


def chain_model(samples, tab1, tab2):
    return fir_model(clip_model(fir_model(clip_model(samples, tab1)), tab2))


class Basis:
    def __init__(self):
        self.bi = [[0, 0, 0] for _ in range(3)]
        self.bq = [[0, 0, 0] for _ in range(3)]

    def push(self, i, q):
        m2 = i * i + q * q
        r = min(32767, m2 >> 15)
        r2 = (r * r + 16384) >> 15
        new = [(i, q), ((i * r + 16384) >> 15, (q * r + 16384) >> 15), ((i * r2 + 16384) >> 15, (q * r2 + 16384) >> 15)]
        for j in range(3):
            self.bi[j] = [new[j][0]] + self.bi[j][:2]
            self.bq[j] = [new[j][1]] + self.bq[j][:2]

    def phi(self):
        return [(self.bi[t // 3][t % 3], self.bq[t // 3][t % 3]) for t in range(9)]


def dpd_model(samples, coefs):
    """coefs: list of 9 (re, im) Q4.12 integers; returns the output samples"""
    b = Basis()
    out = []
    for i, q in samples:
        b.push(i, q)
        ph = b.phi()
        ar = sum(coefs[t][0] * ph[t][0] - coefs[t][1] * ph[t][1] for t in range(9))
        ai = sum(coefs[t][0] * ph[t][1] + coefs[t][1] * ph[t][0] for t in range(9))
        out.append((sat((ar + 2048) >> 12), sat((ai + 2048) >> 12)))
    return out


def corr_model(pairs):
    """pairs: (y, u) complex integer tuples; returns the 54 accumulators as (re, im) integers"""
    b = Basis()
    acc = [[0, 0] for _ in range(54)]
    for (yi, yq), (ui, uq) in pairs:
        b.push(yi, yq)
        ph = b.phi()
        e = 0
        for p in range(9):
            for q in range(p, 9):
                a, bb = ph[p]
                c, d = ph[q]
                acc[e][0] += a * c + bb * d
                acc[e][1] += a * d - bb * c
                e += 1
        for p in range(9):
            a, bb = ph[p]
            acc[e][0] += a * ui + bb * uq
            acc[e][1] += a * uq - bb * ui
            e += 1
    return acc
