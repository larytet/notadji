#!/usr/bin/env python3
"""Consistency audit: recompute every derived number in the spec and compare it with the text.

Usage: python3 -I scripts/audit_numbers.py        (exit code 1 on any failure)

Each check recomputes a value from first principles (or from scripts/link_budget.py) and asserts that the
spec text states the same value. A failure means the spec and its own arithmetic disagree.
"""
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import link_budget as lb  # noqa: E402

SPEC = ROOT / "spec"
TEXT = {p.name: p.read_text() for p in sorted(SPEC.glob("*.md"))}
SRS = TEXT["01-system-requirements.md"]
FAILS: list[str] = []
CHECKS = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILS.append(f"{name}: {detail}")


def has(doc: str, needle: str) -> bool:
    return needle in TEXT[doc]


def table_rows(doc: str, header_start: str) -> list[list[str]]:
    """Return the data rows of the first table whose header line starts with header_start."""
    lines = TEXT[doc].split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith(header_start):
            rows = []
            for r in lines[i + 2:]:
                if not r.startswith("|"):
                    break
                rows.append([c.strip() for c in r.strip().strip("|").split("|")])
            return rows
    raise KeyError(header_start)


def num(s: str) -> float:
    return float(re.sub(r"[^0-9.\-]", "", s.replace("**", "")))


# ---- 1. numerology and channel plan ------------------------------------------------------------------------
SCS = 78.125e3
for fft, bw in [(64, 5), (128, 10), (256, 20), (512, 40), (1024, 80)]:
    check(f"FFT {fft} gives {bw} MHz", abs(fft * SCS / 1e6 - bw) < 1e-9)
