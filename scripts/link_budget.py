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


SPLIT_UL_BW_MHZ = 5.0
DL_DUTY_SPLIT = 0.95  # downlink share when the video band carries no uplink: 5% idle for frame-based-equipment rules and pilots


def split_band_uplink_table() -> str:
    """Split-band uplink: video band is downlink-only; feedback and telemetry on a narrowband channel in another band."""
    rows = ["| Class | Video band | Uplink band | Range km | GU TX dBm | Antennas dBi (GU/AU) | Margin QPSK 1/2 at 5 MHz dB | Same-band TDD margin dB | Video net rate Mbit/s (split / TDD) |",
            "|---|---|---|---|---|---|---|---|---|"]
    cases = [("S", 5800, 2400, 5, 5, 5), ("X", 5800, 2400, 10, 5, 5), ("L", 2400, 915, 14, 3, 3)]
    for name, vf, uf, d, g_gu, g_au in cases:
        tx = min(27.0, fcc_conducted_limit_dbm(g_gu))
        s = Scenario(name, uf, d, tx, g_gu, g_au, bw_mhz=SPLIT_UL_BW_MHZ)  # AU has one uplink receive chain: no MRC gain
        m = margin_db(s, UPLINK_QPSK_HALF)
        tdd = Scenario(name, vf, d, min(27.0, fcc_conducted_limit_dbm(10 if name == "X" else 5)), 10 if name == "X" else 5, 5, diversity_gain_db=3)
        m_tdd = margin_db(tdd, UPLINK_QPSK_HALF)
        rate_split = DATA_TONES[20.0] * MCS_TABLE[1].bits_per_sym / SYMBOL_US * DL_DUTY_SPLIT * 0.85
        rate_tdd = phy_rate_mbps(MCS_TABLE[1], 20, d)
        rows.append(f"| {name} | {vf / 1000:.1f} GHz | {uf / 1000:.3g} GHz | {d} | {tx:.0f} | {g_gu}/{g_au} | {m:.1f} | {m_tdd:.1f} | {rate_split:.1f} / {rate_tdd:.1f} |")
    return "\n".join(rows)


ETA_SAT = 0.55  # PA drain/power-added efficiency at saturation (E: GaAs/GaN/SiGe 5.8 GHz class AB, to be replaced by the PA study)
# Back-off from saturation needed to meet EVM and ACLR with DPD (E: ideal class-B scaling eta = eta_sat * sqrt(P/Psat); real PAs deviate)
BACKOFF_DB = {"OFDM 64QAM + DPD": 7.0, "OFDM QPSK/16QAM + DPD": 6.0, "DFT-s-OFDM QPSK + DPD": 4.5}
RADIO_OTHER_W = 1.5  # transceiver + baseband + memory (ASIC target, excluding PA and sensor)
REGULATOR_EFF = 0.88


def pae(backoff_db: float, eta_sat: float = ETA_SAT) -> float:
    return eta_sat * math.sqrt(10 ** (-backoff_db / 10))


def input_power_w(avg_dbm: float, backoff_db: float) -> float:
    return (10 ** (avg_dbm / 10) / 1000 / pae(backoff_db) + RADIO_OTHER_W) / REGULATOR_EFF


def pa_mode_table() -> str:
    rows = ["| Mode | Back-off dB | PAE | Input W at 25 dBm | at 27 dBm | at 30 dBm |", "|---|---|---|---|---|---|"]
    for name, bo in BACKOFF_DB.items():
        rows.append(f"| {name} | {bo:.1f} | {pae(bo):.1%} | {input_power_w(25, bo):.1f} | {input_power_w(27, bo):.1f} | {input_power_w(30, bo):.1f} |")
    return "\n".join(rows)


def numerology_table() -> str:
    """Doppler and delay-spread limits for three sub-carrier spacings (T-04). ICI SIR = 3 / (pi fd T)^2 (Jakes approximation)."""
    rows = ["| Spacing kHz | Symbol us | CP 1/16 us | CP 1/8 us | Max Doppler Hz for 21 dB SIR (64QAM) | for 28 dB SIR (256QAM) | Closing speed km/h at 5.8 GHz for 28 dB |", "|---|---|---|---|---|---|---|"]
    for khz in (39.0625, 78.125, 156.25):
        t_us = 1e3 / khz
        def fd_max(sir_db: float) -> float:
            return math.sqrt(3 * 10 ** (-sir_db / 10)) * khz * 1e3 / math.pi
        v_kmh = fd_max(28) * 3e8 / 5.8e9 * 3.6
        rows.append(f"| {khz:g} | {t_us:.1f} | {t_us / 16:.2f} | {t_us / 8:.2f} | {fd_max(21):.0f} | {fd_max(28):.0f} | {v_kmh:.0f} |")
    return "\n".join(rows)


LDPC_BASE_NONZERO = 90  # assumed non-zero entries of a 648-bit rate-1/2 quasi-cyclic base matrix (E)
LDPC_ITERATIONS = 10
LDPC_FCLK_MHZ = 200
LDPC_INFO_BITS = 324


