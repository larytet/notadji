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


GU_TX_CAPABILITY_DBM = 27.0  # ground-unit transmit capability (E: battery-powered PA class); regional limits are profiles, not design drivers


def uplink_table() -> str:
    """Uplink (ground unit transmits, air unit receives with 2-branch MRC, 5 dBi). Capability first, then the FCC-type profile for comparison."""
    rows = ["| Class | GU antenna dBi | GU TX dBm (capability) | Range km | Margin at QPSK 1/2 dB | Margin at BPSK 1/2 dB | Max range for QPSK 1/2 at 6 dB km | Same, FCC-type profile (conducted power cut above 6 dBi) km |", "|---|---|---|---|---|---|---|---|"]
    for name, f, d, gu_ant in [("S", 5800, 5, 5), ("X", 5800, 10, 10), ("L", 2400, 14, 5)]:
        tx = GU_TX_CAPABILITY_DBM
        s = Scenario(name, f, d, tx, gu_ant, 5, diversity_gain_db=3)
        s_fcc = Scenario(name, f, d, min(tx, fcc_conducted_limit_dbm(gu_ant)), gu_ant, 5, diversity_gain_db=3)
        rows.append(f"| {name} | {gu_ant} | {tx:.0f} | {d} | {margin_db(s, UPLINK_QPSK_HALF):.1f} | {margin_db(s, MCS_TABLE[0]):.1f} | {max_range_km(s, UPLINK_QPSK_HALF):.1f} | {max_range_km(s_fcc, UPLINK_QPSK_HALF):.1f} |")
    return "\n".join(rows)


SPLIT_UL_BW_MHZ = 5.0
DL_DUTY_SPLIT = 0.95  # downlink share when the video band carries no uplink: 5% idle for frame-based-equipment rules and pilots


def split_band_uplink_table() -> str:
    """Split-band uplink: video band is downlink-only; feedback and telemetry on a narrowband channel in another band."""
    rows = ["| Class | Video band | Uplink band | Range km | GU TX dBm | Antennas dBi (GU/AU) | Margin QPSK 1/2 at 5 MHz dB | Same-band TDD margin dB | Video net rate Mbit/s (split / TDD) |",
            "|---|---|---|---|---|---|---|---|---|"]
    cases = [("S", 5800, 2400, 5, 5, 5), ("X", 5800, 2400, 10, 5, 5), ("L", 2400, 915, 14, 3, 3)]
    for name, vf, uf, d, g_gu, g_au in cases:
        tx = GU_TX_CAPABILITY_DBM
        s = Scenario(name, uf, d, tx, g_gu, g_au, bw_mhz=SPLIT_UL_BW_MHZ)  # AU has one uplink receive chain: no MRC gain
        m = margin_db(s, UPLINK_QPSK_HALF)
        tdd = Scenario(name, vf, d, GU_TX_CAPABILITY_DBM, 10 if name == "X" else 5, 5, diversity_gain_db=3)
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


def sector_gain_dbi(sectors: int, elevation_deg: float, eta: float = 0.6) -> float:
    """Directivity of one beam of a switched-sector array: eta x 41253 / (azimuth x elevation beamwidth in degrees^2) (E: patch-array efficiency 0.6)."""
    return 10 * math.log10(eta * 41253 / ((360 / sectors) * elevation_deg))


def sector_table() -> str:
    rows = ["| Sectors | Azimuth beamwidth | Gain dBi, elevation 60 deg | 40 deg | 30 deg |", "|---|---|---|---|---|"]
    for n in (4, 6, 8, 12):
        rows.append(f"| {n} | {360 // n} deg | {sector_gain_dbi(n, 60):.1f} | {sector_gain_dbi(n, 40):.1f} | {sector_gain_dbi(n, 30):.1f} |")
    return "\n".join(rows)


def genlock_table() -> str:
    """Latency drift between sensor frame clock and display clock for a given combined frequency error (T-17)."""
    rows = ["| Case | Combined error ppm | Drift per minute ms | Drift per 10 min ms | Time to slip one 60 fps frame min |", "|---|---|---|---|---|"]
    for name, ppm in (("Both ends on 20 ppm crystals", 40.0), ("Both ends on 2 ppm TCXOs (RF-007)", 4.0), ("Display steered to the received frame timing (residual 1 ppm)", 1.0)):
        per_min = ppm * 1e-6 * 60 * 1000
        slip_min = (1000 / 60) / (ppm * 1e-6 * 1000) / 60
        rows.append(f"| {name} | {ppm:g} | {per_min:.2f} | {per_min * 10:.1f} | {slip_min:.0f} |")
    return "\n".join(rows)


