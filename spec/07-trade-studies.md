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
16.4 km with 14 dBi; 8.2 km at 10 MHz with 5/5 dBi; 8.2 km with a 33 dBm PA; 11.6 km if the video drops to BPSK 1/2.
At 2.4 GHz with 5/5 dBi: 14.1 km. Under the ETSI limit of about 20 dBm EIRP at 2.4 GHz: about 2.5 km.

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Require a 10 dBi or better ground antenna for the 10 km class | +5 dB at no power cost; works with any bandwidth; cheap (patch or helical) | Beamwidth about 60 degrees; needs pointing, a tracker or a switched-beam array (ANT-008); not goggle-mounted |
| B | Reduce the channel bandwidth to 10 MHz for long range | +3 dB; halves the number of channels needed (T-05); fits narrower regional bands | Halves the rate (10 Mbit/s); quality loss at 1080p60 |
| C | Raise the PA to 33 dBm | +3 dB with a drop-in change | PA power 5 W at 40% efficiency (T-02); thermal; EIRP limits make it useless in ETSI regions |
| D | Use 2.4 GHz (or 900 MHz) for long range | +4 dB (2.4 GHz), more with 900 MHz; better foliage penetration | Congested band; fewer channels; 900 MHz is a different RF design (RF-002); 2.4 GHz range under ETSI is 2.5 km |

Recommendation: restate SYS-003 as **range classes** that combine A, B and D. Class S: 5 km, 5 dBi antennas, 5.8 GHz,
20 MHz, QPSK 3/4. Class X: 10 km, 10 dBi ground antenna (or switched-beam array), 5.8 GHz, 20 MHz. Class L: 15 km,
2.4 GHz, 5/5 dBi, or 900 MHz variant. Give ETSI values separately.

## T-02 Power classes (G-06)

PA DC power = RF power / efficiency [calc]: 33 dBm at 40%: 5.0 W; 30 dBm at 40%: 2.5 W; 27 dBm at 40%: 1.25 W;
27 dBm at 30%: 1.7 W; 25 dBm at 30%: 1.05 W.

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | One class: 30 dBm, 40% PAE target, total at most 7 W | One SKU | Total 7 W exceeds the old SYS-005 (6 W) and the efficiency target needs a Doherty or envelope-tracking PA, which complicates DPD |
| B | Three programmable classes (25, 27, 30 dBm), total at most 4.5, 5 and 6.5 W; 33 dBm for a separate high-power SKU | Matches regional limits; thermal and battery choices for the user; the FPGA/ASIC is the same | More validation; the PA/FEM selection must cover the range efficiently |
| C | Fixed 25 dBm, rely on antenna gain | Lowest power and weight | Range classes S/X would need 10 to 14 dBi ground antennas; weak in clutter |

Recommendation: **B**. SYS-005 becomes "at most 6.5 W at 30 dBm (PAE 40% or better), 4.5 W at 25 dBm".
RF-010 keeps 33 dBm as a capability of the transceiver chain, not of the standard product. PWR-004 is restated
at the same power points.

## T-03 TDD frame structure, guard and sensing (G-08, G-13, G-21)

Propagation: 3.33 us per km one way. DL to UL guard must cover about 2 x delay: 100 us at 15 km, 200 us at 30 km.

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Fixed 1.0 ms super-frame, DL 0.85 ms / UL 0.08 ms / guards 0.07 ms, timing advance at the ground unit | Lowest feedback latency (1 ms); guard doubles as an ETSI FBE idle period (at least 100 us, [not verified]); uplink about 5.5 symbols per ms | The 0.07 ms guard covers only about 10 km (needs 2 x delay + 2 x 10 us turn-around); at 15 km it must grow to 0.12 ms (12% of the frame); at 30 km it does not fit |
| B | 2.0 ms super-frame, DL 1.76 / UL 0.12 / guards 0.12 ms, timing advance | Guard overhead at 15 km is 6% instead of 12%; covers 15 km | Feedback period 2 ms (MAC-005 gets looser); uplink about 4.4 symbols per ms (less than A) and more buffering for the per-frame MCS change; 30 km still does not fit |
| C | Range-adaptive frame: 1 ms at less than 5 km, 2 ms up to 15 km, 4 ms up to 30 km, set by the measured delay | Optimal overhead for each range; one design | More states to verify; the frame length change must be glitch-free |

Recommendation: **C**, with the 1 ms frame as the default and the guard computed from the measured round-trip
delay (timing advance estimated from the preamble). MAC-007 is restated as "1 Mbit/s uplink at an MCS of QPSK 1/2
or higher, 300 kbit/s at the lowest MCS". The RC option (MAC-008) rides in the same uplink slot with priority.

