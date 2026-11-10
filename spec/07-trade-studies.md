# 07 - Trade Studies

Status: DRAFT, pass 4. Every open decision from `06` has two or three options with pros and cons and a
recommendation. Recommendations are proposals for the system team to confirm, not decisions. Numbers marked
[calc] come from `scripts/link_budget.py` and the pass-4 range calculation (QPSK 3/4, 6 dB margin, 2-branch MRC,
30 dBm unless stated, free space).

Index: T-01 range closure, T-02 power classes, T-03 TDD frame and guard, T-04 numerology, T-05 co-located links,
T-06 codec, T-07 loss protection, T-08 ASIC partitioning, T-09 open vs locked RF, T-10 BLE/Remote ID,
T-11 P1 baseband base, T-12 P1 transceiver, T-13 antenna/diversity, T-14 DPD architecture, T-15 hopping,
T-16 FEC code, T-17 clock and genlock.

---

## T-01 Range closure at 5.8 GHz (G-01, G-02, G-04)

Range for QPSK 3/4 20 MHz at 6 dB margin [calc]: 5.8 km with 5/5 dBi antennas; 10.3 km with a 10 dBi ground antenna;
16.4 km with 14 dBi; 8.2 km at 10 MHz with 5/5 dBi; 8.2 km with a 33 dBm PA; 10.3 km if the video drops to BPSK 1/2.
At 2.4 GHz with 5/5 dBi: 14.1 km. With an EIRP cap of 20 dBm at 2.4 GHz (an ETSI-type profile): about 2.8 km (`02` section 1.2).

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Require a 10 dBi or better ground antenna for the 10 km class | +5 dB at no power cost; works with any bandwidth; cheap (patch or helical) | Beamwidth about 60 degrees; needs pointing, a tracker or a switched-beam array (ANT-008); not goggle-mounted |
| B | Reduce the channel bandwidth to 10 MHz for long range | +3 dB; halves the number of channels needed (T-05); fits narrower regional bands | Net rate about 8 Mbit/s at 10 km (`02`), below the 10 Mbit/s of SYS-003, so it is a fallback or race mode, not a range class; quality loss at 1080p60 |
| C | Raise the PA to 33 dBm | +3 dB with a drop-in change | PA power 5 W at 40% efficiency (T-02); thermal; EIRP limits make it useless in ETSI regions |
| D | Use 2.4 GHz (or 900 MHz) for long range | +4 dB (2.4 GHz), more with 900 MHz; better foliage penetration | Congested band; fewer channels; 900 MHz is a different RF design (RF-002); 2.4 GHz range under ETSI is 2.5 km |

Recommendation: restate SYS-003 as **range classes** that combine A, B and D. Class S: 5 km, 5 dBi antennas, 5.8 GHz,
20 MHz, QPSK 3/4. Class X: 10 km, 10 dBi ground antenna (or switched-beam array), 5.8 GHz, 20 MHz. Class L: 15 km,
2.4 GHz, 5/5 dBi, or 900 MHz variant. Give ETSI values separately.

Review (iteration 14, T-01; after the T-03 iteration changed the uplink): the options A to D buy range with hardware (antenna, bandwidth, power, band). An option that needs no hardware was missing: (E) **trade video quality for
range** by stepping down the MCS and the video bit rate, which the system already does (SYS-004). Range against MCS for the baseline antennas (split-band mode, 20 MHz, 30 dBm, 5/5 dBi, 2-branch MRC, 6 dB margin, free space;
`scripts/link_budget.py`):

| MCS | Net rate Mbit/s | Range km at 5.8 GHz | Range km at 2.4 GHz |
|---|---|---|---|
| BPSK 1/2 | 6.9 | 10.3 | 25.0 |
| QPSK 3/4 | 20.8 | 5.8 | 14.1 |
| 16QAM 3/4 | 41.7 | 2.3 | 5.6 |
| 64QAM 3/4 | 62.5 | 1.2 | 2.8 |

At BPSK 1/2 the video band carries about 6.9 Mbit/s and reaches 10.3 km at 5.8 GHz (25 km at 2.4 GHz) with ordinary 5 dBi antennas, so the 10 km range of Class X does **not** require the 10 dBi array if a reduced-quality profile
(about 720p30 at 6 Mbit/s or less) is accepted; the array turns the same 10 km into the full 20 Mbit/s profile. Also considered: (F) a relay drone (research, not specified). Decision: keep the range classes, and add the
**reduced-quality range profile** as the first step before any accessory (VID-022); SYS-003 states both the full-rate and the reduced-rate ranges.

Review (iteration 16, design stance of `notes.md` entry 9): regional limits are no longer a design driver. The range options above were compared under regional caps (for example the
FCC dB-for-dB rule in the uplink and the ETSI-type EIRP cap in Class L); they are now compared by capability, and a region profile is a derived column (`02` section 1.2). Effects: the in-band uplink at Class X
reaches 9.2 km instead of 8.2 km (the FCC-type profile is shown as a comparison), the Class L figure of 2.5 km becomes one row (2.8 km at a 20 dBm EIRP cap) of the profile table, and the option "raise the PA to 33 dBm" (C) is judged by
its power cost only. No option changes rank; the conclusions of T-01 stand, with SYS-003 stated as capability ranges.

## T-02 Power classes (G-06)

Input power excluding the sensor, ASIC target, PAE 30% unless stated (`02` section 3): 25 dBm 2.9 W; 27 dBm 3.6 W;
30 dBm 5.5 W (6.3 W at 25% PAE); 33 dBm 9.3 W.

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | One class: 30 dBm, with the 6.0 W limit | One SKU; meets 6.0 W only with PAE of about 27% or better at 30 dBm average OFDM | Thin margin, needs a Doherty or envelope-tracking PA, which complicates DPD (T-14); 6.3 W if PAE is 25% |
| B | Three programmable classes (25, 27, 30 dBm) with input power at most 3.5, 4.0 and 6.0 W; 33 dBm only for a separate high-power SKU (about 10 W) | Matches regional limits; the user trades range for thermal and battery; the same silicon | More validation; the PA/FEM must be efficient across the range |
| C | Fixed 25 dBm, rely on antenna gain | Lowest power and weight (2.9 W) | Class X range (10 km) would need about a 14 dBi ground antenna; weak in clutter |

Recommendation: **B**. SYS-005 becomes "at most 3.5 W at 25 dBm, 4.0 W at 27 dBm and 6.0 W at 30 dBm (excluding the sensor)".
RF-010 keeps 33 dBm as a capability of the transceiver chain, not of the standard product. PWR-004 is restated
as PAE of 30% or better at 27 and 30 dBm average OFDM output, with a PA study (T-14) to confirm feasibility.

