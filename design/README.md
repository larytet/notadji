# Module design specifications and test plans

One file per module of `spec/18-development-plan.md` (same numbering). Each file is the design specification and the test plan of that module, written and pushed **before** the RTL; the RTL and tests follow in a second commit.

Layout: `design/NN-name.md` (this directory), `rtl/NN-name/*.sv` (RTL), `tests/NN-name/` (cocotb tests and Makefile).

Run a module's tests: `source /home/arkady/tools/oss-cad-suite/environment && make -C tests/NN-name` (Verilator 5 with cocotb 2). Lint and synthesis checks: `make -C tests/NN-name lint synth`.

## Status

| # | Module | Design and test plan | Implementation and tests |
|---|---|---|---|
| 1 | AXI-Stream and AXI-Lite library | pending | pending |
