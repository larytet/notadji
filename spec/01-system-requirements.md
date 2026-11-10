# 01 - System Requirements Specification (SRS)

Status: DRAFT, revision 1.5 (T-15/T-17 iteration; revision 1.4 was the T-13 iteration; revision 1.3 was the T-09/T-10 iteration; revision 1.2 was the T-11/T-12/T-19 iteration; revision 1.1 was the T-06/T-07 iteration; revision 1.0 was the T-05 iteration; revision 0.9 was the T-04/T-16 iteration; revision 0.8 was the T-02/T-14 iteration; revision 0.7 was the T-03 iteration; revision 0.6 was the verification pass; revision 0.5 was iteration 2 of the second goal; revision 0.3 was pass 6; revision 0.2 was pass 5; applies the trade-study results of `07` to the pass-1 text). See `00-overview.md` for conventions (Priority M/S/O, Phase P1/P2, Verification T/A/I/D/S).

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
| SYS-003 | The link shall sustain 1080p60 video (at least 10 Mbit/s net) with at least 6 dB free-space margin in these range classes (30 dBm conducted, 2-branch MRC on the ground unit, lowest MCS that meets the rate): **Class S** 5 km, 5.8 GHz, 20 MHz, 5/5 dBi antennas; **Class X** 10 km, 5.8 GHz, 20 MHz, 10 dBi ground antenna (for example the six-sector array of ANT-008); **Class L** 14 km, 2.4 GHz, 20 MHz, 5/5 dBi. Ranges under ETSI EIRP limits are specified separately (Class L is about 2.5 km at 20 dBm EIRP). Real-world margins per scenario are in `02` (G-02). Revised by T-01. | M | P2 | A,T |
| SYS-004 | The video shall degrade gracefully (lower resolution/quality, never a frozen frame longer than 100 ms) as SNR drops, down to the lowest MCS. | M | | T |
| SYS-005 | Air unit total DC input power, excluding the camera sensor module: at most 3.5 W at 25 dBm and 4.1 W at 27 dBm average output in any modulation; at most 6.0 W at 30 dBm in OFDM QPSK/16QAM and in the low-PAPR mode (64QAM and higher are capped at 27 dBm, RF-031). A separate 33 dBm SKU is allowed up to 10 W. Basis: PA model in `02` section 3 [E]. Revised by T-02. | M | P2 | T |
| SYS-006 | Air unit mass, including the antennas' feed cables and the heatsink, shall not exceed 25 g. | S | P2 | I |
| SYS-007 | Ground unit shall operate from a 1S-6S battery for at least 3 h at the nominal consumption. | S | | T |
| SYS-008 | One ground unit shall pair with up to 4 air units and receive one (or two, picture-in-picture, O) at a time. | S | | D |
| SYS-009 | Co-located operation by frequency plan. Race mode (all links within 500 m of their pilots, air units at least 7 m apart, adjacent channels allowed): at least 6 simultaneous links at 20 MHz and 12 at 10 MHz in 5.8 GHz; 4 at 20 MHz and 8 at 10 MHz in 2.4 GHz; with 5 MHz channels 25 links in 5.8 GHz and 16 in 2.4 GHz at reduced rate and range. Long-range operation (links beyond 500 m): alternate channels only (3, 6 and 13 links at 20, 10 and 5 MHz in 5.8 GHz; 2, 4 and 8 in 2.4 GHz) unless neighbouring air units are at least 184 m apart (ACLR -45 dBc, `07` T-05). Beyond these numbers the links shall degrade gracefully through ADA-001 and power control. In split-band mode the 5 MHz uplink channels limit the count to 16 links in 2.4 GHz. Revised by T-05. | M | | T |
| SYS-010 | Out of scope for version 1: goggles optics and head tracking (the ground unit outputs HDMI/DP/DSI), multi-camera switching. Audio is optional (VID-019). See assumption A-01. | M | | I |

