#!/usr/bin/env python3
"""Role assignment of requirements: air unit only, ground unit only, everything else common (notes.md entry 5).

The SRS carries the role as a tag at the start of the requirement text: "[AU] ..." or "[GU] ...". Untagged means common to both units.
This file is the single source for the tags; `python3 -I scripts/roles.py` applies them (idempotent) and the audit checks that the SRS agrees.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRS = ROOT / "spec" / "01-system-requirements.md"

AU_ONLY = {
    "SYS-005", "SYS-006",                                   # air unit power and mass
    "VID-001", "VID-002", "VID-005", "VID-006", "VID-007",  # sensor, encoder
    "VID-013", "VID-014", "VID-020", "VID-021", "VID-022", "VID-026",
    "IF-001", "IF-002",                                     # flight controller and camera interfaces
    "REG-002",                                              # Remote ID module
    "PWR-001", "PWR-005", "PWR-006",                        # battery input, standby, sleep
    "THM-004", "ENV-002", "ENV-003",                        # hover thermal, vibration, shock
    "RF-030", "ANT-014",                                    # TX-to-RX isolation of the air unit in split-band mode, air-unit beamforming
}
GU_ONLY = {
    "SYS-007", "SYS-008",                                   # ground battery life, several air units
    "VID-008", "VID-015", "VID-016", "VID-018",             # decoder, display output, OSD, display lock
    "PHY-006", "PHY-016", "PHY-017",                        # receive branches, enhanced decoding
    "ANT-007", "ANT-008", "ANT-009", "ANT-010", "ANT-011", "ANT-012", "ANT-013", "CAL-010",
    "ADA-001", "ADA-002", "ADA-007", "ADA-010", "ADA-011",  # the ground unit scans and decides
    "MAC-011",                                              # timing advance estimated at the ground unit
    "IF-003", "RF-032", "PWR-007", "PWR-008", "PWR-009", "PWR-010",                                     # display and host interfaces, enhanced front end
}
TAGS = {rid: "[AU]" for rid in AU_ONLY} | {rid: "[GU]" for rid in GU_ONLY}


def role_of_text(cell: str) -> str:
    m = re.match(r"\[(AU|GU)\] ", cell)
    return m.group(1) if m else "common"


def apply() -> int:
    lines = SRS.read_text().split("\n")
    seen = set()
    for i, line in enumerate(lines):
        m = re.match(r"\| ([A-Z]{2,4}-\d{3}) \| (.*)$", line)
        if not m:
            continue
        rid, rest = m.group(1), m.group(2)
        rest = re.sub(r"^\[(AU|GU)\] ", "", rest)
        if rid in TAGS:
            rest = TAGS[rid] + " " + rest
            seen.add(rid)
        lines[i] = f"| {rid} | {rest}"
    missing = set(TAGS) - seen
    if missing:
        print("tagged IDs not found in the SRS:", sorted(missing), file=sys.stderr)
        return 1
    SRS.write_text("\n".join(lines))
    print(f"roles applied: {len(AU_ONLY)} AU-only, {len(GU_ONLY)} GU-only")
    return 0


if __name__ == "__main__":
    sys.exit(apply())
