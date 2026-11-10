# 08 - Verification Plan

Status: DRAFT, pass 5 (closes G-14). The requirement-to-test-group mapping is generated into
`09-traceability-matrix.md` by `scripts/trace_matrix.py`. Verification methods: T test, A analysis, I inspection,
D demonstration, S simulation.

## 1. Test groups

| Group | Covers | Method and equipment | Where |
|---|---|---|---|
| TG-LAT latency rig | LAT-*, SYS-001, SYS-002, VID-007/008 | LED on the camera view driven by the rig, photodiode on the display; or a 1000 fps camera seeing both; per-stage timestamp taps (LAT-004) logged over the debug port; 10 000 frames per run; report mean, p99, p99.9 | Lab, then outdoors |
| TG-PHY baseband conformance | PHY-* | Bit-exact C/Python model versus RTL (S); loop-back and channel emulator with Doppler, delay spread and fading (Rician, Rayleigh, two-ray); BER/PER curves per MCS | Lab |
| TG-MAC protocol | MAC-*, ADA-002/003/004 | Two-unit testbed with a programmable attenuator and delay line (propagation delay up to 100 us); timing advance and guard checks; hop and band-switch timing with a logic analyser on the PA enable | Lab |
| TG-RF conducted RF | RF-* | Vector signal analyser (EVM, ACLR, mask, LO leakage, IQ image), real-time spectrum analyser (hop settling, ramp), signal generator with fading (sensitivity), noise-figure meter, harmonic measurement, time-gated measurements for ramp (RF-012) | RF lab |
| TG-ANT antenna and VSWR | ANT-*, CAL-006/008 | Mismatch tuner or open/short/attenuator set, network analyser for the coupler, anechoic chamber or open-area test site for patterns | RF lab and range |
| TG-ADA spectrum and hopping | ADA-* | Interference generator (WiFi, ELRS, wideband), radar signal generator for DFS (where fitted), spectrum scan accuracy | Lab |
| TG-CAL calibration | CAL-* | Chamber sweeps with EVM/ACLR logs; cold start; DPD convergence timing; calibration status telemetry | RF lab, chamber |
| TG-THM thermal | THM-* | Chamber, thermocouples, IR camera, hover-without-airflow soak, hardware trip injection | Thermal lab |
| TG-PWR power | PWR-*, SYS-005 | Power analyser at the input (1 kHz or faster), ESC ripple injector, surge generator | Lab |
| TG-SEC security | SEC-* | Protocol review, replay/forgery tests, fuzzing, secure-boot attack tests, signed-table tamper tests | Lab, third-party review |
| TG-REG regulatory | REG-* | Accredited test house (FCC, ETSI, ISED), Remote ID conformance test, export review, EN 18031 assessment | External |
| TG-ENV environmental | ENV-* | Random-vibration shaker with a live link, shock table, ESD gun, humidity chamber, EMI scan with receiver desense (ENV-007) | Environmental lab |
| TG-VID video pipeline | VID-* | Reference video set (high-motion, low-light, fine detail), objective metrics (PSNR, VMAF), loss injection, genlock drift test over 10 minutes | Lab |
| TG-SW / TG-IF | SW-*, IF-* | Integration tests against flight controller (MSP, MAVLink) and displays; update/rollback tests | Lab |
| TG-SYS system and range | SYS-003, SYS-008, SYS-009 | Range flights per class (S, X, L) in open field, urban and forest; multi-link tests on a site with a defined channel plan | Field |
| TG-PRO / TG-ASC | PRO-*, ASC-* | Design reviews, lint/CDC reports, DFT coverage, production test time | Design |

## 2. Staged execution

| Stage | Tests | Gate |
|---|---|---|
| P0 | TG-LAT on commodity WiFi (baseline), TG-SYS range flights of the baseline | Latency floor and range data replace the vendor figures in `05` (observation 3) |
| P1a | TG-PHY (model versus RTL), TG-RF on the SDR board, TG-LAT with the custom modem | SYS-002 (30 ms) |
| P1b | TG-MAC, TG-CAL, TG-ANT, TG-ADA | Calibration loops closed; hop and TDD timing met |
| P1c | TG-VID with the custom encoder, TG-THM, TG-PWR on the prototype | SYS-001 within 20% |
| P2 | All groups on silicon; TG-REG, TG-ENV, TG-SEC | Release |

## 3. Pass criteria and statistics

- Latency: means over at least 10 000 frames; p99 and p99.9 reported; temperature recorded.
- Sensitivity: PER 1e-3 per slice measured with at least 10 000 slices per point (the 95% confidence limit is then
  about 3e-4 to 1.8e-3); a point passes if the upper confidence bound meets the requirement.
- Range: at least 5 flights per class and scenario; margin derived from logged RSSI and SNR (SW-005).
- RF: three units minimum across temperature extremes before any figure is released.

## 4. Production test (ASC-003)

Target 60 s or less per unit: boot and self-test (10 s), loop-back RF test with the internal TX to RX path and
the calibration load (20 s), one-point conducted power and EVM check at 2 channels (20 s), serial number and
region-lock provisioning with signed tables (10 s). Calibration data is written to non-volatile memory with a
CRC (CAL-001).

## 5. Open items

- Accredited test-house selection and lead times.
- G2G rig design and calibration against a reference (TST-002).
- Channel emulator choice (hardware emulator versus a software channel model on an SDR).
