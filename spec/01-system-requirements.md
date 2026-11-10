# 01 - System Requirements Specification (SRS)

Status: DRAFT, revision 0.2 (pass 5; applies the trade-study results of `07` to the pass-1 text). See `00-overview.md` for conventions (Priority M/S/O, Phase P1/P2, Verification T/A/I/D/S).

## 1. System scope

```
 Camera sensor -> ISP -> Encoder -> Framer/FEC -> Modem (TX) -> RF front end -> Antenna
                                                                                   |
 Display <- Decoder <- Deframer/FEC <- Modem (RX) <- RF front end <- Antenna  <----+
                                  ^                                  
                                  +-- uplink: control, CSI feedback, telemetry
```

The system is a bidirectional TDD link. The downlink carries video, the uplink carries link feedback,
telemetry and optional control frames. The air unit and the ground unit use the same silicon, configured by role.

## 2. Top-level targets

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| SYS-001 | The link shall deliver live video from AU to GU with G2G latency (mean) of 20 ms or less at 1080p60 and 12 ms or less at 1080p120. [TBV] | M | P2 | T |
| SYS-002 | The FPGA prototype shall reach G2G of 30 ms or less at 1080p60 (mean) as the first milestone. | M | P1 | T |
| SYS-003 | The link shall sustain 1080p60 video (at least 10 Mbit/s net) with at least 6 dB free-space margin in these range classes (30 dBm conducted, 2-branch MRC on the ground unit, lowest MCS that meets the rate): **Class S** 5 km, 5.8 GHz, 20 MHz, 5/5 dBi antennas; **Class X** 10 km, 5.8 GHz, 20 MHz, 10 dBi ground antenna; **Class L** 14 km, 2.4 GHz, 20 MHz, 5/5 dBi. Ranges under ETSI EIRP limits are specified separately (Class L is about 2.5 km at 20 dBm EIRP). Real-world margins per scenario are in `02` (G-02). Revised by T-01. | M | P2 | A,T |
| SYS-004 | The video shall degrade gracefully (lower resolution/quality, never a frozen frame longer than 100 ms) as SNR drops, down to the lowest MCS. | M | | T |
| SYS-005 | Air unit total DC input power, excluding the camera sensor module: at most 3.5 W at 25 dBm, 4.0 W at 27 dBm and 6.0 W at 30 dBm conducted average output (the 30 dBm case needs PA PAE of about 28% or better). A separate 33 dBm SKU is allowed up to 10 W. [TBV] Revised by T-02. | M | P2 | T |
| SYS-006 | Air unit mass, including the antennas' feed cables and the heatsink, shall not exceed 25 g. | S | P2 | I |
| SYS-007 | Ground unit shall operate from a 1S-6S battery for at least 3 h at the nominal consumption. | S | | T |
| SYS-008 | One ground unit shall pair with up to 4 air units and receive one (or two, picture-in-picture, O) at a time. | S | | D |
| SYS-009 | Co-located operation by frequency plan: at least 6 simultaneous links at 20 MHz and 12 at 10 MHz in 5.8 GHz; 4 at 20 MHz and 8 at 10 MHz in 2.4 GHz; a race mode with 5 MHz channels giving 25 links in 5.8 GHz and 16 in 2.4 GHz at reduced rate and range. Beyond these numbers the links shall degrade gracefully through ADA-001 and power control. Revised by T-05. | M | | T |
| SYS-010 | Out of scope for version 1: goggles optics and head tracking (the ground unit outputs HDMI/DP/DSI), multi-camera switching. Audio is optional (VID-019). See assumption A-01. | M | | I |