## T-04 Numerology (G-12, G-25)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Constant 78.125 kHz sub-carrier spacing; FFT 64/128/256/512 for 5/10/20/40 MHz | One symbol time (12.8 us) for all bandwidths; matches 802.11ax, so the WiFi prototype modes are close; Doppler tolerance independent of bandwidth | FFT 64 at 5 MHz means only a few data tones (about 48); CP overhead in time is fixed |
| B | Two spacings: 78.125 kHz (default) and 39 kHz (long range, long CP for multipath) | Better multipath tolerance at long range | 39 kHz halves the Doppler margin (still adequate to about 1.7 kHz); two modes to verify; the CP tolerance is rarely the limit for a drone link |
| C | 156 kHz spacing (802.11n-like 312 kHz / 2) | Highest Doppler tolerance (supports 256QAM at 3.5 kHz) | Shorter symbol 6.4 us, so a large CP fraction for the same delay spread; less efficient |

Recommendation: **A** with FFT 64 added to PHY-001 (and a 78.125 kHz default). Run an S (simulation) item for
the ICI loss against the maximum Doppler and restrict 256QAM to Doppler below 1 kHz (G-25).

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

## T-06 Video codec (G-11)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | HEVC (H.265) with a custom low-latency slice encoder | Best compression at 1080p to 4K (roughly 30 to 50% below AVC at equal quality); the vendor hard cores support it (waybeam, Xilinx VCU) | Several patent pools and royalty exposure; encoder complexity is high |
| B | AVC (H.264) | Lower complexity and area; simplest low-latency encoder; mature hardware decoders everywhere | Higher bit rate (about 1.5x), so more link margin or lower quality at range; also in patent pools (though the older and better understood) |
| C | AV1 (or a royalty-free intra-heavy codec such as JPEG-XS for the lowest latency) | AV1: royalty-free by declaration; JPEG-XS: sub-millisecond latency and slice-based by design | AV1 low-latency hardware encoders are heavy; JPEG-XS needs 3 to 10x the bit rate of AVC at similar quality and does not fit the link at long range |

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

## T-08 ASIC partitioning, process, integration (G-23)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | One die in 22 nm FD-SOI (RF + baseband + encoder + CPU) | Smallest board and lowest BOM; FD-SOI has good RF and low-power digital | Highest NRE and risk; IP availability (RF, CPU, MIPI) in the node; yields |
| B | Two dice: RF transceiver in a mature RF node (e.g. 40 nm or 28 nm RF-CMOS or 22FDX) and a digital SoC in 12/16/22 nm, with a high-speed digital interface (JESD204 or LVDS) | Each die in its best node; the RF die can be a first tape-out (test chip A1); lower risk; second source possible | Interface power (about 100 to 200 mW); two packages; larger board |
| C | System-in-package: off-the-shelf transceiver plus custom baseband ASIC | Fastest; lowest RF risk | Not a "chip"; BOM cost and the transceiver vendor dependency; calibrations limited to what the vendor exposes |

Recommendation: **B for the first product, with C as the bridging step** (the FPGA prototype is already C), and
A as a later cost-down. The RF die test chip (A1) in the plan is consistent with B.

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
| A | AD9361/AD9364 (70 MHz to 6 GHz, up to 56 MHz) | Cheapest, well supported (openwifi, ADI HDL); known | Limited DPD/observation support; no built-in tracking calibrations beyond basics |
| B | ADRV9002 (up to 40 MHz, DPD and tracking calibration support) | Closest to the target calibration architecture (`03`); lower power | Newer, more complex boot and API; cost; check licences of the reference firmware |
| C | LMS7002M (LimeSDR) | Open hardware docs; flexible | Fewer vendor calibration features; supply |

Recommendation: **A for the first bench link (fast) and B for the calibration work** (CAL-005 DPD with an observation
path). Keep the HAL (SW-002) so that both can be used.

## T-13 Antenna and diversity

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | 2 omni antennas on the air unit, 2 on the ground (spatial diversity, MRC) | Simple; robust to shadowing and polarisation mismatch | Limited gain (about 3 dB from MRC only) |
| B | Ground switched-beam patch array (4 beams, 90 degrees each) plus 1 omni for acquisition | +8 to 10 dB gain; no moving parts; fits Class X | Cost; the beam choice per frame must be fast (ANT-008); hand-held tolerance |
| C | Ground phased array (4 to 8 elements, beamforming) | Tracking without pointing; interference nulling | Calibration complexity (CAL-010); cost; power |

Recommendation: **A for P1 and the base product, B as the long-range accessory**, C as a research item on the SDR
(it exercises CAL-010).

