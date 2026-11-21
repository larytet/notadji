"""PAPR and link-level simulation of DFT-s-OFDM against plain OFDM (R31-03, R31-04, R31-05)."""
import math
import random
import sys
from pathlib import Path

import numpy as np

T = next(q for q in Path(__file__).resolve().parents if (q / "12-fft").is_dir())     # the tests directory (also from a mutation copy)
sys.path.insert(0, str(T / "14-demapper"))
sys.path.insert(0, str(T / "16-tx-chain"))
sys.path.insert(0, str(T / "20-ldpc-decoder"))

from dfts_cal import csi_eff, csi_eff_zf, make_gain_lut                       # noqa: E402
from dfts_model import MS, N_TO_MSEL, R, REFAMP_OF, REFSIGN, dfts_rx, dfts_tx, ref_pos, unity_lut, used_bins  # noqa: E402
from dm_model import llrs, point                                              # noqa: E402

PLAN = {64: (1, 26, [7, 21]), 128: (2, 58, [11, 25, 53]), 256: (2, 122, [11, 39, 75, 103]),
        512: (3, 244, [12, 42, 72, 102, 132, 162, 192, 222])}
NB = {0: 1, 1: 2, 2: 4}                       # module 6 modulation index -> bits per symbol (BPSK, QPSK, 16QAM)
MODNAME = {0: "BPSK", 1: "QPSK", 2: "16QAM"}


# ---------------------------------------------------------------- PAPR
def float_points(rng, mod, shape):
    if mod == 0:
        return rng.choice([-1.0, 1.0], shape).astype(complex)
    if mod == 1:
        return (rng.choice([-1.0, 1.0], shape) + 1j * rng.choice([-1.0, 1.0], shape)) / math.sqrt(2)
    return (rng.choice([-3.0, -1.0, 1.0, 3.0], shape) + 1j * rng.choice([-3.0, -1.0, 1.0, 3.0], shape)) / math.sqrt(10)


def plan_tones(n):
    kmin, kmax, pil = PLAN[n]
    data, pilots = [], []
    for k in list(range(-kmax, -kmin + 1)) + list(range(kmin, kmax + 1)):
        (pilots if abs(k) in pil else data).append(k)
    return data, pilots


