#!/usr/bin/env python3
"""Link budget calculator for notadji spec (document 02).

Usage: python3 scripts/link_budget.py
Prints markdown tables. All inputs are explicit so the spec numbers are reproducible.
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Mcs:
    name: str
    bits_per_sym: float  # modulation bits * code rate
    sens_20mhz_dbm: float  # RF-020 rev 0.2: -101 dBm + NF 4 dB + required SNR + 2 dB implementation loss


MCS_TABLE = [
    Mcs("BPSK 1/2", 0.5, -93.0),
    Mcs("QPSK 3/4", 1.5, -88.0),
    Mcs("16QAM 3/4", 3.0, -80.0),
    Mcs("64QAM 3/4", 4.5, -74.0),
]


@dataclass(frozen=True)
class Scenario:
    name: str
    freq_mhz: float
    dist_km: float
    tx_dbm: float
    tx_ant_dbi: float
    rx_ant_dbi: float
    cable_loss_db: float = 1.0
    diversity_gain_db: float = 0.0  # MRC gain on the ground unit
    bw_mhz: float = 20.0


def fspl_db(freq_mhz: float, dist_km: float) -> float:
    return 32.44 + 20 * math.log10(dist_km) + 20 * math.log10(freq_mhz)


def sens_dbm(mcs: Mcs, bw_mhz: float) -> float:
    return mcs.sens_20mhz_dbm + 10 * math.log10(bw_mhz / 20.0)


# Data tones per channel bandwidth at 78.125 kHz spacing (PHY-001): FFT 64 (5 MHz), 128 (10 MHz), 256 (20 MHz), 512 (40 MHz).
DATA_TONES = {5.0: 48, 10.0: 108, 20.0: 234, 40.0: 468}
SYMBOL_US = 13.6  # 12.8 us + 0.8 us guard interval (CP 1/16)
TURNAROUND_US = 10.0  # per DL/UL switch (RF-009 5 us switch + ramp and margin)
UL_PREAMBLE_SYMBOLS = 2  # frame-synchronous uplink burst: timing is known, so a short reference preamble is enough
UL_FEEDBACK_BITS = 100  # per frame: CSI summary + per-slice ACK bitmap (MAC-004)
UL_RATE_MBPS = 1.0  # MAC-007 uplink at QPSK 1/2
QPSK_HALF_BITS_PER_TONE = 1.0


def frame_ms_for_range(dist_km: float) -> float:
    """Range-adaptive super-frame length (T-03 option C): 1 ms up to 7 km, 2 ms up to 15 km, 4 ms beyond."""
    return 1.0 if dist_km <= 7 else 2.0 if dist_km <= 15 else 4.0


def tdd_budget(frame_ms: float, dist_km: float, bw_mhz: float = 20.0) -> dict:
    """Uplink slot sized for MAC-007, guard from propagation delay (MAC-001); returns shares of the frame."""
    tones = DATA_TONES[bw_mhz]
    data_syms = math.ceil((UL_RATE_MBPS * 1e6 * frame_ms / 1000 + UL_FEEDBACK_BITS) / (tones * QPSK_HALF_BITS_PER_TONE))
    ul_syms = data_syms + UL_PREAMBLE_SYMBOLS
    ul_us = ul_syms * SYMBOL_US
    guard_us = 2 * dist_km * 3.33 + 2 * TURNAROUND_US
    frame_us = frame_ms * 1000
    return {"ul_symbols": ul_syms, "ul_us": ul_us, "guard_us": guard_us, "dl_share": 1 - (ul_us + guard_us) / frame_us}


def dl_duty(dist_km: float, bw_mhz: float = 20.0) -> float:
    return tdd_budget(frame_ms_for_range(dist_km), dist_km, bw_mhz)["dl_share"]


def phy_rate_mbps(mcs: Mcs, bw_mhz: float, dist_km: float, overhead: float = 0.85) -> float:
    """Approximate net downlink rate with the range-dependent TDD frame."""
    return DATA_TONES[bw_mhz] * mcs.bits_per_sym / SYMBOL_US * dl_duty(dist_km, bw_mhz) * overhead


UPLINK_QPSK_HALF = Mcs("QPSK 1/2", 1.0, -90.0)  # -101 + 4 + 5 dB SNR + 2 dB implementation loss


def max_range_km(s: Scenario, mcs: Mcs, margin: float = 6.0) -> float:
    """Free-space range at which the margin for this MCS falls to `margin` dB."""
    path_loss = (s.tx_dbm - s.cable_loss_db + s.tx_ant_dbi + s.rx_ant_dbi - s.cable_loss_db
                 + s.diversity_gain_db - sens_dbm(mcs, s.bw_mhz) - margin)
    return 10 ** ((path_loss - 32.44 - 20 * math.log10(s.freq_mhz)) / 20)


def fcc_conducted_limit_dbm(ant_gain_dbi: float, cap_dbm: float = 30.0) -> float:
    """FCC 15.247 general rule: reduce conducted power dB for dB above 6 dBi (point-to-multipoint/mobile)."""
    return cap_dbm - max(0.0, ant_gain_dbi - 6.0)


def margin_db(s: Scenario, mcs: Mcs) -> float:
    rx = s.tx_dbm - s.cable_loss_db + s.tx_ant_dbi - fspl_db(s.freq_mhz, s.dist_km) + s.rx_ant_dbi - s.cable_loss_db
    return rx + s.diversity_gain_db - sens_dbm(mcs, s.bw_mhz)


SCENARIOS = [
    Scenario("5.8 GHz, 10 km, 5/5 dBi, 20 MHz", 5800, 10, 30, 5, 5),
    Scenario("5.8 GHz, 10 km, 5/5 dBi, 2-branch MRC, 20 MHz", 5800, 10, 30, 5, 5, diversity_gain_db=3),
    Scenario("5.8 GHz, 10 km, 5/10 dBi patch, MRC, 20 MHz", 5800, 10, 30, 5, 10, diversity_gain_db=3),
    Scenario("5.8 GHz, 10 km, 5/10 dBi patch, MRC, 10 MHz", 5800, 10, 30, 5, 10, diversity_gain_db=3, bw_mhz=10),
    Scenario("2.4 GHz, 15 km, 5/5 dBi, 20 MHz", 2400, 15, 30, 5, 5),
    Scenario("2.4 GHz, 15 km, 5/5 dBi, MRC, 10 MHz", 2400, 15, 30, 5, 5, diversity_gain_db=3, bw_mhz=10),
    Scenario("915 MHz, 30 km, 3/8 dBi, MRC, 5 MHz", 915, 30, 30, 3, 8, diversity_gain_db=3, bw_mhz=5),
]


def main() -> None:
    print("| Scenario | FSPL dB | Best MCS with >= 6 dB margin | Net rate Mbit/s | Margin at BPSK 1/2 dB |")
    print("|---|---|---|---|---|")
    for s in SCENARIOS:
        best = None
        for m in MCS_TABLE:
            if margin_db(s, m) >= 6.0:
                best = m
        rate = f"{phy_rate_mbps(best, s.bw_mhz, s.dist_km):.1f}" if best else "-"
        label = best.name if best else "none (fails SYS-003)"
        print(f"| {s.name} | {fspl_db(s.freq_mhz, s.dist_km):.1f} | {label} | {rate} | {margin_db(s, MCS_TABLE[0]):.1f} |")


def uplink_table() -> str:
    """Uplink (ground unit transmits, air unit receives with 2-branch MRC, 5 dBi)."""
    rows = ["| Class | GU antenna dBi | GU conducted dBm (FCC rule) | Range km | Margin at QPSK 1/2 dB | Margin at BPSK 1/2 dB | Max range for QPSK 1/2 at 6 dB km |", "|---|---|---|---|---|---|---|"]
    for name, f, d, gu_ant in [("S", 5800, 5, 5), ("X", 5800, 10, 10), ("L", 2400, 14, 5)]:
        tx = min(27.0, fcc_conducted_limit_dbm(gu_ant))
        s = Scenario(name, f, d, tx, gu_ant, 5, diversity_gain_db=3)
        rows.append(f"| {name} | {gu_ant} | {tx:.0f} | {d} | {margin_db(s, UPLINK_QPSK_HALF):.1f} | {margin_db(s, MCS_TABLE[0]):.1f} | {max_range_km(s, UPLINK_QPSK_HALF):.1f} |")
    return "\n".join(rows)


def tdd_table() -> str:
    """TDD frame budget per range class with the range-adaptive frame length (T-03 option C)."""
    rows = ["| Range km | Frame ms | UL symbols (QPSK 1/2, 1 Mbit/s + 2 preamble) | UL us | Guard us | DL share of frame |", "|---|---|---|---|---|---|"]
    for d in (5, 7, 10, 15, 30):
        fm = frame_ms_for_range(d)
        t = tdd_budget(fm, d)
        rows.append(f"| {d} | {fm:.0f} | {t['ul_symbols']} | {t['ul_us']:.0f} | {t['guard_us']:.0f} | {t['dl_share']:.3f} |")
    return "\n".join(rows)


def tdd_compare_table() -> str:
    """Downlink share for fixed 1 ms, fixed 2 ms and adaptive frames (T-03 options A, B, C)."""
    rows = ["| Range km | A: fixed 1 ms | B: fixed 2 ms | C: adaptive |", "|---|---|---|---|"]
    for d in (5, 10, 15, 30):
        a = tdd_budget(1.0, d)["dl_share"]
        b = tdd_budget(2.0, d)["dl_share"]
        c = tdd_budget(frame_ms_for_range(d), d)["dl_share"]
        rows.append(f"| {d} | {a:.3f} | {b:.3f} | {c:.3f} |")
    return "\n".join(rows)


if __name__ == "__main__":
    main()
    print()
    print(uplink_table())
    print()
    print(tdd_table())
    print()
    print(tdd_compare_table())
