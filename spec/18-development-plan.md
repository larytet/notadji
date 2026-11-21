# 18 - Module Development Plan (FPGA phase, P1)

Status: DRAFT (initial). Lists the modules to develop for the FPGA prototype, **ordered by rising complexity: the
first row is the easiest, the last row the hardest**. Complexity is a relative engineering judgement **[E]**, not a
schedule; effort in person-years for the whole ASIC programme is in `16`. Test identifiers (`SIM-nnn`) refer to
`17`; requirement identifiers to `01`; platform phases A and B to `13`.

## 1. How to read the order

- The order is by complexity. Where a module needs another that is more complex, the dependency column says so and the
  easier module can still be built and tested alone against a stub.
- Complexity classes: **XS** a day or two, **S** about a week, **M** a few weeks, **L** a few months, **XL** a team-year or more
  **[E]**; one engineer with the golden model already written.
- Every module follows the same steps (definition of done): (1) golden model in Python and, where bit-accuracy matters, C++;
  (2) test vectors in the shared file format (`17` section 4); (3) RTL; (4) cocotb or formal test passing against the
  vectors; (5) lint clean in Verilator; (6) Yosys synthesis without latches or unresolved clock crossings; (7) a timestamp
  tap (LAT-004) on the block boundary.
- Clean-room rule (`04` section 6): RTL is written from the specification and the literature; GPL and AGPL projects are
  behavioural references only.

Block diagram of the modules (interactive, open in a browser; zoom from components to modules to internal blocks): [`diagrams/modem-modules.html`](diagrams/modem-modules.html). It also marks the interfaces that no module covers yet.

## 2. Modules in order of rising complexity

