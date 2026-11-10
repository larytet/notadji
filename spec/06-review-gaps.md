# 06 - Review: Gaps, Contradictions and Assumptions

Status: DRAFT, pass 3 (re-read of documents 00 to 05).
Method: (1) a script checked IDs (156 requirements, no duplicates, no dangling references, every row has a
verification method); (2) a manual re-read cross-checked numbers between requirements, the link budget
(`scripts/link_budget.py`) and the latency/power budgets in `02`.

Severity: **Critical** (the spec cannot be satisfied or is physically inconsistent), **High** (a decision is
needed before the design can proceed), **Medium** (clarify), **Low** (editorial).
"Resolution" points to the trade study in `07` where there is a real choice.

## 1. Contradictions (the spec disagrees with itself or with physics)

| ID | Sev. | Finding | Evidence | Resolution |
|---|---|---|---|---|
| G-01 | Critical | SYS-003 (10 km at 5.8 GHz, 5 dBi antennas, 6 dB margin, 1080p60) does not close. | `02` section 1: no MCS with 6 dB margin at 5/5 dBi; with 2-branch MRC only BPSK 1/2 (about 6.8 Mbit/s). 1080p60 needs about 10 to 20 Mbit/s. | T-01 |
| G-06 | High | SYS-005 (6.0 W at maximum power), RF-010 (33 dBm) and PWR-004 (30% PA efficiency) cannot all hold. | 33 dBm is 2.0 W RF; at 30% efficiency the PA alone burns 6.65 W, so 9.3 W at the input (`02` section 3). At 30 dBm the total is 5.5 W only if PAE is 30% at that operating point (6.3 W at 25%). PWR-004 states 30% at 24 dBm, a different operating point, so the margin is thin. (Pass 3 first wrote this as Critical using 25% PAE and including the sensor; corrected in pass 5.) | T-02 |
| G-20 | Critical | SYS-009 (20 co-located links at 2.4 GHz, 40 at 5.8 GHz) contradicts the bandwidths in PHY-002. | 2.4 GHz band is 83.5 MHz: 4 channels at 20 MHz, 8 at 10 MHz, 16 at 5 MHz. 5.8 GHz (5725-5850) is 125 MHz: 6, 12, 25 channels. Even at 5 MHz neither number is reachable by frequency division alone. | T-05 |
| G-13 | High | The TDD guard times (2 x 10 us, MAC-001, RF-009, section 4 of `02`) ignore propagation delay. | Round-trip delay is 100 us at 15 km and 200 us at 30 km (3.33 us per km each way). The DL to UL guard must cover about 2 x one-way delay, i.e. 10% to 20% of a 1 ms super-frame, so the 0.9 duty and the net rates in `02` are optimistic at long range. A timing-advance mechanism is also missing. | T-03 |
| G-08 | High | MAC-007 (uplink telemetry 1 Mbit/s) does not fit the uplink slot at low MCS. | `02` section 4: 5 to 6 symbols per ms; at 20 MHz BPSK 1/2 this is about 0.67 Mbit/s raw, before the per-ms feedback (MAC-004) and RC (MAC-008). The uplink must also close at range at the lowest MCS with the ground unit's (lower) TX power. | T-03 |
| G-12 | High | PHY-001 (FFT 128/256/512), PHY-002 (5 MHz mandatory) and PHY-003 (sub-carrier spacing 60 kHz or more) disagree. | 78.125 kHz spacing needs FFT 64 at 5 MHz, 128 at 10 MHz, 256 at 20 MHz, 512 at 40 MHz. FFT 64 is not listed; FFT 128 at 5 MHz gives 39 kHz, below PHY-003. | T-04 |
| G-25 | Medium | PHY-003 claims 0.5 dB ICI penalty at 3.5 kHz Doppler; PHY-004 allows 256QAM. | ICI power for spacing 78 kHz and Doppler 3.5 kHz is about -22 dB relative to the signal, which is fine for QPSK/16QAM but is a limit of about 22 dB SIR for 64QAM and below the 28 dB or more that 256QAM needs. The 0.5 dB claim is unverified. | T-04, run S |
| G-18 | Medium | ENV-001 specifies the full performance range as 0 to +40 C, but `03` section 8 verifies EVM from -10 to +50 C and cold start at -20 C. | | Align: specify performance over -10 to +50 C (or test only inside the stated range). |
| G-21 | Medium | MAC-002 forbids contention-based access while ADA-009 requires listen-before-talk where regulation demands it. | Not necessarily contradictory: ETSI frame-based equipment rules allow a fixed frame period with a short idle period for channel sensing [not verified, check EN 300 328 v2.2.2 clause on FBE]. A 1 ms super-frame with an idle time of at least 5% (at least 100 us) would also provide the DL/UL guard. | T-03 |
| G-03 | Medium | RF-020 sensitivities are inconsistent with a single noise model, and RF-021 noise figures. | Ideal sensitivity = -101 dBm (20 MHz) + NF + required SNR + implementation loss. With NF 4 dB, BPSK 1/2 SNR 2 dB and 2 dB implementation loss: -93 dBm (RF-020 asks -94). The 16QAM 3/4 and 64QAM 3/4 figures are 4 to 6 dB looser than the same model gives (-80.5 and -74). | Replace the table by the formula and a stated implementation loss budget; see revised RF-020. |

