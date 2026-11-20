import binascii
import os
import random
import zlib

import cocotb
from cocotb.triggers import FallingEdge

from stream_tb import reset, start_clock

MAXB = int(os.environ.get("MAXB", "4096"))


def frame_bytes(payload, frame_no, idx, flags, bad_len=None):
    n = len(payload) if bad_len is None else bad_len
    h = bytes([flags & 0xF, frame_no & 0xFF, frame_no >> 8, idx, n & 0xFF, n >> 8])
    crc = binascii.crc_hqx(h, 0xFFFF)
    return list(h) + [crc >> 8, crc & 0xFF] + list(payload) + list(zlib.crc32(bytes(payload)).to_bytes(4, "little"))


def rand_slice(rng, n):
    return [rng.getrandbits(8) for _ in range(n)]


def rand_meta(rng):
    return (rng.getrandbits(16), rng.randrange(34), rng.getrandbits(4))


def flat(frames):
    return [(b, i == len(f) - 1) for f in frames for i, b in enumerate(f)]


async def setup(dut):
    dut.s_axis_valid.value = 0
    dut.m_axis_ready.value = 0
    dut.s_axis_data.value = 0
    dut.s_axis_last.value = 0
    for s in ("meta_frame", "meta_idx", "meta_flags"):
        if hasattr(dut, s):
            getattr(dut, s).value = 0
    start_clock(dut.clk)
    await reset(dut)


def meta_hook(dut, metas, lens):
    bounds, acc = [], 0
    for n in lens:
        bounds.append(acc)
        acc += n

    def pre(d, cyc, idx):
        s = 0
        for i, b in enumerate(bounds):
            if idx >= b:
                s = i
        m = metas[min(s, len(metas) - 1)]
        d.meta_frame.value = m[0]
        d.meta_idx.value = m[1]
        d.meta_flags.value = m[2]

    return pre


class StatusMon:
    def __init__(self, dut):
        self.dut = dut
        self.items = []
        self.task = cocotb.start_soon(self.run())

    async def run(self):
        d = self.dut
        while True:
            await FallingEdge(d.clk)
            if int(d.st_valid.value):
                self.items.append(dict(hdr_ok=int(d.st_hdr_ok.value), crc_ok=int(d.st_crc_ok.value), trunc=int(d.st_trunc.value),
                                       frame=int(d.st_frame.value), idx=int(d.st_idx.value), flags=int(d.st_flags.value),
                                       length=int(d.st_len.value)))

    def stop(self):
        self.task.cancel()
