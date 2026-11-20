"""Vectorised equivalents of the RTL models, an OFDM source, a PA model and the figures of merit (EVM, ACLR, PAPR)."""
import ctypes as C
import subprocess

import numpy as np

import dpdmodel as M

HERE = M.ROOT / "tests" / "26-papr-dpd"
FW = M.ROOT / "fw" / "26-dpd"
OS = 4
NFFT = 256


def sat(v):
    return np.clip(v, -32768, 32767)


def clip_np(i, q, table):
    m2 = i * i + q * q
    g = np.array(table, dtype=np.int64)[np.minimum(255, m2 >> 22)]
    return sat((i * g + 16384) >> 15), sat((q * g + 16384) >> 15)


def fir_np(i, q):
    c = np.array(M.COEF, dtype=np.int64)
    n = len(i)
    return sat((np.convolve(i, c)[:n] + 16384) >> 15), sat((np.convolve(q, c)[:n] + 16384) >> 15)


def chain_np(i, q, tab1, tab2):
    i, q = clip_np(i, q, tab1)
    i, q = fir_np(i, q)
    i, q = clip_np(i, q, tab2)
    return fir_np(i, q)


def basis_np(i, q):
    """returns phi[t] = (re, im) arrays for t = 3 j + m, equal to the Basis class of the scalar model"""
    m2 = i * i + q * q
    r = np.minimum(32767, m2 >> 15)
    r2 = (r * r + 16384) >> 15
    b = [(i, q), ((i * r + 16384) >> 15, (q * r + 16384) >> 15), ((i * r2 + 16384) >> 15, (q * r2 + 16384) >> 15)]
    phi = []
    n = len(i)
    for j in range(3):
        for m in range(3):
            re = np.concatenate([np.zeros(m, dtype=np.int64), b[j][0][:n - m]])
            im = np.concatenate([np.zeros(m, dtype=np.int64), b[j][1][:n - m]])
            phi.append((re, im))
    return phi


def dpd_np(i, q, a):
    phi = basis_np(i, q)
    ar = sum(a[t][0] * phi[t][0] - a[t][1] * phi[t][1] for t in range(9))
    ai = sum(a[t][0] * phi[t][1] + a[t][1] * phi[t][0] for t in range(9))
    return sat((ar + 2048) >> 12), sat((ai + 2048) >> 12)


def corr_np(yi, yq, ui, uq):
    phi = basis_np(yi, yq)
    re, im = [], []
    for p in range(9):
        for qq in range(p, 9):
            a, b = phi[p]
            c, d = phi[qq]
            re.append(int((a * c + b * d).sum()))
            im.append(int((a * d - b * c).sum()))
    for p in range(9):
        a, b = phi[p]
        re.append(int((a * ui + b * uq).sum()))
        im.append(int((a * uq - b * ui).sum()))
    return re, im


def load_fw():
    out = HERE / "build"
    out.mkdir(exist_ok=True)
    so = out / "libdpd.so"
    subprocess.check_call(["gcc", "-std=c99", "-O2", "-Wall", "-shared", "-fPIC", str(FW / "dpd_fw.c"), "-I", str(FW), "-o", str(so)])
    lib = C.CDLL(str(so))
    lib.dpd_solve.argtypes = [C.POINTER(C.c_int64), C.POINTER(C.c_int64), C.c_uint32, C.c_float, C.POINTER(C.c_int16), C.POINTER(C.c_int16)]
    lib.dpd_solve.restype = C.c_int
    lib.dpd_update.argtypes = [C.POINTER(C.c_int16), C.POINTER(C.c_int16), C.POINTER(C.c_int16), C.POINTER(C.c_int16), C.c_uint8]
    lib.dpd_update.restype = C.c_int32
    lib.dpd_align.argtypes = [C.POINTER(C.c_int16), C.POINTER(C.c_int16), C.c_uint32, C.c_int32, C.POINTER(C.c_int32), C.POINTER(C.c_int32), C.POINTER(C.c_int32)]
    return lib