| # | Module | Class | Domain | What it does | Requirements | Needs | Tests |
|---|---|---|---|---|---|---|---|
| 1 | AXI-Stream and AXI-Lite library: skid buffer, FIFO, width converter, clock-crossing FIFO, register file | XS | Data plane | Common plumbing for every later block | HSI-001 | none | SIM-010 (as harness) |
| 2 | Timestamp unit: 64-bit free-running counter, latch registers per pipeline tap, trace output | XS | Data plane | Per-stage timing evidence for the latency budget | HSI-003, LAT-004 | 1 | SIM-020 |
| 3 | Scrambler (PRBS) and CRC engines (header and slice CRC) | XS | Data plane | Whitening and error detection on slices | PHY-005, VID-004 | 1 | SIM-022 |
| 4 | Cyclic-prefix insert and remove, sample buffering | XS | Data plane | Guard interval options 1/16, 1/8, 1/4 | PHY-003 | 1 | SIM-010 |
| 5 | Bit interleaver and de-interleaver | S | Data plane | Spreads burst errors across subcarriers | PHY-001, PHY-005 | 1 | SIM-012 |
| 6 | Constellation mapper | S | Data plane | BPSK, QPSK, 16QAM, 64QAM, 256QAM (256QAM only in P2) | PHY-004 | 1 | SIM-012 |
| 7 | Preamble and pilot generator | S | Data plane | Sequences and pilot positions for sync and tracking | PHY-007, PHY-010 | 1 | SIM-011 |
| 8 | Serial telemetry bridge (UART, MSP, MAVLink framing) | S | Data plane | Telemetry and control channel at 5 ms latency | MAC-007, IF-001 | 1 | SIM-030 |
| 9 | Slice packetiser and depacketiser, slice header | S | Data plane | Slice-aligned codeword packing, sequence numbers, ACK bitmap fields | VID-004, VID-011, PHY-005 | 1, 3 | SIM-022 |
| 10 | Frame-timeline sequencer (event table, executor, safe schedule) | M | Data plane | Hops, TX/RX enable, PA enable, gain steps, slice slots from a table loaded a frame ahead; keeps running if the CPU stalls | HSI-001, HSI-002, SW-001 | 1, 2 | SIM-020, SIM-031 |
| 11 | Radio interface wrapper (AD9361 or ADRV9002 data port, SPI control, sample timing) | M | Data plane | Moves I/Q between fabric and transceiver; behavioural stub in simulation, real behaviour measured on the boards | PRO-007, RF-006 | 1, 10 | SIM-014 (stub) |
| 12 | FFT and IFFT, 64 to 512 points, run-time selectable | M | Data plane | Core of the OFDM modem; 1024 points for the optional 80 MHz mode in P2 | PHY-001, PHY-002, PHY-013 | 1 | SIM-010 |
| 13 | LDPC encoder (quasi-cyclic, 648 and 1944 bits, four rates) | M | Data plane | Encodes slices | PHY-005 | 1, 9 | SIM-013 |
| 14 | Demapper with soft output (LLR) | M | Data plane | Log-likelihood ratios for the decoder; fixed-point width set by SIM-006 | PHY-004, PHY-005 | 6 | SIM-012 |
| 15 | Authenticated encryption (ChaCha20-Poly1305, per-slice tag, replay counter) | M | Data plane | Link encryption without AES hardware | SEC-002, HSI-004 | 1, 9 | SIM-022 |
| 16 | Transmit chain integration: mapper, pilots, IFFT, CP, preamble, framing | M | Data plane | First end-to-end transmit path; loopback to a software receiver model | PHY-001 to PHY-004 | 4, 6, 7, 9, 12, 13 | SIM-014 |
| 17 | Channel estimator, equaliser and pilot tracking | L | Data plane | Per-subcarrier correction; tracks a channel that changes inside a frame | PHY-003, PHY-007 | 7, 12 | SIM-003, SIM-014 |
| 18 | Preamble detector, AGC controller, timing and carrier-offset synchroniser | L | Data plane | Burst acquisition within 40 us; residual offset below 0.1 ppm | PHY-008, PHY-010 | 7, 11, 12 | SIM-011 |
| 19 | Multi-branch combiner (two branches, then four to eight) | L | Data plane | Maximum-ratio combining across receive chains | PHY-006, PHY-016 | 17 | SIM-014 |
| 20 | LDPC decoder (layered min-sum, 648 and 1944 bits, iteration control) | L | Data plane | 155 Mbit/s information throughput, codeword decode in 10 us or less | PHY-015, PHY-011 | 13, 14 | SIM-013 |
| 21 | Receive chain integration and full link loopback with impairments | L | Data plane | Closes the modem: PER per MCS against the model | PHY-* | 16, 17, 18, 20 | SIM-014 |
| 22 | TDD MAC engine: super-frame, timing advance, guard sizing, feedback and ACK bitmap, selective retransmission | L | Data plane with real-time core | Scheduled access, 1 us time sync, uplink feedback each millisecond | MAC-001 to MAC-006 | 2, 9, 10, 21 | SIM-021 |
| 23 | Link-adaptation controller (MCS, power, slice budget) | L | Real-time core firmware | Reacts to feedback within 2 ms | MAC-005, PHY-012 | 22 | SIM-030 |
| 24 | Spectrum scan and channel-selection logic | L | Real-time core with data plane | Scans channels in 50 us dwells, ranks them, drives channel switches | ADA-001 to ADA-003 | 10, 11, 18 | SIM-030 |
| 25 | Calibration engine: factory tables, background IQ and LO-leakage loops, thermal triggers | L | Real-time core with data plane | Keeps the front end calibrated without interrupting video | CAL-001 to CAL-004 | 10, 11, 18 | SIM-004 |
| 26 | Peak-to-average reduction and digital pre-distortion (correlation hardware) | XL | Data plane | Meets the spectrum mask with the planned PA back-off; adapts from the observation receiver | PHY-009, CAL-005, HSI-004 | 11, 21, 25 | SIM-004 |
| 27 | Display synchronisation and scan-out (line-synchronised output, pixel-clock steering) | XL | Ground-unit data plane | Display starts scanning before the frame is fully decoded; clock steered to 0.1 ppm resolution | VID-015, VID-018 | 2, 9 | SIM-030 (partial; needs hardware) |
| 28 | Video path, phase A: wrapper around the hard encoder and a hardware or software decoder | XL | Data plane | Slice-based low-latency configuration, intra-refresh, rate control hooks; cannot be simulated, measured on boards | VID-003 to VID-005, VID-020, VID-021 | 9, 22 | TG-VID (`08`) |
| 29 | Custom slice-based video encoder and decoder (replaces the hard unit) | XL | Data plane | The product encoder: no cross-slice dependencies, reactive slice refresh, optional foveation | VID-003 to VID-005, VID-021, VID-023 | 28 | TG-VID (`08`) |
| 30 | Soft combining of retransmitted slices and decoder array (extension, requirements in `../requirements/30-soft-combining.md`) | M | Data plane | Chase combining of LLRs before the decoder, retention policy, array of decoder instances for the heavier decoding | PHY-017, MAC-006 | 14, 20, 22 | SIM-002 |
| 31 | DFT-spread OFDM low-PAPR mode (extension, `../requirements/31-dft-s-ofdm.md`) | L | Data plane | Transmit spreading and receive MMSE despreading, contiguous allocation with reference symbols | PHY-014, PHY-009 | 6, 12, 14, 17 | SIM-005 |
| 32 | Custom codec efficiency, profile SL2 (extension, `../requirements/32-codec-efficiency.md`) | XL | Data plane | Integer DCT, intra modes, quarter-pel motion, context-adaptive arithmetic coding, deblocking, RDO on the module 29 slice structure | VID-027 | 29 | SIM-040 |
| 33 | Firmware framework for the real-time control core (extension, `../requirements/33-firmware-framework.md`) | XL | Control plane | HAL and simulated sequencer, static scheduler, crash log, supervision and monitor core, MAC feedback path, thermal and RF protection, MAVLink/MSP parsing, X25519 pairing, Ed25519-signed tables and A/B updates; AArch64 (LP64) target, host tests | SW-001..SW-009, HSI-005..HSI-015 | 10, 22, 23, 24, 25, 26 | SIM-031 (SIM-030 needs QEMU or Renode: not done) |

