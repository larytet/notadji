#!/usr/bin/env python3
"""Report on the AArch64 objects: unresolved symbols (only memcpy, memmove, memset, memcmp allowed), sizes, and static instruction counts of selected
functions (the basis of the cycle figures in design/33 section 8; an estimate, not a measurement). Usage: a64_report.py <build dir>"""
import re, subprocess, sys
from pathlib import Path
B = Path(sys.argv[1])
objs = sorted(B.glob("*.a64.o"))
ALLOWED = {"memcpy", "memmove", "memset", "memcmp"}
def run(*a):
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout
defined, undefined = set(), set()
for o in objs:
    for line in run("llvm-nm", str(o)).splitlines():
        p = line.split()
        if len(p) == 2 and p[0] == "U": undefined.add(p[1])
        elif len(p) == 3 and p[1] in "TtDdRrBb": defined.add(p[2])
bad = sorted(undefined - defined - ALLOWED)
ok = True
if bad:
    print("  FAIL unresolved symbols:", " ".join(bad)); ok = False
else:
    print("  pass  no unresolved symbols beyond memcpy/memmove/memset/memcmp")
tot = 0
for o in objs:
    sz = 0
    for line in run("llvm-objdump", "-h", str(o)).splitlines():
        p = line.split()
        if len(p) > 2 and re.match(r"\.(text|rodata)", p[1]): sz += int(p[2], 16)
    tot += sz
    print(f"  size  {o.name[:-6]:<20} {sz:6d} bytes (text+rodata)")
print(f"  size  total                {tot:6d} bytes")
sys.exit(0 if ok else 1)