## 2. Gaps (something needed is missing)

| ID | Sev. | Gap | Proposed action |
|---|---|---|---|
| G-02 | High | Real-world propagation is not in the budget: ground reflection (two-ray) at low altitude, Fresnel clearance, foliage, rain, body shadowing, polarisation mismatch. The "6 dB fade margin" has no defined statistics. | Define scenarios (open field at 100 m altitude, urban, forest) and a margin per scenario with an outage probability. |
| G-04 | High | ETSI (and other regions) performance is not specified; power limits in the EU are about 20 dBm EIRP. Headline range applies to FCC-type regions only. | Add a per-region range table; consider TX-power-independent requirements (sensitivity, EVM). |
| G-05 | Medium | VID-007/VID-008 give encoder/decoder latency for 1080p60 only, but SYS-001 has a 1080p120 target and the budget in `02` assumes 1.2 ms each. | Add requirements scaled per frame rate. |
| G-07 | High | SEC-005 (locked RF parameters) conflicts with the open-source and open-documentation ethos (SW-003). Regulators expect that users cannot exceed power/band limits (FCC software security guidance for U-NII devices [not verified, check KDB 594280]). | Decide which part of the stack is closed or signed (T-09). |
| G-09 | High | Four repositories (improver, docs, realtek-wlan, LimeSDR-Mini) have no licence file, one is non-commercial (OpenIPC decoder), one has a field-of-use clause (RubyFPV), openwifi is AGPLv3. | Keep as behavioural reference only; record the policy as a requirement (below). |
| G-10 | High | No clean-room / IP policy and no freedom-to-operate analysis against patents (video-link, OFDM, LDPC, rate control). | Add a requirement, budget a patent search before P2 funding. |
| G-11 | High | HEVC (VID-003) carries patent-pool royalties (several pools) for products; AVC has a pool too; AV1 is royalty-free by declaration but hardware encoders with sub-frame latency are less mature. | T-06 (codec choice); add a licensing requirement. |
| G-14 | Medium | There is no verification plan or traceability matrix: 83 of 156 requirements are not referenced by any other document, and the test equipment, the G2G measurement rig (LAT-001) and the production test are not described. | Write `08-verification-plan.md` in the next iteration; generate the matrix from `01`. |
| G-15 | Medium | The 8 ms sensor readout used in `02` is an assumption (many sensors at 1080p60 read out in about 16 ms; some do 4 ms). The slice readout term scales with it. | Select the sensor class; add a requirement for readout time at each mode. |
| G-16 | Medium | No requirement for matching the clocks of the sensor and the display. A line-synchronised scan-out (VID-015) needs genlock or periodic frame-timing adaptation; otherwise the latency drifts by up to one frame. | Add a requirement (frame-rate locking at the ground unit, drift correction below 1 ppm equivalent without visible glitches). |
| G-17 | Low | Thermal thresholds in `03` are placeholders and not consistent with the PA datasheet. | Fill after PA selection. |
| G-19 | Medium | REG-002 (Remote ID over Bluetooth 5 LR or WiFi) is mandatory but the PHY requirements have no Bluetooth LE PHY (GFSK, coded PHY) and no WiFi beacon mode in the ASIC; PHY-013 WiFi mode is P1 only. The air unit also needs position data (GNSS or flight controller) for RID. | Add a BLE-compatible PHY mode to the SDR modem; or use a separate BLE chip (T-10). |
| G-22 | Medium | Missing topics: audio; multiple cameras/switching; goggles/optics scope; reliability (MTBF, lifetime, field return rate); manufacturing and calibration time per unit; logging privacy; accessibility of the pilot display for link quality. | Add requirements or an explicit "out of scope" statement (A-01). |
| G-23 | Medium | ASC-002/ASC-004/ASC-005: integrating a 2x2 RF transceiver, 4K encoder and decoder, ISP, CPU and DDR PHY in 40 mm2 at 22/28 nm and USD 12 is optimistic [TBV]; NRE and volume assumptions are missing. | Area and cost estimate with block-level numbers (T-08). |
| G-24 | Medium | ADA-004 (band hop re-establishment in 300 ms) needs a rendezvous protocol after link loss: both ends must predict each other's hop schedule with clock drift. | Specify the rendezvous scheme and the out-of-band beacon (ADA-005) cadence. |
| G-27 | Medium | SYS-009 packs 6 links of 20 MHz into the 125 MHz of the 5.8 GHz band (120 MHz) but no adjacent-channel rejection or near-far requirement existed (found in pass 6). | Added RF-029 in rev 0.3; the near-far analysis (two units 10 m apart, ACLR -45 dBc) is still to be done. |
| G-28 | Medium | The link-budget rate model used 242 data tones and a fixed 0.9 duty, ignoring PHY-001 tone counts and the range-dependent guard of MAC-001; net rates were 5 to 10% optimistic and 10 MHz mode (8 Mbit/s) falls below the 10 Mbit/s of SYS-003 (found in pass 6). | Script and `02` corrected in rev 0.3; 10 MHz mode is a fallback/race mode (T-01). |
| G-26 | Low | MAC-002 had a wrong cross-reference (FHSS-ADA-001). Fixed in `01`. | done |

