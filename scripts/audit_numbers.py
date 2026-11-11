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
down, up, tdd, cmp_, split, pa_tbl, numer_tbl, ldpc_tbl, nf_tbl, slice_tbl, intra_tbl, sector_tbl, gl_tbl, hop_tbl, iface_tbl, rng_tbl, reg_tbl, lev_tbl, coax_tbl, brk_tbl, aoa_tbl, bf_tbl, fov_tbl, race_tbl, sc_tbl, sfo_tbl, lad_tbl, trn_tbl, mass_tbl, bat_tbl, hold_tbl = out.strip().split("\n\n")
check("02 contains the downlink table from the script", down.strip() in TEXT["02-link-and-latency-budgets.md"])
check("02 contains the uplink table from the script", up.strip() in TEXT["02-link-and-latency-budgets.md"])
check("02 contains the PA mode table from the script", pa_tbl.strip() in TEXT["02-link-and-latency-budgets.md"])
check("SYS-005 limits hold in the PA model", lb.input_power_w(25, 7.0) <= 3.5 and lb.input_power_w(27, 7.0) <= 4.1 and lb.input_power_w(30, 6.0) <= 6.0 and lb.input_power_w(30, 4.5) <= 6.0)
check("64QAM at 30 dBm would exceed 6.0 W (justifies RF-031)", lb.input_power_w(30, 7.0) > 6.0)
check("PWR-004 values consistent with the model", lb.pae(6.0) >= 0.275 and lb.pae(4.5) >= 0.32 and lb.pae(7.0) >= 0.245)
check("07 contains the numerology table from the script", numer_tbl.strip() in TEXT["07-trade-studies.md"])
check("07 contains the LDPC decoder table from the script", ldpc_tbl.strip() in TEXT["07-trade-studies.md"])
check("PHY-003 Doppler limits have margin (3.5 kHz for 64QAM, 1.0 kHz for 256QAM)", math.sqrt(3 * 10 ** -2.1) * SCS / math.pi >= 3500 and math.sqrt(3 * 10 ** -2.8) * SCS / math.pi >= 1000)
check("PHY-015 states 3 instances for 155 Mbit/s", "155 Mbit/s" in SRS and math.ceil(lb.DATA_TONES[40.0] * 4.5 / lb.SYMBOL_US / 72) == 3)
check("07 contains the near-far table from the script", nf_tbl.strip() in TEXT["07-trade-studies.md"])
check("SYS-009 separation figures follow the script (184 m edge, 7 m short range)", round(lb.separation_m(45, lb.EDGE_I_MAX_DBM)) == 184 and round(lb.separation_m(45, lb.SHORT_RANGE_SIGNAL_DBM - lb.SHORT_RANGE_SIR_DB)) == 7 and "184 m apart" in SRS and "at least 7 m apart" in SRS)
check("SYS-009 alternate-channel counts", all(f"{a}, {b} and {c}" in SRS for a, b, c in ((3, 6, 13), (2, 4, 8))) and [-(-n // 2) for n in (6, 12, 25)] == [3, 6, 13] and [-(-n // 2) for n in (4, 8, 16)] == [2, 4, 8])
check("RF-029 near-far level: 35 dBm EIRP at 10 m is about -33 dBm", abs((35 - (32.44 + 20 * math.log10(0.01) + 20 * math.log10(5800))) - (-32.7)) < 0.2)
check("07 contains the slice protection and intra-refresh tables", slice_tbl.strip() in TEXT["07-trade-studies.md"] and intra_tbl.strip() in TEXT["07-trade-studies.md"])
_sb = 20e6 / 60 / 8
check("PHY-011 states 86 codewords and 1.2e-5", math.ceil(_sb / 486) == 86 and abs((1 - (1 - 1e-3) ** (1 / 86)) - 1.2e-5) < 0.05e-5 and "86 codewords" in SRS and "1.2e-5" in SRS)
check("VID-021 average overhead about 0.3%", abs(0.48 * 0.375 / 60 * 100 - 0.3) < 0.01 and "about 0.3%" in SRS)
check("VID-005 wave overhead 5% at 60 frames", abs((lb.INTRA_TO_INTER_BITS - 1) / 60 - 0.05) < 1e-9 and "period of 60 frames or less" in SRS)
check("PRO-007 A1 frequencies are inside the Pluto guaranteed range", 325 <= 915 <= 3800 and 325 <= 2400 <= 3800 and not (325 <= 5800 <= 3800) and "915 MHz" in SRS)
check("07 contains the sector gain table", sector_tbl.strip() in TEXT["07-trade-studies.md"])
check("ANT-008: 6 sectors at 40 degrees reach 10 dBi, 4 sectors at 60 degrees do not", lb.sector_gain_dbi(6, 40) >= 10.0 and lb.sector_gain_dbi(4, 60) < 8.0 and "at least 6 sectors" in SRS)
check("07 contains the genlock and hop tables", gl_tbl.strip() in TEXT["07-trade-studies.md"] and hop_tbl.strip() in TEXT["07-trade-studies.md"])
check("VID-018 drift figures (2.4 and 0.24 ms/min, 0.6 ms per 10 min)", abs(40e-6 * 60 * 1e3 - 2.4) < 1e-9 and abs(4e-6 * 60 * 1e3 - 0.24) < 1e-9 and abs(1e-6 * 600 * 1e3 - 0.6) < 1e-9 and "2.4 ms per minute" in SRS and "0.24 ms per minute" in SRS)
check("07 contains the interface table", iface_tbl.strip() in TEXT["07-trade-studies.md"])
_gbps = 61.44e6 * 2 * 12 * 2 / 1e9
check("ASC-006: air unit 2.95 Gbit/s, 20 pJ/bit both ends stays under 120 mW", abs(_gbps - 2.95) < 0.01 and _gbps * 1e9 * 20e-12 * 2 * 1e3 <= 120 and "2.95 Gbit/s" in SRS)
check("07 contains the range-versus-MCS table", rng_tbl.strip() in TEXT["07-trade-studies.md"])
_b = lb.MCS_TABLE[0]
_r58 = lb.max_range_km(lb.Scenario("x", 5800, 1, 30, 5, 5, diversity_gain_db=3), _b)
_r24 = lb.max_range_km(lb.Scenario("x", 2400, 1, 30, 5, 5, diversity_gain_db=3), _b)
check("SYS-003/VID-022 reduced-profile ranges 10.3 km and 25 km", abs(_r58 - 10.3) < 0.06 and abs(_r24 - 25.0) < 0.3 and "10.3 km at 5.8 GHz and 25 km at 2.4 GHz" in SRS)
check("ADA-003 overhead range matches the hop table (5% to 0.5%)", abs(50e-3 / 1.0 - 0.05) < 1e-9 and abs(50e-3 / 10.0 - 0.005) < 1e-9 and "5% to 0.5% of airtime" in SRS)
check("02 contains the region profile table from the script", reg_tbl.strip() in TEXT["02-link-and-latency-budgets.md"])
_ux = lb.Scenario("X", 5800, 10, lb.GU_TX_CAPABILITY_DBM, 10, 5, diversity_gain_db=3)
_us = lb.Scenario("S", 5800, 5, lb.GU_TX_CAPABILITY_DBM, 5, 5, diversity_gain_db=3)
_ul = lb.Scenario("L", 2400, 14, lb.GU_TX_CAPABILITY_DBM, 5, 5, diversity_gain_db=3)
check("MAC-007 in-band uplink ranges 5/9/12 km hold with 6 dB margin at QPSK 1/2", lb.max_range_km(_us, lb.UPLINK_QPSK_HALF) >= 5 and lb.max_range_km(_ux, lb.UPLINK_QPSK_HALF) >= 9 and lb.max_range_km(_ul, lb.UPLINK_QPSK_HALF) >= 12 and "9 km (Class X)" in SRS)
check("capability budget is not cut by the FCC rule (REG-008) and the FCC profile costs 4 dB at 10 dBi", lb.fcc_conducted_limit_dbm(10) == 26.0 and lb.GU_TX_CAPABILITY_DBM == 27.0 and "REG-008" in SRS)
check("SYS-003 no longer carries an ETSI-specific range", "about 2.5 km at 20 dBm EIRP" not in SRS)
check("02 contains the ground-lever and coax tables", lev_tbl.strip() in TEXT["02-link-and-latency-budgets.md"] and coax_tbl.strip() in TEXT["02-link-and-latency-budgets.md"])
check("07 contains the tape-out break-even table", brk_tbl.strip() in TEXT["07-trade-studies.md"] and "21 to 24 million units" in TEXT["07-trade-studies.md"])
check("break-even is 21 to 24 million units", round((3 + 50 * 0.15) / 0.5) == 21 and round((3 + 60 * 0.15) / 0.5) == 24)
check("8 branches and NF 2 add 8 dB over the baseline (PHY-016, RF-032)", abs((3.0 * math.log2(8) + (4.0 - 2.0)) - (3.0 * math.log2(2)) - 8.0) < 1e-9)
_g8 = lb.max_range_km(lb.Scenario("x", 5800, 1, 30, 5, 5, diversity_gain_db=3.0 * math.log2(8) + 2.0), lb.MCS_TABLE[1])
check("ground levers: 8 branches NF 2 reach 14.6 km at 5.8 GHz QPSK 3/4", abs(_g8 - 14.6) < 0.06 and "5.8 km to 14.6 km" in TEXT["02-link-and-latency-budgets.md"], f"{_g8:.2f}")
_ul24 = lb.Scenario("x", 2400, 1, 27, 5, 5, bw_mhz=5.0)
check("uplink-limited ranges 17.7 / 25.1 km (2.4 GHz) stated in 02", abs(lb.max_range_km(_ul24, lb.UPLINK_QPSK_HALF) - 17.7) < 0.06 and abs(lb.max_range_km(_ul24, lb.MCS_TABLE[0]) - 25.1) < 0.06 and "17.7 km at QPSK 1/2 and 25.1 km at BPSK 1/2" in TEXT["02-link-and-latency-budgets.md"])
check("coax delay at 20 m (150 ns) is inside the 0.8 us prefix, passive 20 m costs 8.2 dB", abs(20 / (3e8 * 0.8) * 1e9 + 20 / 3e8 * 1e9 - 150) < 1 and abs(0.41 * 20 - 8.2) < 1e-9 and "150 ns at 20 m" in SRS)
check("ASC-007: 8 receive chains at 40 MHz are 11.8 Gbit/s", abs(61.44e6 * 2 * 12 * 8 / 1e9 - 11.8) < 0.01 and "11.8 Gbit/s" in SRS)
import roles as _roles  # noqa: E402
_tags = {m.group(1): m.group(2) for m in re.finditer(r"^\| ([A-Z]{2,4}-\d{3}) \| \[(AU|GU)\] ", SRS, flags=re.M)}
check("role tags in the SRS match scripts/roles.py", _tags == {k: v[1:3] for k, v in _roles.TAGS.items()}, "run python3 -I scripts/roles.py")
check("SYS-011 present and RF-032 gain is 2 dB", "SYS-011" in SRS and (4.0 - 2.0) == 2.0)
check("02 contains the AoA and beamforming tables", aoa_tbl.strip() in TEXT["02-link-and-latency-budgets.md"] and bf_tbl.strip() in TEXT["02-link-and-latency-budgets.md"])
_err = math.radians(5.0) / (2 * math.pi * 0.5)
check("ANT-013: 1.6 degrees and 139 m at 5 km (half-wavelength, 5 degrees phase error); range resolution 15 m", abs(math.degrees(_err) - 1.59) < 0.01 and round(5000 * _err) == 139 and abs(3e8 * 0.1e-6 / 2 - 15) < 1e-9 and "1.6 degrees" in SRS and "139 m of cross-range" in SRS and "about 15 m of range" in SRS)
check("AoA unambiguous field of view of a 5-wavelength baseline is 5.7 degrees", abs(math.degrees(math.asin(1 / (2 * 5))) - 5.7) < 0.05)
_b = lb.max_range_km(lb.Scenario("x", 5800, 1, 30, 5, 5, diversity_gain_db=3), lb.MCS_TABLE[1])
check("beamforming: +6 dB doubles the range (5.8 -> 11.6 km), +3 dB gives 8.2 km", abs(_b * 10 ** (6 / 20) - 11.6) < 0.1 and abs(_b * 10 ** (3 / 20) - 8.2) < 0.1)
check("ASC-008 area overhead 1.5-4 mm2 is 5% to 14% of 29 mm2", abs(1.5 / 29 - 0.052) < 0.001 and abs(4 / 29 - 0.138) < 0.001 and "about 5% to 14% of the die" in TEXT["07-trade-studies.md"])
check("14 contains the foveation and race-channel tables", fov_tbl.strip() in TEXT["14-appendix-foveated-video.md"] and race_tbl.strip() in TEXT["14-appendix-foveated-video.md"])
check("foveation savings: 60% region +6 QP saves 20%; 25% region +9 QP saves 48%", abs((1 - (0.6 + 0.4 * 2 ** -1)) - 0.20) < 1e-9 and abs((1 - (0.25 + 0.75 * 2 ** -1.5)) - 0.48) < 0.005 and "about 20%" in TEXT["14-appendix-foveated-video.md"] and "about 48%" in TEXT["14-appendix-foveated-video.md"])
check("race channel at 5 MHz: 4.3 Mbit/s at QPSK 3/4; gaze 7.7 kbit/s is 0.8% of 1 Mbit/s", abs(lb.DATA_TONES[5.0] * 1.5 / lb.SYMBOL_US * lb.DL_DUTY_SPLIT * 0.85 - 4.3) < 0.05 and abs(8 * 8 * 120 / 1000 - 7.68) < 0.01 and "7.7 kbit/s" in SRS)
check("notes entry 8 facts: 915 MHz is 16.0 dB below 5.8 GHz in path loss; quarter wave 8.2 cm and 1.3 cm, ratio 6.3", abs(20 * math.log10(5800 / 915) - 16.0) < 0.05 and abs(3e8 / 915e6 / 4 * 100 - 8.2) < 0.05 and abs(3e8 / 5.8e9 / 4 * 100 - 1.3) < 0.05 and abs(5800 / 915 - 6.3) < 0.05)
check("00 says closely matches and drops the plain dash bullet", "closely matches or beats" in TEXT["00-overview.md"] and "Plain dash" not in TEXT["00-overview.md"])
check("07 index lists every trade study T-01..T-23", all(f"T-{n:02d}" in TEXT["07-trade-studies.md"].split("Index:")[1].split("---")[0] for n in range(1, 24)))
_dots = sorted((SPEC / "diagrams").glob("*.dot"))
check("every diagram source has a rendered PNG and SVG, and is referenced by a document", all((d.with_suffix(".png")).exists() and d.with_suffix(".svg").exists() and f"diagrams/{d.stem}.png" in "".join(TEXT.values()) for d in _dots) and len(_dots) >= 4)
check("no ASCII diagrams (fenced blocks) remain in the spec documents", all("```" not in t for n, t in TEXT.items() if n not in ("notes.md",)), "convert to spec/diagrams/*.dot")
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

# ---- 11. requirement rationale (doc 15) ------------------------------------------------------------------------
R15 = TEXT["15-requirement-rationale.md"]
r15_rows = {m.group(1): m.group(0) for m in re.finditer(r"^\| ([A-Z]{2,4}-\d{3}) \|.*$", R15.split("## 3. Rationale table")[1], flags=re.M)}
check("15 explains every requirement", set(ids) <= set(r15_rows), str(sorted(set(ids) - set(r15_rows))))
check("15 rows have basis, alternative and proof (4 cells)", all(len(r.strip().strip("|").split("|")) == 4 and all(c.strip() for c in r.strip().strip("|").split("|")) for r in r15_rows.values()))
check("15 contains the slice tables from the script", lb.slice_count_table().strip() in R15 and lb.slice_first_out_table().strip() in R15)
check("15 contains the intra-refresh table from the script", lb.intra_refresh_table().strip() in R15)
check("slice count: N = 8 is the smallest integer meeting VID-007 at 1080p60 and 1080p120",
      all(lb.SENSOR_READOUT_MS[f] / 8 + lb.ENCODER_CORE_MS[f] <= b + 1e-9 and lb.SENSOR_READOUT_MS[f] / 7 + lb.ENCODER_CORE_MS[f] > b for f, b in ((60, 2.0), (120, 1.2))))
check("slice count: N = 1 costs 42 ms against N = 8, N = 4 costs 6 ms", abs(lb.SLICE_PROPORTIONAL_MS_AT_8 * 8 * (1 - 1 / 8) - 42.0) < 1e-9 and abs(48 * (1 / 4 - 1 / 8) - 6.0) < 1e-9)
check("slice count: reactive refresh at N = 8 is about 0.3% (VID-021)", abs(lb.slice_overhead(8)["refresh"] - 0.003) < 0.0002)
check("VID-002: 4K60 12 bit 5.97 Gbit/s, 7.46 with 25%, 3 lanes of 2.5", abs(3840 * 2160 * 60 * 12 / 1e9 - 5.97) < 0.005 and abs(3840 * 2160 * 60 * 12 * 1.25 / 1e9 - 7.46) < 0.005 and math.ceil(7.46 / 2.5) == 3)
check("VID-005: wave band 1920/60 = 32 px, overhead (4-1)/60 = 5%", 1920 / 60 == 32 and abs((4 - 1) / 60 - 0.05) < 1e-12)
check("no stray string-concatenation artefacts in the spec", all('""" + "' not in t and '" + """' not in t for t in TEXT.values()))

# ---- 12. notes entries 15, 17, 18 ------------------------------------------------------------------------------
check("15 contains the ladder, transition, mass, battery and hold-up tables", all(x().strip() in R15 for x in (lb.ladder_table, lb.transition_table, lb.mass_class_table, lb.battery_table, lb.holdup_table)))
check("ladder: L1 video rate meets the 10 Mbit/s of SYS-003, L2 rate is 4.9 Mbit/s", "| L1 |" in lb.ladder_table() and "11.9 |" in lb.ladder_table() and "4.9 |" in lb.ladder_table())
check("budgeted IDR meets 100 ms, normal IDRs do not", 1280 * 720 * 0.15 / 4.9e6 < 0.1 and 5 * 4.9e6 / 30 / 4.9e6 > 0.1)
check("SYS-004/006/007 text states the ladder, per-class mass and 1 h", all(k in SRS for k in ("quality ladder", "30 g in the 30 dBm class", "at least 1 h at the nominal consumption")))
check("1S pack gives 7.8 W for 1 h cold; 2S gives 15.5 W (PWR-010 limits 8 and 15)", abs(3 * 3.7 * 0.7 - 7.77) < 0.01 and 7.77 * 1.03 >= 8 - 0.3 and 2 * 3 * 3.7 * 0.7 >= 15)
check("hold-up: 5 ms at 11 W on a 12 V bus is 1.4 mF; at a 1S input 12.7 mF", abs(2 * 11 * 0.005 / (144 - 64) * 1000 - 1.375) < 0.01 and abs(2 * 11 * 0.005 / (4.2 ** 2 - 9) * 1000 - 12.7) < 0.05)
check("1S input current at 11 W, 90% efficiency, 3.0 V is 4.1 A", abs(11 / 0.9 / 3.0 - 4.07) < 0.01)
check("mass limits: 25 g at 27 dBm is inside the estimated range, 33 dBm needs more than 25 g", "| 27 dBm |" in lb.mass_class_table() and "| 33 dBm | 9.9 | 2.0 | 7.9 | 18.0 to 27.0 | 12 to 16 | 30 to 43 | 40 |" in lb.mass_class_table())
check("effort estimate is part of the specification (16)", "16-silicon-size-and-effort.md" in TEXT and "effort.md" not in TEXT)

import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("claim_register", ROOT / "scripts" / "claim_register.py")
_reg_before = TEXT["12-claim-audit-and-feasibility.md"]
_n_reqs = len(ids)
check("12 register lists every requirement", f"| total | {_n_reqs} |" in _reg_before, f"expected total {_n_reqs}")

print(f"{CHECKS} checks, {len(FAILS)} failed")
for f in FAILS:
    print("FAIL:", f)
sys.exit(1 if FAILS else 0)
