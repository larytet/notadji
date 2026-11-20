# 01 - AXI-Stream and AXI-Lite Library

Plan entry: module 1 of `spec/18-development-plan.md`, class XS, data plane. Requirement anchor: HSI-001 (data plane independent of the CPU). The library has no requirement of its own; every later block uses it.

## 1. Purpose

Common plumbing so that later modules do not each re-invent handshakes, buffering, width change and register access, and so that the
clock-crossing and back-pressure rules are verified once.

## 2. Conventions (apply to all modules in `rtl/`)

- Language: SystemVerilog-2012 subset accepted by Verilator 5 and Yosys: `logic`, `always_ff`, `always_comb`, packages, parameters. No latches, no `initial` for state other than simulation-only.
- Clocks and resets: `clk`, `rst_n` (synchronous assert and release in each domain, active low). Reset values are explicit for every control flop; data flops are not reset.
- Stream interface (AXI-Stream subset): `*_valid`, `*_ready`, `*_data[W-1:0]`, `*_last`. A transfer happens on the clock edge where valid and ready are both 1. The source holds valid and data stable until the transfer; `valid` never depends combinationally on `ready`. No `keep`, `strb`, `id`, `dest`, `user` (frames are whole words; see 3.3).
- Naming: `s_axis_*` is the slave (input), `m_axis_*` the master (output).
- Every module has a parameter list with defaults and no hidden constants.

## 3. Blocks

### 3.1 `axis_skid` - register slice with full throughput

Parameter `W` (data width). Breaks the combinational `ready` path between two stages with no throughput loss: after reset it accepts a word every clock when the sink is ready every clock. Two storage entries (output register and skid register). Latency 1 clock when empty. Output `m_axis_*` is registered; `s_axis_ready` is registered (does not depend on `m_axis_ready` in the same cycle).

### 3.2 `axis_fifo` - synchronous FIFO

Parameters `W`, `DEPTH` (power of two, 2 or more). Common-clock FIFO with first-word-fall-through: `m_axis_valid` is high whenever the FIFO is not empty. Storage in an array (maps to block RAM or distributed RAM). Output `level[$clog2(DEPTH):0]` is the number of stored words. Writes when full are not accepted (`s_axis_ready` low); no overflow or underflow is possible through the stream ports. Latency 1 clock from write to `m_axis_valid` (write then read data in the next cycle).

### 3.3 `axis_width_conv` - integer-ratio width converter

Parameters `IN_W`, `OUT_W`, where one is an integer multiple of the other (equal widths are a pass-through). Packing order: little-endian (the first input beat occupies the least significant bits of the output beat for up-conversion; for down-conversion the least significant output beat is sent first). `last` is passed on the last output beat of a frame. Contract: for up-conversion the number of input beats in a frame is a multiple of `OUT_W/IN_W`; a frame that violates it is flagged on `err_frame` (a sticky pulse) and the partial word is flushed with zero fill, so the stream does not hang. Back-pressure is honoured on both sides with no data loss. Throughput: one output word per `OUT_W/IN_W` input beats at full rate for up-conversion; one input word per `IN_W/OUT_W` output beats for down-conversion.

### 3.4 `axis_cdc_fifo` - asynchronous FIFO

Parameters `W`, `AW` (depth is 2^AW, `AW` at least 2). Two clock domains `s_clk`, `m_clk` with independent resets (`s_rst_n`, `m_rst_n`). Gray-coded read and write pointers with two-flop synchronisers; full is computed in the write domain, empty in the read domain, so both flags are conservative (never wrongly allow a write to a full FIFO or a read from an empty one). Throughput is limited only by the slower clock. Latency from write to first read: 2 to 4 cycles of the read clock after the synchroniser delay [E]. Reset: both sides reset together (the integrator asserts both resets at the same time); documented in the module header.

### 3.5 `axil_regfile` - AXI-Lite slave register file

Parameters `N` (number of 32-bit registers, default 16), `ADDR_W` (byte address width, at least `$clog2(N)+2`), `RO_MASK` (bit vector of length N; 1 marks a read-only register whose value comes from the input `ro_data[N*32-1:0]`), `RESET_VALUES` (N x 32 bits, default 0). Outputs: `rw_data[N*32-1:0]` (current value of every register), `wr_pulse[N-1:0]` (one clock when a register is written, for side effects). AXI-Lite: 32-bit data, `AWADDR`, `AWVALID`, `AWREADY`, `WDATA`, `WSTRB`, `WVALID`, `WREADY`, `BRESP`, `BVALID`, `BREADY`, `ARADDR`, `ARVALID`, `ARREADY`, `RDATA`, `RRESP`, `RVALID`, `RREADY`. Write strobes honoured per byte. A write to a read-only register is accepted with `OKAY` and ignored; an access outside the register range answers `SLVERR` (response `2'b10`) and returns 0 on reads. One outstanding transaction of each type; address and data may arrive in any order. Registers are word-aligned (`addr[1:0]` ignored).