def ldpc_estimate() -> str:
    """Layered min-sum decoder sized for peak PHY rate (T-16): one pass per base-matrix entry with the lifting size processed in parallel."""
    cycles = LDPC_BASE_NONZERO * LDPC_ITERATIONS
    t_us = cycles / LDPC_FCLK_MHZ
    thr = LDPC_INFO_BITS / t_us
    peak = DATA_TONES[40.0] * MCS_TABLE[3].bits_per_sym / SYMBOL_US  # 40 MHz 64QAM 3/4, no duty or overhead
    rows = ["| Quantity | Value |", "|---|---|",
            f"| Cycles per codeword ({LDPC_BASE_NONZERO} entries x {LDPC_ITERATIONS} iterations) | {cycles} |",
            f"| Time per codeword at {LDPC_FCLK_MHZ} MHz | {t_us:.1f} us |",
            f"| Throughput per decoder instance (K = {LDPC_INFO_BITS}) | {thr:.0f} Mbit/s |",
            f"| Peak PHY information rate (40 MHz, 64QAM 3/4) | {peak:.0f} Mbit/s |",
            f"| Decoder instances needed | {math.ceil(peak / thr)} |"]
    return "\n".join(rows)


NEIGHBOUR_EIRP_DBM = 35.0  # 30 dBm conducted + 5 dBi (Class S/X air unit)
NOISE_FLOOR_DBM = -97.0  # -101 dBm in 20 MHz + 4 dB noise figure
EDGE_I_MAX_DBM = NOISE_FLOOR_DBM - 6.0  # interference 6 dB below noise = about 1 dB desense for a victim at the edge of its range
SHORT_RANGE_SIGNAL_DBM = -62.0  # victim 500 m from its own pilot at 5.8 GHz, 34 dBm EIRP, 5 dBi receive
SHORT_RANGE_SIR_DB = 13.0  # QPSK 3/4 needs 7 dB SNR plus 6 dB


def separation_m(leak_dbc: float, i_max_dbm: float, f_mhz: float = 5800.0) -> float:
    """Distance at which a neighbour's leakage (EIRP minus leak_dbc) falls to i_max_dbm at the victim receiver (free space, 0 dBi receive)."""
    path_loss_needed = NEIGHBOUR_EIRP_DBM - leak_dbc - i_max_dbm
    return 1000 * 10 ** ((path_loss_needed - 32.44 - 20 * math.log10(f_mhz)) / 20)


def near_far_table() -> str:
    rows = ["| Neighbour ACLR dBc (in the victim channel) | Min separation, victim at edge of range (1 dB desense) m | Min separation, victim within 500 m (SIR 13 dB) m |", "|---|---|---|"]
    for aclr in (45, 50, 55, 60, 65):
        edge = separation_m(aclr, EDGE_I_MAX_DBM)
        short = separation_m(aclr, SHORT_RANGE_SIGNAL_DBM - SHORT_RANGE_SIR_DB)
        rows.append(f"| {aclr} | {edge:.0f} | {short:.0f} |")
    return "\n".join(rows)


def slice_protection_table() -> str:
    """What a slice-level packet error rate of 1e-3 (PHY-011) requires of the codeword error rate (T-07)."""
    rows = ["| Video | Slices per frame | Slice bits | Codewords per slice (648-bit, R 3/4, K 486) | Codeword error rate for slice PER 1e-3 |", "|---|---|---|---|---|"]
    for name, mbps, fps in (("1080p60, 20 Mbit/s", 20.0, 60), ("1080p120, 20 Mbit/s", 20.0, 120), ("1080p60, 10 Mbit/s", 10.0, 60)):
        slice_bits = mbps * 1e6 / fps / 8
        cw = math.ceil(slice_bits / 486)
        p_cw = 1 - (1 - 1e-3) ** (1 / cw)
        rows.append(f"| {name} | 8 | {slice_bits:,.0f} | {cw} | {p_cw:.1e} |")
    return "\n".join(rows)


INTRA_TO_INTER_BITS = 4.0  # intra-coded area costs about 4x the bits of inter-coded area (E, content dependent)


def intra_refresh_table() -> str:
    """Bit-rate overhead of a rolling intra-refresh wave versus its period (T-07), and the reactive alternative."""
    rows = ["| Refresh period (frames) | Time at 60 fps ms | Overhead (1/N x (r - 1), r = 4) |", "|---|---|---|"]
    for n in (8, 15, 30, 60):
        rows.append(f"| {n} | {n / 60 * 1000:.0f} | {(INTRA_TO_INTER_BITS - 1) / n:.0%} |")
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
    print()
    print(split_band_uplink_table())
    print()
    print(pa_mode_table())
    print()
    print(numerology_table())
    print()
    print(ldpc_estimate())
    print()
    print(near_far_table())
    print()
    print(slice_protection_table())
    print()
    print(intra_refresh_table())
