# 04 - Prototype (WiFi, BLE, FPGA) and ASIC Plan

Status: DRAFT, pass 2.

## 1. Staged plan

| Stage | Platform | What it proves | Exit criterion |
|---|---|---|---|
| P0a | Commodity WiFi in injection mode (wfb-ng/OpenIPC with Realtek adapters) plus an IP camera SoC | Video pipeline, latency measurement method, field range data | G2G and camera half measured and logged (PRO-006); baseline numbers |
| P0b | WiFi 802.11n/ac with low-latency tweaks (see section 2) | How low commodity WiFi can go | Latency floor documented |
| P1a | openwifi-style SDR (Zynq + AD9361) running 802.11 mode | Full-control baseband and MAC; SIFS-level timing; calibration hooks | 802.11 link at 20 MHz with timestamps at every stage |
| P1b | Same hardware with the custom PHY/MAC (OFDM, short LDPC, slice framing, TDD) | The custom waveform | SYS-002 (30 ms G2G) and RF requirements met on the bench |
| P1c | Custom encoder core (replacing the hard VCU) and the calibration loops (DPD, VSWR) | Latency and linearity | SYS-001 within 20% |
| P2 | ASIC | Cost, power, size | SYS-001..009 |

## 2. WiFi as the prototype

WiFi variants with low-latency features, and what to take from each (this is the "pick ideas from the specs"
list requested):

| Technology | Low-latency feature | Idea to take | Limitation for us |
|---|---|---|---|
| 802.11 OCB / 802.11p, 802.11bd (V2X) | No association, 10 MHz channel, long guard interval; 11bd adds midambles for high Doppler, LDPC, 256QAM | Operate without a BSS; midamble channel tracking (PHY-007); 10 MHz default numerology | 5.9 GHz band only in the standard; we reuse the PHY design, not the band |
| 802.11n/ac injection (wfb-ng) | Raw packet injection, 1:1 RTP packet to frame mapping, FEC above the MAC | Frame mapping per slice, FEC design, TX diversity by RSSI | Rate/MCS control depends on the adapter and driver; no sub-slice control |
| 802.11ax (Wi-Fi 6) | OFDMA, target wake time (TWT), 4x longer symbol (12.8 us), 242-tone RU | Numerology (the 78.125 kHz spacing used in `02`), scheduled access | Complexity; scheduling designed for many stations |
| 802.11be (Wi-Fi 7) | Restricted TWT, multi-link operation, low-latency access categories, 320 MHz | Multi-link redundancy (two bands simultaneously), R-TWT style scheduling | 6 GHz and 320 MHz not relevant; hardware cost |
| 802.11ah (HaLow) | Sub-GHz (863-928 MHz), 1 to 16 MHz channels, long range | Basis of the 900 MHz variant (RF-002) | Single-stream rates of roughly 40 Mbit/s at 8 MHz and 87 Mbit/s at 16 MHz (standard values from memory, not re-checked); regional channel widths limit the usable rate; latency higher |
| openwifi (FPGA) | 10 microsecond SIFS in an FPGA MAC, injection, CSI | Reference FPGA 802.11 design, open source (AGPLv3, see licence note) | 20 MHz, 802.11a/g/n only in the open tree |
| DECT-2020 NR (ETSI TS 103 636) | Slot-based low-latency design in unlicensed bands | Frame structure ideas | Not in 2.4/5.8 GHz globally |

Practical prototype radio for P0: an RTL8812AU/EU-class adapter or an OpenIPC camera with a WiFi chip, using
the open drivers (`devourer`, `realtek-wlan` in the downloaded set). P0 results become the baseline for
`LAT-*` and for the comparison in PRO-001.

## 3. Bluetooth

Bluetooth cannot carry the video: the 1 Mbit/s and 2 Mbit/s LE PHYs give about 1.4 Mbit/s of throughput, and the
higher-rate extensions are still far below the 10 to 80 Mbit/s needed. Its role is limited and useful:

| Use | Feature | Notes |
|---|---|---|
| Remote ID broadcast (REG-002) | BLE 5 advertising extensions, Long Range (coded PHY) | Required in the US and EU; works with the video link off |
| Pairing and out-of-band setup (MAC-009) | LE Secure Connections (ECDH P-256), NFC/QR for authentication | Reuse the standard cryptography |
| Low-latency sideband for telemetry/control | LE Isochronous Channels (CIS/BIS) with an ISO interval of 5 ms or more, sub-event retransmission, flush timeout | Gives a deterministic 5 to 10 ms latency, the same ideas (time-scheduled events, adaptive channel map, bounded retransmissions) are used in our MAC |
| Channel sounding (BT 6.0) | Phase-based ranging | Optional: distance estimate for the pilot display |

Ideas taken from Bluetooth LE: the isochronous event structure (scheduled events with sub-events and a flush
timeout, a bounded latency for each payload), adaptive frequency hopping with a channel map, and the coded PHY
(S=2/S=8) as an example of a very low rate fallback.

## 4. FPGA prototype hardware (P1)