## 3. Video (VID)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| VID-001 | Input formats: 1080p at 30, 50, 60, 90, 100, 120 fps; 720p up to 240 fps; 4K at 30 and 60 fps (4K may exceed the latency in SYS-001 by up to 1.5 frame times). | M | P2 | T |
| VID-002 | Sensor interface: MIPI CSI-2, 4 lanes, D-PHY 2.5 Gbit/s per lane minimum. | M | | I |
| VID-003 | Codecs: AVC (H.264) high profile as the baseline in P1 and P2; HEVC (H.265) main profile as the quality mode in P2. The encoder architecture shall be codec-agnostic at slice level. Revised by T-06. | M | | T |
| VID-004 | The encoder shall be slice-based with at least 8 slices per frame, each slice independently decodable and independently protected. | M | | T |
| VID-005 | No I-frames in steady state. A rolling intra-refresh wave with a period of 60 frames or less acts as the safety net (about 5% bit-rate overhead [E]); recovery from detected losses uses reactive slice refresh (VID-021). Revised by T-07. | M | | T |
| VID-006 | Rate control: per-slice constant bit budget with a rate buffer of at most 1 slice, retargeted every slice from the MCS in force; hard bound: no slice shall exceed 105% of its budget, verified on the encoded bitstream and not from encoder readback (source review S-4). | M | | T |
| VID-007 | Encoder pipeline latency (first pixel in to first slice bits out) of 2.0 ms or less at 1080p60. | M | P2 | T |
| VID-008 | Decoder pipeline latency (first slice bits in to first line out) of 2.0 ms or less at 1080p60. | M | P2 | T |
| VID-009 | Video bit rate range: 1 to 80 Mbit/s, adjustable per frame. | M | | T |
| VID-010 | Loss concealment: a lost slice shall be concealed from the previous frame (motion-compensated, O) and recovered by reactive slice refresh in the next frame (VID-021) or at the latest by the rolling wave within 60 frames. | M | | T |
| VID-011 | Unequal error protection: slice header and parameter data shall have at least 6 dB more protection than residual data. | S | | T |
| VID-012 | 10-bit input and HDR10/HLG pass-through. | O | P2 | T |
| VID-013 | Optional on-air stabilisation using gyro data (electronic image stabilisation) with an added latency of at most 1 frame. The mode shall be switchable so a zero-added-latency path exists. | O | | T |
| VID-014 | Optional local recording at 100 Mbit/s or higher to SD/NVMe, independent of the radio link (full quality copy on the air unit). | S | | D |
| VID-015 | The ground unit shall output HDMI 2.0, DisplayPort and/or MIPI DSI with a fixed line-synchronised scan-out (display starts scanning a frame before it is completely decoded). | M | | T |
| VID-016 | On-screen display overlay (OSD) in the ground unit, MSP DisplayPort and MAVLink sources. | M | | D |
| VID-017 | Codec licensing: a royalty and patent-pool review for AVC and HEVC shall be completed before P2 funding; the product shall ship with the pool licences or the codec shall be disabled in that region. | M | P2 | I |
| VID-018 | Display synchronisation: the ground unit shall lock the display scan-out to the received frame timing, steering the display pixel clock by at least +/-50 ppm with 0.1 ppm resolution (the free-running drift is 2.4 ms per minute for two 20 ppm crystals and 0.24 ms per minute for two TCXOs, `07` T-17), so that latency varies by no more than 1 ms over a 10 minute flight (residual 1 ppm gives 0.6 ms) and no visible glitch is produced. Revised by T-17. | M | | T |
| VID-019 | Optional audio: 48 kHz, 32 to 128 kbit/s, end-to-end latency 20 ms or less, lip-sync within 40 ms of the video. | O | P2 | T |
| VID-020 | No hidden encoder limits: every rate, intra-refresh and reference-structure parameter takes effect within one slice time without restarting the pipeline; unsupported values are rejected with an error and never silently replaced; input frame-rate ceilings of at least 120 fps at 1080p and 240 fps at 720p (source review S-4 to S-7). | M | | T |
| VID-021 | Reactive slice refresh: a slice reported lost in the acknowledgement bitmap (MAC-004) shall be re-coded in intra mode in the next frame, provided the acknowledgement reaches the encoder within one frame time; average overhead at the target loss rate about 0.3% [E]. | M | | T |

