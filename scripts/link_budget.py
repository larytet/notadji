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


def phy_rate_mbps(mcs: Mcs, bw_mhz: float, duty: float = 0.9, overhead: float = 0.85) -> float:
    """Approximate net rate: 242 data sub-carriers per 20 MHz, 13.6 us symbol (12.8 + 0.8 GI)."""
    sc = 242 * bw_mhz / 20.0
    sym_us = 13.6
    return sc * mcs.bits_per_sym / sym_us * duty * overhead


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
        rate = f"{phy_rate_mbps(best, s.bw_mhz):.1f}" if best else "-"
        label = best.name if best else "none (fails SYS-003)"
        print(f"| {s.name} | {fspl_db(s.freq_mhz, s.dist_km):.1f} | {label} | {rate} | {margin_db(s, MCS_TABLE[0]):.1f} |")


if __name__ == "__main__":
    main()