## 3. Video (VID)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| VID-001 | Input formats: 1080p at 30, 50, 60, 90, 100, 120 fps; 720p up to 240 fps; 4K at 30 and 60 fps (4K may exceed the latency in SYS-001 by up to 1.5 frame times). | M | P2 | T |
| VID-002 | Sensor interface: MIPI CSI-2, 4 lanes, D-PHY 2.5 Gbit/s per lane minimum. | M | | I |
| VID-003 | Codecs: AVC (H.264) high profile as the baseline in P1 and P2; HEVC (H.265) main profile as the quality mode in P2. The encoder architecture shall be codec-agnostic at slice level. Revised by T-06. | M | | T |
| VID-004 | The encoder shall be slice-based with at least 8 slices per frame, each slice independently decodable and independently protected. | M | | T |
| VID-005 | No I-frames in steady state. The encoder shall use rolling intra-refresh (column or row wave) with a refresh period of 30 frames or less. | M | | T |
| VID-006 | Rate control: per-slice constant bit budget with a rate buffer of at most 1 slice, retargeted every slice from the MCS in force. | M | | T |
| VID-007 | Encoder pipeline latency (first pixel in to first slice bits out) of 2.0 ms or less at 1080p60. | M | P2 | T |
| VID-008 | Decoder pipeline latency (first slice bits in to first line out) of 2.0 ms or less at 1080p60. | M | P2 | T |
| VID-009 | Video bit rate range: 1 to 80 Mbit/s, adjustable per frame. | M | | T |
| VID-010 | Loss concealment: a lost slice shall be concealed from the previous frame (motion-compensated, O) and recovered by intra-refresh within 30 frames. | M | | T |
| VID-011 | Unequal error protection: slice header and parameter data shall have at least 6 dB more protection than residual data. | S | | T |
| VID-012 | 10-bit input and HDR10/HLG pass-through. | O | P2 | T |
| VID-013 | Optional on-air stabilisation using gyro data (electronic image stabilisation) with an added latency of at most 1 frame. The mode shall be switchable so a zero-added-latency path exists. | O | | T |
| VID-014 | Optional local recording at 100 Mbit/s or higher to SD/NVMe, independent of the radio link (full quality copy on the air unit). | S | | D |
| VID-015 | The ground unit shall output HDMI 2.0, DisplayPort and/or MIPI DSI with a fixed line-synchronised scan-out (display starts scanning a frame before it is completely decoded). | M | | T |
| VID-016 | On-screen display overlay (OSD) in the ground unit, MSP DisplayPort and MAVLink sources. | M | | D |
| VID-017 | Codec licensing: a royalty and patent-pool review for AVC and HEVC shall be completed before P2 funding; the product shall ship with the pool licences or the codec shall be disabled in that region. | M | P2 | I |
| VID-018 | Display synchronisation: the ground unit shall lock the display scan-out to the received frame timing (display pixel clock steered, residual drift 1 ppm equivalent or better) so that latency varies by no more than 1 ms over a 10 minute flight and no visible glitch is produced. Revised by T-17. | M | | T |
| VID-019 | Optional audio: 48 kHz, 32 to 128 kbit/s, end-to-end latency 20 ms or less, lip-sync within 40 ms of the video. | O | P2 | T |

## 4. Latency and jitter (LAT)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| LAT-001 | G2G latency shall be measured with a high-speed camera or photodiode method at 1000 fps or better. | M | | T |
| LAT-002 | Latency jitter: p99 shall be within +3 ms and p99.9 within +8 ms of the mean at the nominal MCS. | M | | T |
| LAT-003 | Air-interface latency (first bit of a slice at the modem TX input to the same slice at the modem RX output), excluding retransmissions, shall be 2.5 ms or less. | M | P2 | T |
| LAT-004 | The system shall keep a latency budget table (see `02`) and each block shall report its measured latency via a timestamp tap. | M | | T |
| LAT-005 | All stages shall be cut-through (process data as it arrives, no store-and-forward of a whole frame). | M | | I |
| LAT-006 | A latency-versus-robustness switch shall be provided: a "race mode" (no retransmission, minimum interleaving) and a "cruise mode" (up to 2 sub-frame retransmissions, deeper interleaving, up to 40 ms G2G). | S | | T |