## 4. Latency and jitter (LAT)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| LAT-001 | G2G latency shall be measured with a high-speed camera or photodiode method at 1000 fps or better; a secondary method that steps a sensor register and timestamps the first changed frame on one clock (as in `reference/openipc/latency-probe`) shall be used to split the camera half from the rest. | M | | T |
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
| PHY-005 | FEC: LDPC with code rates 1/2, 2/3, 3/4, 5/6; codeword length 648 bits in race mode (lowest latency) and 1944 bits in cruise mode; slice-aligned codeword packing. Revised by T-16. | M | | S,T |
| PHY-006 | Spatial: 2 RX chains at the ground unit with MRC or better. Two TX chains (STBC or spatial multiplexing) as option in P2. | M(RX) / O(TX) | | T |
| PHY-007 | Pilot design shall track a channel that changes within a frame: midambles/pilots at least every 0.25 ms of airtime at the highest Doppler setting. | M | | S |
| PHY-008 | Carrier frequency offset tolerance: initial 25 ppm; after acquisition residual below 0.1 ppm equivalent. | M | | T |
| PHY-009 | Peak-to-average power reduction (clipping with filtering or tone reservation) plus DPD so that the PA meets RF-014 and RF-015 with a back-off of at most 7 dB for 64QAM and 6 dB for QPSK/16QAM OFDM (the 4 dB of rev 0.6 was unrealistic). | M | P2 | T |
| PHY-010 | Frame (burst) preamble acquisition time (detect + AGC settle + sync) shall be 40 microseconds or less. | M | | T |
| PHY-011 | Packet-error-rate target after FEC: 1e-3 per slice at the lowest MCS at the sensitivity in RF-020, equivalent to a codeword error rate of about 1.2e-5 for 86 codewords per slice at 1080p60 and 20 Mbit/s (`07` T-07). | M | | T |
| PHY-012 | The PHY shall run at least 4 MCS adaptation steps per second and up to one per frame (see MAC-005). | M | | T |
| PHY-013 | The numerology shall be programmable (not hard-wired) so that the same engine can run a WiFi-compatible mode (see PRO-001) for the prototype. | M | P1 | I |
| PHY-014 | Optional low-PAPR mode: DFT-spread OFDM for BPSK, QPSK and 16QAM with a PAPR at least 3 dB below plain OFDM at a CCDF of 1e-3 [E], selectable per link; it is the mitigation if the PA study shows less than 27% PAE at OFDM QPSK/16QAM. | O | P2 | S,T |
| PHY-015 | LDPC decoder throughput of at least 155 Mbit/s of information (3 layered-decoder instances at 200 MHz in the model of `07` T-16, or equivalent) and a codeword decode time of 10 us or less. [E, TBV] | M | | S,T |

