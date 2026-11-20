# 17 - Simulation Test Plan and Tool Inventory

Status: DRAFT (initial). This document covers the **S** (simulation) verification method for the FPGA phase (P1) and
names the tools installed on the development machine. It refines test groups `TG-PHY`, `TG-MAC`, `TG-HSI` and `TG-VID` of
`08` for the simulation stage only; bench and field tests stay in `08`. Evidence labels as in `12`: **[S]** from a cited
source, **[C]** computed or checked by a script, **[E]** estimate. Tool versions below were read from the installed
binaries on 2026-11-20 (Ubuntu 22.04 class host, 12 cores).

## 1. Installed tools

| Tool | Version | Location | Role | Status |
|---|---|---|---|---|
| Verilator | 5.055 (suite); 4.038 (apt, too old, do not use) | OSS CAD Suite | RTL simulation and lint, C++ models | Hello-world compiled and ran [C] |
| Icarus Verilog | 14.0 devel (suite); 11.0 (apt) | OSS CAD Suite | Second Verilog simulator, cross-check | Version read |
| GHDL | 7.0.0 devel (suite); 1.0.0 (apt) | OSS CAD Suite | VHDL simulation (only if vendor VHDL is used) | Version read |
| Yosys | 0.71 (suite); 0.9 (apt) | OSS CAD Suite | Synthesis estimates, netlist checks | Version read |
| SymbiYosys (`sby`) | 0.71 | OSS CAD Suite | Formal properties (sequencer, handshakes) | Version read |
| nextpnr (ice40, ecp5) | 0.11.1 | OSS CAD Suite | Not a target (no Zynq UltraScale+ support); small-block timing experiments only | Version read |
| cocotb | 2.1.0 devel | OSS CAD Suite Python 3.11 | Python testbenches over Verilator or Icarus | Imports [C]; no test written yet |
| GTKWave | apt and suite | system and suite | Waveform viewer | Starts (a harmless `canberra-gtk-module` message is printed) |
| Surfer | in suite | suite | Waveform viewer | **Does not run**: needs glibc 2.43, host has less |
| ngspice | 36 | apt | Circuit-level SPICE (filters, matching) | Installed; not exercised |
| AFF3CT | 4.7.3 | `/home/arkady/tools/aff3ct` | LDPC encoder/decoder simulation, BER and FER curves | Build in progress (see section 5) |
| Python 3.10 modelling stack | numpy 2.2.6, scipy 1.15.3, matplotlib 3.10.3, scikit-rf 2.2.0, commpy 1.2.0 | `~/.local` (system Python) | Golden model, channel and RF impairment models, S-parameters | Installed [C] |
| gcc / g++ / cmake | system | `/usr/bin` | Bit-accurate C++ model, AFF3CT build | Installed |

Not installed (not needed yet): Qucs-S (not in the Ubuntu 22.04 repository), openEMS, Sionna, Vivado, any commercial
simulator.

### 1.1 Two Python environments

The system Python 3.10 holds the modelling stack. cocotb lives in the suite's Python 3.11, which does not see
`~/.local`. Rule: **the golden model writes test vectors to files; testbenches read them.** No testbench imports scipy.
Activate the suite with `source /home/arkady/tools/oss-cad-suite/environment`.

## 2. Known tool gaps

| Gap | Effect | Mitigation |
|---|---|---|
| No Vivado | No resource, timing or power numbers for the Zynq UltraScale+ target; no xsim | Yosys gives rough LUT counts only. Vivado ML Standard (free licence; device coverage to be checked for ZU4EV/ZU5EV/K26) is needed before any PRO-005 or timing claim |
| Hard blocks (video encoder unit, MIPI D-PHY, DDR controller, AD9361 and ADRV9002) cannot be simulated | Encoder, sensor and radio paths are not covered | Behavioural stubs with AXI-Stream interfaces; real behaviour is measured on the evaluation boards (`13`, phase A) |
| No analog or RF circuit-level tools beyond ngspice | PA load-pull and 5.8 GHz transistor-level design not possible | Behavioural PA, phase-noise and IQ models in Python; vendor S-parameters through scikit-rf |
| CDC and DFT sign-off | None for the ASIC | Out of scope until P2 |

## 3. Simulation test cases

Each test has a pass criterion. A test that compares against a model uses the same input vectors for model and RTL.

