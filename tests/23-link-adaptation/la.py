"""ctypes binding of fw/23-link-adaptation/link_adapt.c and an independent channel model."""
import ctypes as C
import math
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FW = HERE.parent.parent / "fw" / "23-link-adaptation"
LIB = HERE / "build" / "liblink_adapt.so"
MAXM = 16


class Mcs(C.Structure):
    _fields_ = [("rate_x256", C.c_uint16), ("thr_x10", C.c_int16), ("rung", C.c_uint8)]


class Cfg(C.Structure):
    _fields_ = [("mcs", Mcs * MAXM), ("n_mcs", C.c_uint8), ("mcs_min", C.c_uint8), ("mcs_max", C.c_uint8),
                ("per_target_ppm", C.c_uint32), ("up_hys_x10", C.c_int16), ("down_hys_x10", C.c_int16),
                ("up_dwell_us", C.c_uint32), ("down_dwell_us", C.c_uint32), ("olla_step_udb", C.c_uint32),
                ("olla_neg_limit_udb", C.c_uint32), ("probe_window_us", C.c_uint32), ("probe_max_us", C.c_uint32),
                ("pwr_min_x4", C.c_int16), ("pwr_max_x4", C.c_int16), ("pwr_margin_x10", C.c_int16),
                ("pwr_headroom_x10", C.c_int16), ("pwr_dwell_us", C.c_uint32), ("fb_timeout_us", C.c_uint32),
                ("outage_us", C.c_uint32), ("dl_sym_per_frame", C.c_uint16), ("data_tones", C.c_uint16),
                ("slices_per_frame", C.c_uint16), ("video_share_x256", C.c_uint16)]


class Fb(C.Structure):
    _fields_ = [("t_us", C.c_uint32), ("snr_x10", C.c_int16), ("n_slices", C.c_uint8), ("n_lost", C.c_uint8), ("mcs_rec", C.c_uint8)]


class Out(C.Structure):
    _fields_ = [("mcs", C.c_uint8), ("pwr_x4", C.c_int16), ("slice_budget", C.c_uint32), ("rung", C.c_uint8),
                ("outage", C.c_uint8), ("safe", C.c_uint8), ("changed", C.c_uint8)]


class State(C.Structure):
    _fields_ = [("snr_f_x100", C.c_int32), ("offset_udb", C.c_int32), ("step_up_udb", C.c_uint32),
                ("last_up_us", C.c_uint32), ("last_down_us", C.c_uint32), ("last_pwr_us", C.c_uint32), ("last_fb_us", C.c_uint32),
                ("below_since_us", C.c_uint32), ("probe_hold_us", C.c_uint32), ("snr_at_up_x100", C.c_int32),
                ("mcs", C.c_uint8), ("rung", C.c_uint8), ("below", C.c_uint8), ("outage", C.c_uint8), ("safe", C.c_uint8),
                ("have_snr", C.c_uint8), ("probing", C.c_uint8), ("pwr_x4", C.c_int16), ("prev", Out)]


def build():
    LIB.parent.mkdir(exist_ok=True)
    subprocess.check_call(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-shared", "-fPIC", str(FW / "link_adapt.c"), "-I", str(FW), "-o", str(LIB)])


def load():
    build()
    lib = C.CDLL(str(LIB))
    lib.la_default_cfg.argtypes = [C.POINTER(Cfg)]
    lib.la_init.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.c_uint32]
    lib.la_on_feedback.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.POINTER(Fb), C.POINTER(Out)]
    lib.la_tick.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.c_uint32, C.POINTER(Out)]
    lib.la_slice_budget.argtypes = [C.POINTER(Cfg), C.c_uint8]
    lib.la_slice_budget.restype = C.c_uint32
    return lib


class Ctl:
    def __init__(self, lib, cfg=None, t0=0):
        self.lib = lib
        self.cfg = Cfg()
        lib.la_default_cfg(C.byref(self.cfg))
        if cfg:
            for k, v in cfg.items():
                setattr(self.cfg, k, v)
        self.s = State()
        self.o = Out()
        self.fb = Fb()
        lib.la_init(C.byref(self.s), C.byref(self.cfg), t0)

    def feed(self, t_us, snr_x10, n_slices=8, n_lost=0, rec=255):
        self.fb.t_us = t_us
        self.fb.snr_x10 = snr_x10
        self.fb.n_slices = n_slices
        self.fb.n_lost = n_lost
        self.fb.mcs_rec = rec
        self.lib.la_on_feedback(C.byref(self.s), C.byref(self.cfg), C.byref(self.fb), C.byref(self.o))
        return self.o

    def tick(self, t_us):
        self.lib.la_tick(C.byref(self.s), C.byref(self.cfg), t_us, C.byref(self.o))
        return self.o

    @property
    def thr(self):
        return [self.cfg.mcs[i].thr_x10 for i in range(self.cfg.n_mcs)]

    @property
    def rate(self):
        return [self.cfg.mcs[i].rate_x256 for i in range(self.cfg.n_mcs)]


def p_loss(thr_x10, snr_db):
    """Independent channel model: slice loss probability, one decade per 0.5 dB, 1e-3 at the threshold [E]."""
    e = -3 + 2 * (thr_x10 / 10 - snr_db)
    return 1.0 if e >= 0 else 10 ** e