## 6. MAC and framing (MAC)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| MAC-001 | In-band TDD mode (fallback, and for single-band products or regions where the second band is unusable): super-frame of 1 ms up to 7 km, 2 ms up to 15 km and 4 ms beyond, selected from the measured round-trip delay; the uplink slot is sized for MAC-007 (7 symbols at 1 ms: 1 Mbit/s at QPSK 1/2 plus 100 feedback bits plus a 2-symbol preamble); the DL to UL guard is at least 2 x the one-way propagation delay plus 2 x 10 us turn-around (100 us + 20 us at 15 km); the guard shall also provide the idle period required by frame-based-equipment rules where applicable (G-21). Revised by T-03. | M | | T |
| MAC-002 | All airtime is scheduled by the ground unit or by the air unit master. No contention-based access (no CSMA) inside a link. Coexistence with other systems is done by channel selection (ADA-001). | M | | T |
| MAC-003 | Time synchronisation between air and ground within 1 microsecond (derived from the preamble). | M | | T |
| MAC-004 | Uplink slots carry channel feedback (CSI summary, MCS recommendation, RSSI, per-slice ACK/NAK bitmap) with 1 ms or less period. | M | | T |
| MAC-005 | The air unit shall change MCS, power and slice budget within 2 ms of receiving the feedback. | M | | T |
| MAC-006 | Selective retransmission of slices only if the slice deadline (display deadline) can still be met; otherwise drop. | M | | T |
| MAC-007 | Telemetry/control channel carrying MAVLink, MSP and generic serial with latency of 5 ms or less: downlink at least 2 Mbit/s; uplink at least 1 Mbit/s with 6 dB margin at the full class range in split-band mode (margins 17.0, 11.0 and 12.4 dB for Classes S, X and L, `02`); in in-band TDD mode at least 1 Mbit/s (QPSK 1/2) within 5 km (Class S), 8 km (Class X) and 12 km (Class L) and at least 300 kbit/s (BPSK 1/2) out to the full class range, the uplink MCS adapting automatically. | M | | T |
| MAC-008 | Optional hard real-time RC channel: 1 kHz update, 3 ms one-way latency, link-lost failsafe in 100 ms. | O | | T |
| MAC-009 | Pairing and key exchange without a network connection (see SEC-001). Re-pairing in the field within 10 s. | M | | D |
| MAC-010 | Multi-link: a link shall be able to survive a change of channel (frequency hop) with a gap in video of 1 frame or less. | M | | T |
| MAC-011 | Timing advance: the ground unit shall estimate the round-trip delay from the preamble (resolution 0.1 us) and advance its uplink slot so that the uplink arrives aligned with the air unit's frame; the estimate is also reported to the pilot as range (O). | M | | T |
| MAC-012 | Split-band mode (baseline for Classes X and L where regulation allows): the video band carries downlink only (5% idle for frame-based-equipment rules); feedback, telemetry and control use a 5 MHz uplink channel at 2.4 GHz (for 5.8 GHz video) or 900 MHz (for 2.4 GHz video, where the band allows continuous operation), with feedback every 0.25 ms or faster; the mode falls back to in-band TDD (MAC-001) when the uplink band is unavailable or fails. | M | | T |

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
| RF-029 | Interference tolerance (needed by SYS-009): with the wanted signal 3 dB above the QPSK 3/4 sensitivity, the receiver shall tolerate an adjacent-channel interferer of -30 dBm and an alternate-channel interferer of -25 dBm with 1 dB or less desensitisation (a 35 dBm EIRP neighbour at 10 m gives about -33 dBm); the transmit leakage of RF-015 is the separate limit that sets the separation of `07` T-05 (G-27). [E, TBV] | M | | T |
| RF-030 | Air unit TX-to-RX isolation for split-band mode: at least 70 dB from the 5.8 GHz transmit chain (30 dBm, with its broadband noise) to the 2.4 GHz uplink receive chain, by antenna separation plus transmit and receive filtering, such that the uplink sensitivity degrades by 1 dB or less. [E, TBV] | M | | T |
| RF-031 | Average output power cap by modulation: 64QAM and 256QAM at most 27 dBm, other modes up to the class limit (RF-010), enforced by the transmit power control (SYS-005, `02`). | M | | T |

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
| ANT-008 | Support for a ground unit with a switched-beam patch array of at least 6 sectors (60 degrees azimuth, 40 degrees elevation or narrower, 10 dBi or better per beam, `07` T-13) with beam choice per frame from the preamble. The 4-sector version of rev 0.5 gave only 6.6 to 9.6 dBi. | S | P2 | T |
| ANT-009 | Support for electronically steered beamforming with 4 or more elements in the ground unit (phase and amplitude weights per element, calibration per element). | O | P2 | T |
| ANT-010 | Cross-polar mismatch (circular versus linear) shall be handled by a 2-antenna receiver covering both polarisations. | S | | T |
| ANT-011 | Antenna return loss and pattern data shall be taken into account by the link-budget estimator displayed to the pilot (predicted range and margin). | O | | D |

