"""Bit-exact models of dft_mixed, dfts_tx and dfts_rx (design/31-dft-s-ofdm.md), floating-point references, helpers."""
import math
import sys
from pathlib import Path

T = next(q for q in Path(__file__).resolve().parents if (q / "12-fft").is_dir())     # the tests directory (also from a mutation copy)
sys.path.insert(0, str(T / "12-fft"))
sys.path.insert(0, str(T / "17-equalizer"))
from fft_model import fft_fixed, sat16      # noqa: E402
from eq_model import recip                  # noqa: E402

MS = [48, 96, 192, 384]
SHIFT_S = [2, 3, 3, 4]
CM = [9459, 13377, 9459, 13377]
S15 = 28378
R = 8
REFSIGN = [1, -1, 1, 1, -1, 1, -1, -1]
REFAMP_OF = [4096, 8192]            # reference symbol amplitude: 1x or 2x the data amplitude (ref_boost, see the design)
N_TO_MSEL = {64: 0, 128: 1, 256: 2, 512: 3}


def tw(m_sel, n):
    m = MS[m_sel]
    a = 2 * math.pi * (n % m) / m
    return int(math.floor(32767 * math.cos(a) + 0.5)), int(math.floor(32767 * math.sin(a) + 0.5))


def rnd15(v):
    return (v + 16384) >> 15


def cmul_tw(y, w, inverse):
    c, s = w
    wi = s if inverse else -s
    return (rnd15(y[0] * c - y[1] * wi), rnd15(y[0] * wi + y[1] * c))


def dft_mixed(x, m_sel, inverse, in_rot=0, out_rot=0):
    """x: list of M (re, im). Returns (list of M (re, im), saturation count)."""
    m = MS[m_sel]
    ell = m // 3
    la = ell.bit_length() - 1
    xs = [None] * m
    for i, s in enumerate(x):
        xs[(i + in_rot) % m] = s
    mask = (1 << SHIFT_S[m_sel]) - 1
    ovf = 0
    y = []
    for r in range(3):
        yr, o = fft_fixed([xs[3 * k + r] for k in range(ell)], la, inverse, mask)
        ovf += o
        y.append(yr)
    xo = [None] * m
    for k in range(ell):
        a = y[0][k]
        b = cmul_tw(y[1][k], tw(m_sel, k), inverse)
        c = cmul_tw(y[2][k], tw(m_sel, 2 * k), inverse)
        t = (b[0] + c[0], b[1] + c[1])
        d = (b[0] - c[0], b[1] - c[1])
        u = (a[0] - ((t[0] + 1) >> 1), a[1] - ((t[1] + 1) >> 1))
        v = (rnd15(d[0] * S15), rnd15(d[1] * S15))
        x0 = (a[0] + t[0], a[1] + t[1])
        if not inverse:
            x1 = (u[0] + v[1], u[1] - v[0])          # U - jV
            x2 = (u[0] - v[1], u[1] + v[0])          # U + jV
        else:
            x1 = (u[0] - v[1], u[1] + v[0])
            x2 = (u[0] + v[1], u[1] - v[0])
        xo[k], xo[k + ell], xo[k + 2 * ell] = x0, x1, x2
    out = []
    for n in range(m):
        s = xo[(n + out_rot) % m]
        cm = CM[m_sel]
        comp = []
        for val in s:
            q = (val * cm + 8192) >> 14
            if q > 32767 or q < -32768:
                ovf += 1
            comp.append(sat16(q))
        out.append((comp[0], comp[1]))
    return out, ovf


def ref_pos(m):
    return [j * (m // R) + m // (2 * R) for j in range(R)]


def build_d(data, m, boost=0):
    """data: M - R samples; returns the M-sample vector with the reference symbols in place"""
    pos = set(ref_pos(m))
    refs = {p: (REFAMP_OF[boost] * REFSIGN[j], 0) for j, p in enumerate(ref_pos(m))}
    it = iter(data)
    d = []
    for n in range(m):
        d.append(refs[n] if n in pos else next(it))
    return d


def dfts_tx(data, n, boost=0):
    """data: M - R samples (re, im); returns (N bins in bin order, ovf)"""
    ms = N_TO_MSEL[n]
    m = MS[ms]
    assert len(data) == m - R
    x, ovf = dft_mixed(build_d(data, m, boost), ms, False, 0, m // 2)
    bins = [(0, 0)] * n
    for o in range(m // 2):
        bins[1 + o] = x[o]
    for o in range(m // 2):
        bins[n - m // 2 + o] = x[m // 2 + o]
    return bins, ovf


def used_bins(n):
    m = MS[N_TO_MSEL[n]]
    return list(range(1, m // 2 + 1)) + list(range(n - m // 2, n))


def unity_lut():
    return [256] * 256


def dfts_rx(bins, csi, n, lut, csi_out, boost=0):
    """bins: N (re, im) zero-forcing equalised tones in bin order, csi: N values. Returns (list of M - R (re, im), csi, ovf)"""
    ms = N_TO_MSEL[n]
    m = MS[ms]
    xin = []
    for b in used_bins(n):
        g = lut[csi[b]]
        xin.append((sat16((bins[b][0] * g + 128) >> 8), sat16((bins[b][1] * g + 128) >> 8)))
    d, ovf = dft_mixed(xin, ms, True, m // 2, 0)
    csi_r = cs_q = 0
    for j, p in enumerate(ref_pos(m)):
        csi_r += REFSIGN[j] * d[p][0]
        cs_q += REFSIGN[j] * d[p][1]
    rn = 8192 >> boost                # c = csum / (R x REFAMP / 4096) in Q12
    ci = sat16((csi_r * rn + 32768) >> 16)
    cq = sat16((cs_q * rn + 32768) >> 16)
    x = ci * ci + cq * cq
    r = recip(x)
    gi = sat16((ci * r + 32768) >> 16)
    gq = sat16((-cq * r + 32768) >> 16)
    pos = set(ref_pos(m))
    out = []
    for nn in range(m):
        if nn in pos:
            continue
        wi, wq = d[nn]
        out.append((sat16((wi * gi - wq * gq + 2048) >> 12), sat16((wi * gq + wq * gi + 2048) >> 12)))
    return out, csi_out, ovf


# ---------------- floating-point references ----------------
def dft_ref(x, inverse):
    import numpy as np
    z = np.array([complex(a, b) for a, b in x])
    m = len(z)
    y = (np.fft.ifft(z) if inverse else np.fft.fft(z)) * (m if inverse else 1) / math.sqrt(m)
    return y


def rms_err(got, ref):
    import numpy as np
    g = np.array([complex(a, b) for a, b in got])
    return float(np.sqrt(np.mean(np.abs(g - ref) ** 2) / np.mean(np.abs(ref) ** 2)))
