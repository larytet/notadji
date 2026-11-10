#!/usr/bin/env python3
"""Control-plane CPU workload estimate for the air unit (document 13).

Every row is rate x cycles-per-event under stated assumptions. The cycle counts are engineering ESTIMATES (E) to be replaced by
measured worst-case execution times on the target core (HSI-006); the point of the table is to size the real-time core and to show
which functions must be in hardware.

Usage: python3 -I scripts/cpu_budget.py     (prints the markdown tables used in spec/13)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    name: str
    rate_hz: float
    cycles: float
    note: str
    where: str = "RT core"

    @property
    def mcps(self) -> float:  # million cycles per second
        return self.rate_hz * self.cycles / 1e6


# 1080p120 worst case: 8 slices per frame
SLICES_PER_S = 8 * 120
DPD_SAMPLES = 4096
DPD_COEFFS = 15  # memory polynomial: nonlinearity order 5 x memory depth 3
CMAC_CYCLES = 8  # complex multiply-accumulate in software floating point on an M7/R5F-class core (E)
DPD_MATRIX_CYCLES = DPD_SAMPLES * DPD_COEFFS * DPD_COEFFS * CMAC_CYCLES
UART_BYTES_PER_S = 300_000  # 3 Mbaud
CHACHA_CYCLES_PER_BYTE = 4  # software ChaCha20-Poly1305 on a core without SIMD (E)
VIDEO_BYTES_PER_S = 10e6  # 80 Mbit/s peak

TASKS = [
    Task("Frame sequencer table update (1 ms frame)", 1000, 3000, "program TX/RX/PA/gain events for the next frame"),
    Task("Link adaptation (MCS, power, slice budget)", 1000, 2000, "one decision per feedback (MAC-004/005)"),
    Task("Per-slice rate-control retarget", SLICES_PER_S, 4000, "VID-006, 8 slices per frame at 120 fps"),
    Task("Feedback parsing (CSI, ACK bitmap)", 1000, 1500, "uplink slot every frame"),
    Task("AGC / RSSI / antenna diversity", 1000, 800, "ANT-006, per frame"),
    Task("VSWR and forward/reverse power loop", 1000, 1500, "ANT-001..003, CAL-006"),
    Task("Thermal and supply monitoring", 100, 3000, "THM-001, THM-005"),
    Task("Genlock display steering (ground unit) / FSIN alignment (air unit)", 1000, 1000, "VID-018, IF-002"),
    Task("TX/RX IQ and LO calibration, background", 5, 200_000, "CAL-002"),
    Task("DPD solve (Cholesky on the small normal matrix)", 10, 40_000, "CAL-005, 15 coefficients"),
    Task("MAVLink / MSP byte handling after DMA", UART_BYTES_PER_S, 50, "IF-001, MAC-007"),
    Task("Logging into the ring buffer", 1000, 1500, "SW-005"),
    Task("RTOS tick and interrupt overhead", 1000, 2600, "2000 tick + 600 interrupt entry/exit"),
]

OPTIONAL_SW = [
    Task("DPD correlation matrix formed in software", 10, DPD_MATRIX_CYCLES, "4096 samples x 15 x 15 complex MACs; put in a hardware accumulator instead", "avoid in CPU"),
    Task("Link encryption in software", VIDEO_BYTES_PER_S, CHACHA_CYCLES_PER_BYTE, "SEC-002; use the hardware block instead", "avoid in CPU"),
]


def totals() -> dict:
    base = sum(t.mcps for t in TASKS)
    return {"base": base, "with_dpd_sw": base + OPTIONAL_SW[0].mcps, "with_both_sw": base + OPTIONAL_SW[0].mcps + OPTIONAL_SW[1].mcps}


def tables() -> str:
    rows = ["| Function | Rate per s | Cycles per event | Mcycles/s | Basis |", "|---|---|---|---|---|"]
    for t in TASKS:
        rows.append(f"| {t.name} | {t.rate_hz:,.0f} | {t.cycles:,.0f} | {t.mcps:.1f} | {t.note} |")
    tot = totals()
    rows.append(f"| **Total, real-time core, hardware assist for DPD matrix and crypto** | | | **{tot['base']:.1f}** | |")
    rows += ["", "| Function kept out of the CPU | Rate per s | Cycles per event | Mcycles/s | Basis |", "|---|---|---|---|---|"]
    for t in OPTIONAL_SW:
        rows.append(f"| {t.name} | {t.rate_hz:,.0f} | {t.cycles:,.0f} | {t.mcps:.1f} | {t.note} |")
    rows += ["", "| Core clock MHz | Load, hardware assist | Load, DPD matrix in software | Load, DPD and crypto in software |", "|---|---|---|---|"]
    for mhz in (200, 300, 400, 600):
        rows.append(f"| {mhz} | {tot['base'] / mhz:.0%} | {tot['with_dpd_sw'] / mhz:.0%} | {tot['with_both_sw'] / mhz:.0%} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(tables())