## 5. PHY (PHY)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| PHY-001 | Waveform: OFDM with cyclic prefix, FFT sizes 64, 128, 256 and 512 for 5, 10, 20 and 40 MHz at a constant sub-carrier spacing of 78.125 kHz (FFT 1024 for the optional 80 MHz). Revised by T-04. | M | | S,T |
| PHY-002 | Channel bandwidths: 5, 10, 20, 40 MHz mandatory; 80 MHz optional (P2). | M | | T |
| PHY-003 | Default sub-carrier spacing 78.125 kHz (symbol 12.8 us); cyclic prefix selectable among 1/16, 1/8, 1/4. Maximum Doppler for full-rate operation: 3.5 kHz for BPSK to 64QAM (inter-carrier interference about -22 dB, verified by simulation, G-25) and 1.0 kHz for 256QAM. | M | | S |
| PHY-004 | Modulations: BPSK, QPSK, 16QAM, 64QAM, 256QAM (256QAM in P2 and only when EVM allows). | M | | T |
| PHY-005 | FEC: LDPC with code rates 1/2, 2/3, 3/4, 5/6, codeword lengths adapted to the slice size (short codeword of 648 bits or less for the lowest latency). | M | | S,T |
| PHY-006 | Spatial: 2 RX chains at the ground unit with MRC or better. Two TX chains (STBC or spatial multiplexing) as option in P2. | M(RX) / O(TX) | | T |
| PHY-007 | Pilot design shall track a channel that changes within a frame: midambles/pilots at least every 0.25 ms of airtime at the highest Doppler setting. | M | | S |
| PHY-008 | Carrier frequency offset tolerance: initial 25 ppm; after acquisition residual below 0.1 ppm equivalent. | M | | T |
| PHY-009 | Peak-to-average power reduction (clipping with filtering, or tone reservation) so that the PA output meets RF-014 with at most 4 dB back-off for 64QAM. | M | P2 | T |
| PHY-010 | Frame (burst) preamble acquisition time (detect + AGC settle + sync) shall be 40 microseconds or less. | M | | T |
| PHY-011 | Packet-error-rate target after FEC: 1e-3 per slice at the lowest MCS at the sensitivity in RF-020. | M | | T |
| PHY-012 | The PHY shall run at least 4 MCS adaptation steps per second and up to one per frame (see MAC-005). | M | | T |
| PHY-013 | The numerology shall be programmable (not hard-wired) so that the same engine can run a WiFi-compatible mode (see PRO-001) for the prototype. | M | P1 | I |

## 6. MAC and framing (MAC)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| MAC-001 | Time-division duplex with a super-frame of 1.0 ms by default and range-adaptive lengths of 2 and 4 ms selected from the measured round-trip delay; downlink to uplink ratio about 9:1; the DL to UL guard is at least 2 x the one-way propagation delay plus 2 x the turn-around time (100 us + 20 us at 15 km); the guard shall also provide the idle period required by frame-based-equipment rules where applicable (G-21). Revised by T-03. | M | | T |
| MAC-002 | All airtime is scheduled by the ground unit or by the air unit master. No contention-based access (no CSMA) inside a link. Coexistence with other systems is done by channel selection (ADA-001). | M | | T |
| MAC-003 | Time synchronisation between air and ground within 1 microsecond (derived from the preamble). | M | | T |
| MAC-004 | Uplink slots carry channel feedback (CSI summary, MCS recommendation, RSSI, per-slice ACK/NAK bitmap) with 1 ms or less period. | M | | T |
| MAC-005 | The air unit shall change MCS, power and slice budget within 2 ms of receiving the feedback. | M | | T |
| MAC-006 | Selective retransmission of slices only if the slice deadline (display deadline) can still be met; otherwise drop. | M | | T |
| MAC-007 | Telemetry/control channel carrying MAVLink, MSP and generic serial with latency of 5 ms or less: uplink at least 1 Mbit/s at QPSK 1/2 or higher and at least 300 kbit/s at the lowest MCS; downlink at least 2 Mbit/s. | M | | T |
| MAC-008 | Optional hard real-time RC channel: 1 kHz update, 3 ms one-way latency, link-lost failsafe in 100 ms. | O | | T |
| MAC-009 | Pairing and key exchange without a network connection (see SEC-001). Re-pairing in the field within 10 s. | M | | D |
| MAC-010 | Multi-link: a link shall be able to survive a change of channel (frequency hop) with a gap in video of 1 frame or less. | M | | T |
| MAC-011 | Timing advance: the ground unit shall estimate the round-trip delay from the preamble (resolution 0.1 us) and advance its uplink slot so that the uplink arrives aligned with the air unit's frame; the estimate is also reported to the pilot as range (O). | M | | T |