| ID | Level | Test | Requirements | Tools | Pass criterion |
|---|---|---|---|---|---|
| SIM-001 | Model | Python reference modem: OFDM mapper, IFFT, CP, preamble, FFT, equaliser, demapper at 5, 10, 20, 40 MHz | PHY-001, PHY-002, PHY-003, PHY-004 | numpy, scipy | BER over AWGN within 0.5 dB of theory for each modulation |
| SIM-002 | Model | LDPC (648 and 1944 bits, rates 1/2, 2/3, 3/4, 5/6): FER against SNR, layered min-sum with the iteration limit planned for the decoder | PHY-005, PHY-011, PHY-015 | AFF3CT, then the C++ model | FER curves per rate; SNR at FER 1e-3 per slice recorded to replace the [E] values in `07` T-16 |
| SIM-003 | Model | Doppler and delay-spread sweep: 3.5 kHz Doppler, 0.5 to 2 us delay spread, each CP option | PHY-003, PHY-007 | numpy channel model | ICI floor matches `07` T-04 (about -22 dB at 3.5 kHz); no error floor above the PER target |
| SIM-004 | Model | RF impairments: PA AM/AM and AM/PM, phase noise, IQ imbalance, DC offset, ADC/DAC quantisation, CFO | RF-*, CAL-*, PHY-009 | numpy, scikit-rf | EVM and ACLR per MCS reported; implied back-off per mode compared with `02` section 3 |
| SIM-005 | Model | Split-band blocker and TX leakage into the uplink receiver | RF-029, RF-030, RF-015 | numpy | Uplink margin and desensitisation compared with `02` |
| SIM-006 | Model | Fixed-point study: word length per stage (FFT, equaliser, LLR, decoder) | PHY-015 | C++ model | Loss against floating point 0.2 dB or less per stage [E] |
| SIM-010 | RTL | FFT 64 to 512 against NumPy | PHY-001 | Verilator, cocotb | Error within the fixed-point budget from SIM-006 |
| SIM-011 | RTL | Preamble detection, AGC settle and timing sync | PHY-010 | Verilator, cocotb | Acquisition within 40 us at the SNRs of `02` |
| SIM-012 | RTL | Modulator and demapper, all five constellations | PHY-004 | Verilator, cocotb | Bit-exact with the C++ model |
| SIM-013 | RTL | LDPC encoder and decoder | PHY-005, PHY-015 | Verilator, cocotb | Bit-exact with the C++ model; decode time of one codeword 10 us or less; throughput target of PHY-015 at the planned clock |
| SIM-014 | RTL | Full TX to RX loopback through the SIM-004 channel | PHY-* | Verilator, cocotb | PER per MCS within 0.5 dB of the model |
| SIM-020 | RTL | Frame-timeline sequencer: event table playback, jitter and stall behaviour | SW-001, MAC-003, HSI-* | Verilator, SymbiYosys | Events issued on their cycle; the data plane keeps running with the CPU stalled; formal properties hold |
| SIM-021 | RTL | TDD MAC super-frame, timing advance, guard sizing for 7, 15 and 30 km | MAC-001, MAC-003 | Verilator, cocotb | Slot boundaries within 1 us of the model; no overlap at the maximum propagation delay |
| SIM-022 | RTL | Slice framer and packetiser | VID-004, PHY-005 | Verilator, cocotb | Each slice independently decodable; codeword packing is slice-aligned |
| SIM-030 | System | Firmware against the register map under QEMU or Renode with RTL co-simulation | HSI-* | Verilator, QEMU | Register map conformance; boot to link-up sequence |
| SIM-031 | System | Fault injection: stalled core, corrupted table, PA fault | HSI-*, SEC-* | Verilator, cocotb | Fail-safe state reached within the stated time |

SIM-001 to SIM-006 need no RTL and can start immediately. SIM-010 onward need the interface definition in section 4.

## 4. Prerequisites before RTL

1. A detailed PHY and MAC design note: preamble and pilot layout, frame and slice header format, MCS table, the
   code matrices used for LDPC. Not found in the current documents [E: a re-read may find parts of it].
2. AXI-Stream interfaces and a register map for every block.
3. Fixed-point word lengths from SIM-006.
4. A test-vector file format shared by the Python model, the C++ model and the cocotb testbenches.

## 5. Tool smoke tests (done and pending)

| Check | Result |
|---|---|
| Verilator 5.055 compiles and runs a hello-world `--binary` build | Pass |
| cocotb imports in the suite Python | Pass |
| numpy, scipy, matplotlib, scikit-rf and commpy import in the system Python | Pass (versions in section 1) |
| AFF3CT builds and runs one short LDPC simulation | Pending (build running) |
| cocotb test driving a Verilator model of a small block | Not done |
| ngspice runs a netlist | Not done |

## 6. Licence reminder

The modem, FEC and MAC RTL is written clean-room (`04` section 6). AFF3CT is MIT-licensed; GNU Radio and gr-ieee802-11
(GPL) are used for comparison only and no code is copied.
