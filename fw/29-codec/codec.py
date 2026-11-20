"""Reference model of the custom slice-based codec SL1 (design/29-custom-codec.md section 1).
Luma only, 8-bit; every slice is coded from its own bit string, with no dependency on any other slice of the same frame."""
import math

import numpy as np

# ---------------------------------------------------------------- transform and quantisation tables
def _hadamard_seq():
    h = np.array([[1]], dtype=np.int64)
    for _ in range(3):
        h = np.block([[h, h], [h, -h]])
    changes = [(np.diff(r) != 0).sum() for r in h]
    return h[np.argsort(changes)]


H8 = _hadamard_seq()
IDX = np.add.outer(np.arange(8), np.arange(8))
STEP = np.array([np.round(8 * 0.625 * 2 ** (qp / 6) * (1 + 0.05 * IDX)).astype(np.int64) for qp in range(52)])
RECIP = np.round(65536 / STEP).astype(np.int64)
ROUND_INTRA, ROUND_INTER = 29491, 21845


def scan_order():
    order = sorted(((i, j) for i in range(8) for j in range(8)), key=lambda p: (p[0] + p[1], p[0] if (p[0] + p[1]) % 2 else -p[0]))
    return order


SCAN = scan_order()
SCAN_I = np.array([p[0] for p in SCAN])
SCAN_J = np.array([p[1] for p in SCAN])


def fwd(x):
    return H8 @ x @ H8


def inv(c):
    return (H8 @ c @ H8 + 32) >> 6


def quant(c, qp, intra):
    f = ROUND_INTRA if intra else ROUND_INTER
    return np.sign(c) * ((np.abs(c) * RECIP[qp] + f) >> 16)


def dequant(l, qp):
    return l * STEP[qp]


# ---------------------------------------------------------------- bit I/O
class BitWriter:
    def __init__(self):
        self.bits = []

    def u(self, v, n):
        for k in range(n - 1, -1, -1):
            self.bits.append((v >> k) & 1)

    def ue(self, v):
        v += 1
        n = v.bit_length()
        self.u(0, n - 1)
        self.u(v, n)

    def se(self, v):
        self.ue(2 * v - 1 if v > 0 else -2 * v)

    def tobytes(self):
        b = self.bits + [1]
        while len(b) % 8:
            b.append(0)
        return bytes(int("".join(map(str, b[k:k + 8])), 2) for k in range(0, len(b), 8))