## 9. Frequency use: adaptive selection and hopping (ADA)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| ADA-001 | Adaptive frequency selection: the ground unit shall scan the permitted channels (spectrum sensing using the receiver, 50 microsecond dwell per channel per scan) and rank them by interference energy and by decoded video quality. | M | | T |
| ADA-002 | Channel switch on degraded quality: decision latency of 20 ms or less, and execution as defined in MAC-010. | M | | T |
| ADA-003 | Two hopping modes: (a) slow hop: change channel when the current one is bad (per ADA-002); (b) fast hop (for control/telemetry and as a robust fallback; in ETSI regions only in an adaptive form, because non-adaptive hopping is limited to a 5 ms on-time followed by a 5 ms gap [to be checked in EN 300 328]): frequency hopping with a dwell of 1 to 10 ms across at least 20 channels in a pseudo-random sequence shared at pairing. | M | | T |
| ADA-004 | Band hopping: switching between 2.4 GHz and 5.8 GHz (and 900 MHz when fitted) in a link-loss case, with a re-establishment time of 300 ms or less (using the stored hop sequence and the control channel). | M | P2 | T |
| ADA-005 | Out-of-band control: the beacon/control channel shall remain on a robust, low-rate, separate channel (e.g. 900 MHz or the 2.4 GHz band when video is on 5.8 GHz) so that the link can be re-established after loss; in split-band mode (MAC-012) the uplink channel is this channel. | S | | T |
| ADA-006 | Regional compliance: the set of allowed channels, powers and dwell times is data-driven per region and locked at the factory (region code) with signed updates only. | M | | I |
| ADA-007 | Spectrum analyser mode on the ground unit: occupancy per channel shown to the pilot (pre-flight and in-flight). | S | | D |
| ADA-008 | DFS: radar detection in the bands where required (5250-5350 and 5470-5725 MHz), with channel move time of 10 s and channel closing transmission time of 260 ms. | S | P2 | T |
| ADA-009 | Listen-before-talk, where regulation requires (e.g. EN 300 328 adaptivity), shall be implemented without exceeding the LAT-003 budget by using the TDD slot structure for sensing. | M | | T |
| ADA-010 | Neighbour awareness: from the spectrum scan (ADA-001) the ground unit shall detect strong adjacent-channel signals (above -60 dBm) and prefer an alternate channel or lower power, and shall report the interference to the pilot. | S | | T |

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
| PWR-003 | SoC/baseband plus transceiver power (excluding PA and sensor): at most 1.5 W typical for the ASIC; at most 9.5 W for the FPGA prototype (a K26-class module is 7.5 W typical [S] plus a 1.5 W transceiver; was 8 W in rev 0.4, corrected after the vendor figure was found). | M | | T |
| PWR-004 | PA power-added efficiency at average output with DPD: 27.5% or better for OFDM QPSK/16QAM and 32% or better in the low-PAPR mode at 30 dBm; 24.5% or better for OFDM 64QAM at 27 dBm. [E, from the model in `02`; the PA study shall confirm or replace the values.] Revised by T-02, T-14. | S | | T |
| PWR-005 | Standby (link established, no video) of 1.0 W or less. | S | | T |
| PWR-006 | Sleep: main device 5 mW or less (RAM retention); Remote ID is served by the separate certified module (REG-002), whose own power is at most 50 mW. | S | P2 | T |