def solve(lib, re, im, n, ridge=1e-4):
    A = (C.c_int64 * 54)(*re)
    B = (C.c_int64 * 54)(*im)
    ar = (C.c_int16 * 9)()
    ai = (C.c_int16 * 9)()
    st = lib.dpd_solve(A, B, n, ridge, ar, ai)
    return st, [(ar[t], ai[t]) for t in range(9)]


# ---------------------------------------------------------------- OFDM source
def mapper_64qam(rng, n):
    lv = np.array([-7, -5, -3, -1, 1, 3, 5, 7]) / np.sqrt(42)
    return rng.choice(lv, n) + 1j * rng.choice(lv, n)


TONES = np.concatenate([np.arange(1, 118), np.arange(NFFT - 117, NFFT)])


def ofdm(rng, nsym, mod="64qam"):
    """returns (time samples at OS x the symbol rate, data tones [nsym x 234]); symbol = 1024 samples + prefix of 128"""
    big = NFFT * OS
    data = mapper_64qam(rng, nsym * len(TONES)).reshape(nsym, len(TONES))
    if mod == "qpsk":
        data = (rng.choice([-1, 1], data.shape) + 1j * rng.choice([-1, 1], data.shape)) / np.sqrt(2)
    out = []
    for s in range(nsym):
        X = np.zeros(big, complex)
        for t, k in enumerate(TONES):
            X[k if k < NFFT // 2 else big - (NFFT - k)] = data[s, t]
        x = np.fft.ifft(X) * np.sqrt(big)
        out.append(np.concatenate([x[-big // 8:], x]))
    return np.concatenate(out), data


def papr_ccdf(x, level=1e-3, block=None):
    p = np.abs(x) ** 2
    r = p / p.mean()
    thr = np.quantile(r, 1 - level)
    return 10 * np.log10(thr)


# ---------------------------------------------------------------- PA model [E]
def pa(x, asat=0.7, p=2.0, pm=0.35):
    h_in = np.array([1.0, 0.10, -0.03])
    h_out = np.array([1.0, 0.04])
    xin = np.convolve(x, h_in)[:len(x)]
    r = np.abs(xin)
    g = 1.0 / (1 + (r / asat) ** (2 * p)) ** (1 / (2 * p))
    ph = pm * (r / asat) ** 2 / (1 + (r / asat) ** 2)
    y = xin * g * np.exp(1j * ph)
    return np.convolve(y, h_out)[:len(x)]


# ---------------------------------------------------------------- figures of merit
def evm_db(y, data):
    """demodulate the OS-rate signal and measure EVM after a per-tone least-squares equaliser"""
    big = NFFT * OS
    sym = big + big // 8
    nsym = len(y) // sym
    rx = []
    for s in range(nsym):
        seg = y[s * sym + big // 8: (s + 1) * sym]
        Y = np.fft.fft(seg) / np.sqrt(big)
        rx.append([Y[k if k < NFFT // 2 else big - (NFFT - k)] for k in TONES])
    rx = np.array(rx)
    d = data[:nsym]
    h = (rx * np.conj(d)).sum(0) / (np.abs(d) ** 2).sum(0)
    err = rx - h * d
    return 10 * np.log10((np.abs(err) ** 2).sum() / (np.abs(h * d) ** 2).sum())


def aclr_db(y):
    """adjacent-channel power over channel power (worst side), OS = 4: channel +/-0.125, adjacent 0.125 to 0.375 cycles per sample"""
    nfft = 8192
    n = (len(y) // nfft) * nfft
    seg = y[:n].reshape(-1, nfft) * np.hanning(nfft)
    P = (np.abs(np.fft.fftshift(np.fft.fft(seg, axis=1), axes=1)) ** 2).mean(0)
    f = np.fft.fftshift(np.fft.fftfreq(nfft))
    chan = P[np.abs(f) <= 0.1125].sum()
    up = P[(f > 0.1375) & (f < 0.3625)].sum()
    lo = P[(f < -0.1375) & (f > -0.3625)].sum()
    return 10 * np.log10(max(up, lo) / chan)