## T-14 DPD architecture

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | No DPD: fixed back-off (6 to 8 dB) | Simple | Back-off costs 2x or more PA power; 256QAM unusable; ties to T-02 |
| B | Memory-polynomial DPD with an observation receiver (adapted in the background) | Standard practice; allows 3 to 4 dB back-off; fits the obs path in `03` | Needs an observation receiver (area, power); convergence logic; VSWR sensitivity (hence CAL-008) |
| C | Look-up-table DPD with a slow feedback loop and temperature/VSWR bins | Low complexity and power | Less accuracy; large tables per bin; does not track fast changes |

Recommendation: **B in P1/P2** with the C table as the fast fallback while B converges (the calibration data store in
`03` holds seed coefficients per bin). A is acceptable for 25 dBm class products.

## T-15 Hopping strategy

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Static channel plus adaptive channel selection (ADA-001, ADA-002) | Simplest; uses the full TDD design; best latency | Slow reaction to bursty interference; regulatory limits on fixed channels for some regions |
| B | Fast frequency hopping on every super-frame | Excellent against narrowband interference and jammers; robust | PLL settling each time (RF-006); calibration per channel; harder timing; consumes airtime |
| C | Hybrid: static video channel with fast hopping on the control/telemetry channel and a robust out-of-band beacon on another band | Video keeps latency; control survives interference; link recovery (ADA-004/005) | Two radios or a time-multiplexed transceiver; more states |

Recommendation: **C**, with the video on a static adaptive channel and the control/beacon on a separate, hopped
band (900 MHz when fitted, otherwise 2.4 GHz). The fast hop of the video (B) is a fallback in anti-jam mode (SEC-004).

## T-16 FEC code

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | LDPC (quasi-cyclic, 802.11n/ax-like short and medium blocks) | Near-capacity performance; parallel decoder suitable for FPGA/ASIC; known standard codes | Short-block performance degrades; decoder iteration latency |
| B | Polar codes (5G NR control channel style) with CRC-aided list decoding | Excellent at short block lengths (the slice header, control) | Decoder latency and area for list decoding; patent licences from a few parties [not verified] |
| C | Convolutional (K=7, Viterbi) plus Reed-Solomon / packet-level FEC (wfb-ng style) | Simple; low latency per bit; proven | About 2 dB worse than LDPC at long blocks; the packet-level FEC adds the latency of a whole block |

Recommendation: **A for the data**, **B (or the same LDPC with a short code) for the control/feedback burst**; keep C's
packet-level FEC as an optional outer code across slices in cruise mode (LAT-006).

## T-17 Clocking, genlock and timing (G-16)

| Option | Description | Pros | Cons |
|---|---|---|---|
| A | Free-running ground-unit display, slice buffer absorbs drift; periodic frame drop/repeat | Simple | Visible glitches; latency drifts by up to a frame between corrections |
| B | Ground-unit display scan-out is locked to the received frame timing (display PLL adjusts the pixel clock in tiny steps) | No glitches; constant latency | Needs a display that accepts a variable pixel clock (OLED/DSI custom timing); a few lines of buffer |
| C | Air unit slaves the sensor frame rate to the ground display via the uplink (sensor FSIN) | Both ends aligned; lowest buffer | Needs the uplink loop and sensor support; interacts with MAC |

Recommendation: **B**, plus the FSIN alignment of the sensor to the TDD frame on the air unit (`03` section 7).
C is a later option for fixed-rate displays.

---

## Summary of recommendations

| Study | Recommendation |
|---|---|
| T-01 | Range classes S/X/L, per region |
| T-02 | Three programmable power classes; 33 dBm separate SKU |
| T-03 | Range-adaptive TDD frame, timing advance |
| T-04 | 78.125 kHz sub-carrier spacing, FFT 64 to 512 |
| T-05 | Frequency division with race mode; restate SYS-009 |
| T-06 | AVC baseline plus HEVC quality mode; start licensing review |
| T-07 | Slice UEP and intra-refresh; two-layer option; JSCC research |
| T-08 | Two dice for the first product |
| T-09 | Open stack with a signed RF limiter |
| T-10 | Certified BLE/RID module |
| T-11 | Wifi (P0), clean-room custom baseband (P1) |
| T-12 | AD9361 first, ADRV9002 for the calibration work |
| T-13 | Diversity base, switched-beam ground accessory |
| T-14 | Memory-polynomial DPD with LUT fallback |
| T-15 | Static adaptive video channel, hopped control, separate beacon |
| T-16 | LDPC data, short code or polar for control |
| T-17 | Display locked to received timing |
