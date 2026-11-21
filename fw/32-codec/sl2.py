"""Python wrapper of the SL2 reference model (fw/32-codec/sl2.c): builds the library on first use."""
import ctypes
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
T_DCT, T_INTRA, T_SUBPEL, T_CTX, T_DEBLOCK, T_RDO = 1, 2, 4, 8, 16, 32
T_ALL = 63


class Cfg(ctypes.Structure):
    _fields_ = [("W", ctypes.c_int), ("H", ctypes.c_int), ("SH", ctypes.c_int), ("tools", ctypes.c_int)]


class Stats(ctypes.Structure):
    _fields_ = [("bins", ctypes.c_longlong), ("probes", ctypes.c_longlong), ("sad_evals", ctypes.c_longlong), ("encodes", ctypes.c_longlong), ("kind_cnt", ctypes.c_longlong * 8), ("cat_bits", ctypes.c_double * 8)]


_lib = None


def lib():
    global _lib
    if _lib is None:
        d = tempfile.mkdtemp(prefix="sl2_")
        so = os.path.join(d, f"libsl2_{os.getpid()}.so")
        subprocess.check_call(["gcc", "-O2", "-Wall", "-Wextra", "-shared", "-fPIC", "-o", so, str(HERE / "sl2.c"), "-lm"])
        L = ctypes.CDLL(so)
        u8 = ctypes.POINTER(ctypes.c_uint8)
        L.sl2_encode_slice.argtypes = [ctypes.POINTER(Cfg), u8, u8, u8, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int8), ctypes.c_int, u8, ctypes.c_int]
        L.sl2_encode_slice.restype = ctypes.c_int
        L.sl2_encode_slice_budget.argtypes = [ctypes.POINTER(Cfg), u8, u8, u8, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int8), u8, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
        L.sl2_encode_slice_budget.restype = ctypes.c_int
        L.sl2_decode_slice.argtypes = [ctypes.POINTER(Cfg), u8, u8, ctypes.c_int, u8, ctypes.c_int]
        L.sl2_decode_slice.restype = ctypes.c_int
        L.sl2_fwd.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32)]
        L.sl2_inv.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32)]
        L.st = Stats.in_dll(L, "sl2_st")
        L.tune = (ctypes.c_double * 8).in_dll(L, "sl2_tune")
        _lib = L
    return _lib


def _p(a, t=ctypes.c_uint8):
    return None if a is None else a.ctypes.data_as(ctypes.POINTER(t))


def fwd(block, dct=True):
    x = np.ascontiguousarray(block, dtype=np.int32).reshape(64)
    c = np.zeros(64, np.int32)
    lib().sl2_fwd(int(dct), _p(x, ctypes.c_int32), _p(c, ctypes.c_int32))
    return c.reshape(8, 8)


def inv(coef, dct=True):
    c = np.ascontiguousarray(coef, dtype=np.int32).reshape(64)
    x = np.zeros(64, np.int32)
    lib().sl2_inv(int(dct), _p(c, ctypes.c_int32), _p(x, ctypes.c_int32))
    return x.reshape(8, 8)


class Codec:
    def __init__(self, W=320, H=256, SH=32, tools=T_ALL):
        self.cfg = Cfg(W, H, SH, tools)
        self.W, self.H, self.SH = W, H, SH
        self.ns = H // SH
        self.mbw, self.mbh = W // 16, H // 16

    def stats_reset(self):
        for f in ("bins", "probes", "sad_evals", "encodes"):
            setattr(lib().st, f, 0)
        for i in range(8):
            lib().st.cat_bits[i] = 0.0
            lib().st.kind_cnt[i] = 0

    def stats(self):
        s = lib().st
        return dict(bins=s.bins, probes=s.probes, sad_evals=s.sad_evals, encodes=s.encodes, cat_bits=list(s.cat_bits), kind_cnt=list(s.kind_cnt))

    def enc_slice(self, src, ref, recon, sl, intra, qp, dqp=None, keep=64, cap=60000):
        out = np.zeros(cap, np.uint8)
        n = lib().sl2_encode_slice(ctypes.byref(self.cfg), _p(src), _p(ref), _p(recon), sl, int(intra or ref is None), qp,
                                   _p(dqp, ctypes.c_int8), keep, _p(out), cap)
        if n < 0:
            raise RuntimeError("slice does not fit the buffer")
        return bytes(out[:n])

    def enc_slice_budget(self, src, ref, recon, sl, intra, budget, dqp=None, cap=60000):
        out = np.zeros(cap, np.uint8)
        qp, ne = ctypes.c_int(), ctypes.c_int()
        n = lib().sl2_encode_slice_budget(ctypes.byref(self.cfg), _p(src), _p(ref), _p(recon), sl, int(intra or ref is None), budget,
                                          _p(dqp, ctypes.c_int8), _p(out), cap, ctypes.byref(qp), ctypes.byref(ne))
        if n < 0:
            raise RuntimeError("slice does not fit the buffer")
        return bytes(out[:n]), qp.value, ne.value

    def dec_slice(self, ref, recon, sl, data):
        buf = np.frombuffer(data, np.uint8).copy()
        return lib().sl2_decode_slice(ctypes.byref(self.cfg), _p(ref), _p(recon), sl, _p(buf), len(buf))

    # ---- whole frames
    def frame_arrays(self, frame):
        return np.ascontiguousarray(frame, dtype=np.uint8)

    def encode_frame(self, frame, ref, qp=None, budgets=None, intra=(), dqp=None):
        """returns (list of slice byte strings, reconstruction, list of (qp, nenc))"""
        src = self.frame_arrays(frame)
        recon = np.zeros_like(src)
        slices, info = [], []
        for s in range(self.ns):
            isi = ref is None or s in intra
            if budgets is not None:
                b, q, ne = self.enc_slice_budget(src, ref, recon, s, isi, budgets[s] if hasattr(budgets, "__len__") else budgets, dqp)
            else:
                b = self.enc_slice(src, ref, recon, s, isi, qp, dqp)
                q, ne = qp, 1
            slices.append(b)
            info.append((q, ne))
        return slices, recon, info

    def decode_frame(self, slices, ref):
        """slices: list of bytes or None (lost: concealed by copying the previous frame, or grey without one)"""
        recon = np.full((self.H, self.W), 128, np.uint8) if ref is None else ref.copy()
        for s, b in enumerate(slices):
            if b is None:
                continue
            if self.dec_slice(ref, recon, s, b):
                raise RuntimeError("malformed slice")
        return recon


def set_tune(lam=1.0, f_intra=21845.0, f_inter=10923.0, lam_motion=1.0):
    t = lib().tune
    t[0], t[1], t[2], t[3] = lam, f_intra, f_inter, lam_motion