Review (iteration 5): PA efficiency and back-off per mode were modelled (`02` section 3). Alternatives not in the first round: (D) a **low-PAPR
DFT-spread OFDM mode** for the long-range low-order region (PAE 32.8% at QPSK instead of 27.6%, saving about 0.6 W at 30 dBm), (E) envelope tracking, (F) a GaN PA.
D saves 10 to 14% of the power budget but adds a DFT precoder at the transmitter and a frequency-domain equaliser plus inverse DFT at the receiver:
kept as an optional mode (PHY-014) and as the mitigation if the PA study shows less than 27% PAE at OFDM QPSK/16QAM. E and F raise PAE but add a supply
modulator or cost; evaluated in the PA study (HSI-style gate: PA study before freezing SYS-005). Decision: **keep option B (three power classes)** with a per-modulation
power cap (RF-031) and the restated SYS-005/PWR-004.

## T-03 TDD frame structure, guard and sensing (G-08, G-13, G-21)

Propagation: 3.33 us per km one way. The DL to UL guard must cover about 2 x delay plus two turn-arounds (`02` section 4). The uplink slot is
sized for MAC-007 (1 Mbit/s at QPSK 1/2, 100 feedback bits per frame, 2 preamble symbols). Downlink share of the frame [calc]:

| Range km | A: fixed 1 ms | B: fixed 2 ms | C: adaptive |
|---|---|---|---|
| 5 | 0.852 | 0.899 | 0.852 |
| 10 | 0.818 | 0.882 | 0.882 |
| 15 | 0.785 | 0.865 | 0.865 |
| 30 | 0.685 | 0.815 | 0.877 |

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Fixed 1.0 ms super-frame at all ranges, timing advance at the ground unit | Lowest feedback latency (1 ms); the guard doubles as an ETSI frame-based-equipment idle period (at least 100 us, [not verified]) | Downlink share falls from 0.852 at 5 km to 0.785 at 15 km and 0.685 at 30 km |
| B | Fixed 2.0 ms super-frame | Better efficiency at range (0.865 at 15 km, 0.815 at 30 km) | Feedback period 2 ms (MAC-005 looser); 0.899 at 5 km does not use the short-range advantage of fast feedback |
| C | Range-adaptive frame: 1 ms to 7 km, 2 ms to 15 km, 4 ms beyond, from the measured round-trip delay | Best share at every range (0.852, 0.882, 0.865, 0.877) | More states to verify; the frame length change must be glitch-free; feedback period grows with range |

| D | Split-band uplink: video band downlink-only, feedback/telemetry/RC on a 5 MHz channel in a far band (2.4 GHz for 5.8 GHz video, 900 MHz for 2.4 GHz video) | Uplink margin 11.0-17.0 dB instead of 5.0-6.3 dB (`02` section 1.1b); no guard, no timing advance, no uplink slot in the video band; video rate about 8% higher; the uplink can run continuously (feedback every 0.25 ms or faster, RC at 1 kHz); also provides the out-of-band beacon of ADA-005 | Second receive chain at the air unit and a 2.4 GHz/900 MHz transmit chain at the ground unit; TX-to-RX isolation requirement (RF-030); 900 MHz not usable for a 1 Mbit/s uplink in the EU; uplink channels are limited (16 at 5 MHz in 2.4 GHz) |
| E | Same-band FDD (uplink 30 MHz away in the video band) | One band, no second radio | Rejected: about 67 dB of isolation needed at a 30 MHz offset [E, estimate in `02`] cannot be reached |

Review (iteration 4): the two missing options were the split-band uplink (D) and same-band FDD (E). D beats in-band TDD on uplink margin and airtime,
and removes the timing-advance and frame-length machinery from the video band; its cost is hardware (a second band) and regional dependence. E is
physically infeasible. In-band TDD (C) stays as the fallback for single-band products and for regions where the second band is unusable.

Decision: **D as the baseline architecture for Classes X and L where regulation allows (MAC-012); C as the fallback mode (MAC-001)**.

## T-04 Numerology (G-12, G-25)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Constant 78.125 kHz sub-carrier spacing; FFT 64/128/256/512 for 5/10/20/40 MHz | One symbol time (12.8 us) for all bandwidths; matches 802.11ax, so the WiFi prototype modes are close; Doppler tolerance independent of bandwidth | FFT 64 at 5 MHz means only a few data tones (about 48); CP overhead in time is fixed |
| B | Two spacings: 78.125 kHz (default) and 39 kHz (long range, long CP for multipath) | Better multipath tolerance at long range | 39 kHz halves the Doppler margin (still adequate to about 1.7 kHz); two modes to verify; the CP tolerance is rarely the limit for a drone link |
| C | 156 kHz spacing (802.11n-like 312 kHz / 2) | Highest Doppler tolerance (supports 256QAM at 3.5 kHz) | Shorter symbol 6.4 us, so a large CP fraction for the same delay spread; less efficient |

Recommendation: **A** with FFT 64 added to PHY-001 (and a 78.125 kHz default). Run an S (simulation) item for
the ICI loss against the maximum Doppler and restrict 256QAM to Doppler below 1 kHz (G-25).

Review (iteration 6, numbers from `scripts/link_budget.py`, Jakes ICI approximation):

| Spacing kHz | Symbol us | CP 1/16 us | CP 1/8 us | Max Doppler Hz for 21 dB SIR (64QAM) | for 28 dB SIR (256QAM) | Closing speed km/h at 5.8 GHz for 28 dB |
|---|---|---|---|---|---|---|
| 39.0625 | 25.6 | 1.60 | 3.20 | 1919 | 857 | 160 |
| 78.125 | 12.8 | 0.80 | 1.60 | 3839 | 1715 | 319 |
| 156.25 | 6.4 | 0.40 | 0.80 | 7678 | 3429 | 639 |

Findings: (1) Option C (156 kHz) has a 0.4 us cyclic prefix, too short for the 0.5 to 2 us delay spreads that low-altitude forest or urban sites can have [E, typical
literature values, not measured here], although it tolerates 640 km/h closing speed for 256QAM; it is rejected. (2) Option B (39 kHz) gives a 1.6 us prefix at 6% overhead but
halves the Doppler margin to 160 km/h for 256QAM; the same 1.6 us is available in option A with the 1/8 prefix at 11% overhead, so the saving is about 5 points of airtime
and does not justify a second numerology. (3) The 78.125 kHz default holds 64QAM to 3.8 kHz Doppler and 256QAM to 1.7 kHz, so PHY-003 (3.5 kHz and 1.0 kHz) has margin.
Open-field delay spread is far smaller (a two-ray ground reflection at 100 m altitude and 1 km gives about 1 ns of extra delay, `2 h1 h2 / (d c)`). Decision: **A unchanged**, with the
1/8 prefix selectable for forest and urban use.

## T-05 Co-located links (G-20)