## 13. Security and compliance (SEC, REG)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| SEC-001 | Pairing by ECDH (P-256 or X25519) with authentication through a short code or NFC/QR; no shared default key. | M | | T |
| SEC-002 | Link encryption ChaCha20-Poly1305 by default (as in wfb-ng, no AES hardware needed) with AES-256-GCM as the hardware option, per-slice authentication tag, anti-replay counter. Latency impact below 0.2 ms. | M | | T |
| SEC-003 | Secure boot, signed firmware and bitstreams (FPGA) and signed region/power tables. | M | | T |
| SEC-004 | Jam resistance: detection of wideband jamming and automatic fallback to fast hopping and to lower rate (ADA-003). | S | | T |
| SEC-005 | RF limits (region, power, band, dwell, DFS) shall be enforced by a hardware-locked limiter (modem register lock set from a signed, region-bound table) in the ASIC and by a signed bitstream in FPGA builds; the rest of the stack stays open. The limiter design and the signing process shall be published for audit. FPGA prototypes are not sold and run in conducted or shielded set-ups or under the applicable test authorisation. Revised by T-09. | M | | I |
| REG-001 | FCC Part 15 (15.247, 15.407), ETSI EN 300 328 and EN 301 893, ISED RSS-247, and the Radio Equipment Directive (RED) cyber-security delegated act (EN 18031). | M | P2 | T |
| REG-002 | Remote ID: broadcast RID from a certified separate BLE/WiFi module (T-10) that works with the main device off, meeting the FAA-accepted means of compliance ASTM F3586-22 (an overlay on ASTM F3411-22a) for Part 89 and the EU Direct RID rules; a Bluetooth implementation shall include both Bluetooth 4 legacy advertising and Bluetooth 5 Long Range with extended advertising, a WiFi implementation NAN or beacon frames (at least one transport); the RID data (position, altitude, ID) comes from the flight controller or GNSS over IF-001. A later revision may integrate it. | M | | T |
| REG-003 | Export classification and licensing review (encryption, EAR 5D002 / dual-use) before shipping. | M | | I |
| REG-004 | RoHS, REACH, and battery-related requirements where applicable. | M | P2 | I |
| REG-005 | IP policy: RTL and software derived from GPL, AGPL, non-commercial or unlicensed references shall be written clean-room (behavioural reference only); a licence register shall be kept for every reference (`reference/MANIFEST.tsv`); a freedom-to-operate patent search shall be completed before P2 funding. | M | | I |
| REG-006 | Patent design-around register (`11`, section 4): PA bias current and supply voltage shall be set from temperature and PA current only and shall not be adjusted as a function of measured load impedance or VSWR while DPD is active; reflection data may be used for fold-back, DPD coefficient-set selection, the optional tunable match and alarms. Other constraints D-2 to D-5 apply until counsel clears them. | M | | I |
| REG-007 | A software security statement shall be prepared before certification, covering 47 CFR 2.944 (only approved software loadable, method described) and the FCC U-NII device security guidance (KDB 594280 D02, current revision to be checked): the RF parameters software can change, the authentication of updates and the limiter of SEC-005. | M | P2 | I |

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
| IF-002 | Camera: MIPI CSI-2 (VID-002), I2C/SPI control, sensor sync (FSIN) output for rolling-shutter alignment; fixed frame period policy: exposure is limited below the frame time so that the sensor never stretches the frame (source review S-5). | M | | I |
| IF-003 | Ground unit host interface: HDMI/DP/DSI out, USB-C (video and data), Ethernet 1 Gbit (O), 5 GHz WiFi/BLE for the phone app (low-priority sideband). | M | | I |
| IF-004 | Debug: JTAG/SWD, UART console, a trace port for the latency timestamps, and a test header for RF conducted measurements (U.FL). | M | P1 | I |
| SW-001 | Control plane in Linux (or Zephyr/RTOS) on the application CPU; data plane in hardware. The data plane shall continue to work if the application CPU stalls for 100 ms. | M | | T |
| SW-002 | A hardware abstraction (HAL) shall isolate the modem from the transceiver, so that the same software runs on the AD936x/ADRV9002-based prototype and the ASIC. | M | | I |
| SW-003 | Open documentation of the host APIs, the register map, and the on-air frame formats. | M | | I |
| SW-004 | Over-the-air (over the link) firmware update of the air unit with fail-safe rollback. | S | | T |
| SW-005 | Logging: link statistics, per-slice RSSI/SNR/PER, calibration events, thermal events, at 1 kHz into a ring buffer that survives a crash (for flight forensics). | M | | T |

