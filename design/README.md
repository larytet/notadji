# Module design specifications and test plans

One file per module of `spec/18-development-plan.md` (same numbering). Each file is the design specification and the test plan of that module, written and pushed **before** the RTL; the RTL and tests follow in a second commit.

Layout: `design/NN-name.md` (this directory), `rtl/NN-name/*.sv` (RTL), `tests/NN-name/` (cocotb tests and Makefile).

Run a module's tests: `source scripts/sim_env.sh && make -C tests/NN-name test` (Verilator 5 with cocotb 2). Lint and synthesis checks: `make -C tests/NN-name lint synth`.

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
| 20 | LDPC decoder | in progress | pending |