## 7. RF front end (RF)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| RF-001 | Bands (mandatory): 2400-2483.5 MHz and 5725-5850 MHz. | M | | T |
| RF-002 | Bands (should): 5150-5250 MHz and 5250-5350/5470-5725 MHz where regulation allows (with DFS), and 902-928 MHz and 863-870 MHz long-range variants. | S | P2 | T |
| RF-003 | Bands (optional): 1.2 GHz, 1.3 GHz (amateur), 2.3 GHz (licensed, for professional customers). | O | | T |
| RF-004 | The transceiver shall tune over 70 MHz to 6 GHz in P1 (off-the-shelf SDR) and over the bands in RF-001..RF-002 in P2. | M | | T |
| RF-005 | Channel raster of 1 MHz or finer, channel selection by software. | M | | T |
| RF-006 | Frequency-hop settling time (PLL lock plus calibration restore from cache) of 50 microseconds or less for hops inside a band, and 150 microseconds or less between 2.4 and 5.8 GHz bands. | M | P2 | T |
| RF-007 | Frequency accuracy: 2 ppm or better over temperature (TCXO), with digital correction by AFC from the received preamble. | M | | T |
| RF-008 | Phase noise (integrated 1 kHz to 10 MHz) of 0.6 degrees RMS or better at 5.8 GHz, 0.4 degrees RMS or better at 2.4 GHz. | M | | T |
| RF-009 | TX/RX switching time (TDD turn-around) of 5 microseconds or less. | M | | T |
| RF-010 | Maximum conducted TX power capability 33 dBm, programmable in 0.25 dB steps; standard product power classes are 25, 27 and 30 dBm average output (see SYS-005, PWR-004); the 33 dBm class is a separate SKU for regions that allow it. Region limits are applied by firmware (SEC-005). | M | | T |
| RF-011 | TX power control range of 40 dB or more, with accuracy of +/- 1.0 dB over temperature and frequency after calibration. | M | | T |
| RF-012 | TX power ramp: rise time (10% to 90% of final power) and fall time (90% to 10%) of 2.0 microseconds or less, with no more than 1 dB overshoot, and a TX-off leakage of -70 dBc or better within 5 microseconds of the end of the burst. | M | | T |
| RF-013 | Spectral emission mask: meets FCC 15.247 and 15.407, ETSI EN 300 328 and EN 301 893 for the configured bandwidth, with 3 dB margin. | M | | T |
| RF-014 | TX EVM: -32 dB or better at 64QAM and -35 dB at 256QAM, at 3 dB below maximum power, after DPD. | M | | T |
| RF-015 | ACLR of -45 dBc or better at the adjacent channel after DPD at the average power for 64QAM. | M | | T |
| RF-016 | Out-of-band harmonics below -41.25 dBm/MHz EIRP (FCC general limit) and 2nd/3rd harmonics suppressed by at least 50 dB without a heavy filter, using the FEM filter. | M | | T |
| RF-020 | RX sensitivity at PER 1e-3 per slice follows one model: `-101 dBm + 10 log10(BW/20 MHz) + NF + required SNR + implementation loss`, with NF per RF-021 and implementation loss 2.0 dB or less. For NF 4 dB at 20 MHz: BPSK 1/2 -93 dBm (SNR 2 dB), QPSK 3/4 -88 dBm (7 dB), 16QAM 3/4 -80 dBm (15 dB), 64QAM 3/4 -74 dBm (21 dB). Revised in rev 0.2 (G-03). | M | | T |
| RF-021 | RX noise figure (full chain including the LNA and switch): 3.5 dB or better at 2.4 GHz, 4.0 dB or better at 5.8 GHz. | M | | T |
| RF-022 | RX dynamic range: -100 dBm to -10 dBm input without damage up to +10 dBm, AGC settling in 20 microseconds, AGC accuracy +/- 1.5 dB. | M | | T |
| RF-023 | RX blocking: 1-dB desensitisation by an in-band interferer of -40 dBm at 20 MHz offset and -25 dBm at 100 MHz offset (important with co-located WiFi and ELRS). | M | | T |
| RF-024 | RX IQ image rejection of 40 dB or better after calibration; RX DC offset removed to below -80 dBFS. | M | | T |
| RF-025 | TX LO leakage of -45 dBc or better and sideband (IQ image) of -45 dBc or better after calibration. | M | | T |
| RF-026 | Co-existence with GNSS: no more than 3 dB desensitisation of a GNSS receiver (L1 1575 MHz and L2 1227 MHz) at 10 cm distance, with the link transmitting at maximum power. | M | | T |
| RF-027 | Switchable antenna ports: at least 2 on the ground unit (diversity), 2 on the air unit (diversity or 2 TX streams). | M | | I |
| RF-028 | External PA/FEM control interface: bias, enable, gain-step, temperature, and power detector signals shall be in the chip's I/O (analogue and digital lines) so that PAs from at least 3 vendors can be used. | M | P2 | I |