Not hardware modules but required for the first link: the real-time firmware and hardware abstraction layer (HSI-*
requirements and `13`), pairing and secure boot (SEC-001, SEC-003), and the application-core services (`13` section 1). They start
after module 10 and are sequenced in `13`.

## 3. Milestones

| Milestone | Modules | Exit criterion |
|---|---|---|
| M0 Tooling and harness | 1 to 4 | A cocotb test drives a Verilator model of a small block; shared test-vector format agreed; a block passes lint and Yosys synthesis |
| M1 Transmit path in simulation | 5 to 9, 12, 13, 16 | Transmit output matches the Python model bit for bit |
| M2 Timing infrastructure | 10, 11 | Sequencer table plays back on its cycles with the CPU stalled; radio stub exchanges samples |
| M3 Modem loopback | 14, 17, 18, 20, 21 | PER per MCS within 0.5 dB of the model through the impairment channel (SIM-014) |
| M4 First link on boards | 11, 15, 21, 22 | Two evaluation boards exchange scheduled frames conducted through an attenuator; timestamps logged at every stage |
| M5 Closed-loop operation | 19, 23 to 25 | Link adaptation, channel selection and background calibration running on the link |
| M6 Latency and linearity | 26 to 29 | SYS-002 (30 ms glass to glass) and spectrum mask met on the prototype (`08` stage P1a to P1c) |

## 4. Where to start

Modules 1, 2 and 3 first: they are quick, every later block depends on module 1, and they exercise the whole toolchain
(Verilator, cocotb, Yosys, test-vector files) at low risk. In parallel, and with no RTL, run the model-only items
SIM-001 to SIM-006 of `17`, because their results (word lengths, SNR operating points, back-off) feed modules 6, 14, 17,
20 and 26.

## 5. Risks to the order

- The video path (modules 27 to 29) dominates the schedule and the latency result; start the phase A wrapper (module 28)
  as soon as a board and the vendor tools are available, in parallel with the modem.
- Module 11 depends on the exact transceiver chosen (AD9361 or ADRV9002, trade study T-11); keep the radio-facing code
  behind a thin interface so the choice does not touch the modem.
- The interface definitions of `17` section 4 (preamble layout, slice header, register map) are not yet written; modules
  7, 9 and 18 cannot be finished without them.
- Complexity classes are judgement; the first two milestones will show how far off they are and the table should be
  revised then.
