"""Independent model of the demapper (design/14-demapper.md): folded LLR, exact max-log, and the mapper constellation."""
import math

S = 4096
BITS = {0: 1, 1: 2, 2: 4, 3: 6, 4: 8, 5: 1, 6: 1, 7: 1}


def unit(m):
    M = 1 << m
    return S / math.sqrt(2 * (M * M - 1) / 3)


def rnd(x):
    return int(math.floor(x + 0.5))


THR = {2: (rnd(2 * unit(2)),), 3: (rnd(4 * unit(3)), rnd(2 * unit(3))), 4: (rnd(8 * unit(4)), rnd(4 * unit(4)), rnd(2 * unit(4)))}


def maxm(mod):
    return {1: 1, 2: 2, 3: 3, 4: 4}.get(mod)         # None: BPSK


def fold(m, a):
    f = [-a]
    if m >= 2:
        f.append(abs(a) - THR[m][0])
    if m >= 3:
        f.append(abs(f[1]) - THR[m][1])
    if m >= 4:
        f.append(abs(f[2]) - THR[4][2])
    return f


def scale8(f, csi, sh):
    p = f * csi
    r = (p + (1 << (sh - 1))) >> sh if sh else p
    return max(-127, min(127, r))


def llrs(mod, i, q, csi, sh):
    m = maxm(mod)
    if m is None:
        return [scale8(-i, csi, sh)]
    return [scale8(f, csi, sh) for f in fold(m, i)] + [scale8(f, csi, sh) for f in fold(m, q)]


# ---- constellation (mapper definition of module 6, written again here) ----
def mag(m, j):
    return rnd((2 * j + 1) * unit(m))


def axis_level(gbits):
    m = len(gbits)
    b, prev = 0, 0
    for g in gbits:
        prev ^= g
        b = (b << 1) | prev
    level = 2 * b - ((1 << m) - 1)
    j = (abs(level) - 1) // 2
    return mag(m, j) if level > 0 else -mag(m, j)


def point(mod, word):
    m = maxm(mod)
    if m is None:
        return (S if word & 1 else -S), 0
    nb = 2 * m
    bits = [(word >> k) & 1 for k in range(nb)]
    return axis_level(bits[:m]), axis_level(bits[m:])


def constellation(mod):
    nb = BITS[mod]
    return [(w, point(mod, w)) for w in range(1 << nb)]


def exact_llrs(mod, i, q, pts):
    """max-log LLR per bit (positive = bit 0) by brute force over the constellation"""
    nb = BITS[mod]
    out = []
    for k in range(nb):
        d0 = min((i - p[0]) ** 2 + (q - p[1]) ** 2 for w, p in pts if not (w >> k) & 1)
        d1 = min((i - p[0]) ** 2 + (q - p[1]) ** 2 for w, p in pts if (w >> k) & 1)
        out.append(d1 - d0)
    return out


def nearest(mod, i, q, pts):
    best = min(pts, key=lambda wp: (i - wp[1][0]) ** 2 + (q - wp[1][1]) ** 2)
    return best[0]
