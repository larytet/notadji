import cocotb
from cocotb.triggers import Timer

from fft_model import COS, SIN


@cocotb.test()
async def t12_09_twiddle_table(dut):
    """T12-09 all 512 ROM entries equal the independently computed table"""
    def s16(x):
        return x - 0x10000 if x & 0x8000 else x
    for k in range(512):
        dut.k.value = k
        await Timer(1, unit="ns")
        assert s16(int(dut.cos_q.value)) == COS[k], f"cos[{k}]"
        assert s16(int(dut.sin_q.value)) == SIN[k], f"sin[{k}]"