## 3. Assumptions made in this specification

| ID | Assumption | Reason |
|---|---|---|
| A-01 | The goggles/optics/display are out of scope; the ground unit outputs HDMI/DP/DSI. | The request names glasses, but the technical gap is the link and the chip. A goggles design can be added as a separate document. |
| A-02 | "Antenna signal front shape" means the antenna radiation pattern (beam shape) and the wavefront shaping with several elements. | The wording was ambiguous. Alternative reading: the RF front-end signal shape (spectral mask, burst envelope), which is covered by RF-012 to RF-015. |
| A-03 | "Rall time" means the TX burst rise/fall time and the sensor rolling-shutter roll time. | Ambiguous; both are covered (`03` section 7). |
| A-04 | "Diapozns" means frequency bands/ranges; "band hoping" means frequency hopping and band switching. | |
| A-05 | DJI performance figures are our estimates from public information and are not specifications. | |
| A-06 | Regulatory statements (FCC 15.247/15.407, ETSI EN 300 328/301 893, EN 18031, FBE timing) are from memory and need verification by regulatory counsel. | |
| A-07 | PA efficiency, sensor readout and ASIC cost figures are targets [TBV]. | |
| A-08 | Cyclic prefix, sub-carrier spacing and LDPC choices in `02` are starting points for the trade studies. | |

## 4. Changes required in `01` (to be applied in pass 4, after the trade studies)

1. SYS-003: restate range per antenna class and region (G-01, G-04).
2. SYS-005/RF-010/PWR-004: replace by consistent power classes (G-06).
3. SYS-009: restate as a number of simultaneous links per channel plan (G-20).
4. PHY-001/002/003: one consistent numerology table (G-12, G-25).
5. MAC-001/007, RF-009: guard time, timing advance and uplink capacity per range class (G-08, G-13).
6. RF-020: formula plus implementation loss budget (G-03).
7. New requirements: IP/clean-room policy (G-10), codec licensing (G-11), genlock (G-16), BLE PHY (G-19),
   verification plan (G-14), audio and other missing items or explicit exclusions (G-22).

