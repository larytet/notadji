"""Bit-exact model of the layered normalised min-sum decoder (design/20-ldpc-decoder.md section 1)."""
import sys
from pathlib import Path

T = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(T / "13-ldpc-encoder"))
from ldpc_py import CODES   # noqa: E402


def sat8(v):
    return 127 if v > 127 else (-127 if v < -127 else v)


def sat9(v):
    """posterior and extrinsic range: 9 bits (the posterior needs more range than the 8-bit channel LLR)"""
    return 255 if v > 255 else (-255 if v < -255 else v)


def scale(m):
    return (3 * m) >> 2


def decode(ci, llr, max_iter):
    """llr: list of N ints. Returns (info_bits list of K ints, ok, iterations)."""
    c = CODES[ci]
    z, mb, kb = c["Z"], c["mb"], c["kb"]
    base = c["base"]
    post = [[sat8(llr[j * z + b]) for b in range(z)] for j in range(24)]
    ents = [[(j, base[i][j]) for j in range(24) if base[i][j] is not None] for i in range(mb)]
    m1 = [[0] * z for _ in range(mb)]
    m2 = [[0] * z for _ in range(mb)]
    ix = [[0] * z for _ in range(mb)]
    sg = [[0] * z for _ in range(mb)]
    max_iter = max(1, max_iter)
    ok = False
    it = 0
    for it in range(1, max_iter + 1):
        all_ok = True
        changed = False
        for i in range(mb):
            lm1 = [127] * z
            lm2 = [127] * z
            lix = [0] * z
            lsp = [0] * z
            lns = [0] * z
            par = [0] * z
            for e, (col, sh) in enumerate(ents[i]):
                for r in range(z):
                    x = post[col][(r + sh) % z]
                    om = scale(m2[i][r] if e == ix[i][r] else m1[i][r])
                    cold = -om if (sg[i][r] >> e) & 1 else om
                    v = sat9(x - cold)
                    mag = min(abs(v), 127)
                    sgn = 1 if v < 0 else 0
                    if mag < lm1[r]:
                        lm2[r] = lm1[r]
                        lm1[r] = mag
                        lix[r] = e
                    elif mag < lm2[r]:
                        lm2[r] = mag
                    lsp[r] ^= sgn
                    lns[r] |= sgn << e
                    par[r] ^= 1 if x < 0 else 0
            if any(par):
                all_ok = False
            for e, (col, sh) in enumerate(ents[i]):
                for r in range(z):
                    idx = (r + sh) % z
                    x = post[col][idx]
                    om = scale(m2[i][r] if e == ix[i][r] else m1[i][r])
                    cold = -om if (sg[i][r] >> e) & 1 else om
                    v = sat9(x - cold)
                    nm = scale(lm2[r] if e == lix[r] else lm1[r])
                    ns = lsp[r] ^ ((lns[r] >> e) & 1)
                    xn = sat9(v + (-nm if ns else nm))
                    if (xn < 0) != (x < 0):
                        changed = True
                    post[col][idx] = xn
            # stored message signs: sign product XOR the sign of each entry's own input (the sign of the outgoing message)
            m1[i], m2[i], ix[i], sg[i] = lm1, lm2, lix, [lns[r] ^ (0xFFFFFF if lsp[r] else 0) for r in range(z)]
        if all_ok and not changed:
            ok = True
            break
    bits = [1 if post[j][b] < 0 else 0 for j in range(kb) for b in range(z)]
    return bits, ok, it


def words(bits):
    n = (len(bits) + 31) // 32
    out = []
    for w in range(n):
        v = 0
        for t in range(32):
            if 32 * w + t < len(bits):
                v |= bits[32 * w + t] << t
        out.append(v)
    return out


def noisy_llr(ci, msg_bits, ebn0_db, rng, mode="fixed"):
    """quantised BPSK/AWGN LLRs of the codeword of msg_bits (encoder model of module 16).
    mode "fixed": 24 per unit amplitude (what the demapper delivers: independent of the noise variance);
    mode "sigma": 2 y / sigma^2 x 4 (grows with the SNR and saturates at high SNR: a stress case)"""
    import math
    sys.path.insert(0, str(T / "16-tx-chain"))
    from tx_model import ldpc_encode
    c = CODES[ci]
    cw = ldpc_encode(ci, msg_bits)
    rate = c["K"] / c["N"]
    sigma = math.sqrt(1 / (2 * rate * 10 ** (ebn0_db / 10)))
    out = []
    for b in cw:
        y = (1 - 2 * b) + rng.gauss(0, sigma)
        l = 24.0 * y if mode == "fixed" else 4 * 2 * y / (sigma * sigma)
        out.append(max(-127, min(127, int(round(l)))))
    return cw, out


def float_decode(ci, llr, max_iter, alpha=0.75):
    """floating-point layered normalised min-sum of the same structure (an independent reference)"""
    import numpy as np
    c = CODES[ci]
    z, mb = c["Z"], c["mb"]
    base = c["base"]
    post = np.array(llr, float).reshape(24, z)
    ents = [[(j, base[i][j]) for j in range(24) if base[i][j] is not None] for i in range(mb)]
    c2v = {}
    for it in range(1, max_iter + 1):
        for i in range(mb):
            vs = []
            for e, (col, sh) in enumerate(ents[i]):
                vs.append(np.roll(post[col], -sh) - c2v.get((i, e), np.zeros(z)))
            V = np.array(vs)
            sgn = np.sign(V)
            sgn[sgn == 0] = 1
            mag = np.abs(V)
            tot = np.prod(sgn, axis=0)
            order = np.argsort(mag, axis=0)
            m1 = np.take_along_axis(mag, order[:1], 0)[0]
            m2 = np.take_along_axis(mag, order[1:2], 0)[0]
            for e, (col, sh) in enumerate(ents[i]):
                new = tot * sgn[e] * np.where(order[0] == e, m2, m1) * alpha
                c2v[(i, e)] = new
                post[col] = np.roll(V[e] + new, sh)
        hard = (post < 0).astype(int).reshape(24, z)
        ok = True
        for i in range(mb):
            par = np.zeros(z, int)
            for (col, sh) in ents[i]:
                par ^= np.roll(hard[col], -sh)
            if par.any():
                ok = False
                break
        if ok:
            return [int(v) for v in hard.ravel()[:c["K"]]], True, it
    return [int(v) for v in (post < 0).astype(int).ravel()[:c["K"]]], False, max_iter
