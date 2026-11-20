"""Golden model of the transmit chain (design/16-tx-chain.md section 1), built from the models of the earlier modules."""
import sys
from pathlib import Path

T = Path(__file__).resolve().parent.parent
for d in ("13-ldpc-encoder", "12-fft", "14-demapper"):
    sys.path.insert(0, str(T / d))

from fft_model import fft_fixed        # noqa: E402
from dm_model import point, BITS         # noqa: E402
from ldpc_py import CODES, h_rows, check  # noqa: E402

PLAN = {6: (1, 26, [7, 21]), 7: (2, 58, [11, 25, 53]), 8: (2, 122, [11, 39, 75, 103]),
        9: (3, 244, [12, 42, 72, 102, 132, 162, 192, 222]), 10: (3, 500, [12, 72, 132, 192, 252, 312, 372, 432])}
ND = {6: 48, 7: 108, 8: 234, 9: 468}
NB = {0: 1, 1: 2, 2: 4, 3: 6, 4: 8, 5: 1, 6: 1, 7: 1}
SH = {0: 4, 1: 3, 2: 2, 3: 2}


def bytes_to_bits(data):
    return [(b >> i) & 1 for b in data for i in range(8)]


def rot(v, s, z):
    return [v[(r + s) % z] for r in range(z)]


def ldpc_encode(ci, msg):
    c = CODES[ci]
    z, mb, kb = c["Z"], c["mb"], c["kb"]
    base = c["base"]
    blocks = [msg[j * z:(j + 1) * z] for j in range(kb)]
    lam = []
    for i in range(mb):
        acc = [0] * z
        for j in range(kb):
            s = base[i][j]
            if s is not None:
                r = rot(blocks[j], s, z)
                acc = [a ^ b for a, b in zip(acc, r)]
        lam.append(acc)
    p0 = [0] * z
    for l in lam:
        p0 = [a ^ b for a, b in zip(p0, l)]
    par = [p0]
    cur = p0
    x = c["x"]
    nxt = [a ^ b for a, b in zip(lam[0], rot(p0, x, z))]
    par.append(nxt)
    cur = nxt
    for i in range(1, mb - 1):
        nxt = [a ^ b for a, b in zip(lam[i], cur)]
        if i == mb // 2:
            nxt = [a ^ b for a, b in zip(nxt, p0)]
        par.append(nxt)
        cur = nxt
    cw = list(msg)
    for p in par:
        cw += p
    return cw


def pos(k, n):
    R = (n + 15) // 16
    full = ((n - 1) % 16) + 1
    r, c = divmod(k, 16)
    base = c * R if c < full else full * R + (c - full) * (R - 1)
    return base + r


def interleave(block):
    n = len(block)
    out = [0] * n
    for k, x in enumerate(block):
        out[pos(k, n)] = x
    return out


def deinterleave(block):
    n = len(block)
    return [block[pos(k, n)] for k in range(n)]


class Preamble:
    """tone plan, training symbols and pilot template of module 7"""

    def __init__(self):
        self.pol_state = 0x7F

    def pn(self):
        s = 0x1FF
        while True:
            fb = ((s >> 8) ^ (s >> 4)) & 1
            s = ((s << 1) & 0x1FF) | fb
            yield fb

    def symbol(self, kind, l, frame_start=False):
        n = 1 << l
        kmin, kmax, pil = PLAN[l]
        pn = self.pn()
        pol = 0
        if kind == 2:
            st = 0x7F if frame_start else self.pol_state
            pol = bin(st & 0b1001000).count("1") & 1
            self.pol_state = ((st << 1) & 0x7F) | pol
        order = [-p for p in reversed(pil)] + list(pil)
        out = []
        for b in range(n):
            k = b if b < n // 2 else b - n
            ak = abs(k)
            used = kmin <= ak <= kmax and k != 0
            t, i, q = 0, 0, 0
            if kind == 2:
                if used and k in order:
                    j = order.index(k)
                    neg = pol ^ (1 if j % 4 == 3 else 0)
                    t, i = 2, (-4096 if neg else 4096)
                elif used:
                    t = 1
            elif kind == 0:
                if used and ak % 4 == 0:
                    t = 2
                    i = 5793 if next(pn) else -5793
                    q = 5793 if next(pn) else -5793
            else:
                if used:
                    t = 2
                    i = 4096 if next(pn) else -4096
            out.append((t, i, q))
        return out


def ofdm_symbol(bins, l, shift_mask, cp_sel):
    n = 1 << l
    y, _ = fft_fixed(bins, l, True, shift_mask)
    cp = n >> SH[cp_sel]
    return y[n - cp:] + y


def coded_blocks(data, l, mod, ci):
    """returns (list of interleaved bit blocks, number of blocks)"""
    c = CODES[ci]
    k = c["K"]
    bits = bytes_to_bits(data)
    ncw = max(1, -(-len(bits) // k))
    bits += [0] * (ncw * k - len(bits))
    coded = []
    for j in range(ncw):
        coded += ldpc_encode(ci, bits[j * k:(j + 1) * k])
    ncbps = ND[l] * NB[mod]
    nblk = -(-len(coded) // ncbps)
    coded += [0] * (nblk * ncbps - len(coded))
    return [coded[i * ncbps:(i + 1) * ncbps] for i in range(nblk)]


def tx_frame(data, l, cp_sel, mod, ci, shift_mask):
    """list of (I, Q) output samples of a frame"""
    pre = Preamble()
    syms = []
    for kind in (0, 1, 1):
        s = pre.symbol(kind, l)
        syms.append(ofdm_symbol([(i, q) if t else (0, 0) for t, i, q in s], l, shift_mask, cp_sel))
    nb = NB[mod]
    blocks = coded_blocks(data, l, mod, ci)
    for bi, blk in enumerate(blocks):
        il = interleave(blk)
        words = []
        for t in range(len(il) // nb):
            w = 0
            for b in range(nb):
                w |= il[t * nb + b] << b
            words.append(w)
        tpl = pre.symbol(2, l, frame_start=(bi == 0))
        it = iter(words)
        bins = []
        for t, i, q in tpl:
            if t == 1:
                bins.append(point(mod, next(it)))
            elif t == 2:
                bins.append((i, q))
            else:
                bins.append((0, 0))
        syms.append(ofdm_symbol(bins, l, shift_mask, cp_sel))
    out = []
    for s in syms:
        out += s
    return out, len(blocks)


def mask_for(l):
    return (1 << (l - 3)) - 1
