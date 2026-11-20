"""ctypes access to the calibration firmware (through the test shim)."""
import ctypes as C
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FW = HERE.parent.parent / "fw" / "25-calibration"
import os
LIB = HERE / "build" / f"libcal_{os.getpid()}.so"


def load():
    LIB.parent.mkdir(exist_ok=True)
    subprocess.check_call(["gcc", "-std=gnu99", "-O2", "-Wall", "-Wextra", "-shared", "-fPIC", str(FW / "cal_mgr.c"), str(HERE / "cal_shim.c"),
                           "-I", str(FW), "-o", str(LIB)])
    lib = C.CDLL(str(LIB))
    lib.shim_result.argtypes = [C.c_int, C.POINTER(C.c_int64), C.c_uint32, C.c_uint32, C.c_int, C.POINTER(C.c_int16)]
    lib.shim_estimate.argtypes = [C.POINTER(C.c_int64), C.c_uint32, C.POINTER(C.c_int16)]
    lib.shim_regs.argtypes = [C.POINTER(C.c_int16)]
    lib.shim_set_lim.argtypes = [C.c_uint32, C.c_uint32, C.c_int, C.c_int]
    lib.shim_init.argtypes = []
    lib.shim_load.argtypes = [C.POINTER(C.c_uint8), C.c_uint16]
    lib.shim_lookup.argtypes = [C.c_int, C.c_int, C.c_int, C.POINTER(C.c_int)]
    lib.shim_hop.argtypes = [C.c_int, C.c_int, C.c_int, C.c_uint32]
    lib.shim_tick.argtypes = [C.c_uint32, C.c_int, C.c_int]
    lib.shim_set_gap.argtypes = [C.c_uint32]
    lib.cal_crc32.argtypes = [C.POINTER(C.c_uint8), C.c_uint32]
    lib.cal_crc32.restype = C.c_uint32
    return lib


def sums_arr(s):
    return (C.c_int64 * 5)(*[int(x) for x in s])


def result(lib, job, sums, n, now_ms=0, temp=250):
    out = (C.c_int16 * 8)()
    st = lib.shim_result(job, sums_arr(sums), n, now_ms, temp, out)
    return st, list(out)


def estimate(lib, sums, n):
    out = (C.c_int16 * 4)()
    st = lib.shim_estimate(sums_arr(sums), n, out)
    return st, list(out)