| Block | Candidate | Notes |
|---|---|---|
| FPGA/SoC | Zynq UltraScale+ MPSoC EV (ZU4EV/ZU5EV) | Hard H.264/H.265 VCU with a low-latency mode, ARM cores, enough logic for the modem and FEC |
| Alternative | Versal AI Edge | Larger, more expensive; later |
| Alternative (budget) | Zynq-7000 plus a separate encoder SoC (OpenIPC camera) | Fewer resources; used for P0 hybrid |
| RF transceiver | AD9361 (2x2) / AD9364 (1x1): receive 70 MHz to 6 GHz, transmit 47 MHz to 6 GHz, channel bandwidth below 200 kHz to 56 MHz, best-case noise figure 2 dB ([datasheet page found by search](https://www.analog.com/AD9361/datasheet)) | Cheapest, well supported (openwifi, ADI HDL) | No integrated DPD; whether its TX monitor path can act as an observation receiver is to be checked in UG-570; fast-lock profiles give about 15 to 25 us retune ([ADI wiki](https://wiki.analog.com/resources/eval/user-guides/adrv936x_rfsom/tutorials/frequency_hopping)) but RX to TX in TDD goes through the ALERT state and a 5 us turn-around is not demonstrated |
| RF transceiver (better) | ADRV9002 (2 Tx / 2 Rx, 30 MHz to 6 GHz, 12 kHz to 40 MHz bandwidth, integrated DPD per the ADI product page); hopping demonstrated with 13 us hop frames and about 3 us transitions in an ADI Link 16 example ([Analog Dialogue](https://www.analog.com/en/resources/analog-dialogue/articles/the-next-gen-software-defined-radio-sdr-transceiver-delivers-big-advances-in-frequency-hopping-fh.html)) | Closest to the final calibration architecture (section 3 of `03`) and to RF-006/RF-009 | Power figures and tracking-calibration scheduling not verified; 40 MHz limit rules out the optional 80 MHz mode in P1; check the licence of its reference firmware |
| RF transceiver (alt.) | LimeSDR / LMS7002M | Open hardware and a lot of documentation |
| FEM | Discrete 2.4 and 5.8 GHz FEMs with a power detector and a coupler, 33 dBm | Vendor choice by trade study T-06 |
| Camera | MIPI CSI-2 sensor board (4 lanes), global-shutter option | |
| Debug | Timestamp tap at every stage, GPIO outputs for the photodiode G2G rig | LAT-004 |

## 5. ASIC roadmap

| Step | Content | Time (est.) | Cost (est.) |
|---|---|---|---|
| A0 | Architecture, bit-accurate models (Python/C++), RTL for FPGA | in P1 | included |
| A1 | RF test chip: transceiver, PLL, observation receiver, in a mature RF node, used with the FPGA as baseband | 12 to 18 months | MPW run of about USD 0.3 to 1 M [TBV] |
| A2 | Baseband ASIC: modem, FEC, encoder/decoder, CPU, in 22 nm or 28 nm | 18 to 24 months in parallel with A1 (a team of about 60 would need about 2.5 years for the 265 to 330 person-years of `16`) | NRE USD 5 to 10 M [TBV] covers masks, IP licences and tools only; team labour is separate (about 240 person-years of digital SoC work at USD 0.15 M each is about USD 35 M [E, `16`]) |
| A3 | Integration: one-chip (or two-chip) product, certification | 12 months | USD 3 to 8 M [TBV] |

Options (A: one die, B: two dice, C: SiP) are evaluated in trade study T-08. The numbers are order-of-magnitude
and depend on the process, the IP licences (CPU, SerDes, DDR PHY, MIPI) and the team.

## 6. Licence notes for the reference code

Verified by reading the licence file of each downloaded repository (`reference/MANIFEST.tsv` lists the
commits). Licence text is the authority; this table is a summary and is not legal advice.

| Project | Licence found | Consequence for notadji |
|---|---|---|
| wfb-ng, befinitiv/wifibroadcast | GPLv3 | Code reuse makes our code GPLv3; the protocol ideas are free to use |
| OpenHD, QOpenHD | GPLv3 | As above |
| OpenIPC firmware, hardware, research, sandbox-fpv, waybeam, configurator, steam-groundstations | MIT | Reusable, keep the notice |
| OpenIPC msposd, aviateur, devourer, PixelPilot, wiki, openhisilicon | GPL | Copyleft |
| OpenIPC decoder | Prosperity Public License 3.0 (non-commercial; 30-day commercial trial) | Not usable in a product; reference only |
| OpenIPC improver, docs, realtek-wlan | No licence file | All rights reserved until clarified (G-09) |
| RubyFPV | Custom "Ruby Licence": BSD-like with a notice-preservation clause and **"Military use is not permitted"** | Not an open-source licence in the OSI sense; the field-of-use restriction conflicts with some customers and with GPL mixing |
| openwifi, openwifi-hw | AGPLv3 (a separate commercial licence is offered by the authors) | A product with a silicon baseband derived from the HDL would need the commercial licence, or a clean-room design |
| openofdm, BTLE | Apache 2.0 | Reusable with attribution; patent grant included |
| HDZero VTX | GPL | Firmware only; the FPGA bitstream and ASIC are not part of the repository |
| HDZero goggle | MIT | Firmware only |
| hx-esp32-cam-fpv | MIT | |
| gnuradio, gr-ieee802-11 | GPL | Simulation and rapid prototyping only |
| ADI hdl, plutosdr-fw | Mixed (GPL, LGPL, BSD, commercial) per file | Check per file; the ADI HDL licence note describes a compound licence |
| LimeSDR-Mini | No licence file in the clone | Check the hardware licence on the project page |

Consequence for the plan: the custom PHY/MAC/encoder RTL should be written from the specification and the
literature (clean room), using the GPL/AGPL projects as behavioural references only (G-09, G-10). The
software repositories under MIT/Apache can be reused directly.