check("symbol time 12.8 us", abs(1e6 / SCS - 12.8) < 1e-9)
check("symbol incl. 1/16 CP 13.6 us", abs(1e6 / SCS * (1 + 1 / 16) - 13.6) < 1e-9)
band24, band58 = 83.5, 125.0
chan = {(b, bw): int(b // bw) for b in (band24, band58) for bw in (20, 10, 5)}
check("SYS-009 channel counts", all(has("01-system-requirements.md", s) for s in (
    f"at least {chan[(band58, 20)]} simultaneous links at 20 MHz and {chan[(band58, 10)]} at 10 MHz in 5.8 GHz",
    f"{chan[(band24, 20)]} at 20 MHz and {chan[(band24, 10)]} at 10 MHz in 2.4 GHz",
    f"{chan[(band58, 5)]} links in 5.8 GHz and {chan[(band24, 5)]} in 2.4 GHz")), str(chan))

# ---- 2. TDD guard / timing advance -------------------------------------------------------------------------
check("guard at 15 km = 120 us", abs(2 * 15 * 3.33 + 20 - 120) < 0.5)
check("MAC-001 states 100+20 us at 15 km", has("01-system-requirements.md", "(100 us + 20 us at 15 km)"))

# ---- 3. Doppler and ICI ------------------------------------------------------------------------------------
def ici_sir_db(fd: float, t_sym: float = 12.8e-6) -> float:
    return -10 * math.log10((math.pi * fd * t_sym) ** 2 / 3)


check("ICI at 3.5 kHz about -22 dB", abs(ici_sir_db(3500) - 21.8) < 0.1 and has("01-system-requirements.md", "about -22 dB"))
check("ICI at 1 kHz about 33 dB (256QAM ok)", abs(ici_sir_db(1000) - 32.7) < 0.2)
v_35 = 3500 * 3e8 / 5.8e9
check("3.5 kHz at 5.8 GHz is about 650 km/h", abs(v_35 * 3.6 - 652) < 3, f"{v_35 * 3.6:.0f} km/h")

# ---- 4. sensitivity model ----------------------------------------------------------------------------------
def sens(snr: float, nf: float = 4.0, impl: float = 2.0, bw: float = 20) -> float:
    return -101 + 10 * math.log10(bw / 20) + nf + snr + impl


for name, snr, expect in [("BPSK 1/2", 2, -93), ("QPSK 3/4", 7, -88), ("16QAM 3/4", 15, -80), ("64QAM 3/4", 21, -74)]:
    check(f"sensitivity {name}", abs(sens(snr) - expect) < 1e-9)
check("thermal noise 20 MHz -101 dBm", abs(-174 + 10 * math.log10(20e6) + 0 - (-101)) < 0.1)
for m, e in zip(lb.MCS_TABLE, (-93, -88, -80, -74)):
    check(f"script table {m.name}", m.sens_20mhz_dbm == e)

# ---- 5. link budget tables in 02 equal script output --------------------------------------------------------
import subprocess  # noqa: E402

out = subprocess.check_output([sys.executable, "-I", str(ROOT / "scripts" / "link_budget.py")], text=True)
down, up, tdd, cmp_, split, pa_tbl = out.strip().split("\n\n")
check("02 contains the downlink table from the script", down.strip() in TEXT["02-link-and-latency-budgets.md"])
check("02 contains the uplink table from the script", up.strip() in TEXT["02-link-and-latency-budgets.md"])
check("02 contains the PA mode table from the script", pa_tbl.strip() in TEXT["02-link-and-latency-budgets.md"])
check("SYS-005 limits hold in the PA model", lb.input_power_w(25, 7.0) <= 3.5 and lb.input_power_w(27, 7.0) <= 4.1 and lb.input_power_w(30, 6.0) <= 6.0 and lb.input_power_w(30, 4.5) <= 6.0)
check("64QAM at 30 dBm would exceed 6.0 W (justifies RF-031)", lb.input_power_w(30, 7.0) > 6.0)
check("PWR-004 values consistent with the model", lb.pae(6.0) >= 0.275 and lb.pae(4.5) >= 0.32 and lb.pae(7.0) >= 0.245)
check("02 contains the split-band table from the script", split.strip() in TEXT["02-link-and-latency-budgets.md"])
check("split-band uplink margin >= 6 dB for all classes (MAC-007)", all(float(r.split("|")[7]) >= 6 for r in split.strip().split("\n")[2:]))
check("MAC-007 states the split-band margins 17.0, 11.0 and 12.4", "17.0, 11.0 and 12.4 dB" in SRS)
check("02 contains the TDD table from the script", tdd.strip() in TEXT["02-link-and-latency-budgets.md"])
check("07 (T-03) contains the TDD comparison from the script", cmp_.strip() in TEXT["07-trade-studies.md"])
_t = lb.tdd_budget(1.0, 5)
check("uplink slot carries MAC-007 (1 Mbit/s QPSK 1/2 + feedback)", (_t["ul_symbols"] - lb.UL_PREAMBLE_SYMBOLS) * lb.DATA_TONES[20.0] >= 1000 + lb.UL_FEEDBACK_BITS)
check("old 80 us uplink slot would fail MAC-007", (math.floor(80 / lb.SYMBOL_US) - lb.UL_PREAMBLE_SYMBOLS) * lb.DATA_TONES[20.0] < 1000 + lb.UL_FEEDBACK_BITS)
check("BPSK 1/2 uplink >= 300 kbit/s at 1 ms frame", (_t["ul_symbols"] - lb.UL_PREAMBLE_SYMBOLS) * 117 - lb.UL_FEEDBACK_BITS >= 300)

# ---- 6. range classes (SYS-003) and T-01 ranges --------------------------------------------------------------
def sc(freq, tx, gt, gr, div, bw):
    return lb.Scenario("x", freq, 1, tx, gt, gr, diversity_gain_db=div, bw_mhz=bw)


qpsk34 = lb.MCS_TABLE[1]
bpsk = lb.MCS_TABLE[0]
ranges = {
    "5.8 km": lb.max_range_km(sc(5800, 30, 5, 5, 3, 20), qpsk34),
    "10.3 km with a 10 dBi": lb.max_range_km(sc(5800, 30, 5, 10, 3, 20), qpsk34),
    "16.4 km with 14 dBi": lb.max_range_km(sc(5800, 30, 5, 14, 3, 20), qpsk34),
    "8.2 km at 10 MHz": lb.max_range_km(sc(5800, 30, 5, 5, 3, 10), qpsk34),
    "8.2 km with a 33 dBm PA": lb.max_range_km(sc(5800, 33, 5, 5, 3, 20), qpsk34),
    "10.3 km if the video drops to BPSK 1/2": lb.max_range_km(sc(5800, 30, 5, 5, 3, 20), bpsk),
    "14.1 km": lb.max_range_km(sc(2400, 30, 5, 5, 3, 20), qpsk34),
}
for label, km in ranges.items():
    value = float(label.split(" km")[0])
    check(f"T-01 range {label}", abs(km - value) < 0.06 and has("07-trade-studies.md", label.split(" km")[0] + " km"), f"computed {km:.2f}")
check("SYS-003 class ranges (5/10/14 km) close with QPSK 3/4 and 6 dB",
      ranges["5.8 km"] >= 5 and ranges["10.3 km with a 10 dBi"] >= 10 and ranges["14.1 km"] >= 14)
for cls, f, d, g in [("S", 5800, 5, 5), ("X", 5800, 10, 10), ("L", 2400, 14, 5)]:
    rate = lb.phy_rate_mbps(qpsk34, 20, d)
    check(f"class {cls} net rate >= 10 Mbit/s", rate >= 10, f"{rate:.1f}")

# ---- 7. latency budget table in 02 ---------------------------------------------------------------------------
rows = table_rows("02-link-and-latency-budgets.md", "| Stage |")
stages = [r for r in rows if not r[0].startswith("**") and not r[0].startswith("Reserve")]
sum60 = sum(num(r[1]) for r in stages)
sum120 = sum(num(r[2]) for r in stages)
tot = [r for r in rows if r[0].startswith("**Sum**")][0]
check("latency sum 1080p60", abs(sum60 - num(tot[1])) < 1e-9, f"computed {sum60}")
check("latency sum 1080p120", abs(sum120 - num(tot[2])) < 1e-9, f"computed {sum120}")
reserve = [r for r in rows if r[0].startswith("Reserve")][0]
total = [r for r in rows if r[0].startswith("**Total**")][0]
check("latency total 1080p60", abs(sum60 + num(reserve[1]) - num(total[1])) < 1e-9)
check("latency total 1080p120", abs(sum120 + num(reserve[2]) - num(total[2])) < 1e-9)
check("SYS-001 targets 20/12 ms hold", num(total[1]) <= 20 and num(total[2]) <= 12)

# ---- 8. power budget in 02 -------------------------------------------------------------------------------------
def pa_w(dbm: float, pae: float) -> float:
    return 10 ** (dbm / 10) / 1000 / pae


for dbm, pae, expect in [(25, .30, 2.9), (27, .30, 3.6), (30, .30, 5.5), (30, .25, 6.3), (33, .30, 9.3)]:
    total_in = (pa_w(dbm, pae) + 1.5) / 0.88
    check(f"input power {dbm} dBm @ {pae:.0%}", abs(total_in - expect) < 0.06, f"{total_in:.2f}")
check("SYS-005 6.0 W at 30 dBm needs PAE of about 27% (26.5%)", (pa_w(30, .27) + 1.5) / .88 <= 6.0 and (pa_w(30, .26) + 1.5) / .88 > 6.0)
check("SYS-005 states the per-mode limits", "6.0 W at 30 dBm in OFDM QPSK/16QAM" in SRS and "4.1 W at 27 dBm" in SRS)

# 8b. power table arithmetic in 02 (ASIC and FPGA columns)
prow = table_rows("02-link-and-latency-budgets.md", "| Block | ASIC target W")
blocks = [r for r in prow if r[0].startswith(("RF PA", "Transceiver", "Baseband", "Memory"))]
for col, name in ((1, "ASIC"), (2, "FPGA")):
    sub = sum(num(re.match(r"[0-9.]+", r[col]).group(0)) for r in blocks)
    stated_sub = num(re.match(r"[0-9.]+", [r for r in prow if r[0].startswith("Subtotal")][0][col]).group(0))
    stated_tot = num(re.match(r"[0-9.]+", [r for r in prow if r[0].startswith("**Total at the input")][0][col].replace("*", "")).group(0))
    stated_with = num(re.match(r"[0-9.]+", [r for r in prow if r[0].startswith("Total including sensor")][0][col]).group(0))
    check(f"power subtotal {name}", abs(sub - stated_sub) < 0.051, f"computed {sub:.2f}")
    check(f"power total {name} (/0.88)", abs(sub / 0.88 - stated_tot) < 0.06, f"computed {sub / 0.88:.2f}")
    check(f"power total with sensor {name}", abs((sub + 0.8) / 0.88 - stated_with) < 0.06, f"computed {(sub + 0.8) / 0.88:.2f}")
import cpu_budget as cb  # noqa: E402
check("13 contains the CPU budget tables from the script", cb.tables().strip() in TEXT["13-hardware-software-integration.md"])
check("RT core load with hardware assist <= 50% at 300 MHz", cb.totals()["base"] / 300 <= 0.5)
check("software DPD+crypto would exceed 40% at 300 MHz (justifies HSI-004)", cb.totals()["with_both_sw"] / 300 > 0.4)
check("PWR-003 prototype ceiling covers K26 7.5 W + 1.5 W transceiver", "at most 9.5 W for the FPGA prototype" in SRS and 7.5 + 1.5 <= 9.5)

# ---- 9. data tones and rates -----------------------------------------------------------------------------------
check("data tone counts (48/108/234/468)", lb.DATA_TONES == {5.0: 48, 10.0: 108, 20.0: 234, 40.0: 468})
check("VID-009 80 Mbit/s fits 40 MHz 64QAM 3/4 at 10 km", lb.phy_rate_mbps(lb.MCS_TABLE[3], 40, 10) >= 80)

# ---- 10. SRS structure -----------------------------------------------------------------------------------------
ids = re.findall(r"^\| ([A-Z]{2,4}-\d{3}) \|", SRS, flags=re.M)
check("SRS requirement IDs unique", len(ids) == len(set(ids)))
known = set(ids)
dangling = set()
for doc, t in TEXT.items():
    for r in re.findall(r"\b([A-Z]{2,4}-\d{3})\b", t):
        if r not in known and not r.startswith(("G-", "T-", "A-", "S-", "R-", "P-", "D-", "O-", "TG-")) and r not in ("AES-256", "RSS-247", "EN-300", "UG-570"):
            dangling.add((doc, r))
check("no dangling requirement references", not dangling, str(sorted(dangling)))
rev = re.search(r"revision (\d+\.\d+)", SRS).group(1)
check("revision history lists the current revision", f"| {rev} |" in SRS, rev)
check("trace matrix is current", f"Requirements: {len(ids)}" in TEXT["09-traceability-matrix.md"])

import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("claim_register", ROOT / "scripts" / "claim_register.py")
_reg_before = TEXT["12-claim-audit-and-feasibility.md"]
_n_reqs = len(ids)
check("12 register lists every requirement", f"| total | {_n_reqs} |" in _reg_before, f"expected total {_n_reqs}")

print(f"{CHECKS} checks, {len(FAILS)} failed")
for f in FAILS:
    print("FAIL:", f)
sys.exit(1 if FAILS else 0)
