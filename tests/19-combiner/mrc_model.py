import sys
from pathlib import Path

T = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(T / "17-equalizer"))
from eq_model import TAB   # noqa: E402


def sat16(v):
    return 32767 if v > 32767 else (-32768 if v < -32768 else v)


def r34(s):
    """2^34 / S through the table of module 17"""
    p = s.bit_length() - 1
    m = (s >> (p - 8)) if p >= 8 else (s << (8 - p))
    return TAB[m - 256] << (19 - p)


def combine(zs, csis):
    s = sum(csis)
    if s == 0:
        return (0, 0), 0
    r = r34(s)
    ni = sum(z[0] * c for z, c in zip(zs, csis))
    nq = sum(z[1] * c for z, c in zip(zs, csis))
    return (sat16((ni * r + (1 << 33)) >> 34), sat16((nq * r + (1 << 33)) >> 34)), min(255, s)