def hop_overhead_table() -> str:
    """Airtime lost to retuning for a hopped channel (T-15): settle time divided by dwell."""
    rows = ["| Dwell ms | Overhead at 50 us settle | at 150 us (cross-band) |", "|---|---|---|"]
    for dwell in (1.0, 2.0, 5.0, 10.0):
        rows.append(f"| {dwell:g} | {50e-3 / dwell:.1%} | {150e-3 / dwell:.1%} |")
    return "\n".join(rows)


def interface_table() -> str:
    """Inter-die sample interface between the RF die and the digital die (T-08): 12-bit I/Q samples."""
    rows = ["| Mode | Sample rate MSPS | Chains crossing the interface | Bit rate Gbit/s | Power both ends at 5 / 10 / 20 pJ/bit mW |", "|---|---|---|---|---|"]
    for name, msps, chains in (("40 MHz, air unit (1 Tx + 1 Rx)", 61.44, 2), ("40 MHz, ground unit (2 Rx + 1 Tx)", 61.44, 3), ("20 MHz, ground unit (2 Rx + 1 Tx)", 30.72, 3), ("40 MHz, enhanced ground unit (8 Rx + 1 Tx)", 61.44, 9)):
        gbps = msps * 1e6 * 2 * 12 * chains / 1e9
        p5, p10, p20 = (gbps * 1e9 * pj * 1e-12 * 2 * 1e3 for pj in (5, 10, 20))
        rows.append(f"| {name} | {msps} | {chains} | {gbps:.2f} | {p5:.0f} / {p10:.0f} / {p20:.0f} |")
    obs_bits = 4096 * 2 * 12
    rows.append(f"| DPD observation capture kept on the RF die ({obs_bits / 1e3:.0f} kbit per capture) | burst | 0 (read out slowly) | 0 | 0 |")
    return "\n".join(rows)


def range_vs_mcs_table() -> str:
    """Free-space range at 6 dB margin and net video-band rate per MCS (split-band mode, 20 MHz, 30 dBm, 5/5 dBi, 2-branch MRC) (T-01)."""
    rows = ["| MCS | Net rate Mbit/s | Range km at 5.8 GHz | Range km at 2.4 GHz |", "|---|---|---|---|"]
    for m in MCS_TABLE:
        rate = DATA_TONES[20.0] * m.bits_per_sym / SYMBOL_US * DL_DUTY_SPLIT * 0.85
        r58 = max_range_km(Scenario("x", 5800, 1, 30, 5, 5, diversity_gain_db=3), m)
        r24 = max_range_km(Scenario("x", 2400, 1, 30, 5, 5, diversity_gain_db=3), m)
        rows.append(f"| {m.name} | {rate:.1f} | {r58:.1f} | {r24:.1f} |")
    return "\n".join(rows)


def region_range_table() -> str:
    """Downlink range as a derived column per region profile (illustrative EIRP caps; real profiles are data, REG-008).
    Air unit 5 dBi, 1 dB cable loss, conducted power at most 30 dBm, ground 2-branch MRC, 20 MHz, 6 dB margin, free space."""
    rows = ["| Profile (EIRP cap at the air unit) | AU conducted dBm | 5.8 GHz QPSK 3/4 km | 5.8 GHz BPSK 1/2 km | 2.4 GHz QPSK 3/4 km | 2.4 GHz BPSK 1/2 km |", "|---|---|---|---|---|---|"]
    for name, cap in (("Capability (no regional limit)", None), ("EIRP cap 36 dBm (FCC-type 6 dBi antenna case)", 36.0), ("EIRP cap 25 dBm (illustrative)", 25.0), ("EIRP cap 20 dBm (ETSI-type 2.4 GHz case)", 20.0), ("EIRP cap 14 dBm (illustrative)", 14.0)):
        tx = 30.0 if cap is None else min(30.0, cap - 5 + 1)
        vals = []
        for f in (5800, 2400):
            for m in (MCS_TABLE[1], MCS_TABLE[0]):
                vals.append(max_range_km(Scenario("x", f, 1, tx, 5, 5, diversity_gain_db=3), m))
        rows.append(f"| {name} | {tx:.0f} | " + " | ".join(f"{v:.1f}" for v in (vals[0], vals[1], vals[2], vals[3])) + " |")
    return "\n".join(rows)


