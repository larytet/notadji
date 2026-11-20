"""ctypes binding of fw/24-channel-selection/chan_select.c and a spectrum/link model independent of the controller."""
import ctypes as C
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FW = HERE.parent.parent / "fw" / "24-channel-selection"
LIB = HERE / "build" / "libchan_select.so"
MAXCH, MAXFB = 32, 8


class Cfg(C.Structure):
    _fields_ = [("n_ch", C.c_uint8), ("enabled_mask", C.c_uint32), ("fallback", C.c_uint8 * MAXFB), ("n_fallback", C.c_uint8),
                ("link_id", C.c_uint16), ("stale_ms", C.c_uint32), ("memory_ms", C.c_uint32), ("det_ms", C.c_uint32),
                ("min_stay_ms", C.c_uint32), ("probation_ms", C.c_uint32), ("blacklist_ms", C.c_uint32), ("jitter_ms", C.c_uint32),
                ("margin", C.c_int32), ("rise", C.c_int32), ("adj_pen", C.c_int32), ("unknown_pen", C.c_int32), ("qual_pen", C.c_int32),
                ("strong_lg", C.c_int32), ("loss_trig_ppm", C.c_uint32), ("severe_ppm", C.c_uint32), ("confirm", C.c_uint8),
                ("switch_lead", C.c_uint8)]


class Chan(C.Structure):
    _fields_ = [("lvl_q4", C.c_int32), ("t_scan", C.c_uint32), ("bl_until", C.c_uint32), ("q_t", C.c_uint32), ("q_loss", C.c_uint32),
                ("have", C.c_uint8), ("bl", C.c_uint8), ("q_valid", C.c_uint8)]


class Dec(C.Structure):
    _fields_ = [("switch_now", C.c_uint8), ("target", C.c_uint8), ("effective_frame", C.c_uint16), ("reason", C.c_uint8)]


class State(C.Structure):
    _fields_ = [("ch", Chan * MAXCH), ("cur", C.c_uint8), ("prev", C.c_uint8), ("have_prev", C.c_uint8),
                ("last_switch_ms", C.c_uint32), ("degr_since_ms", C.c_uint32), ("severe_since_ms", C.c_uint32), ("trig_ms", C.c_uint32),
                ("degr", C.c_uint8), ("severe", C.c_uint8), ("trig_set", C.c_uint8), ("confirm_cnt", C.c_uint8), ("confirm_ch", C.c_uint8),
                ("base_q4", C.c_int32), ("base_set", C.c_uint8), ("loss_ppm", C.c_uint32), ("snr_ok", C.c_uint32),
                ("jitter_wait", C.c_uint32), ("n_switch", C.c_uint32)]


def load():
    LIB.parent.mkdir(exist_ok=True)
    subprocess.check_call(["gcc", "-std=c99", "-O2", "-Wall", "-Wextra", "-shared", "-fPIC", str(FW / "chan_select.c"), "-I", str(FW), "-o", str(LIB)])
    lib = C.CDLL(str(LIB))
    lib.cs_default_cfg.argtypes = [C.POINTER(Cfg)]
    lib.cs_init.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.c_uint8, C.c_uint32]
    lib.cs_scan.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.c_uint8, C.c_uint16, C.c_uint32]
    lib.cs_quality.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.c_uint32, C.c_uint32]
    lib.cs_tick.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.c_uint32, C.c_uint16, C.POINTER(Dec)]
    lib.cs_score.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.c_uint8, C.c_uint32]
    lib.cs_score.restype = C.c_int32
    lib.cs_strong_adjacent.argtypes = [C.POINTER(State), C.POINTER(Cfg), C.c_uint32]
    lib.cs_strong_adjacent.restype = C.c_uint32
    return lib


class Sel:
    def __init__(self, lib, start=0, t0=0, **kw):
        self.lib = lib
        self.cfg = Cfg()
        lib.cs_default_cfg(C.byref(self.cfg))
        for k, v in kw.items():
            if k == "fallback":
                for i, f in enumerate(v):
                    self.cfg.fallback[i] = f
                self.cfg.n_fallback = len(v)
            else:
                setattr(self.cfg, k, v)
        self.s = State()
        self.d = Dec()
        lib.cs_init(C.byref(self.s), C.byref(self.cfg), start, t0)

    def scan(self, ch, lg, t):
        self.lib.cs_scan(C.byref(self.s), C.byref(self.cfg), ch, int(max(0, min(4095, lg))), t)

    def quality(self, loss_ppm, t):
        self.lib.cs_quality(C.byref(self.s), C.byref(self.cfg), int(loss_ppm), t)

    def tick(self, t, frame=0):
        self.lib.cs_tick(C.byref(self.s), C.byref(self.cfg), t, frame, C.byref(self.d))
        return self.d

    def score(self, ch, t):
        return self.lib.cs_score(C.byref(self.s), C.byref(self.cfg), ch, t)

    @property
    def cur(self):
        return self.s.cur


FLOOR = 300           # noise floor in lg units
INTERF = 160          # a co-channel interferer adds this much above the floor (energy sum: it dominates the floor)


def level(floor, interferers):
    """Energy level (lg units) of a channel with the given interferer levels (each in lg): power sum of floor and interferers."""
    import math
    tot = 2 ** (floor / 16)
    for lv in interferers:
        tot += 2 ** (lv / 16)
    return 16 * math.log2(tot)


def loss_ppm(excess_lg):
    """Loss rate of a link on a channel whose level is `excess_lg` above the noise floor [E]."""
    if excess_lg < 16:
        return 0
    return min(1_000_000, int(1000 * 2 ** ((excess_lg - 16) / 4)))