2.4 GHz band: 4/8/16 channels at 20/10/5 MHz; 5.8 GHz: 6/12/25 channels [calc: 83.5 and 125 MHz].

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Frequency division only, with channel plans per bandwidth | Simple; no cross-link coordination | 20 links in 2.4 GHz need 5 MHz channels (16 at most); 40 links in 5.8 GHz are impossible |
| B | Time sharing within a channel: several links share a channel by TDMA slices (an air unit uses 1/N of the super-frames) | Many links per channel | Latency and rate fall by N; needs a shared time reference (GNSS or over-the-air sync); not for race mode |
| C | Spatial reuse with directional antennas and power control; plus dynamic channel selection (ADA-001) | Works for sparse outdoor flying | No guarantee at a crowded race gate |
| D | Per-region "race mode" with narrow 5/10 MHz channels (8 to 12 pilots in 5.8 GHz, lower rate and range) | Matches the real race use case | Lower quality |

Recommendation: restate SYS-009 as: 6 simultaneous links at 20 MHz and 12 at 10 MHz in 5.8 GHz (A), 25 at 5 MHz
in a race mode (D); 4/8 in 2.4 GHz; beyond this, graceful interference handling by ADA-001 and power control (C).
Option B is a P2+ feature for event organisers.

Review (iteration 7): the near-far case was analysed (`scripts/link_budget.py`; free space, 35 dBm EIRP neighbour, victim noise floor -97 dBm, 1 dB desense means leakage 6 dB below noise):

| Neighbour ACLR dBc (in the victim channel) | Min separation, victim at edge of range (1 dB desense) m | Min separation, victim within 500 m (SIR 13 dB) m |
|---|---|---|
| 45 | 184 | 7 |
| 50 | 103 | 4 |
| 55 | 58 | 2 |
| 60 | 33 | 1 |
| 65 | 18 | 1 |