## 8. Antenna and antenna feedback (ANT)

"Antenna signal front shape" is read in this document as the antenna radiation pattern (beam shape) and the
wavefront shaping possible with more than one antenna element. Recorded as assumption A-02 in `06`.

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| ANT-001 | A directional coupler or equivalent sensing path at the PA output shall provide forward and reflected power to an observation receiver (used for DPD, power control, and VSWR). | M | P2 | T |
| ANT-002 | VSWR measurement from 1.0:1 to 10:1 with accuracy of +/- 0.3 at 3:1, once per second in the background, and during every TX burst for power. | M | | T |
| ANT-003 | If VSWR exceeds 3:1 the transmitter shall reduce power (fold-back) by at least 6 dB; above 6:1 shut down within 1 ms; recover automatically when the antenna is reconnected. Protects the PA against a missing antenna. | M | | T |
| ANT-004 | Antenna-fault detection: open, short, wrong antenna (band) and detuned antenna (e.g. hand covering it) shall be flagged to the host and to the pilot's OSD. | M | | D |
| ANT-005 | Optional digitally tunable antenna match (tunable capacitor bank), controlled from the VSWR reading, adjustment time 1 ms. | O | P2 | T |
| ANT-006 | Antenna diversity selection per frame (switching in the guard time) using the preamble RSSI, or combining (MRC) on 2 receive chains. | M | | T |
| ANT-007 | The system shall support a pattern database per antenna type: gain, 3 dB beamwidth and polarisation, used by the link budget estimator and by the antenna-tracking option. | S | | I |
| ANT-008 | Support for a ground unit with switched-beam patch array (at least 4 beams, 90 degrees each) with beam choice per frame from the preamble. | S | P2 | T |
| ANT-009 | Support for electronically steered beamforming with 4 or more elements in the ground unit (phase and amplitude weights per element, calibration per element). | O | P2 | T |
| ANT-010 | Cross-polar mismatch (circular versus linear) shall be handled by a 2-antenna receiver covering both polarisations. | S | | T |
| ANT-011 | Antenna return loss and pattern data shall be taken into account by the link-budget estimator displayed to the pilot (predicted range and margin). | O | | D |

## 9. Frequency use: adaptive selection and hopping (ADA)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| ADA-001 | Adaptive frequency selection: the ground unit shall scan the permitted channels (spectrum sensing using the receiver, 50 microsecond dwell per channel per scan) and rank them by interference energy and by decoded video quality. | M | | T |
| ADA-002 | Channel switch on degraded quality: decision latency of 20 ms or less, and execution as defined in MAC-010. | M | | T |
| ADA-003 | Two hopping modes: (a) slow hop: change channel when the current one is bad (per ADA-002); (b) fast hop (for control/telemetry and as a robust fallback): frequency hopping with a dwell of 1 to 10 ms across at least 20 channels in a pseudo-random sequence shared at pairing. | M | | T |
| ADA-004 | Band hopping: switching between 2.4 GHz and 5.8 GHz (and 900 MHz when fitted) in a link-loss case, with a re-establishment time of 300 ms or less (using the stored hop sequence and the control channel). | M | P2 | T |
| ADA-005 | Out-of-band control: the beacon/control channel shall remain on a robust, low-rate, separate channel (e.g. 900 MHz or the 2.4 GHz band when video is on 5.8 GHz) so that the link can be re-established after loss. | S | | T |
| ADA-006 | Regional compliance: the set of allowed channels, powers and dwell times is data-driven per region and locked at the factory (region code) with signed updates only. | M | | I |
| ADA-007 | Spectrum analyser mode on the ground unit: occupancy per channel shown to the pilot (pre-flight and in-flight). | S | | D |
| ADA-008 | DFS: radar detection in the bands where required (5250-5350 and 5470-5725 MHz), with channel move time of 10 s and channel closing transmission time of 260 ms. | S | P2 | T |
| ADA-009 | Listen-before-talk, where regulation requires (e.g. EN 300 328 adaptivity), shall be implemented without exceeding the LAT-003 budget by using the TDD slot structure for sensing. | M | | T |