def ground_levers_table() -> str:
    """Ground-unit receive levers (notes entries 5 and 6): branch count (ideal MRC, 10 log N), noise figure, antenna gain.
    Downlink range at 6 dB margin, 20 MHz, 30 dBm, air unit 5 dBi, free space. Correlation loss between branches (about 0.5 to 1.5 dB [E]) is not included."""
    rows = ["| Ground configuration | Branches | NF dB | Ground antenna dBi | Gain over baseline dB | 5.8 GHz QPSK 3/4 km | 5.8 GHz BPSK 1/2 km | 2.4 GHz BPSK 1/2 km |", "|---|---|---|---|---|---|---|---|"]
    base_gain = 3.0 * math.log2(2)
    cfgs = [("Baseline: 2 branches, NF 4 dB", 2, 4.0, 5.0), ("4 branches, NF 4 dB", 4, 4.0, 5.0), ("4 branches, NF 2.5 dB", 4, 2.5, 5.0),
            ("8 branches, NF 2 dB", 8, 2.0, 5.0), ("8 branches, NF 2 dB, 10 dBi antenna", 8, 2.0, 10.0)]
    for name, n, nf, ant in cfgs:
        div = 3.0 * math.log2(n) + (4.0 - nf)  # about 3 dB per doubling of branches (ideal MRC)
        gain = div + (ant - 5.0) - base_gain
        r = lambda f, m: max_range_km(Scenario("x", f, 1, 30, 5, ant, diversity_gain_db=div), m)
        rows.append(f"| {name} | {n} | {nf:g} | {ant:g} | {gain:+.1f} | {r(5800, MCS_TABLE[1]):.1f} | {r(5800, MCS_TABLE[0]):.1f} | {r(2400, MCS_TABLE[0]):.1f} |")
    return "\n".join(rows)


COAX_LOSS_DB_PER_M = {5800: 0.41, 2400: 0.22}  # low-loss coax (E, to be verified against a datasheet)
VELOCITY_FACTOR = 0.8  # coax velocity factor (E)


def _db_to_lin(x: float) -> float:
    return 10 ** (x / 10)


def coax_table() -> str:
    """External antenna on coax (notes entry 7): system noise figure with a passive cable versus an LNA at the antenna (Friis), and the extra delay against the cyclic prefix."""
    nf_rx, nf_lna, g_lna = 4.0, 1.5, 20.0
    rows = ["| Cable m | Loss at 5.8 GHz dB | System NF passive cable dB | System NF with LNA at the antenna dB | Sensitivity penalty passive / with LNA dB | Extra delay ns (cable + 20 m geometry) |", "|---|---|---|---|---|---|"]
    for length in (1, 2, 5, 10, 20):
        loss = COAX_LOSS_DB_PER_M[5800] * length
        nf_passive = loss + nf_rx
        f_sys = _db_to_lin(nf_lna) + (_db_to_lin(loss) - 1) / _db_to_lin(g_lna) + (_db_to_lin(nf_rx) - 1) / (_db_to_lin(g_lna) / _db_to_lin(loss))
        nf_lna_sys = 10 * math.log10(f_sys)
        delay_ns = length / (3e8 * VELOCITY_FACTOR) * 1e9 + 20 / 3e8 * 1e9
        rows.append(f"| {length} | {loss:.1f} | {nf_passive:.1f} | {nf_lna_sys:.1f} | {nf_passive - nf_rx:+.1f} / {nf_lna_sys - nf_rx:+.1f} | {delay_ns:.0f} |")
    return "\n".join(rows)


def tapeout_breakeven_table() -> str:
    """Break-even volume of a second tape-out for separate air and ground chips (T-22). Inputs from spec/effort.md [E]."""
    mask_musd, usd_per_py_m, saving_usd_per_unit = 3.0, 0.15, 0.5
    rows = ["| Second tape-out effort PY | Cost MUSD (masks 3 + labour at 0.15 MUSD/PY) | Saving per unit USD (about 5 mm2, 15%) | Break-even volume million units |", "|---|---|---|---|"]
    for py in (50, 60):
        cost = mask_musd + py * usd_per_py_m
        rows.append(f"| {py} | {cost:.1f} | {saving_usd_per_unit:.1f} | {cost / saving_usd_per_unit:.0f} |")
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
    print()
    print(sector_table())
    print()
    print(genlock_table())
    print()
    print(hop_overhead_table())
    print()
    print(interface_table())
    print()
    print(range_vs_mcs_table())
    print()
    print(region_range_table())
    print()
    print(ground_levers_table())
    print()
    print(coax_table())
    print()
    print(tapeout_breakeven_table())