Findings: the leakage of a neighbouring transmitter into the victim's channel cannot be filtered out by the victim, so it sets a minimum separation: at -45 dBc ACLR a neighbour in the *adjacent*
channel must be 184 m away for a victim at the edge of its range, but only 7 m away for a victim within 500 m of its pilot (the racing case). The channel counts of option A therefore hold
for racing; for long-range operation only alternate channels can be used (3, 6 and 13 links at 20, 10 and 5 MHz in 5.8 GHz; 2, 4 and 8 in 2.4 GHz) unless neighbours are separated by about 200 m. Improving ACLR
helps slowly (58 m at -55 dBc, 18 m at -65 dBc) and costs PA linearity. Alternatives added: (F) neighbour-aware power control from the spectrum scan (ADA-001): a nearby
strong signal makes the unit prefer alternate channels or reduce power, no hardware cost, helps but cannot remove the leakage; (G) GNSS-synchronised time sharing of a channel by several
air units: removes simultaneous leakage but cuts rate and raises latency by the number of units, only for events; (H) directional ground antennas (spatial separation), useful in addition. Decision:
**D (race mode with 5 MHz channels) for events plus alternate-channel planning (A') for long range, F as an optional feature (ADA-010)**; SYS-009 and RF-029 restated.

## T-06 Video codec (G-11)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | HEVC (H.265) with a custom low-latency slice encoder | Best compression at 1080p to 4K (roughly 30 to 50% below AVC at equal quality); the vendor hard cores support it (waybeam, Xilinx VCU) | Several patent pools and royalty exposure; encoder complexity is high |
| B | AVC (H.264) | Lower complexity and area; simplest low-latency encoder; mature hardware decoders everywhere | Higher bit rate (about 1.5x), so more link margin or lower quality at range; also in patent pools (though the older and better understood) |
| C | AV1 (or an intra-heavy codec such as JPEG-XS for the lowest latency) | AV1: offered royalty-free by AOMedia members, but a third-party patent pool also claims essential patents [to be checked]; JPEG-XS: sub-millisecond latency and slice-based by design | AV1 low-latency hardware encoders are heavy; JPEG-XS needs roughly 10x or more of the bit rate of AVC at similar quality [typical compression ratios, from memory] and does not fit the link at long range |

Recommendation: **B and A in parallel**: AVC as the P1 baseline and the ASIC fallback (easier, lower risk, decoders
everywhere), HEVC as the quality mode. Keep the encoder architecture codec-agnostic at slice level; start the
licensing review now (G-11). Keep JPEG-XS as an "ultra-low-latency short-range mode" research item.

## T-07 Loss protection and graceful degradation

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Slices with UEP (stronger LDPC on headers) and per-slice selective retransmission; intra-refresh for recovery | Standard codecs; good compression; fits the PHY | Degradation is a "cliff" (a slice is lost or not), concealment needed |
| B | Joint source-channel coding (analogue-like or SoftCast-style linear transform with direct mapping to OFDM amplitude) | Graceful: quality scales continuously with SNR, no cliff, no rate adaptation latency; ideal for moving vehicles | Lower compression efficiency at high SNR; research-grade; no standard decoders (the ground unit must be custom); hard to combine with encryption |
| C | Scalable (layered) coding: base layer at the lowest MCS with strong FEC, enhancement layers at higher MCS | Graceful in steps; base layer always arrives | Layering costs 10 to 20% bit rate; SVC support in hardware encoders is limited |

Recommendation: **A as the baseline** (SYS-004 and VID-010 through intra-refresh and concealment) with a **C-like
two-layer option** for P2 by using separate slice groups at different MCS (UEP at the PHY level), and **B as a
research track on the FPGA** (it uses only the OFDM modem and a transform, so the cost of trying is low).

Review (iteration 8, T-06 and T-07 together, numbers from `scripts/link_budget.py`):

| Video | Slices per frame | Slice bits | Codewords per slice (648-bit, R 3/4, K 486) | Codeword error rate for slice PER 1e-3 |
|---|---|---|---|---|
| 1080p60, 20 Mbit/s | 8 | 41,667 | 86 | 1.2e-05 |
| 1080p120, 20 Mbit/s | 8 | 20,833 | 43 | 2.3e-05 |
| 1080p60, 10 Mbit/s | 8 | 20,833 | 43 | 2.3e-05 |

A slice-level packet error rate of 1e-3 (PHY-011) therefore needs a codeword error rate of about 1.2e-5 at 1080p60 and 20 Mbit/s: the receiver sensitivity (RF-020) and the SNR values in it are
defined at that operating point, not at the 1e-2 or 1e-3 codeword point usually quoted [E: the SNR values are to be re-derived by simulation; for steep LDPC waterfalls the difference is small but real].

The cost of the recovery method was computed (intra-coded area assumed to cost 4x the bits of inter-coded area, [E], content dependent):

| Refresh period (frames) | Time at 60 fps ms | Overhead (1/N x (r - 1), r = 4) |
|---|---|---|
| 8 | 133 | 38% |
| 15 | 250 | 20% |
| 30 | 500 | 10% |
| 60 | 1000 | 5% |

A short fixed refresh wave is expensive (38% at 8 frames) and a long one recovers slowly (1 s at 60 frames). Alternative added: (D) **reactive slice refresh**: a slice reported lost in the
acknowledgement bitmap is re-coded in intra mode in the next frame. At the target loss rate (1e-3 per slice, 8 slices, 60 fps: 0.48 losses per second) one lost slice costs (4 - 1)/8 = 37.5% of one
frame, which averages about 0.3% of the bit rate, against 10% for a 30-frame wave. It needs the acknowledgement to reach the encoder within one frame time, which both the split-band uplink (0.25 ms) and the
in-band TDD frame (1 to 4 ms) provide. The periodic wave is kept only as a safety net (period up to 60 frames, 5%) for start-up and undetected drift. Other alternatives: (E) scalable two-layer coding
(unchanged: costs 10 to 20% bit rate, kept as a P2 option), (F) packet-level erasure coding across slices (adds block latency, cruise mode only). On the codec: HEVC gives lower bit rates at the
same quality (about 30 to 50% [E, literature]) which matters when the net link rate is 18 to 21 Mbit/s (`02`); AVC remains the baseline for risk and licensing reasons (VID-017). Decision: **T-06 unchanged
(AVC baseline, HEVC quality mode); T-07 option A plus reactive refresh (D)**, new VID-021.

## T-08 ASIC partitioning, process, integration (G-23)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | One die in 22 nm FD-SOI (RF + baseband + encoder + CPU) | Smallest board and lowest BOM; FD-SOI has good RF and low-power digital | Highest NRE and risk; IP availability (RF, CPU, MIPI) in the node; yields |
| B | Two dice: RF transceiver in a mature RF node (e.g. 40 nm or 28 nm RF-CMOS or 22FDX) and a digital SoC in 12/16/22 nm, with a high-speed digital interface (JESD204 or LVDS) | Each die in its best node; the RF die can be a first tape-out (test chip A1); lower risk; second source possible | Interface power (about 100 to 200 mW); two packages; larger board |
| C | System-in-package: off-the-shelf transceiver plus custom baseband ASIC | Fastest; lowest RF risk | Not a "chip"; BOM cost and the transceiver vendor dependency; calibrations limited to what the vendor exposes |

Recommendation: **B for the first product, with C as the bridging step** (the FPGA prototype is already C), and
A as a later cost-down. The RF die test chip (A1) in the plan is consistent with B.

Review (iteration 13, T-08): the cost of option B (two dice) is the sample interface between them; it was computed for the chain counts of the split-band architecture (12-bit I/Q, `scripts/link_budget.py`; energy per bit is an assumption [E]):

| Mode | Sample rate MSPS | Chains crossing the interface | Bit rate Gbit/s | Power both ends at 5 / 10 / 20 pJ/bit mW |
|---|---|---|---|---|
| 40 MHz, air unit (1 Tx + 1 Rx) | 61.44 | 2 | 2.95 | 29 / 59 / 118 |
| 40 MHz, ground unit (2 Rx + 1 Tx) | 61.44 | 3 | 4.42 | 44 / 88 / 177 |
| 20 MHz, ground unit (2 Rx + 1 Tx) | 30.72 | 3 | 2.21 | 22 / 44 / 88 |
| 40 MHz, enhanced ground unit (8 Rx + 1 Tx) | 61.44 | 9 | 13.27 | 133 / 265 / 531 |
| DPD observation capture kept on the RF die (98 kbit per capture) | burst | 0 (read out slowly) | 0 | 0 |

Findings: the air unit moves 2.95 Gbit/s across the interface at 40 MHz (30 to 120 mW for both ends depending on 5 to 20 pJ/bit; a serial JESD204-class link is in the lower part of that range, a parallel LVDS bus in the upper part), 2 to 10% of the 1.2 W
transceiver plus baseband budget of `02`, and half at 20 MHz. The DPD observation path (a 3 to 5 times wider signal) does not cross the interface in real time: it is captured into a memory on the RF die (4096 complex samples are 98 kbit) and read out slowly, which
removes the largest potential interface cost. Alternatives added: (D) a decimated 20 MHz interface for the default channel (halves the cost), (E) a single die in a mixed-signal/RF-capable node (no interface, higher risk and NRE, evaluated again after the RF test chip A1). Decision: **B unchanged**,
with the observation capture on the RF die and a 120 mW worst-case interface limit (ASC-006).

## T-09 Open versus locked RF parameters (G-07)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Fully open firmware including RF limits (like wfb-ng driver-based systems) | Maximum openness; community trust | Regulatory approval is difficult; users can exceed limits; export and liability exposure |
| B | Open source stack with a small signed, closed (or at least secure-boot-verified) "RF limiter" block in hardware/firmware that enforces region, power, band and dwell tables | Preserves openness for 99% of the code; regulatory path exists; the limiter is auditable by inspection under NDA or public source with signed binaries | A signed region means a manufacturer key (the system is no longer fully modifiable); contributors may object |
| C | Two SKUs: certified locked product and an open "development/amateur-radio" SKU with a licensed operator | Both communities served | Doubled support; risk of grey-market conversion |

Recommendation: **B**, with the limiter implemented in hardware (ASIC register lock) and firmware signed. Record in
SEC-005. Check the current FCC software-security guidance with counsel (A-06).

## T-10 Remote ID and BLE (G-19)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Separate low-cost BLE/WiFi SoC (for example a Nordic or Espressif class part) used for RID and pairing | Certified module; lowest risk; works with the main chip off (PWR-006) | Another part and antenna; extra 30 to 100 mW and BOM cost |
| B | BLE 5 PHY (GFSK, coded PHY) in the SDR modem, with the main transceiver in a narrow mode | No extra chip; reuses the antenna | Needs the full SoC awake (sleep power 50 mW may not be achievable); BLE qualification for an in-house stack; more validation |
| C | WiFi NAN/beacon RID using the 802.11 mode (PHY-013 in P2) | No Bluetooth stack; RID receivers support WiFi | Rates; WiFi mode must exist in P2; certification of the WiFi mode |

Recommendation: **A for the product** (a certified RID/BLE module is cheapest and fastest to approve) and **B** as a
later integration step if a measured sleep-power and cost benefit exists.

Review (iteration 10, T-09 and T-10): evidence found by search: 47 CFR 2.944 requires the manufacturer of a software defined radio to ensure that only software approved with the radio can be loaded (acceptable means include authenticated
download, electronic signatures or hardware coding, to be described in the authorization application), and radios whose software a third party is expected to change in ways that affect frequency range, modulation or power must meet that and be
certified as software defined radios ([eCFR/Cornell text](https://www.law.cornell.edu/cfr/text/47/2.944)); the FCC's U-NII security guidance (KDB 594280 D02) asks the applicant to describe the security measures and list the RF parameters software can change; the 2014 rule change
required software security for U-NII devices. The KDB revision found is from 2015/2016 and the current one was not read.
Consequences for the options: A (fully open firmware including the RF limits) makes every RF parameter third-party modifiable, so the product would have to be certified as an SDR with approved-software-only loading, which contradicts the openness it was meant to give: rejected for the sold product.
B (open stack, signed RF limiter) fits: third-party software cannot move the RF parameters outside the approved set, which is exactly the statement the application must make. New alternative (D): put the limiter in the **modem hardware** (register lock set from a signed, region-bound
table) so even a compromised processor cannot exceed it; this is B implemented in silicon and is the ASIC target (SEC-005); in the FPGA phases the same is done by a signed bitstream. The FPGA prototypes are not sold and run in
conducted or shielded set-ups or under the applicable test authorisation. Option C (an open SKU) would need an amateur-radio style authorisation and is left to the community, not a product. Decision: **B, with D as its ASIC form**; REG-007 requires the software security statement.
For Remote ID (T-10): the FAA accepts ASTM F3586-22 for broadcast modules and each manufacturer files a declaration of compliance; using a module that already has one avoids that process for the main device, so **A (separate certified module) is confirmed** and B/C wait for a later revision.

## T-11 Baseband base for the FPGA prototype (P1)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Start from openwifi (AGPLv3) | Working 802.11 a/g/n on Zynq plus AD9361 now; SIFS-level MAC | AGPL contaminates anything derived; 20 MHz, a/g/n only; a commercial licence is an option but costs money |
| B | Clean-room custom PHY/MAC with ADI HDL for the transceiver interface; openofdm (Apache 2.0) as a block reference | No copyleft; designed for our numerology (T-04) from day one | Longer (6 to 12 months for the modem); more risk |
| C | Commodity WiFi (wfb-ng) for the whole prototype | Immediate | No PHY control; no calibration or timing study; useful only as a baseline (P0) |

Recommendation: **C now (P0), B for P1**, using A only as a behavioural reference (no code copied) and
buying the commercial licence only if time-to-flight matters more than the legal cleanliness.

## T-12 Transceiver for P1

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | AD9361 (2x2) / AD9364 (1x1), 70 MHz to 6 GHz receive, 56 MHz | Cheapest, well supported (openwifi, ADI HDL); retune about 15 to 25 us with fast-lock profiles | No integrated DPD; TDD RX to TX goes through the ALERT state, so the 5 us turn-around (RF-009) is not demonstrated on this part |
| B | ADRV9002 (30 MHz to 6 GHz, up to 40 MHz, integrated DPD) | Closest to the target calibration architecture (`03`); hop frames of 13 us with about 3 us transitions demonstrated by ADI, which supports RF-006 and RF-009 | Newer, more complex boot and API; cost; power and tracking calibration not verified; check licences of the reference firmware |
| C | LMS7002M (LimeSDR) | Open hardware docs; flexible | Fewer vendor calibration features; supply |

Recommendation: **A for the first bench link (fast) and B for the calibration work** (CAL-005 DPD with an observation
path). Keep the HAL (SW-002) so that both can be used.

Review (iteration 9, T-11, T-12 and T-19 together, using the two-phase rule of `13`): the split-band architecture (T-03) needs a transmitter at the video band and a receiver at a
different band at the same time. The AD936x family has two independent RF synthesizers, one for receive and one for transmit, and the receive and transmit LO frequencies are set
independently ([ADI Linux driver documentation](https://analogdevicesinc.github.io/linux/drivers/iio-transceiver/ad9361.html), found by search); the independent FDD mode is pin-controlled; the AD9364 (1 Rx, 1 Tx) is mentioned only as the 1x1 variant and its
independent-mode behaviour was **not** confirmed. Consequences and alternatives:

| Phase A configuration | Radios | Covers | Limits |
|---|---|---|---|
| A1 | Two ADALM-PLUTO-class radios (AD9363, 325 MHz to 3.8 GHz guaranteed, 20 MHz) | The Class L split-band configuration: video at 2.4 GHz, uplink at 915 MHz, both inside the guaranteed range, no firmware modification; modem, MAC, sequencer, calibration hooks | 20 MHz only; no 5.8 GHz; no DPD; low power |
| A2 | Pair of AD9361 (ground: 2 Rx at 5.8 GHz, 1 Tx at 2.4 GHz; air: AD9364-class 1 Tx at 5.8 GHz, 1 Rx at 2.4 GHz) or ADRV9002 evaluation boards | Class S/X split-band configuration at 5.8 GHz with 2.4 GHz uplink; turn-around, hop and isolation measurements | Cost; AD9364 independent mode to be confirmed; 40 MHz limit on ADRV9002 |
| A3 | K26-class board (codec) plus Rockchip/Pi-class ground decoder | Video pipeline, VCU latency, slice handling, display lock | Not joined to the radio at low latency in phase A |

Decision: **T-19 option A and B in parallel as planned, with A split into A1 (Pluto pair, 2.4 GHz + 915 MHz) and A2 (AD9361/ADRV9002, 5.8 GHz + 2.4 GHz)**; **T-12: AD936x for phase A, ADRV9002 for phase B** (it
is the only part with sourced evidence for the 5 us turn-around and the hop time and has integrated DPD); **T-11: clean-room custom baseband** unchanged. New alternative rejected: using
openwifi as the A1 baseline (AGPL, 20 MHz, 802.11 timing only) except as a behavioural reference.

## T-13 Antenna and diversity

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | 2 omni antennas on the air unit, 2 on the ground (spatial diversity, MRC) | Simple; robust to shadowing and polarisation mismatch | Limited gain (about 3 dB from MRC only) |
| B | Ground switched-beam patch array (six 60-degree sectors with 40-degree elevation beams, 10.1 dBi per beam, see the review below) plus 1 omni for acquisition | 5 dB over a 5 dBi omni, no moving parts, fits Class X | Cost; the beam choice per frame must be fast (ANT-008); hand-held tolerance; four 90-degree sectors would give only 6.6 to 9.6 dBi |
| C | Ground phased array (4 to 8 elements, beamforming) | Tracking without pointing; interference nulling | Calibration complexity (CAL-010); cost; power |

Recommendation: **A for P1 and the base product, B as the long-range accessory**, C as a research item on the SDR
(it exercises CAL-010).

Review (iteration 11): the first-round claim that a 4-beam array of 90-degree sectors gives "+8 to 10 dB" was wrong. Beam gain from the beamwidths (`G = 0.6 x 41253 / (azimuth x elevation)`, patch-array efficiency 0.6 [E]):

| Sectors | Azimuth beamwidth | Gain dBi, elevation 60 deg | 40 deg | 30 deg |
|---|---|---|---|---|
| 4 | 90 deg | 6.6 | 8.4 | 9.6 |
| 6 | 60 deg | 8.4 | 10.1 | 11.4 |
| 8 | 45 deg | 9.6 | 11.4 | 12.6 |
| 12 | 30 deg | 11.4 | 13.1 | 14.4 |

Four 90-degree sectors give only 6.6 to 9.6 dBi, 1.6 to 4.6 dB better than the 5 dBi omni assumed in the budget; the 10 dBi of Class X needs six sectors with 40-degree elevation beams (10.1 dBi) or eight sectors at
60 degrees (9.6 dBi, 11.4 at 40 degrees). For long range the drone is near the horizon, so a narrow elevation beam (30 to 40 degrees) is acceptable, but it must be wide enough for the minimum flight distance and altitude.
Alternatives added: (D) a motorised tracking antenna (14 to 18 dBi directional, pointed from the telemetry position): 14 dBi gives 16.4 km at Class X power (T-01 numbers), at the cost of a motor, a pointing loop and
a failure mode when the position is lost; (E) a helical or patch antenna on a tripod for fixed sites. Decision: **A (diversity) for the base product; B revised to a six-sector array with 40-degree elevation beams as the Class X
accessory; D as an option for ranges beyond 10 km; C (phased array) stays research.**

## T-14 DPD architecture

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | No DPD: fixed back-off (6 to 8 dB) | Simple | Back-off costs 2x or more PA power; 256QAM unusable; ties to T-02 |
| B | Memory-polynomial DPD with an observation receiver (adapted in the background) | Standard practice; allows 3 to 4 dB back-off; fits the obs path in `03` | Needs an observation receiver (area, power); convergence logic; VSWR sensitivity (hence CAL-008) |
| C | Look-up-table DPD with a slow feedback loop and temperature/VSWR bins | Low complexity and power | Less accuracy; large tables per bin; does not track fast changes |

Recommendation: **B in P1/P2** with the C table as the fast fallback while B converges (the calibration data store in
`03` holds seed coefficients per bin). A is acceptable for 25 dBm class products.

Review (iteration 5, with T-02): the patent register (`11`) found US 12,456,952 (Skyworks, active to about 2042) claiming DPD plus load-impedance determination
plus bias/supply adjustment achieved synchronously. The recommended B (memory polynomial with observation receiver) stays, with design-around D-1
(REG-006): bias and supply follow temperature and PA current only; reflection data is used for fold-back, coefficient-set selection and alarms. The
alternatives that rely on bias adjustment from the load (an "adaptive PA" for antenna mismatch) are dropped for this reason. The back-off figure in PHY-009 was
corrected (no DPD choice reaches 4 dB back-off for 64QAM OFDM).

## T-15 Hopping strategy

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Static channel plus adaptive channel selection (ADA-001, ADA-002) | Simplest; uses the full TDD design; best latency | Slow reaction to bursty interference; regulatory limits on fixed channels for some regions |
| B | Fast frequency hopping on every super-frame | Excellent against narrowband interference and jammers; robust | PLL settling each time (RF-006); calibration per channel; harder timing; consumes airtime |
| C | Hybrid: static video channel with fast hopping on the control/telemetry channel and a robust out-of-band beacon on another band | Video keeps latency; control survives interference; link recovery (ADA-004/005) | Two radios or a time-multiplexed transceiver; more states |

Recommendation: **C**, with the video on a static adaptive channel and the control/beacon on a separate, hopped
band (900 MHz when fitted, otherwise 2.4 GHz). The fast hop of the video (B) is a fallback in anti-jam mode (SEC-004).

Review (iteration 12, T-15; the T-03 iteration changed its context): in split-band mode the video band is a static adaptive channel and the control/telemetry uplink is the out-of-band channel, so the "hopped control channel" of option C
exists only if hopping is useful there. The cost of hopping was computed (`scripts/link_budget.py`):

| Dwell ms | Overhead at 50 us settle | at 150 us (cross-band) |
|---|---|---|
| 1 | 5.0% | 15.0% |
| 2 | 2.5% | 7.5% |
| 5 | 1.0% | 3.0% |
| 10 | 0.5% | 1.5% |

A 1 ms dwell costs 5% of airtime within a band and 15% across bands, 10 ms costs 0.5% and 1.5%, so fast hopping of the **video** channel (option B) is justified only as an anti-jam fallback. Regulation adds a limit: non-adaptive hopping in the 2.4 GHz band
is limited to a 5 ms on-time followed by a 5 ms gap [from a search summary of EN 300 328, to be checked], which a continuous uplink cannot satisfy; the uplink therefore stays on a static adaptive channel with a fallback channel list, and
hops (adaptively, with listen-before-talk where required) only on loss. Decision: **C refined**: static adaptive video channel, static adaptive uplink channel with fallback list, fast adaptive hopping only in anti-jam mode (SEC-004).

## T-16 FEC code

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | LDPC (quasi-cyclic, 802.11n/ax-like short and medium blocks) | Near-capacity performance; parallel decoder suitable for FPGA/ASIC; known standard codes | Short-block performance degrades; decoder iteration latency |
| B | Polar codes (5G NR control channel style) with CRC-aided list decoding | Excellent at short block lengths (the slice header, control) | Decoder latency and area for list decoding; patent licences from a few parties [not verified] |
| C | Convolutional (K=7, Viterbi) plus Reed-Solomon / packet-level FEC (wfb-ng style) | Simple; low latency per bit; proven | About 2 dB worse than LDPC at long blocks; the packet-level FEC adds the latency of a whole block |

Recommendation: **A for the data**, **B (or the same LDPC with a short code) for the control/feedback burst**; keep C's
packet-level FEC as an optional outer code across slices in cruise mode (LAT-006).

Review (iteration 6): decoder feasibility was checked, since a short-block decoder must keep up with the peak PHY rate (`scripts/link_budget.py`, [E]: base-matrix size and iteration count are assumptions):

| Quantity | Value |
|---|---|
| Cycles per codeword (90 entries x 10 iterations) | 900 |
| Time per codeword at 200 MHz | 4.5 us |
| Throughput per decoder instance (K = 324) | 72 Mbit/s |
| Peak PHY information rate (40 MHz, 64QAM 3/4) | 155 Mbit/s |
| Decoder instances needed | 3 |

One layered decoder instance handles about 72 Mbit/s of information at 200 MHz, so the 155 Mbit/s peak (40 MHz, 64QAM 3/4, before duty and overhead) needs 3 instances; at the
typical 20 MHz QPSK 3/4 operating point (about 20 Mbit/s) one instance has 3.6x margin. Added alternatives: (D) packet-level erasure code across slices (Raptor-style) instead of
retransmission, and (E) turbo codes; D is kept only for cruise mode (LAT-006) because it adds the latency of a whole block, E offers no advantage over LDPC at these lengths. Codeword length
policy: 648 bits in race mode (shortest latency), 1944 bits in cruise mode (about 0.5 to 1 dB more coding gain [E, literature]). Decision: **A (LDPC) unchanged**, codeword length per mode (PHY-005), decoder sizing
as a requirement (PHY-015).

## T-17 Clocking, genlock and timing (G-16)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Free-running ground-unit display, slice buffer absorbs drift; periodic frame drop/repeat | Simple | Visible glitches; latency drifts by up to a frame between corrections |
| B | Ground-unit display scan-out is locked to the received frame timing (display PLL adjusts the pixel clock in tiny steps) | No glitches; constant latency | Needs a display that accepts a variable pixel clock (OLED/DSI custom timing); a few lines of buffer |
| C | Air unit slaves the sensor frame rate to the ground display via the uplink (sensor FSIN) | Both ends aligned; lowest buffer | Needs the uplink loop and sensor support; interacts with MAC |

Recommendation: **B**, plus the FSIN alignment of the sensor to the TDD frame on the air unit (`03` section 7).
C is a later option for fixed-rate displays.

## T-18 Control-plane processors (ASIC) (see `13`)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Real-time Cortex-R5F/M7-class cores (300 to 400 MHz) plus one power-gated A53/A55-class application core | Same architecture as the phase B device; mature RTOS, tools and WCET analysis; real-time cores cost 5 to 20 mW [E] | Licence and royalty; the application core dominates power if left on |
| B | RISC-V real-time cores plus a Linux-capable RISC-V core | No licence fee; custom instructions possible | Less mature RTOS/WCET/certification ecosystem; software must be ported from the ARM-based FPGA phases |
| C | Real-time cores only on the air unit; Linux only on the ground unit or a companion board | Lowest power, fastest boot, smallest area | No on-board application services; update and configuration paths go through the real-time firmware |

Recommendation: A for the first ASIC with C as the air-unit default configuration; B as a cost/IP study.

Review (iteration 13, T-18; workload in `13` section 2): the control workload is 34 Mcycles/s with hardware assist (11% of a 300 MHz core, 49% if the DPD matrix and the encryption were in software), so the choice between ARM and RISC-V real-time cores is not driven by performance;
any 300 MHz core with a double-precision-capable FPU (HSI-013) fits. The power anchors in `13` section 4 show the application core, not the real-time cores, dominates the processor power (about 0.5 W for one A53 at 1 GHz against an estimated 5 to 20 mW for a real-time core).
Alternative added: (D) no processor at all for the loops that need microsecond response, only hardware state machines (already the sequencer of HSI-002), which keeps the processors out of the fast path but does not remove them from calibration and link adaptation. Decision: **A with C as the air-unit default unchanged**; the ISA question (B) is decided
by the software-port cost from the ARM-based FPGA phases and by licence cost, not by performance or power.

## T-19 Phase A evaluation platform (see `13`)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | ADALM-PLUTO class (AD9363 + Zynq Z-7010) for PHY/MAC plus a separate low-cost video platform | Lowest cost; ADI software support; good for modem and MAC bring-up | 28k logic cells, 20 MHz, 5.8 GHz outside the guaranteed range; encoder/decoder live on another board, so latency across the boards is not representative |
| B | Kria K26/KV260 class (Zynq UltraScale+ with codec) plus an RF board | One device for modem, codec and processors, closest to phase B | 7.5 W typical; RF connection to be solved (no FMC on KV260 [E, check]); VCU latency unknown |
| C | ZCU104-class kit plus FMCOMMS/ADRV9002 evaluation board | Best-supported ADI reference flows | Highest cost, not "low-cost evaluation" |

Recommendation: A for modem/MAC/calibration bring-up in parallel with B for the video pipeline and the VCU latency measurement; C only if A and B cannot be joined.

Review (iteration 12, T-17): drift between the sensor frame clock and the display clock was computed (`scripts/link_budget.py`):

| Case | Combined error ppm | Drift per minute ms | Drift per 10 min ms | Time to slip one 60 fps frame min |
|---|---|---|---|---|
| Both ends on 20 ppm crystals | 40 | 2.40 | 24.0 | 7 |
| Both ends on 2 ppm TCXOs (RF-007) | 4 | 0.24 | 2.4 | 69 |
| Display steered to the received frame timing (residual 1 ppm) | 1 | 0.06 | 0.6 | 278 |

Without steering, 20 ppm crystals wander the latency by 24 ms in 10 minutes and slip a frame every 7 minutes; even TCXOs at both ends (RF-007) give 0.24 ms per minute, so the latency would creep up to a whole frame between slips, which
violates LAT-002 (p99 within 3 ms of the mean). Alternative added: (D) free-running displays disciplined only by the TCXOs plus an occasional deliberate frame drop (a glitch about once per hour): rejected for the latency creep.
Decision: **B (display scan-out locked to the received frame timing) confirmed**, needing a display controller whose pixel clock can be steered by at least +/-50 ppm with 0.1 ppm resolution [E] (VID-018); option C (air unit slaved to the display) stays a later option.

## T-21 Ground-unit configuration (notes entries 5, 6, 7)

The ground unit can be larger, heavier and more power-hungry than the air unit, and its bill of materials matters less. Levers (numbers in `02` sections 1.3 and 1.4): more receive branches
(about 3 dB per doubling), a lower noise figure (a discrete LNA and preselector filter, 2 dB instead of 4 dB), better antennas (six-sector array, tracker), heavier decoding (more LDPC iterations, soft combining of
retransmitted slices), a dedicated scan receiver, external antennas on coax with an LNA at the antenna. The uplink is the weak direction and these levers do not help it (`02` section 1.3).

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Symmetric: both units use the same silicon and two receive branches | One design, lowest cost; sufficient for the range classes S, X and L | No use of the ground unit's freedom; no scan receiver (the video receiver scans, taking airtime) |
| B | Enhanced ground unit from the same silicon: the digital SoC with replicated RF dice (up to 8 receive branches, one die as scan receiver), a discrete front end and external antennas | +8 dB with 8 branches and a 2 dB noise figure (`02` section 1.3); no new tape-out; the air unit and the protocol are unchanged; interface to 8 receive chains is 11.8 Gbit/s | Board complexity and cost (not silicon); the ADC dynamic range stays that of the RF die; more digital power (not critical on the ground) |
| C | Dedicated ground chip (more receive chains, higher-resolution converters, bigger decoder) | Best converters and decoder; fewer chips on the board | A second tape-out (T-22); the area saving of an air-only chip is small |
| D | Programmable ground station (FPGA or SDR hardware, as in phase B) for professional or low-volume use | No tape-out; any number of branches; the phase B ground board is this already | Not a consumer product; power and size |

Decision: **A for the base pair, B as the enhanced configuration on silicon, D for professional/low-volume use (it is also the phase B ground board)**; C only if T-22 justifies it. The enhanced configuration is described by configuration
values and requirements tagged [GU] (PHY-016, PHY-017, RF-032, ADA-011, ANT-012); the on-air protocol and the air unit do not change (SYS-011).

## T-22 Silicon family: one pair of chips or separate air and ground chips (notes entry 5)

The first draft assumed the same silicon in both roles. The estimate in `effort.md` (area and effort estimates [E]) puts a separate air chip at about 25 mm2 (no decoder, no display PHY) and a separate ground chip at about 24 mm2 (no encoder, no ISP, no CSI)
against about 29 mm2 for the shared design: a saving of about 5 mm2 each (about 15%, roughly USD 0.5 per unit), at the price of a second tape-out (about 3 M for masks and 50 to 60 person-years). Break-even (`scripts/link_budget.py`):

| Second tape-out effort PY | Cost MUSD (masks 3 + labour at 0.15 MUSD/PY) | Saving per unit USD (about 5 mm2, 15%) | Break-even volume million units |
|---|---|---|---|
| 50 | 10.5 | 0.5 | 21 |
| 60 | 12.0 | 0.5 | 24 |

| Option | Description | Pros | Cons |
|---|---|---|---|
| S1 | One digital SoC and one RF die for both roles (baseline) | One tape-out pair; the same software and test environment; a basic ground unit is the air-unit silicon | A little area wasted in each role |
| S2 | Separate air and ground digital chips (and possibly RF dice) | Each optimised: air chip without decoder and display PHY, ground chip with more branches and a bigger decoder | Second tape-out with a break-even of 21 to 24 million units on area alone; two verification environments; split software |
| S3 | S1 plus board-level enhancement of the ground unit (replicated RF dice, discrete front end, T-21 option B) | Gets most of the ground benefit without a second tape-out | Limited to what replication and discrete parts give (not better converters) |

Decision: **S1 with S3 for the enhanced ground unit**; S2 is allowed by the specification (SYS-011: units interoperate only through the on-air protocol, so a ground-only chip can be introduced later without touching the air unit) but is justified only by volume of tens of millions of units or by
a capability that replication cannot give (for example converter dynamic range). The multi-die capability is a day-one requirement (ASC-007).

## T-23 Air-unit beamforming and the single-silicon option set (notes entries 10, 11, 12)

For large drones (payload, mass and power far above the 25 g class) beamforming makes sense as a product-class option (options A to D, table in `02` section 1.5). The wish of the review is that **no option needs a new tape-out or die variant**: one chip contains all options and
the selection is a signed value in non-volatile memory (or a fuse); larger arrays are built by replicating the chip or the RF die.

| Option | Description | Pros | Cons |
|---|---|---|---|
| S-a | A die or variant per product class | Each product carries only what it uses | Several tape-outs; rejected by the review |
| S-b | One die with every option present, power-gated and clock-gated, enabled by a signed NVM value (the same mechanism as the region profiles, SEC-005) | One tape-out; a field upgrade is a signed update; entitlement can be bound to the product; disabled options cost only unused gates | Area for the logic that simple products never use; verification of every option state |
| S-c | Same die, but options selected by factory fuses only | Simple, tamper-resistant | No field upgrade; fuse count and test flow |
| S-d | Beyond the built-in chains, replicate the RF die or the whole chip with a shared reference clock and LO | Scales without a new design | Needs multi-chip coherence from day one: a chip-to-chip interface, a shared clock/LO scheme and per-element calibration |

Cost of S-b from `effort.md` [E]: beamforming logic 0.5 to 2 mm2 plus a chip-to-chip interface of 1 to 2 mm2 on the 29 mm2 digital SoC is 1.5 to 4 mm2, about 5% to 14% of the die; verification effort rises by about 10 to 15% because every option state, fuse state, band and role must be verified even when disabled (mitigation: keep the options orthogonal and verify the power
and clock gating once). Caveat: gating removes the digital logic cost but not the RF cost: extra on-die RF chains, converters and mixers cost area, leakage and routing, so the maximum number of on-die chains is fixed at design time (T-08) and only enabled in software; per-element power amplifiers and front ends are external (RF-028), so their cost is board-level.
The air-unit range gains are 3 dB (B), 5.5 dB (C) and 6 dB (D, N = 4), which doubles the Class S range at 5.8 GHz for D (`02` section 1.5).

Decision: **S-b with S-d** (ASC-008, ASC-009, SEC-006); the day-one list that avoids a respin is in ASC-009. The beamforming options are a product-class option for large drones (ANT-014), not a requirement of the small-drone class.

---

## Summary of recommendations

| Study | Recommendation |
|---|---|
| T-01 | Range classes S/X/L, per region |
| T-02 | Three programmable power classes with a per-modulation power cap; low-PAPR mode optional; 33 dBm separate SKU |
| T-03 | Split-band uplink as baseline (D); range-adaptive in-band TDD as fallback (C) |
| T-04 | 78.125 kHz sub-carrier spacing, FFT 64 to 512 |
| T-05 | Frequency division: full counts in race mode, alternate channels for long range; neighbour-aware selection |
| T-06 | AVC baseline plus HEVC quality mode; start licensing review |
| T-07 | Slice UEP, reactive slice refresh plus a long safety-net wave; two-layer option; JSCC research |
| T-08 | Two dice for the first product |
| T-09 | Open stack with a signed RF limiter |
| T-10 | Certified BLE/RID module |
| T-11 | Wifi (P0), clean-room custom baseband (P1) |
| T-12 | AD936x in phase A, ADRV9002 in phase B (hop, turn-around, DPD evidence) |
| T-13 | Diversity base; six-sector (40 degree elevation) ground accessory for Class X; tracker option beyond 10 km |
| T-14 | Memory-polynomial DPD with LUT fallback |
| T-15 | Static adaptive video channel, hopped control, separate beacon |
| T-16 | LDPC data, short code or polar for control |
| T-17 | Display locked to received timing |
| T-18 | Real-time cores plus power-gated application core; air unit without Linux by default |
| T-19 | Phase A1 Pluto pair (2.4 GHz + 915 MHz), A2 AD9361/ADRV9002 pair (5.8 + 2.4 GHz), A3 K26-class video board, in parallel |
| T-21 | Symmetric base pair; enhanced ground unit from the same silicon (replicated RF dice, discrete front end); FPGA ground station for professional use |
| T-22 | One pair of chips for both roles with board-level ground enhancement; separate air and ground chips allowed but justified only by volume or capability |
| T-23 | One die with all beamforming options gated and enabled by a signed NVM value; scaling by replicating the RF die with shared clock and LO |