## 10. Calibration (CAL) - details in document 03

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| CAL-001 | Factory calibration per unit, stored in non-volatile memory with a CRC and a version: TX power vs. frequency vs. temperature table, RX gain vs. frequency vs. temperature table, IQ imbalance, LO leakage, DC offset, and PA DPD seed coefficients. | M | | T |
| CAL-002 | Background (in-field) calibration without interruption of the video: TX LO leakage and IQ via the observation receiver in guard times; RX DC offset in idle slots; RX IQ with a tone injected on a loop-back path. | M | P2 | T |
| CAL-003 | A temperature-triggered re-calibration whenever the temperature changed by more than 5 deg C since the last calibration, and a time-triggered one every 60 s. | M | | T |
| CAL-004 | The front-end shall hold calibration data per (band, channel group, temperature bin) and restore it on hop within the time in RF-006. | M | | T |
| CAL-005 | DPD adaptation using the observation receiver, adaptation converged in 200 ms from cold start and tracking at 10 Hz or faster. | M | P2 | T |
| CAL-006 | TX power control loop: closed loop on the power detector, with correction from the antenna feedback (ANT-001, ANT-002), settling in 100 microseconds. | M | | T |
| CAL-007 | Calibration shall never emit outside the permitted spectrum mask or beyond the permitted power, including during the self-test tone phase. | M | | T |
| CAL-008 | Antenna-feedback-aware calibration: when VSWR changes by more than 0.5 (e.g. different antenna, or antenna touched), the TX gain, DPD and power detector offsets shall be re-calibrated within 50 ms. | M | | T |
| CAL-009 | Calibration status (valid/stale/failed) and the last calibration age shall be available in telemetry. | S | | D |
| CAL-010 | Multi-antenna (ANT-009) per-element phase and gain calibration with an internal reference tone or over-the-air calibration at start-up. | O | P2 | T |

## 11. Thermal and monitoring (THM)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| THM-001 | At least 4 temperature sensors: PA/FEM, transceiver die, baseband/SoC die and board (near the battery connector). Accuracy +/- 2 deg C, resolution 0.25 deg C, 100 Hz sampling at the PA sensor. | M | | T |
| THM-002 | Sensor data shall feed the calibration (CAL-003) and the power control (derating) in real time. | M | | T |
| THM-003 | Thermal throttling in steps: reduce TX power, then video bitrate, then frame rate, then shut-down. No hard failure below a junction temperature of 125 deg C. Thresholds configurable. | M | | T |
| THM-004 | Operation without airflow (hover, no propwash) for 10 min at 40 deg C ambient at 4 W average, with a stated heatsink. | M | | T |
| THM-005 | Supply voltage, current (shunt) and PA current monitoring at 1 kHz, for efficiency tracking and anomaly detection. | S | | T |
| THM-006 | Hardware over-temperature trip independent of software (comparator on the PA sensor). | M | | T |

## 12. Power (PWR)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| PWR-001 | Input supply 6.0 V to 30 V (2S to 6S) with reverse polarity, surge (60 V 1 ms) and ripple (up to 2 Vpp at 100 Hz to 100 kHz from the ESCs) tolerance. | M | | T |
| PWR-002 | The system shall start up (boot to video) in 3 s or less, and recover from a brown-out in 1 s. | M | | T |
| PWR-003 | SoC/baseband plus transceiver power (excluding PA and sensor): at most 1.5 W typical at 1080p60 for the ASIC; at most 8 W for the FPGA prototype. | M | | T |
| PWR-004 | PA power-added efficiency 30% or better at 27 dBm and at 30 dBm average OFDM output with DPD (Doherty or equivalent), confirmed by the PA study. [TBV] Revised by T-02, T-14. | S | | T |
| PWR-005 | Standby (link established, no video) of 1.0 W or less. | S | | T |
| PWR-006 | Sleep (low-power beaconing for RID and pairing) of 50 mW or less. | S | P2 | T |

