# 06 - Constellation Mapper

Plan entry: module 6 of `spec/18-development-plan.md`, class S, data plane. Requirements: PHY-004 (BPSK, QPSK, 16QAM, 64QAM, 256QAM; 256QAM in P2 and only when EVM allows). Depends on module 1 (stream convention).

## 1. Purpose

Turns groups of coded bits into complex constellation points (one per OFDM data subcarrier) with Gray labelling and unit average power, in fixed point.

## 2. Mapping

- Modulation order input `mod[2:0]`: 0 BPSK (1 bit per symbol), 1 QPSK (2), 2 16QAM (4), 3 64QAM (6), 4 256QAM (8). Values 5 to 7 are reserved and are treated as BPSK. `mod` is sampled with every beat, so the modulation may change from one subcarrier to the next (needed for a header in a robust modulation followed by the payload).
- Input element: one symbol's bits per beat, in the low `nbits` bits of the 8-bit word (`nbits` = 1, 2, 4, 6, 8); the upper bits are ignored. Bit 0 is the first bit in time (module 3 convention).
- Bits per axis `m = nbits/2` for the square QAM orders (BPSK uses I only). The first `m` bits (bit 0 first, bit 0 the most significant Gray bit) select the in-phase level, the next `m` bits the quadrature level.
- Gray labelling per axis (IEEE 802.11 labelling): the `m` Gray bits `g` (most significant first) are converted to binary `b` (`b_msb = g_msb`, `b_i = b_{i+1} XOR g_i`) and the PAM level index is `b` in 0..2^m - 1, level `2b - (2^m - 1)` (for example 16QAM: 00 gives -3, 01 gives -1, 11 gives +1, 10 gives +3; 64QAM: 000 -7, 001 -5, 011 -3, 010 -1, 110 +1, 111 +3, 101 +5, 100 +7).
- Amplitudes are fixed-point integers with unit average power scaled to a root-mean-square value of **4096** (that is 2^12, leaving 3 bits of headroom in a 16-bit signed word for the 256QAM peak of 1.15 times RMS and for the IFFT growth to be handled in module 12). Per-axis magnitudes for the odd levels 1, 3, 5, ..., computed as `round((2j+1) x 4096 / sqrt(2(M^2-1)/3))` with M the number of levels per axis (BPSK: 4096 on I, 0 on Q):

| Modulation | Magnitudes (levels 1, 3, 5, ...) |
|---|---|
| BPSK | 4096 (I axis only) |
| QPSK | 2896 |
| 16QAM | 1295, 3886 |
| 64QAM | 632, 1896, 3160, 4424 |
| 256QAM | 314, 942, 1571, 2199, 2827, 3456, 4084, 4712 |

- Output word: 32 bits, I in bits 15..0 and Q in bits 31..16, both two's-complement 16-bit (same layout as module 4).

## 3. Interface

Module `mapper`, no parameters. Ports: `mod[2:0]` (sampled per beat), `s_axis_*` (8-bit data), `m_axis_*` (32-bit data); `last` passes through. The block is combinational between the two stream interfaces (zero latency, `m_axis_valid = s_axis_valid`, `s_axis_ready = m_axis_ready`); a downstream stage registers if timing needs it.

## 4. Test plan

Python reference with the same definition (computed independently from the formulas, not from the RTL table).

| ID | Test | Pass criterion |
|---|---|---|
| T6-01 | Exhaustive: every input word (0..255, so upper bits are also exercised) for every `mod` 0 to 7 | Output equals the model for all 2048 combinations |
| T6-02 | Gray property | For every modulation, constellation points at the minimum distance differ in exactly one bit |
| T6-03 | Average power | Over all 2^nbits input words, mean of I^2 + Q^2 equals 4096^2 within 1% for each modulation (the magnitudes are rounded integers) |
| T6-04 | Per-beat modulation change | A random sequence with `mod` changing on every beat maps correctly |
| T6-05 | Random handshakes and `last` | Output equals the model; `last` passes through; zero latency (valid and ready are combinational pass-through) |
| T6-06 | Tables | The RTL magnitudes equal `round((2j+1) x 4096 / sqrt(2(M^2-1)/3))` (checked through the exhaustive test and a direct comparison with the formula in the test) |
| L-06, S-06 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 5. Deliverables

`rtl/06-mapper/mapper.sv`, `tests/06-mapper/`, results below, row in `design/README.md`.

## 6. Open items

- Non-square 32QAM or 128QAM are not included (not in PHY-004).
- Output scaling (RMS 4096) is a starting value; the final value follows from the fixed-point study SIM-006 and the IFFT scaling (module 12).
- Pilot and preamble BPSK symbols use this block (module 7 may bypass it with its own table).

## 7. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/06-mapper && tests/common/lint_synth.sh tests/06-mapper`.

| Check | Result |
|---|---|
| T6-01 to T6-06 (6 tests) | 6 of 6 pass: all 2048 (mod, input word) combinations equal the independent Python model; nearest neighbours differ in one bit for QPSK, 16QAM, 64QAM and 256QAM; mean power within 1% of 4096^2 for all five modulations; per-beat modulation changes with random handshakes (3000 beats, three handshake patterns); zero-latency pass-through; amplitude tables equal the closed form |
| Test sensitivity | A deliberate one-unit error in a table entry (1896 changed to 1897) failed three tests; the RTL was restored and the run repeated |
| Lint (`verilator -Wall`) | Clean |
| Yosys generic synthesis | 309 cells, 0 flip-flops (purely combinational), no latches |

Notes:
- BPSK polarity: input bit 1 gives +4096 and bit 0 gives -4096 (the same rule as the QAM axes with one bit). The reserved `mod` values 5 to 7 map as BPSK.
- The mapper has `clk` and `rst_n` ports for interface uniformity only; they are unused (the block is combinational).
- Writing the Gray decode in Verilog-2001 function style (variable indices, 32-bit integer arithmetic) was needed to be clean in both Verilator `-Wall` and Yosys.