## 5. Resolution status after pass 5 (SRS rev 0.2)

| ID | Status | How |
|---|---|---|
| G-01 | Resolved | SYS-003 restated as range classes S/X/L (T-01) |
| G-02 | Open | Per-scenario real-world margins still to be defined (two-ray, foliage, rain); needs a propagation study |
| G-03 | Resolved | RF-020 uses one noise model; `scripts/link_budget.py` follows it |
| G-04 | Partly resolved | ETSI range stated in SYS-003 (about 2.5 km Class L); per-region table still to be written |
| G-05 | Open | Encoder/decoder latency per frame rate (VID-007/008) not yet scaled |
| G-06 | Resolved | SYS-005 per power class, PWR-004 at the 27/30 dBm points (T-02); feasibility depends on the PA study |
| G-07 | Resolved | SEC-005 hardware-locked signed limiter, open stack (T-09) |
| G-08 | Resolved | MAC-007 restated per MCS (T-03) |
| G-09 | Resolved | REG-005 licence register and clean-room policy |
| G-10 | Resolved | REG-005 clean-room policy and freedom-to-operate search |
| G-11 | Resolved | VID-003 baseline AVC; VID-017 licensing review |
| G-12 | Resolved | PHY-001 includes FFT 64; constant 78.125 kHz (T-04) |
| G-13 | Resolved | MAC-001 guard from propagation delay; MAC-011 timing advance (T-03) |
| G-14 | Resolved | `08-verification-plan.md`, `09-traceability-matrix.md`, TST-001/002 |
| G-15 | Open | Sensor class and readout time still to be selected |
| G-16 | Resolved | VID-018 display locked to received timing (T-17) |
| G-17 | Open | Thermal thresholds wait for the PA selection |
| G-18 | Resolved | ENV-001 full-spec and operating ranges |
| G-19 | Resolved | REG-002 certified RID module (T-10) |
| G-20 | Resolved | SYS-009 by frequency plan (T-05) |
| G-21 | Resolved | MAC-001 guard doubles as FBE idle period; wording to be checked with counsel (A-06) |
| G-22 | Partly resolved | SYS-010 scope exclusions, VID-019 audio; reliability and manufacturing requirements still missing |
| G-23 | Open | Die area and cost still unproven; ASC-004 now per die |
| G-24 | Open | Rendezvous protocol after link loss still to be specified |
| G-25 | Resolved | PHY-003 restricts 256QAM to Doppler below 1 kHz |
| G-26 | Resolved | Cross-reference fixed |
| G-27 | Partly resolved | RF-029 added; near-field analysis open |
| G-28 | Resolved | Rate model corrected (rev 0.3) |

## 6. Updates since pass 5 (SRS rev 1.8)

Statuses in section 5 are as of rev 0.3. Changes made by the second goal (iterations in `07`, audit in `12`):

| ID | Status now | How |
|---|---|---|
| G-05 | Resolved | VID-007/008 per frame rate (rev 1.8) |
| G-08 | Resolved differently | Split-band uplink (MAC-012) gives 11.0-17.0 dB margin; in-band TDD fallback sized from MAC-007 (T-03) |
| G-13 | Resolved | MAC-001 re-derived (guard from range, frame 1/2/4 ms); only the fallback mode needs it |
| G-15 | Resolved | IF-002 sensor readout time 8 ms (60 fps) and 4 ms (120 fps); sensor selection still open |
| G-19 | Resolved | REG-002 via F3586-22 module |
| G-20 | Resolved | SYS-009 split into race and long-range counts (T-05) |
| G-24 | Partly resolved | The out-of-band uplink channel (ADA-005, MAC-012) is the rendezvous channel; the protocol is still to be specified |
| G-27 | Resolved (analysis) | Near-far table in `07` T-05, RF-029 restated; receiver tolerance still to be measured |
| G-02, G-17, G-22, G-23 | Open | Propagation study, PA datasheet, reliability requirements, ASIC cost model |
| New (second goal) | See `12` section 3 (F-1 to F-17) and the feasibility register | Errors found by recomputation |
| G-04 | Resolved | Capability ranges plus a derived per-profile table (`02` section 1.2, REG-008); real profile values are data for counsel |