## 13. Security and compliance (SEC, REG)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| SEC-001 | Pairing by ECDH (P-256 or X25519) with authentication through a short code or NFC/QR; no shared default key. | M | | T |
| SEC-002 | Link encryption AES-256-GCM (or ChaCha20-Poly1305), per-slice authentication tag, anti-replay counter. Latency impact below 0.2 ms. | M | | T |
| SEC-003 | Secure boot, signed firmware and bitstreams (FPGA) and signed region/power tables. | M | | T |
| SEC-004 | Jam resistance: detection of wideband jamming and automatic fallback to fast hopping and to lower rate (ADA-003). | S | | T |
| SEC-005 | RF limits (region, power, band, dwell, DFS) shall be enforced by a hardware-locked limiter whose tables are signed; the rest of the stack stays open. The limiter design and the signing process shall be published for audit. Revised by T-09. | M | | I |
| REG-001 | FCC Part 15 (15.247, 15.407), ETSI EN 300 328 and EN 301 893, ISED RSS-247, and the Radio Equipment Directive (RED) cyber-security delegated act (EN 18031). | M | P2 | T |
| REG-002 | Remote ID: broadcast RID using Bluetooth 5 Long Range and/or WiFi NAN/beacon per FAA Part 89 and ASTM F3411-22a and the EU Direct RID rules, from a certified separate BLE/WiFi module (T-10) that works with the main device off; the RID data (position, altitude, ID) comes from the flight controller or GNSS over IF-001. A later revision may integrate it. | M | | T |
| REG-003 | Export classification and licensing review (encryption, EAR 5D002 / dual-use) before shipping. | M | | I |
| REG-004 | RoHS, REACH, and battery-related requirements where applicable. | M | P2 | I |
| REG-005 | IP policy: RTL and software derived from GPL, AGPL, non-commercial or unlicensed references shall be written clean-room (behavioural reference only); a licence register shall be kept for every reference (`reference/MANIFEST.tsv`); a freedom-to-operate patent search shall be completed before P2 funding. | M | | I |

## 14. Environment (ENV)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| ENV-001 | Full-specification ambient range -10 deg C to +50 deg C; operating range (link functional, EVM relaxed by up to 3 dB) -20 deg C to +60 deg C; storage -40 to +85 deg C. | M | | T |
| ENV-002 | Vibration: random 20 Hz to 2 kHz, 10 g RMS (propeller harmonics); no loss of lock, no connector failure. Crystal/TCXO micro-phonics: phase-noise degradation below 1 dB at 10 g. | M | | T |
| ENV-003 | Shock: 100 g, 6 ms (crash). The air unit shall boot after the shock. | M | | T |
| ENV-004 | ESD: IEC 61000-4-2 contact +/- 4 kV, air +/- 8 kV on antenna and user ports. | M | | T |
| ENV-005 | Humidity: 95% non-condensing. Water resistance IPX4 (O, variant). | S | | T |
| ENV-006 | Altitude to 5000 m (thermal derating). | S | | A |
| ENV-007 | Radiated EMI of the video pipeline (MIPI, DDR) shall not desensitise the receiver by more than 1 dB in any band. | M | | T |

