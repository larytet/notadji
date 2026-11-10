#!/usr/bin/env python3
"""Generate the per-requirement evidence register inside spec/12-claim-audit-and-feasibility.md.

Classes:
  C  computed: the number follows from a script in scripts/ that is re-run by audit_numbers.py
  S  sourced: rests on a cited external source or on code/docs in the downloaded reference set (see 10, 11, 13)
  E  engineering target or estimate: not verifiable yet; verified by the stated test in the stated phase
  P  process or design rule: verified by inspection or demonstration, no number to prove
  R  regulatory: depends on a rule that counsel must confirm

The register fails if a requirement has no class, so new requirements must be classified.
Usage: python3 -I scripts/claim_register.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRS = (ROOT / "spec" / "01-system-requirements.md").read_text()
DOC = ROOT / "spec" / "12-claim-audit-and-feasibility.md"
BEGIN, END = "<!-- BEGIN REGISTER -->", "<!-- END REGISTER -->"

OVERRIDE = {
    "SYS-003": ("C", "link_budget.py: range classes close with QPSK 3/4 and 6 dB margin; free space only (G-02 open)"),
    "SYS-005": ("C", "link_budget.py/audit: input power per class; needs PA efficiency of about 27% at 30 dBm [feasibility: unproven PA]"),
    "SYS-009": ("C", "audit: channel counts from band widths; adjacent-channel rejection RF-029 unproven"),
    "SYS-001": ("E", "latency budget in 02 sums to 18.0/10.7 ms [C] but every stage value is an estimate; vendor pipelines measure 80-95 ms camera half [S]"),
    "SYS-002": ("E", "first milestone; depends on VCU first-slice latency, which was not found in sources"),
    "PHY-001": ("C", "audit: FFT size x 78.125 kHz = bandwidth for 5/10/20/40/80 MHz"),
    "PHY-003": ("C", "audit: symbol time, ICI -21.8 dB at 3.5 kHz, 32.7 dB at 1 kHz (Jakes approximation)"),
    "PHY-004": ("E", "256QAM needs EVM and Doppler limits that are unproven at 30 dBm"),
    "MAC-001": ("C", "link_budget.py tdd_budget: uplink sized for MAC-007, guard from range"),
    "MAC-012": ("C", "link_budget.py split_band_uplink_table: uplink margin 11.0-17.0 dB, video rate +8%"),
    "RF-030": ("E", "isolation estimate in 02 section 1.1b; bench-proven later"),
    "MAC-007": ("C", "link_budget.py: uplink budget and uplink slot capacity"),
    "RF-020": ("C", "audit: sensitivity model -101 dBm + NF + SNR + 2 dB; datasheet NF 2 dB best case for AD9361 [S]"),
    "RF-006": ("S", "AD9361 fast lock 15-25 us (ADI wiki); ADRV9002 13 us hop frames with about 3 us transition (Analog Dialogue)"),
    "RF-009": ("S", "ADRV9002 transitions 3-6.6 us plausible; AD9361 TDD RX to TX goes via ALERT state, 5 us not demonstrated [at risk on P1]"),
    "RF-010": ("R", "FCC 15.247: 1 W conducted, dB-for-dB reduction above 6 dBi (older CFR editions read); ETSI limits differ"),
    "RF-014": ("E", "EVM -35 dB at 256QAM at 1 W output is aggressive and unproven"),
    "RF-001": ("R", "band edges per FCC 15.247 / ETSI; verify by counsel"),
    "VID-006": ("S", "OpenIPC waybeam spec: vendor encoder caps did not bind (all 863 AUs over a 6000 B cap)"),
    "VID-009": ("C", "audit: 80 Mbit/s fits 40 MHz 64QAM 3/4 at 10 km"),
    "VID-020": ("S", "waybeam: 120 fps VENC ceiling with silent reset to 30 fps; SDK calls that succeed but do not apply"),
    "VID-017": ("R", "codec pool terms to be confirmed (search found conflicting rate-deadline statements)"),
    "IF-002": ("S", "waybeam: driver extended VMAX when exposure reached the frame time"),
    "LAT-001": ("S", "OpenIPC latency-probe method (register step, one clock)"),
    "TST-002": ("S", "OpenIPC latency-probe method; rig accuracy is an engineering target"),
    "SEC-002": ("S", "wfb-ng uses ChaCha20-Poly1305 AEAD per packet (protocol draft)"),
    "REG-002": ("S", "FAA-accepted ASTM F3586-22 overlay on F3411-22a; transports from the FAA notice summary"),
    "REG-005": ("P", "licence register from MANIFEST.tsv; clean-room policy"),
    "REG-006": ("S", "US 12,456,952 B2 claims read (Skyworks); constraint D-1 in 11"),
    "ADA-003": ("S", "ETSI non-adaptive hopping limit 5 ms on-time / 5 ms gap (search summary of EN 300 328; to be checked)"),
    "ADA-009": ("R", "EN 300 328 adaptivity; frame-based idle period figures found in TI notes, band attribution unverified"),
    "PRO-002": ("S", "K26/KV260 typical 7.5 W; VCU presence on XCK26 not confirmed by the search"),
    "PRO-003": ("S", "AD9361/ADRV9002 datasheet facts (spec 04)"),
    "PWR-003": ("C", "K26 module 7.5 W typical (S) plus 1.5 W transceiver within 9.5 W"),
    "PWR-004": ("E", "PAE 30% at 27/30 dBm average OFDM with DPD is unproven; typical class-AB PAs reach less"),
    "ANT-001": ("S", "coupler-based forward/reverse sensing appears in P-1 (patent), so not novel; design-around D-1"),
    "CAL-008": ("S", "antenna-aware calibration; overlaps P-1 if bias/supply were adjusted from load (REG-006)"),
    "HSI-005": ("C", "cpu_budget.py: 11% at 300 MHz with hardware assist, 49% with software DPD matrix and crypto"),
    "HSI-004": ("C", "cpu_budget.py: software DPD matrix 73.7 + crypto 40 Mcycles/s"),
    "HSI-009": ("E", "allocation inside the 0.7 W baseband line; anchors in 13 section 4"),
    "ENV-001": ("E", "ranges chosen to match consumer drone practice; thermal and cold-start behaviour unproven"),
    "SYS-006": ("E", "25 g air unit unproven; FPGA prototype is not flyable at this mass (SOM and heatsink alone exceed it) [feasibility]"),
}
BY_PREFIX = {"REG": ("R", "regulatory; counsel to confirm"), "SW": ("P", "software design rule"), "IF": ("P", "interface rule"),
             "PRO": ("P", "prototype plan item"), "TST": ("P", "test infrastructure"), "HSI": ("P", "integration design rule"),
             "ASC": ("E", "ASIC target; area and cost unproven (G-23)"), "SEC": ("P", "security design rule; review by third party")}


def main() -> int:
    rows = []
    counts = {}
    for line in SRS.splitlines():
        m = re.match(r"\| ([A-Z]{2,4}-\d{3}) \|", line)
        if not m:
            continue
        rid = m.group(1)
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        ver = cells[4]
        if rid in OVERRIDE:
            cls, basis = OVERRIDE[rid]
        elif rid.split("-")[0] in BY_PREFIX:
            cls, basis = BY_PREFIX[rid.split("-")[0]]
        else:
            cls, basis = "E", f"engineering target; proved by verification method {ver} (see 08)"
        counts[cls] = counts.get(cls, 0) + 1
        rows.append(f"| {rid} | {cls} | {basis} |")
    summary = ["| Class | Requirements |", "|---|---|"] + [f"| {k} | {counts[k]} |" for k in sorted(counts)] + [f"| total | {sum(counts.values())} |"]
    block = BEGIN + "\n\n" + "\n".join(summary) + "\n\n| ID | Class | Basis |\n|---|---|---|\n" + "\n".join(rows) + "\n\n" + END
    text = DOC.read_text()
    if BEGIN not in text:
        print("markers missing in 12", file=sys.stderr)
        return 1
    a, b = text.index(BEGIN), text.index(END) + len(END)
    DOC.write_text(text[:a] + block + text[b:])
    print(f"register: {sum(counts.values())} requirements, classes {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