## 15a. Hardware-software integration (HSI) - details in document 13

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| HSI-001 | Three execution domains: hardware data plane, hard real-time control core(s), optional application core. The data plane shall keep forwarding video, feedback and the safe schedule for at least 100 ms if every processor stalls. | M | | T |
| HSI-002 | A frame-timeline sequencer in hardware shall execute hops, turn-arounds, PA enable, gain steps and slice slots from a table committed at least one frame ahead; no software action is in the microsecond path. | M | | T |
| HSI-003 | One 64-bit timestamp counter at 200 MHz or faster (5 ns resolution) shall be latched at every pipeline stage boundary and exposed on the trace port (LAT-004). | M | | T |
| HSI-004 | The DPD correlation accumulation and the link encryption shall be hardware blocks; steady-state operation shall not depend on a software implementation of either. | M | P2 | I |
| HSI-005 | Worst-case load of each real-time core shall be 50% or less at the 1080p120 workload of `13` section 2, measured. | M | | T |
| HSI-006 | The worst-case execution time of every real-time task shall be measured on the target core and recorded; the estimates in `13` section 2 shall be replaced by measurements. | M | | T |
| HSI-007 | Boot to first video in 3 s or less (target 1.5 s) with the real-time path only; the application core shall not be in the critical path. | M | | T |
| HSI-008 | Real-time core interrupt entry within 5 us at 300 MHz (to the first instruction of the handler). [TBV] | M | | T |
| HSI-009 | Processor subsystem power (all cores, caches and SRAM) of the ASIC: 100 mW or less in the streaming state with the application core gated; 5 mW or less in sleep (RAM retention). [target, TBV] | S | P2 | T |
| HSI-010 | Platform phasing: phase A on low-cost evaluation boards (waveform, MAC, calibration, partial latency); phase B on a custom board with the target controllers (latency, thermal, mass); phase C ASIC. Latency measured in phase A shall not be used to claim SYS-001 or SYS-002. | M | | I |
| HSI-011 | A stalled control core (no table update for two frames) shall be detected by the sequencer, which falls back to a safe schedule (lowest MCS, reduced power) and keeps the video running. | M | | T |
| HSI-012 | All modem and RF control shall go through a documented register map and a versioned HAL (SW-002, SW-003) so that phase A, B and C software share the same interface. | M | | I |
| HSI-013 | The DPD solve shall be validated numerically (conditioning, precision, coefficient drift) before the real-time core is selected; double precision or a demonstrated stable single-precision method. | M | P1 | S |
| HSI-014 | The inter-processor channel (mailbox, shared memory) shall never block the real-time side; it shall use non-blocking single-producer queues. | M | | T |
| HSI-015 | Memory protection (MPU/MMU) between real-time control loops, protocol tasks and the application core; a fault in one shall not corrupt the others. | M | P2 | T |

## 16. Prototype-specific and ASIC-specific requirements (PRO, ASC)