## 15. Interfaces and software (IF, SW)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| IF-001 | Host interface (flight controller): UART (up to 3 Mbaud) and USB 2.0 / CAN-FD (P2). MSP, MAVLink 2. | M | | T |
| IF-002 | Camera: MIPI CSI-2 (VID-002), I2C/SPI control, sensor sync (FSIN) output for rolling-shutter alignment. | M | | I |
| IF-003 | Ground unit host interface: HDMI/DP/DSI out, USB-C (video and data), Ethernet 1 Gbit (O), 5 GHz WiFi/BLE for the phone app (low-priority sideband). | M | | I |
| IF-004 | Debug: JTAG/SWD, UART console, a trace port for the latency timestamps, and a test header for RF conducted measurements (U.FL). | M | P1 | I |
| SW-001 | Control plane in Linux (or Zephyr/RTOS) on the application CPU; data plane in hardware. The data plane shall continue to work if the application CPU stalls for 100 ms. | M | | T |
| SW-002 | A hardware abstraction (HAL) shall isolate the modem from the transceiver, so that the same software runs on the AD936x/ADRV9002-based prototype and the ASIC. | M | | I |
| SW-003 | Open documentation of the host APIs, the register map, and the on-air frame formats. | M | | I |
| SW-004 | Over-the-air (over the link) firmware update of the air unit with fail-safe rollback. | S | | T |
| SW-005 | Logging: link statistics, per-slice RSSI/SNR/PER, calibration events, thermal events, at 1 kHz into a ring buffer that survives a crash (for flight forensics). | M | | T |

## 16. Prototype-specific and ASIC-specific requirements (PRO, ASC)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| PRO-001 | A WiFi-based reference mode (802.11n/ac, 20 MHz, injection, no association) shall be available to compare against the custom PHY on the same video pipeline. | M | P0/P1 | T |
| PRO-002 | The FPGA prototype shall use a Zynq UltraScale+ (or Versal) class device with a hard video codec (VCU) as the first encoder, with a path to replace it with a custom encoder core. | M | P1 | I |
| PRO-003 | The prototype RF shall use an off-the-shelf transceiver with an observation path (AD9361/AD9364/ADRV9002 class) and an external FEM for 2.4/5.8 GHz and 33 dBm. | M | P1 | I |
| PRO-004 | A Bluetooth Low Energy sideband (BLE 5 with ISO channels and Long Range) shall serve for pairing, RID and out-of-band control in the prototype. It shall not be used for video. | S | P1 | D |
| PRO-005 | The RTL shall be written to be ASIC-portable (no vendor primitives outside a wrapper layer, clock-domain-crossing rules, lint and CDC clean). | M | P1 | I |
| ASC-001 | First product: two dice, an RF die in a mature RF CMOS or FD-SOI node and a digital SoC in 12 to 22 nm, with a high-speed digital interface (JESD204 or LVDS); single-die 22 nm FD-SOI is a later cost-down. Decision recorded in T-08. | M | P2 | A |
| ASC-002 | The two-die set shall integrate: transceiver (2 TX, 2 RX, observation receiver), ADC/DAC, PLL/VCO and temperature sensors (RF die); OFDM modem, FEC, video encoder and decoder, ISP-lite, CPU subsystem, memory interface and security block (digital SoC). | M | P2 | I |
| ASC-003 | Design for test: scan, BIST for memories, RF loop-back (TX to RX internal path) for production test, 60 s or less of production test time per unit. | M | P2 | T |
| ASC-004 | Die area targets: digital SoC 30 mm2 or less, RF die 15 mm2 or less. [TBV, G-23] | S | P2 | A |
| ASC-005 | Unit cost target at 100k units per year: below USD 12 for the chip (excluding PA/FEM and memory). [TBV] | S | P2 | A |

## 17. Verification (TST)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| TST-001 | A verification plan (`08`) shall map every requirement to a test case with equipment and pass criteria, and a traceability matrix (`09`) shall be generated from this file by `scripts/trace_matrix.py`. | M | | I |
| TST-002 | The G2G latency rig shall measure with 0.5 ms accuracy or better (photodiode and LED, or a camera at 1000 fps or more) and log per-stage timestamps (LAT-004). | M | P1 | T |

## 18. Revision history

| Rev | Pass | Change |
|---|---|---|
| 0.1 | 1 | Baseline: 156 requirements |
| 0.2 | 5 | Applies `06` and `07`: SYS-003, SYS-005, SYS-009, VID-003, PHY-001, PHY-003, MAC-001, MAC-007, RF-010, RF-020, PWR-004, ENV-001, SEC-005, REG-002, ASC-001, ASC-002, ASC-004 rewritten; added SYS-010, VID-017..019, MAC-011, REG-005, TST-001..002 |

