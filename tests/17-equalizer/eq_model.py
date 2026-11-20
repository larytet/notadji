"""Bit-exact model of the equaliser (design/17-equalizer.md section 1) and channel helpers."""
import sys
from pathlib import Path

T = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(T / "16-tx-chain"))
sys.path.insert(0, str(T / "14-demapper"))
from tx_model import Preamble          # noqa: E402
from dm_model import point             # noqa: E402

TAB = [int((2 ** 23) / (256 + i) + 0.5) for i in range(256)]
RN = {6: 16384, 7: 10923, 8: 8192, 9: 4096}


def sat16(v):
    return 32767 if v > 32767 else (-32768 if v < -32768 else v)


def recip(x):
    if x == 0:
        return 0x7FFFFFFF
    p = x.bit_length() - 1
    m = (x >> (p - 8)) if p >= 8 else (x << (8 - p))
    t = TAB[m - 256]
    if p <= 25:
        return min(t << (25 - p), 0x7FFFFFFF)
    return t >> (p - 25)


class EqModel:
    def __init__(self, l):
        self.l = l
        self.n = 1 << l
        self.pre = Preamble()
        self.tm = [(0, 0)] * self.n         # (sign, used)
        self.hm = [(0, 0)] * self.n
        self.gm = [(0, 0)] * self.n
        self.cm = [0] * self.n

    def ltf1(self, ys):
        sym = self.pre.symbol(1, self.l)
        for b, (t, i, q) in enumerate(sym):
            self.tm[b] = (1 if i < 0 else 0, 1 if t != 0 else 0)
            self.hm[b] = ys[b]

    def ltf2(self, ys):
        for b in range(self.n):
            if self.tm[b][1]:
                self.hm[b] = (self.hm[b][0] + ys[b][0], self.hm[b][1] + ys[b][1])
        for b in range(self.n):
            if not self.tm[b][1]:
                self.gm[b] = (0, 0)
                self.cm[b] = 0
                continue
            sg = self.tm[b][0]
            si, sq = self.hm[b]
            vi, vq = (-si, -sq) if sg else (si, sq)
            hri, hrq = sat16((vi + 1) >> 1), sat16((vq + 1) >> 1)
            x = hri * hri + hrq * hrq
            r = recip(x)
            self.gm[b] = (sat16((hri * r + 32768) >> 16), sat16((-hrq * r + 32768) >> 16))
            self.cm[b] = min(255, x >> 17)

    def data(self, ys, first):
        sym = self.pre.symbol(2, self.l, frame_start=first)
        w = {}
        csi, csq = 0, 0
        lastd = None
        types = {}
        for b, (t, i, q) in enumerate(sym):
            types[b] = t
            if t == 0:
                continue
            yi, yq = ys[b]
            gi, gq = self.gm[b]
            wi = sat16((yi * gi - yq * gq + 2048) >> 12)
            wq = sat16((yi * gq + yq * gi + 2048) >> 12)
            w[b] = (wi, wq)
            if t == 2:
                if i < 0:
                    csi -= wi
                    csq -= wq
                else:
                    csi += wi
                    csq += wq
            if t == 1:
                lastd = b
        rn = RN[self.l]
        ci = sat16((csi * rn + 32768) >> 16)
        cq = sat16((csq * rn + 32768) >> 16)
        x = ci * ci + cq * cq
        r = recip(x)
        gi = sat16((ci * r + 32768) >> 16)
        gq = sat16((-cq * r + 32768) >> 16)
        out = []
        for b in range(self.n):
            if types.get(b) == 1:
                wi, wq = w[b]
                zi = sat16((wi * gi - wq * gq + 2048) >> 12)
                zq = sat16((wi * gq + wq * gi + 2048) >> 12)
                out.append(((zi, zq), self.cm[b]))
        return out


def used_bins(l):
    return [b for b, (t, _, _) in enumerate(Preamble().symbol(1, l)) if t != 0]