| ID | Requirement | Pri | Phase | Ver |
|----|-------------|-----|-------|-----|
| PRO-001 | A WiFi-based reference mode (802.11n/ac, 20 MHz, injection, no association) shall be available to compare against the custom PHY on the same video pipeline. | M | P0/P1 | T |
| PRO-002 | The FPGA prototype shall use a Zynq UltraScale+ (or Versal) class device with a hard video codec (VCU) as the first encoder, with a path to replace it with a custom encoder core. | M | P1 | I |
| PRO-003 | The prototype RF shall use an off-the-shelf transceiver with an observation path (AD9361/AD9364/ADRV9002 class) and an external FEM for 2.4/5.8 GHz and 33 dBm. | M | P1 | I |
| PRO-004 | A Bluetooth Low Energy sideband (BLE 5 with ISO channels and Long Range) shall serve for pairing, RID and out-of-band control in the prototype. It shall not be used for video. | S | P1 | D |
| PRO-005 | The RTL shall be written to be ASIC-portable (no vendor primitives outside a wrapper layer, clock-domain-crossing rules, lint and CDC clean). | M | P1 | I |
| PRO-006 | P0 baseline: the camera half and G2G of a stock IP-camera pipeline shall be measured with the register-step method and with the rig and recorded as the reference for the budget in `02`. | M | P0 | T |
| PRO-007 | Phase A radio bring-up in two configurations: A1 a pair of PlutoSDR-class radios with video at 2.4 GHz and the uplink at 915 MHz (inside the guaranteed 325 MHz to 3.8 GHz range); A2 an AD9361/ADRV9002-class evaluation pair with video at 5.8 GHz and the uplink at 2.4 GHz. A2 shall measure turn-around, hop time, TX-to-RX isolation (RF-030) and, on the AD9364-class air unit, whether independent RX and TX LOs work. | M | P1 | T |
| ASC-001 | First product: two dice, an RF die in a mature RF CMOS or FD-SOI node and a digital SoC in 12 to 22 nm, with a high-speed digital interface (JESD204 or LVDS); single-die 22 nm FD-SOI is a later cost-down. Decision recorded in T-08. | M | P2 | A |
| ASC-002 | The two-die set shall integrate: transceiver (2 TX, 2 RX, observation receiver; air unit uses 1 TX at the video band and 1 RX at the uplink band, ground unit 2 RX at the video band and 1 TX at the uplink band), ADC/DAC, PLL/VCO and temperature sensors (RF die); OFDM modem, FEC, video encoder and decoder, ISP-lite, CPU subsystem, memory interface and security block (digital SoC). | M | P2 | I |
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
| 0.3 | 6 | RF-029 adjacent-channel rejection added; link-budget rate model aligned with PHY-001 tone counts and MAC-001 guard |
| 0.4 | G2-1 | Source review (`10`): VID-006 hard bound, VID-020 added, IF-002 fixed frame period, LAT-001 register-step method, SEC-002 default cipher, PRO-006 added |
| 0.5 | G2-2 | Patent search (`11`): REG-006 design-around register added, ADA-003 ETSI note |
| 0.6 | G2-3 | Verification pass: MAC-001/MAC-007 re-derived (uplink sizing, range-adaptive frame), SYS-005 PAE threshold corrected, REG-002 via F3586-22, PWR-003/PWR-006 corrected, HSI-001..015 added (`13`), T-18/T-19 added |
| 0.7 | G2-4 | T-03 iteration: split-band uplink baseline (MAC-012, RF-030), MAC-001 becomes the fallback mode, MAC-007 restated per mode, ADA-005/SYS-009/ASC-002 adjusted |
| 0.8 | G2-5 | T-02/T-14 iteration: SYS-005 and PWR-004 per mode, PHY-009 corrected, PHY-014 (low-PAPR option) and RF-031 added |
| 0.9 | G2-6 | T-04/T-16 iteration: numerology and decoder sizing quantified; PHY-005 per-mode codeword length, PHY-015 added, PHY-003 prefix note |
| 1.0 | G2-7 | T-05 iteration: near-far analysis; SYS-009 split into race and long-range counts, RF-029 restated, ADA-010 added |
| 1.1 | G2-8 | T-06/T-07 iteration: slice PER to codeword error rate, intra-refresh cost, VID-005/010 revised, VID-021 reactive slice refresh added, PHY-011 clarified |
| 1.2 | G2-9 | T-11/T-12/T-19 iteration: phase A configurations A1/A2/A3, ADRV9002 for phase B, PRO-007 added |
| 1.3 | G2-10 | T-09/T-10 iteration: SEC-005 restated (hardware limiter, signed bitstream), REG-007 software security statement added; T-10 confirmed |
| 1.4 | G2-11 | T-13 iteration: sector-array gain corrected (4 sectors give 6.6-9.6 dBi, not 8-10 dB over omni), ANT-008 now 6 sectors, Class X antenna example |
| 1.5 | G2-12 | T-15/T-17 iteration: hop overhead and genlock drift quantified, VID-018 gets steering range and resolution |
