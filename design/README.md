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
| 11 | Radio interface wrapper | done (`30cee02`) | done: 7 tests in 5 simulations pass, lint clean, no latches |
| 12 | FFT and IFFT | done (`4626116`) | done: 17 tests (3 simulations, bit-exact model and numpy accuracy) pass, lint clean, no latches |