def papr_samples(n, mod, ds, nsym, rng, os=4, boost=0):
    """per-symbol PAPR (dB) of the 4x oversampled waveform of nsym data symbols"""
    X = np.zeros((nsym, n * os), complex)
    if ds:
        m = MS[N_TO_MSEL[n]]
        d = float_points(rng, mod, (nsym, m))
        pos = ref_pos(m)
        for j, p in enumerate(pos):
            d[:, p] = REFSIGN[j] * REFAMP_OF[boost] / 4096.0
        S = np.fft.fft(d, axis=1) / math.sqrt(m)
        ks = [k for k in range(-(m // 2), m // 2 + 1) if k != 0]
        for p, k in enumerate(ks):
            X[:, k % (n * os)] = S[:, p]
    else:
        data, pilots = plan_tones(n)
        for k in data:
            X[:, k % (n * os)] = float_points(rng, mod, (nsym,))
        for i, k in enumerate(pilots):
            X[:, k % (n * os)] = 1.0 if (i % 4) != 3 else -1.0
    x = np.fft.ifft(X, axis=1)
    p = np.abs(x) ** 2
    return 10 * np.log10(p.max(axis=1) / p.mean(axis=1))


def papr_at(samples, ccdf=1e-3):
    return float(np.percentile(samples, 100 * (1 - ccdf)))


# ---------------------------------------------------------------- link
def mod_points(mod, bits):
    nb = NB[mod]
    return [point(mod, sum(bits[i * nb + j] << j for j in range(nb))) for i in range(len(bits) // nb)]


def tone_snr(ebn0_db, mod, rate=1.0):
    return 10 ** (ebn0_db / 10) * NB[mod] * rate


def awgn(rng, sigma):
    return rng.gauss(0, sigma / math.sqrt(2)), rng.gauss(0, sigma / math.sqrt(2))


def channel_response(n, kind, rng):
    """frequency response H_k (bin order, complex, mean |H|^2 over the used tones normalised to 1)"""
    taps = {"flat": [(0, 1.0)],
            "2tap": [(0, 1.0), (4, 0.5 * np.exp(1j * rng.uniform(0, 2 * np.pi)))]}
    if kind == "exp6":
        taps_l = [(i * 2, (rng.gauss(0, 1) + 1j * rng.gauss(0, 1)) * math.sqrt(math.exp(-i / 2.0))) for i in range(6)]
    else:
        taps_l = taps[kind]
    k = np.array([b if b < n // 2 else b - n for b in range(n)])
    H = np.zeros(n, complex)
    for d, a in taps_l:
        H += a * np.exp(-2j * np.pi * k * d / n)
    ub = used_bins(n)
    H = H / math.sqrt(np.mean(np.abs(H[ub]) ** 2))
    return H


def eq_and_csi(Y, H, bins_used):
    """module 17 style: zero forcing equalised bins and csi = min(255, 128 |H|^2)"""
    Z = [(0, 0)] * len(Y)
    csi = [0] * len(Y)
    for b in bins_used:
        z = Y[b] / H[b]
        Z[b] = (int(round(z.real)), int(round(z.imag)))
        csi[b] = min(255, int(128 * abs(H[b]) ** 2))
    return Z, csi


def ds_symbol(bits, n, mod, H, sigma, rng, mmse=True, sh=12, nv=None, boost=0):
    """one DFT-s symbol: bits (list of (M-R) nb) through the fixed-point stages and the channel; returns the LLR list"""
    pts = mod_points(mod, bits)
    bins, _ = dfts_tx(pts, n, boost)
    Y = np.zeros(n, complex)
    for b in used_bins(n):
        nr, ni = awgn(rng, sigma)
        Y[b] = H[b] * complex(*bins[b]) + complex(nr, ni)
    Z, csi = eq_and_csi(Y, H, used_bins(n))
    ub = used_bins(n)
    csi_used = [csi[b] for b in ub]
    if mmse:
        lut = make_gain_lut(nv)
        cout = csi_eff(csi_used, nv)
    else:
        lut = unity_lut()
        cout = csi_eff_zf(csi_used)
    out, _, _ = dfts_rx(Z, csi, n, lut, cout, boost)
    llr = []
    for (i, q) in out:
        llr += llrs(mod, i, q, cout, sh)
    return llr


def ofdm_symbol(bits, n, mod, H, sigma, rng, sh=12):
    """plain OFDM data symbol (module 7 plan): returns the LLR list of the data tones"""
    data, pilots = plan_tones(n)
    pts = mod_points(mod, bits)
    llr = []
    for k, (pi, pq) in zip(data, pts):
        b = k if k >= 0 else k + n
        nr, ni = awgn(rng, sigma)
        y = H[b] * complex(pi, pq) + complex(nr, ni)
        z = y / H[b]
        csi = min(255, int(128 * abs(H[b]) ** 2))
        llr += llrs(mod, int(round(z.real)), int(round(z.imag)), csi, sh)
    return llr


# ---------------------------------------------------------------- BER and FER drivers (run in worker processes)
def theory_ber(mod, ebn0_db):
    e = 10 ** (ebn0_db / 10)
    if mod in (0, 1):
        return 0.5 * math.erfc(math.sqrt(e))
    return 0.375 * math.erfc(math.sqrt(0.4 * e))


def ber_chunk(args):
    """uncoded BER in AWGN with ideal channel knowledge: scheme 'ds' (fixed-point stages) or 'ofdm'"""
    scheme, n, mod, ebn0, nsym, seed = args
    rng = random.Random(seed)
    snr = tone_snr(ebn0, mod)
    sigma = 4096.0 / math.sqrt(snr)
    nv = 128.0 / snr
    H = channel_response(n, "flat", rng)
    cap = (MS[N_TO_MSEL[n]] - R) if scheme in ("ds", "dsb") else len(plan_tones(n)[0])
    err = bits_n = 0
    for _ in range(nsym):
        bits = [rng.getrandbits(1) for _ in range(cap * NB[mod])]
        llr = ds_symbol(bits, n, mod, H, sigma, rng, True, 12, nv, 1 if scheme == "dsb" else 0) if scheme in ("ds", "dsb") else ofdm_symbol(bits, n, mod, H, sigma, rng)
        err += sum(1 for b, l in zip(bits, llr) if (l < 0) != bool(b))
        bits_n += len(bits)
    return err, bits_n


def fer_chunk(args):
    """coded frame error rate of code ci with QPSK, block fading per codeword; scheme 'ofdm', 'ds_mmse', 'ds_zf'"""
    scheme, ci, kind, n, ebn0, ncw, seed = args
    from dec_model import CODES, decode
    from tx_model import ldpc_encode
    rng = random.Random(seed)
    c = CODES[ci]
    rate = c["K"] / c["N"]
    mod = 1
    snr = tone_snr(ebn0, mod, rate)
    sigma = 4096.0 / math.sqrt(snr)
    nv = 128.0 / snr
    cap = len(plan_tones(n)[0]) * NB[mod] if scheme == "ofdm" else (MS[N_TO_MSEL[n]] - R) * NB[mod]
    boost = 1 if scheme == "ds_mmse_b" else 0
    nsy = -(-c["N"] // cap)
    perm = list(range(nsy * cap))
    random.Random(12345).shuffle(perm)               # fixed pseudo-random interleaver over the codeword
    fails = 0
    for _ in range(ncw):
        msg = [rng.getrandbits(1) for _ in range(c["K"])]
        cw = ldpc_encode(ci, msg)
        bits = cw + [rng.getrandbits(1) for _ in range(nsy * cap - c["N"])]
        tx = [0] * len(bits)
        for i, p in enumerate(perm):
            tx[p] = bits[i]
        H = channel_response(n, kind, rng)
        llr_all = []
        for s in range(nsy):
            blk = tx[s * cap:(s + 1) * cap]
            if scheme == "ofdm":
                llr_all += ofdm_symbol(blk, n, mod, H, sigma, rng)
            else:
                llr_all += ds_symbol(blk, n, mod, H, sigma, rng, scheme != "ds_zf", 12, nv, boost)
        llr_p = [llr_all[perm[i]] for i in range(nsy * cap)]
        bits_d, ok, _ = decode(ci, llr_p[:c["N"]], 20)
        if not (ok and bits_d == msg):
            fails += 1
    return fails, ncw
