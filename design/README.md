# Module design specifications and test plans

One file per module of `spec/18-development-plan.md` (same numbering). Each file is the design specification and the test plan of that module, written and pushed **before** the RTL; the RTL and tests follow in a second commit.

Layout: `design/NN-name.md` (this directory), `rtl/NN-name/*.sv` (RTL), `tests/NN-name/` (cocotb tests and Makefile).

Run a module's tests: `source scripts/sim_env.sh && make -C tests/NN-name test` (Verilator 5 with cocotb 2). Lint and synthesis checks: `make -C tests/NN-name lint synth`.

Block diagram of all modules, interactive: `spec/diagrams/modem-modules.html` (open it in a browser).

## Status

| # | Module | Design and test plan | Implementation and tests |
|---|---|---|---|
| 1 | AXI-Stream and AXI-Lite library | done (`adc5cac`) | done: 14 tests in 9 configurations pass, lint clean, no latches |
| 2 | Timestamp unit | done (`3475037`) | done: 20 tests (2 configurations) pass, lint clean, no latches |
| 3 | Scrambler and CRC engines | done (`e4e1f2c`) | done: 40 tests (8 configurations) pass, lint clean, no latches |
| 4 | Cyclic-prefix insert and remove | done (`db5e482`) | done: 20 tests (6 configurations) pass, lint clean, no latches |
| 5 | Interleaver and de-interleaver | done (`e9cb26a`) | done: 44 tests (8 configurations) pass, lint clean, no latches |
| 6 | Constellation mapper | done (`33cb2ec`) | done: 6 tests pass (all 2048 mod/word combinations), lint clean, no latches |
| 7 | Preamble and pilot generator | done (`23cb7ba`) | done: 7 tests pass (STF periodicity via numpy), lint clean, no latches |
| 8 | Serial telemetry bridge | done (`7adcb0c`) | done: 13 tests in 5 simulations pass, lint clean, no latches |
| 9 | Slice packetiser and depacketiser | done (`f34b3ab`) | done: 20 tests (6 configurations) pass, lint clean, no latches |
| 10 | Frame-timeline sequencer | done (`583bc29`) | done: 20 tests (2 configurations, cycle-accurate model) pass, lint clean, no latches |
| 11 | Radio interface wrapper | done (`30cee02`) | done: 6 tests in 5 simulations pass, lint clean, no latches |
| 12 | FFT and IFFT | done (`4626116`) | done: 17 tests (3 simulations, bit-exact model and numpy accuracy) pass, lint clean, no latches |
| 13 | LDPC encoder | done (`16744b4`) | done: 7 tests (all 8 codes, real 802.11n code cross-checked against the AFF3CT alist) pass, lint clean, no latches; code quality measured with AFF3CT |
| 14 | Soft demapper | done (`2fb39e1`) | done: 7 tests pass (hard decisions = nearest point, QPSK BER matches theory), lint clean, no latches |
| 15 | Authenticated encryption (ChaCha20-Poly1305) | done (`d88afd0`) | done: 9 tests pass against the `cryptography` reference (RFC 8439), 1135 Mbit/s, lint clean, no latches |
| 16 | Transmit chain integration | done (`5e2e0ff`) | done: whole chain bit-exact against the golden model and recovered by a closed-loop receiver; 5 glue blocks tested; lint clean, no latches |
| 17 | Channel estimator and equaliser | done (`28117b1`) | done: 8 tests pass (bit-exact model, EVM -50 to -60 dB noiseless, within 0.1 dB of a float reference with noise), lint clean, no latches; full gate-level synthesis not completed |
| 18 | Burst detection, timing and carrier-offset estimation | done (`b0b5951`) | done: 7 tests pass (100% detection at 5-20 dB, CFO error 0.012 at 20 dB, marker reliable to 10 dB only), lint clean, no latches; full gate-level synthesis not completed |
| 19 | Multi-branch combiner (MRC) | done (`899988a`) | done: 15 tests (B = 2, 4, 8) pass, array gain 3.03 / 6.01 / 9.03 dB, matches ideal float MRC; lint clean, no latches |
| 20 | LDPC decoder | done (`189c69d`) | done: 5 tests pass; RTL equals the model and corrects as many frames as a floating-point reference; model FER at or below AFF3CT; single-instance throughput 34-114 Mbit/s (below PHY-015); lint clean; Yosys not completed |
| 21 | Receive chain integration | done (`e7f9ba0`) | done: closed loop TX to channel to RX recovers all frames (noiseless, offsets, 2-tap multipath, 11 to 25 dB noise, five frames in a row); three integration defects fixed (FFT scale, trim restart, early detection in module 18); lint clean; sustainable rate limited by the 1 LLR per clock serializer; chain not synthesisable with Yosys |
| 22 | TDD MAC engine | done (`e59eff7`) | done: 9 simulations pass; frame timer, schedule (guard 53 to 220 us as `02`), timing advance (burst alignment 0 ticks, range 0 to 30 km), ACK window, selective retransmission with refresh; two-unit delay-line test; three defects fixed (tail loss, entry race, TA and plan applied together); lint clean; no latches |
| 23 | Link-adaptation controller | done (`7346ba1`) | done (firmware, host build): 12 tests pass; MCS follows a 15 dB drop in the first feedback message, 4+ steps per second, outer loop reaches the loss target under a 3 dB estimate bias, safe schedule at 10 ms; fading result mixed (Rician good, Rayleigh worse than best fixed MCS); not run on a target core (no QEMU/Renode) |
| 24 | Spectrum scan and channel selection | done (`c64ab75`) | done: RTL scan engine (exact energy sums, table, timeout) with 4 cocotb tests; firmware ranking and switching with 11 host tests (decision latency 13 ms worst case, fallback, probation, 4-link coexistence); lint clean, no latches; not run on a target core |
| 25 | Calibration engine | done (`27dccdf`) | done: RTL `cal_stats` and `iq_corr` (bit-exact), blind IQ and DC firmware estimator, tables with CRC, triggers; closed loop in RTL gives 49 dB RX image rejection, -81.6 dBFS DC, -45 dBc TX sideband and leakage; 4800 bit-flips detected; lint clean, no latches; not run on a target core |
| 26 | PAPR reduction and DPD | done (`500092d`) | done: RTL clip, FIR, memory-polynomial DPD (NCM 1/3/9) and correlation accumulator bit-exact; solver with Jacobi scaling; PA model: DPD converges in 3 iterations (4.4 ms cold start); EVM -32.6 dB and ACLR -45.6 dBc at 7.4 dB back-off, **not met together at 7.0 dB** (PHY-009 open); lint clean, no latches |
| 27 | Display synchronisation and scan-out | done (`4656123`) | done: RTL timing generator, phase measurement, PI steering and line freshness bit-exact against models; 10-minute steering simulation holds the display within 1 us after lock (2 us at 1 us reference jitter) against 1 ms required; early scan-out saves 5 to 15 ms; oscillator and display not simulated; lint clean, no latches |
| 28 | Video path phase A: encoder wrapper | done (`8c6827c`) | done: splitter (AVC and HEVC), slice tagging, bitstream-level budget monitor, refresh mapping with encoder-latency queues, rate-control hook; end-to-end 968 slices equal the model; the hard encoder itself not simulated (board measurement); lint clean, no latches |
| 29 | Custom slice-based video encoder and decoder | done (`dc1e295`) | done (reference model + RTL kernel): exact slice independence, hard budget bound (no slice above 105%), reactive refresh within one frame, foveation saves 53% at equal centre quality; RTL `wht8x8` and `quant` bit-exact; **but 6.8 to 7.6 times the bit rate of x264 at equal PSNR** (the codec is not competitive on efficiency); no RTL encoder or decoder; not flight video; tests re-run 2026-11-21, all pass; the efficiency gap is addressed by module 32 (SL2, 1.9 to 2.0 times x264) |
| 30 | Soft combining of retransmitted slices and decoder array (PHY-017) | done (`1405240`) | done: chase combiner with retention policy (7 mutants killed), decoder array P = 1 to 4, closed loop with the real decoder; **two combined receptions gain 3.1 dB** (three 4.5 dB), 20 against 10 iterations only 0.2 to 0.4 dB; array reaches 161 Mbit/s at R5/6 (limited by 1 LLR per clock input); lint clean; combiner no latches, array not synthesised (decoder) |
| 31 | DFT-spread OFDM low-PAPR mode (PHY-014) | done (`2f00e28`) | done: mixed-radix DFT engine (M = 3N/4), transmit stage, MMSE receive stage with reference-symbol correction, all bit-exact; symbol-level loop with the real mapper, IFFT, cyclic prefix and demapper; 7 mutants killed; **PAPR gain 3.1 to 3.3 dB only for QPSK at N >= 128 (BPSK 1.9 to 2.3, 16QAM 2.1 to 2.4, not the 3 dB of PHY-014)**; AWGN BER within 0.1 dB of OFDM with boosted references; coded multipath 0.2 to 1.2 dB worse than OFDM; not integrated into the chains; lint clean, RTL-level no latches, full synthesis not completed |
| 32 | Custom codec efficiency, profile SL2 | done (`f70c95f`) | done: C reference model with integer DCT, intra modes, quarter-pel motion, context-adaptive arithmetic coding, deblocking and RDO; closed loop exact in 9 configurations, slice independence, hard budget (about 8 encodes per slice), refresh; **1.96 times the bit rate of x264 at 35 dB and 1.92 at 38 dB (SL1: 6.8 and 7.6)**, quarter-pel the largest tool; RTL `dct8x8` bit-exact; 8 mutants killed; luma only, one sequence |