class BitReader:
    def __init__(self, data):
        self.bits = [int(c) for c in "".join(f"{x:08b}" for x in data)]
        # strip the stop bit and the padding
        while self.bits and self.bits[-1] == 0:
            self.bits.pop()
        if self.bits:
            self.bits.pop()
        self.p = 0

    def u(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | (self.bits[self.p] if self.p < len(self.bits) else 0)
            self.p += 1
        return v

    def ue(self):
        z = 0
        while self.p < len(self.bits) and self.bits[self.p] == 0:
            z += 1
            self.p += 1
        v = self.u(z + 1)
        return v - 1

    def se(self):
        k = self.ue()
        return (k + 1) // 2 if k & 1 else -(k // 2)


# ---------------------------------------------------------------- foveation
def fov_map(W, H, cx, cy, radius, falloff, strength):
    """per-macroblock QP offset: 0 inside the region, up to `strength` far outside, smooth in between (design section 1)"""
    mbw, mbh = W // 16, H // 16
    out = np.zeros((mbh, mbw), dtype=np.int64)
    for y in range(mbh):
        for x in range(mbw):
            d = math.hypot(x * 16 + 8 - cx, y * 16 + 8 - cy)
            t = min(1.0, max(0.0, (d - radius) / max(falloff, 1e-9)))
            out[y, x] = int(round(strength * t * t * (3 - 2 * t)))
    return out


# ---------------------------------------------------------------- slice coding
def motion_search(cur, ref, rng_=8):
    """integer-pel full search per 8 x 8 block of one slice; the reference area is inside the same slice rows of the previous frame"""
    sh, W = cur.shape
    best = {}
    padded = np.full((sh + 2 * rng_, W + 2 * rng_), 10 ** 6, dtype=np.int64)       # outside: forbidden
    padded[rng_:rng_ + sh, rng_:rng_ + W] = ref
    for by in range(0, sh, 8):
        for bx in range(0, W, 8):
            blk = cur[by:by + 8, bx:bx + 8]
            win = padded[by:by + 8 + 2 * rng_, bx:bx + 8 + 2 * rng_]
            sw = np.lib.stride_tricks.sliding_window_view(win, (8, 8))        # (17, 17, 8, 8)
            sad = np.abs(sw - blk).sum(axis=(2, 3))
            k = np.argmin(sad + 0.0 * sad)
            # prefer the zero vector on ties and small vectors
            cy, cx = divmod(int(k), sad.shape[1])
            if sad[rng_, rng_] <= sad[cy, cx]:
                cy, cx = rng_, rng_
            best[(by, bx)] = (cx - rng_, cy - rng_, int(sad[cy, cx]), int(sad[rng_, rng_]))
    return best


def intra_dc(rec, by, bx):
    parts = []
    if bx > 0:
        parts.append(rec[by:by + 8, bx - 1])
    if by > 0:
        parts.append(rec[by - 1, bx:bx + 8])
    if not parts:
        return 128
    s = int(sum(p.sum() for p in parts))
    n = 8 * len(parts)
    return (s + n // 2) // n


def encode_slice(cur, ref, qp, intra_slice, dqp_mb=None, cut=64, mv_cache=None):
    """returns (bytes, reconstruction); cur, ref: int arrays of one slice (rows x W); ref is None for intra slices"""
    sh, W = cur.shape
    rec = np.zeros_like(cur)
    bw = BitWriter()
    has_dqp = dqp_mb is not None and bool(np.any(dqp_mb))
    bw.u(1 if intra_slice else 0, 1)
    bw.u(qp, 6)
    bw.u(1 if has_dqp else 0, 1)
    pmv = (0, 0)
    mvs = mv_cache if (mv_cache is not None) else (motion_search(cur, ref) if not intra_slice else None)
    for my in range(0, sh, 16):
        for mx in range(0, W, 16):
            dq = 0
            if has_dqp:
                dq = int(dqp_mb[my // 16, mx // 16])
                bw.se(dq)
            qpm = min(51, max(0, qp + dq))
            q = 0.625 * 2 ** (qpm / 6)
            for by in (my, my + 8):
                for bx in (mx, mx + 8):
                    blk = cur[by:by + 8, bx:bx + 8]
                    mode = 2
                    if not intra_slice:
                        mvx, mvy, sad_mv, sad0 = mvs[(by, bx)]
                        dc = intra_dc(rec, by, bx)
                        sad_i = int(np.abs(blk - dc).sum())
                        if sad0 <= 12 * q:
                            mode = 0
                        else:
                            c_inter = sad_mv + 2 * q * (abs(mvx - pmv[0]) + abs(mvy - pmv[1]))
                            c_intra = sad_i + 4 * q
                            mode = 1 if c_inter <= c_intra else 2
                    if mode == 0:
                        pred = ref[by:by + 8, bx:bx + 8]
                        levels = None
                    else:
                        if mode == 1:
                            pred = ref[by + mvy:by + mvy + 8, bx + mvx:bx + mvx + 8]
                        else:
                            pred = np.full((8, 8), intra_dc(rec, by, bx), dtype=np.int64)
                        r = blk - pred
                        levels = quant(fwd(r), qpm, mode == 2)
                        if cut < 64:
                            mask = np.zeros((8, 8), dtype=np.int64)
                            mask[SCAN_I[:cut], SCAN_J[:cut]] = 1
                            levels = levels * mask
                        if mode == 1 and mvx == 0 and mvy == 0 and not levels.any():
                            mode = 0
                            levels = None
                            pred = ref[by:by + 8, bx:bx + 8]
                    if not intra_slice:
                        bw.ue(mode)
                    if mode == 1:
                        bw.se(mvx - pmv[0])
                        bw.se(mvy - pmv[1])
                        pmv = (mvx, mvy)
                    if mode == 0:
                        rec[by:by + 8, bx:bx + 8] = pred
                        continue
                    seq = levels[SCAN_I, SCAN_J]
                    nz = np.nonzero(seq)[0]
                    bw.ue(len(nz))
                    last = -1
                    for k in nz:
                        bw.ue(int(k - last - 1))
                        bw.se(int(seq[k]))
                        last = int(k)
                    resid = inv(dequant(levels, qpm)) if len(nz) else np.zeros((8, 8), dtype=np.int64)
                    rec[by:by + 8, bx:bx + 8] = np.clip(pred + resid, 0, 255)
    return bw.tobytes(), rec


def decode_slice(data, ref, sh, W):
    """returns the reconstruction of one slice; ref: the same slice rows of the previous reconstructed frame (None for the first frame)"""
    br = BitReader(data)
    intra_slice = br.u(1)
    qp = br.u(6)
    has_dqp = br.u(1)
    rec = np.zeros((sh, W), dtype=np.int64)
    pmv = (0, 0)
    for my in range(0, sh, 16):
        for mx in range(0, W, 16):
            dq = br.se() if has_dqp else 0
            qpm = min(51, max(0, qp + dq))
            for by in (my, my + 8):
                for bx in (mx, mx + 8):
                    mode = 2 if intra_slice else br.ue()
                    if mode == 0:
                        rec[by:by + 8, bx:bx + 8] = ref[by:by + 8, bx:bx + 8]
                        continue
                    if mode == 1:
                        mvx = pmv[0] + br.se()
                        mvy = pmv[1] + br.se()
                        pmv = (mvx, mvy)
                        pred = ref[by + mvy:by + mvy + 8, bx + mvx:bx + mvx + 8]
                    else:
                        pred = np.full((8, 8), intra_dc(rec, by, bx), dtype=np.int64)
                    nnz = br.ue()
                    levels = np.zeros((8, 8), dtype=np.int64)
                    k = -1
                    for _ in range(nnz):
                        k += br.ue() + 1
                        levels[SCAN_I[k], SCAN_J[k]] = br.se()
                    resid = inv(dequant(levels, qpm)) if nnz else np.zeros((8, 8), dtype=np.int64)
                    rec[by:by + 8, bx:bx + 8] = np.clip(pred + resid, 0, 255)
    return rec


# ---------------------------------------------------------------- frame level
class Encoder:
    def __init__(self, W, H, S, wave_period=0):
        assert H % S == 0 and (H // S) % 16 == 0 and W % 16 == 0
        self.W, self.H, self.S, self.sh = W, H, S, H // S
        self.ref = None
        self.frame_no = 0
        self.wave_period = wave_period

    def encode_frame(self, frame, qp=None, budgets=None, intra_mask=0, fov=None):
        """returns (list of slice byte strings, list of qp used, list of intra flags); budgets: bytes per slice (rate control) or None"""
        frame = frame.astype(np.int64)
        out, qps, intras = [], [], []
        rec = np.zeros_like(frame)
        for s in range(self.S):
            cur = frame[s * self.sh:(s + 1) * self.sh]
            ref = None if self.ref is None else self.ref[s * self.sh:(s + 1) * self.sh]
            wave = self.wave_period and (self.frame_no % self.wave_period) == s
            is_i = ref is None or bool((intra_mask >> s) & 1) or bool(wave)
            dqp = None if fov is None else fov[s * self.sh // 16:(s + 1) * self.sh // 16]
            mvc = None if is_i else motion_search(cur, ref)
            if budgets is None:
                data, r = encode_slice(cur, ref, qp, is_i, dqp, 64, mvc)
                q = qp
            else:
                data, r, q = self._fit(cur, ref, is_i, dqp, mvc, budgets[s])
            out.append(data)
            qps.append(q)
            intras.append(is_i)
            rec[s * self.sh:(s + 1) * self.sh] = r
        self.ref = rec
        self.frame_no += 1
        return out, qps, intras

    def _fit(self, cur, ref, is_i, dqp, mvc, budget):
        lo, hi = 0, 51
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            data, r = encode_slice(cur, ref, mid, is_i, dqp, 64, mvc)
            if len(data) <= budget:
                best = (data, r, mid)
                hi = mid - 1
            else:
                lo = mid + 1
        if best is not None:
            return best
        for cut in (32, 16, 8, 4, 2, 1, 0):
            data, r = encode_slice(cur, ref, 51, is_i, dqp, cut, mvc)
            if len(data) <= budget:
                return data, r, 51
        return data, r, 51                                     # the budget is below the smallest slice


class Decoder:
    def __init__(self, W, H, S):
        self.W, self.H, self.S, self.sh = W, H, S, H // S
        self.ref = None

    def decode_frame(self, slices):
        """slices: dict index -> bytes (missing indices are concealed from the previous frame)"""
        rec = np.zeros((self.H, self.W), dtype=np.int64)
        for s in range(self.S):
            ref = None if self.ref is None else self.ref[s * self.sh:(s + 1) * self.sh]
            if s in slices and slices[s] is not None:
                rec[s * self.sh:(s + 1) * self.sh] = decode_slice(slices[s], ref, self.sh, self.W)
            elif ref is not None:
                rec[s * self.sh:(s + 1) * self.sh] = ref
            else:
                rec[s * self.sh:(s + 1) * self.sh] = 128
        self.ref = rec
        return rec


def psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return 99.0 if mse == 0 else 10 * math.log10(255 ** 2 / mse)
