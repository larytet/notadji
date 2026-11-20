"""Bit-exact integer model of fft_core (design/12-fft.md section 2) and the independent twiddle table."""
import math

COS = [int(math.floor(32767 * math.cos(2 * math.pi * k / 1024) + 0.5)) for k in range(512)]
SIN = [int(math.floor(32767 * math.sin(2 * math.pi * k / 1024) + 0.5)) for k in range(512)]


def sat16(v):
    return 32767 if v > 32767 else (-32768 if v < -32768 else v)


def bitrev(k, l):
    r = 0
    for i in range(l):
        r |= ((k >> i) & 1) << (l - 1 - i)
    return r


def fft_fixed(x, l, inverse, shift_mask):
    """x: list of (re, im) ints (N = 2**l). Returns (list of (re, im), saturation count)."""
    n = 1 << l
    a = [None] * n
    for k, s in enumerate(x):
        a[bitrev(k, l)] = s
    ovf = 0
    for s in range(1, l + 1):
        h = 1 << (s - 1)
        for c in range(n // 2):
            j = c & (h - 1)
            g = c >> (s - 1)
            ia = (g << s) | j
            ib = ia | h
            t = j << (10 - s)
            wr = COS[t]
            wi = SIN[t] if inverse else -SIN[t]
            br, bi = a[ib]
            pr = sat16(((br * wr - bi * wi) + 16384) >> 15)
            pi = sat16(((br * wi + bi * wr) + 16384) >> 15)
            ar, ai = a[ia]
            sums = (ar + pr, ai + pi, ar - pr, ai - pi)
            if (shift_mask >> (s - 1)) & 1:
                o = tuple((v + 1) >> 1 for v in sums)
            else:
                o = []
                for v in sums:
                    if v > 32767 or v < -32768:
                        ovf += 1
                    o.append(sat16(v))
                o = tuple(o)
            a[ia] = (o[0], o[1])
            a[ib] = (o[2], o[3])
    return a, ovf
