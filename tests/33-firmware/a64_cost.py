#!/usr/bin/env python3
"""Static instruction-count cost model for AArch64 (T33-08 and the cycle figures of design/33 section 8). ESTIMATES, not measurements:
cycles = instructions / IPC with IPC = 0.75 for an in-order dual-issue core (Cortex-A53 class) running from cache, plus an assumed fixed cost for each
call through the HAL. Usage: a64_cost.py <build dir>   Exit 1 if a budget is exceeded."""
import re, subprocess, sys
from pathlib import Path
B = Path(sys.argv[1])
IPC = 0.75
HAL_RET_WRITE_32B = 120      # cycles, assumed: 32 bytes to retained RAM through a bus, not cached
def dis(obj):
    out = subprocess.run(["llvm-objdump", "-d", "--no-show-raw-insn", str(B / obj)], capture_output=True, text=True, check=True).stdout
    funcs, cur = {}, None
    for line in out.splitlines():
        m = re.match(r"[0-9a-f]+ <(\w+)>:", line)
        if m: cur = m.group(1); funcs[cur] = []; continue
        m = re.match(r"\s+([0-9a-f]+):\s+(\S+)\s*(.*)", line)
        if m and cur: funcs[cur].append((int(m.group(1), 16), m.group(2), m.group(3)))
    return funcs
def loop_body(f):
    """instructions of the first loop (a backward conditional branch to an earlier address in the same function)"""
    for i, (addr, op, args) in enumerate(f):
        if op.startswith("b.") or op in ("b", "cbnz", "cbz", "tbnz", "tbz"):
            m = re.search(r"0x([0-9a-f]+)", args)
            if m and int(m.group(1), 16) < addr:
                tgt = int(m.group(1), 16)
                return sum(1 for a, _, _ in f if tgt <= a <= addr)
    return None
ok = True
crc = dis("crc.a64.o"); clg = dis("crashlog.a64.o")
body = loop_body(crc["crc32_ieee"]); n_crc = len(crc["crc32_ieee"])
crc28 = (n_crc - body) + 28 * body
app = len(clg["clog_append"]) + crc28
cyc = app / IPC + HAL_RET_WRITE_32B
print(f"  cost  crc32_ieee: {body} instructions per byte, {crc28} for 28 bytes")
print(f"  cost  clog_append: {app} instructions, about {cyc:.0f} cycles ({cyc * 1000 / 300e6 * 100:.2f}% of a 300 MHz core at 1 kHz)  [estimate]")
if cyc > 1500: print("  FAIL clog_append above the 1500 cycle budget"); ok = False
else: print("  pass  clog_append within 1500 cycles (model)")

# ---- feedback path (R33-07): poll period + computation + register accesses, all as upper bounds
HAL_REG_ACCESS = 100         # cycles per register access, assumed (uncached peripheral bus)
la = dis("link_adapt.a64.o"); mf = dis("mac_fb.a64.o")
n_la = sum(len(f) for f in la.values()); n_mf = sum(len(f) for f in mf.values())
n_crc16 = 18 * len(crc["crc16_mcrf4xx_update"])
bound_instr = 16 * (n_la + n_mf) + n_crc16        # every function of both files executed 16 times (the loops over the MCS table and the bitmap are at most 16 and 8 long)
bound_cyc = bound_instr / IPC + 7 * HAL_REG_ACCESS
latency_us = 1000 + bound_cyc / 300
print(f"  cost  feedback path: bound {bound_instr} instructions, {bound_cyc:.0f} cycles ({bound_cyc / 300:.0f} us), worst latency with a 1 ms poll period {latency_us:.0f} us  [bound, estimate]")
if latency_us > 2000: print("  FAIL feedback to commit above 2 ms (MAC-005)"); ok = False
else: print("  pass  feedback to register commit within 2 ms (bound)")
# ---- rate retarget: 8 slices, every target changed
rt = mf["rate_targets"]; lb = loop_body(rt) or len(rt)
rt_cyc = ((len(rt) - lb) + 8 * lb) / IPC + 8 * HAL_REG_ACCESS
print(f"  cost  rate_targets (8 slices, all changed): about {rt_cyc:.0f} cycles  [estimate]")
if rt_cyc > 4000: print("  FAIL rate_targets above 4000 cycles per frame"); ok = False
else: print("  pass  rate_targets within 4000 cycles (model)")
sys.exit(0 if ok else 1)
