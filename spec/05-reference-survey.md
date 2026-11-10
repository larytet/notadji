# 05 - Reference Survey

Status: DRAFT, pass 2. Source: the repositories listed in `reference/MANIFEST.tsv` (shallow clones at the
recorded commits, kept locally, not committed). Facts below come from the READMEs and licence files read during
this pass unless marked [not verified].

## 1. Is open digital video really missing?

Not missing, but fragmented and built on commodity radios. Three layers can be distinguished:

| Layer | Open today | Gap |
|---|---|---|
| Radio link (PHY/MAC) | Raw WiFi injection (wfb-ng, OpenHD, Ruby) on Realtek-class adapters; openwifi (FPGA 802.11 a/g/n, 20 MHz) | No open PHY designed for video latency, Doppler and rate adaptation; no open silicon |
| Video encode/decode | Vendor SoC encoders driven by open daemons (waybeam on SigmaStar/HiSilicon); hard decoders on SBCs | Encoders are vendor black boxes; no open low-latency slice encoder/decoder RTL |
| System | Ground stations, OSD, MSP/MAVLink integrations, configurators | Calibration, thermal and antenna-feedback loops are not part of any of them (they rely on the WiFi chip) |

HDZero is the closest to a dedicated digital design, but its FPGA/ASIC design is not in the repository
(only the VTX and goggle firmware are).

## 2. Project notes

| Project | What it is (from the repo) | What notadji takes |
|---|---|---|
| wfb-ng | Packet radio over raw WiFi; "1:1 map of RTP to IEEE 802.11 packets for minimum latency"; FEC with SIMD acceleration; automatic TX diversity by RX RSSI; libsodium encryption and authentication; MAVLink telemetry and an IP tunnel; dynamic FEC and modulation without link interruption | Framing per slice, FEC-above-MAC idea, per-frame diversity (ANT-006), encryption design (SEC-002), logging (SW-005) |
| OpenIPC (firmware, waybeam, sandbox-fpv, research, hardware) | IP camera firmware, a standalone H.265 encoder and RTP streamer ("waybeam": SigmaStar Infinity6E/6C and HiSilicon backends, CBR/VBR/AVBR/FIXQP rate control), FPV experiments, PCB designs | P0 prototype platform; rate-control experience; HW reference designs |
| OpenIPC ground side (aviateur, PixelPilot, msposd, steam-groundstations, decoder) | Ground station apps for Linux/Windows/macOS/Android, MSP DisplayPort OSD | OSD (VID-016), ground unit software behaviour. The `decoder` repo is non-commercial (see `04`) |
| devourer, realtek-wlan | Userspace WiFi driver and drivers for Realtek chips | P0 radios; shows which injection controls exist (and which do not) |
| OpenHD / QOpenHD | A full open FPV system and its ground app | System-level feature list (telemetry, multi-camera, RC) |
| RubyFPV | Multiple redundant radio links in 433/868/915 MHz and 2.4/5.8 GHz used simultaneously; relaying; end-to-end encryption (temporarily disabled per its README); SDKs | Multi-band redundancy ideas (ADA-004, ADA-005); relay support as a later feature. Custom licence (see `04`) |
| hx-esp32-cam-fpv | Very low-cost ESP32-CAM digital FPV | Floor of the cost/latency range; MJPEG-style intra-only ideas |
| HDZero VTX/goggle | Firmware for an FPGA-based digital system with a fixed, low latency | Fixed-latency philosophy; analogue-like graceful behaviour (VID-004 design); no RTL available |
| openwifi / openwifi-hw | Linux mac80211-compatible 802.11 a/g/n on Zynq with AD9361; 10 microsecond SIFS in the FPGA MAC; injection and CSI; AGPLv3 with a separate commercial licence | Reference for the FPGA architecture of P1 (AXI-stream modem, ADI HDL, clocking); timing tricks; the licence is the obstacle for reuse |
| openofdm | Synthesisable Verilog 802.11 OFDM decoder | Reference blocks (sync, FFT, Viterbi) |
| gr-ieee802-11, GNU Radio | GNU Radio 802.11 a/g/p transceiver | Fast algorithm exploration |
| BTLE (JiaoXianjun) | Bluetooth LE transmitter/receiver, SDR with Verilog | BLE sideband prototype |
| ADI HDL, plutosdr-fw | HDL libraries and firmware for ADI transceivers (including ADRV9001) | Transceiver interface IP for P1 |
| LimeSDR-Mini | Open SDR hardware | Alternative RF board |

## 3. Observations that change the spec

1. **Everything open runs on someone else's PHY.** The calibration, DPD and antenna-feedback loops in `03`
   have no open reference. For P1 they have to be designed on a transceiver that exposes the loops
   (ADRV9002-class), or built around AD9361 with external detectors.
2. **FEC above the MAC (wfb-ng) is the practical latency tool in the open systems.** Our PHY-level slice LDPC
   plus MAC-level selective retransmission (MAC-006) is a stricter version of the same idea.
3. **Latency claims differ widely between sources** (25 to 80 ms for OpenIPC-class systems; about 14 to 18 ms
   claimed for HDZero). They come from vendor and retailer material and must be re-measured with our own rig
   (LAT-001) in P0 before the budget in `02` is trusted.
4. **The licence landscape rules out direct reuse of the best FPGA reference (openwifi, AGPLv3).** See `04`.
5. **A stock IP-camera pipeline spends about 80 to 95 ms between the sensor register write and the first packet** (OpenIPC latency-probe, p50), of which 25 to 27 ms are ISP tail, encoder and packetising, and its encoder cannot enforce per-frame size caps (waybeam specs). See `10`.

## 4. Local copy

`reference/` holds shallow (depth 1, `.git` stripped) copies of **every repository, including forks and archived
ones, of the GitHub orgs OpenIPC, OpenHD, hd-zero, svpcom, RubyFPV and open-sdr**, plus the individually chosen
projects (wfb-ng, befinitiv/wifibroadcast, RomanLut/hx-esp32-cam-fpv, jhshi/openofdm, ADI HDL, GNU Radio,
gr-ieee802-11, BTLE, LimeSDR-Mini). It lists 372 repositories and is about 14G on disk. It is excluded from git
(`.gitignore`); `reference/MANIFEST.tsv` pins the commit and licence file of each.

Not downloaded: 20 repositories whose full history exceeds 2000 MB, almost all vendor kernel, SDK and OS mirrors
in the OpenHD org (listed with sizes in `reference/SKIPPED_LARGE.tsv`). They hold board-support code, not link
design. Fetch them with `MAX_MB=100000 scripts/fetch_orgs.sh OpenHD` if wanted (about 30 GB).
Other open projects outside these orgs (for example ArduPilot, PX4, Betaflight, INAV, Walksnail tooling, other
FPGA video codec cores) are not downloaded; `scripts/fetch_refs.sh` and `scripts/fetch_orgs.sh` can be extended.

Of the 372 manifest entries, 86 have no licence file; treat those as all rights reserved (REG-005, G-09).

Commands: `scripts/fetch_refs.sh` (the chosen projects) and `scripts/fetch_orgs.sh OpenIPC OpenHD hd-zero svpcom RubyFPV open-sdr`.