## 4. Test plan

Tests are cocotb coroutines against Verilator builds of small wrapper tops (`tests/01-axi-library/`). Each test drives randomised valid and ready patterns from a fixed seed and checks the output against a Python queue model. All tests also check the protocol rule that valid, data and last are stable while valid is high and ready is low.

| ID | Block | Test | Pass criterion |
|---|---|---|---|
| T1-01 | skid | Random back-pressure, 5000 words | Output equals input in order; no loss or duplication |
| T1-02 | skid | Sink always ready, source always valid, 1000 words | One word per clock after fill; no bubbles in the output |
| T1-03 | skid | Sink stalls for 50 clocks with source valid | `s_axis_ready` falls, no word lost, resumes in order |
| T1-04 | fifo | Fill to full then drain, DEPTH 16 | `level` correct at every step; ready low at full; valid low at empty |
| T1-05 | fifo | Random read and write, 20000 operations | Data in order; level matches the model every clock; never overflows |
| T1-06 | width conv | 8 to 32, 32 to 8, 16 to 64, 64 to 16, 8 to 8 with random frames, random back-pressure | Output equals the packed or unpacked input; `last` on the right beat |
| T1-07 | width conv | Up-conversion with a frame of non-multiple length | `err_frame` pulses once per bad frame; the stream does not hang; next frame is correct |
| T1-08 | cdc fifo | Write clock 200 MHz and read clock 150 MHz, then reversed, 20000 words, random enables | Data in order; no loss; no reads when empty; no writes when full |
| T1-09 | cdc fifo | Read clock 10x slower than the write clock (full pressure) | Writes stall via ready, nothing lost |
| T1-10 | regfile | Write and read back every register, with byte strobes | Written bytes change, other bytes keep their value |
| T1-11 | regfile | Read-only register, write attempt | Value unchanged; response OKAY |
| T1-12 | regfile | Out-of-range read and write | Response SLVERR; read data 0; no register changed |
| T1-13 | regfile | Address before data and data before address; back-to-back transactions with random delays | All complete, correct data |
| T1-14 | regfile | `wr_pulse` | Exactly one pulse per written register per write |
| L-01 | all | `verilator --lint-only -Wall` | No warnings (documented waivers allowed in the Makefile) |
| S-01 | all | Yosys `synth -top <name>; stat` plus a check for `$dlatch` cells | No latches; cell counts recorded in the test log |

Coverage target: every branch of the five modules exercised by the tests above; Verilator coverage (`--coverage`) is reported but is not a gate in this module.

## 5. Deliverables

`rtl/01-axi-library/*.sv`, `tests/01-axi-library/` (cocotb tests, Makefile with targets `test`, `lint`, `synth`), this file updated with the measured synthesis counts, and the row in `design/README.md`.

## 6. Open items

- Whether `keep` or `user` sideband signals are needed (decide with module 9, the slice packetiser).
- A formal proof of skid and FIFO invariants with SymbiYosys (optional, after the cocotb tests).

## 7. Results (implementation commit)

Environment: `source scripts/sim_env.sh` (Verilator 5.055 and Yosys 0.71 from the OSS CAD Suite, cocotb 2.1.0 from `/home/arkady/tools/venv-cocotb`). Run `make -C tests/01-axi-library test lint synth`.

| Check | Result |
|---|---|
| Tests T1-01 to T1-14 (9 configurations: skid, fifo, width conversion 8>32, 32>8, 16>64, 64>16, 8>8, cdc fifo, regfile) | All pass |
| Lint (`verilator --lint-only -Wall`, all five tops) | Clean, no waivers except the intentional unused address bits in `axil_regfile` (tied off in an `unused_ok` wire) |
| Yosys generic synthesis, latch check | No latches in any block |

Yosys generic gate counts (`synth`, no technology mapping, so they only compare blocks; Vivado numbers are needed for the FPGA):

| Block (default parameters) | Cells | Flip-flops |
|---|---|---|
| `axis_skid` (W=32) | 112 | 68 |
| `axis_fifo` (W=32, depth 16) | 1362 | 542 |
| `axis_width_conv` (8 to 32) | 201 | 69 |
| `axis_cdc_fifo` (W=32, depth 16) | 1362 | 568 |
| `axil_regfile` (16 registers) | 1343 | 608 |

The FIFO memories are flip-flop arrays here because generic synthesis does not infer block RAM; the FPGA tools will map them to RAM.

Implementation notes found during the work:
- `axil_regfile` does not pulse `wr_pulse` for a write to a read-only register (the design text in 3.5 said a pulse per written register; read-only writes are ignored entirely).
- The clock-crossing test uses 200 MHz against about 150 MHz (period 6666 ps, because the simulator needs an even period in picoseconds).
- The OSS CAD Suite's own cocotb cannot link on this host (it needs glibc 2.38; the host has 2.35), hence the separate virtual environment.
