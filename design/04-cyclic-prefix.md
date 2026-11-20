# 04 - Cyclic-Prefix Insert and Remove

Plan entry: module 4 of `spec/18-development-plan.md`, class XS, data plane. Requirements: PHY-001 (OFDM with cyclic prefix, FFT sizes 64 to 512), PHY-003 (cyclic prefix selectable among 1/16, 1/8 and 1/4 of the useful symbol), PHY-013 (programmable numerology). Depends on module 1 (stream convention).

## 1. Purpose

- **`cp_insert`** (transmit side): takes the IFFT output of one OFDM symbol (N samples) and emits the symbol preceded by a copy of its last L samples (the cyclic prefix), N + L samples in total. The prefix repeats the end of the symbol, so the whole symbol must be held before its first output sample can be sent: a buffer of N samples is inherent.
- **`cp_remove`** (receive side): takes N + L samples per symbol and passes on only the N useful samples to the FFT. An optional back-off starts the FFT window a few samples early inside the prefix, which keeps the window clear of inter-symbol interference when the timing estimate is late; the resulting phase ramp is removed by the equaliser (module 17).

## 2. Common definitions

- Sample word: 32 bits, I in bits 15..0, Q in bits 31..16 (two's-complement 16-bit each). The blocks treat the word as opaque data; the width is the parameter `W`.
- Stream convention of module 1 (`valid`, `ready`, `data`, `last`, whole words).
- Runtime configuration, sampled at the first sample of each symbol and held for that symbol:

| Input | Meaning |
|---|---|
| `fft_log2[3:0]` | log2 of N: 6, 7, 8, 9 for 64, 128, 256, 512 (10 for the optional 80 MHz mode: supported, buffer sized by parameter `MAX_LOG2`) |
| `cp_sel[1:0]` | 0: L = N/16, 1: L = N/8, 2: L = N/4 (3 is reserved and treated as 2) |

Examples: N = 256 with 1/8 gives L = 32; N = 64 with 1/16 gives L = 4; N = 512 with 1/4 gives L = 128. Values outside 6 to `MAX_LOG2` are clamped.

## 3. `cp_insert`

Parameters: `W` (default 32), `MAX_LOG2` (default 9; the buffer holds 2 x 2^MAX_LOG2 words).

Architecture: two banks used as a ping-pong buffer. The write side fills one bank with the N input samples while the read side sends the other bank as prefix then symbol. Read order for a symbol of N samples with prefix L: addresses N-L, N-L+1, ..., N-1, then 0, 1, ..., N-1. A bank is marked full when its N-th sample is written and free again after its last output sample.

Behaviour:
1. The input symbol ends after exactly N accepted samples. `s_axis_last` is expected on the N-th sample; if it is missing or early, the symbol is still closed by the count and the pulse `err_len` is raised (one clock). The output `m_axis_last` is on the last of the N + L output samples.
2. `s_axis_ready` is low only when both banks are full. Throughput: input N samples per symbol at one sample per clock when the output keeps pace; output N + L clocks per symbol, so a sustained input rate is N/(N+L) of one sample per clock and the producer is throttled by `ready` (for example a 1/8 prefix gives 89% duty).
3. Latency: first output sample is available the clock after the N-th input sample was written (N clocks after the first input sample at best).
4. Configuration is latched per bank, so the next symbol may use a different configuration while the previous one is still being sent.

## 4. `cp_remove`

Parameters: `W` (default 32), `MAX_LOG2` (default 9).
Extra input `backoff[$clog2(2**(MAX_LOG2-2))-1:0]`, the number of samples by which the FFT window starts before the end of the prefix (0 means the normal window); values above L are clamped to L. It is sampled with the configuration at the first sample of the symbol.

Behaviour: counts input samples 0 to N+L-1 of each symbol. Samples with index below L - backoff are accepted and discarded; the next N samples are passed to the output (`m_axis_last` on the N-th); the remaining backoff samples are accepted and discarded. The symbol ends after exactly N + L accepted input samples; `s_axis_last` is expected on the last one, else `err_len` pulses. No storage and no latency: output valid is the input valid during the window, and the input ready follows the output ready during the window and is 1 outside it (combinational path through `ready`).

## 5. Test plan

Reference models in Python (list operations on symbols). Stream driving as in modules 1 to 3 (`tests/common/stream_tb.py`), with a new hook `pre` that lets a test change the configuration at the exact word boundary.

| ID | Block | Test | Pass criterion |
|---|---|---|---|
| T4-01 | insert | Every N (64, 128, 256, 512) with every cp_sel (0, 1, 2), 20 symbols each, full speed | Output equals the model: last L samples first, then all N, `last` on the last sample |
| T4-02 | insert | Random valid and ready patterns | Same as T4-01; no loss, no duplicates; the protocol-stability check passes |
| T4-03 | insert | Configuration changes at every symbol (random N and cp_sel) while the previous symbol is still being sent | Each symbol uses the configuration present at its first sample |
| T4-04 | insert | Sustained throughput | With an always-ready sink and an always-valid source, the input duty equals N/(N+L) within one symbol; no deadlock |
| T4-05 | insert | Bad `last` position | `err_len` pulses once per bad symbol, the stream keeps going, next symbols correct |
| T4-06 | remove | Every N and cp_sel, backoff 0 | Output equals the useful samples; `last` on the N-th |
| T4-07 | remove | Backoff 1 to L, and a value above L | Window starts backoff samples early; clamp works |
| T4-08 | remove | Random valid and ready, per-symbol configuration changes through the `pre` hook | Matches the model |
| T4-09 | remove | Bad `last` | `err_len` pulses; the count still closes the symbol |
| T4-10 | both | Loop-back: insert followed by remove (two simulations; the output of the first is the input of the second) | Original samples recovered for all N, cp_sel |
| L-04, S-04 | both | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

Configurations: `W=32, MAX_LOG2=9` for both blocks; `W=16, MAX_LOG2=7` (small) for both.

## 6. Deliverables

`rtl/04-cyclic-prefix/cp_insert.sv` and `cp_remove.sv`, `tests/04-cyclic-prefix/`, results below, row in `design/README.md`; `tests/common/stream_tb.py` gains the `pre` hook (backward compatible).

## 7. Open items

- The sample RAM uses an asynchronous (combinational) read, which synthesises to distributed RAM or flip-flops; a block-RAM mapping needs a registered read and one more pipeline stage. Decide with Vivado results (not available yet).
- Optional windowing (raised-cosine edge shaping to reduce out-of-band emissions) is not part of this module; it is a transmit filter stage to be added with the RF mask work (RF-014, PHY-009).

## 8. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/04-cyclic-prefix && tests/common/lint_synth.sh tests/04-cyclic-prefix`.

| Check | Result |
|---|---|
| T4-01 to T4-10 in 6 configurations (`cp_insert`, `cp_remove`, loop-back; each with W=32/MAX_LOG2=9 and W=16/MAX_LOG2=7) | 20 of 20 pass: all N from 64 to 512 and all three prefix lengths, random handshakes, per-symbol configuration changes, back-off including values above L, bad `last` |
| Throughput (T4-04) | The input period equals N + L clocks within one clock for every N and prefix length, with no deadlock |
| Test sensitivity | A deliberate bug (prefix read address off by one) failed four of the five insert tests; the RTL was restored |
| Lint (`verilator -Wall`) | Clean for `cp_insert`, `cp_remove` and the test wrapper |
| Yosys generic synthesis | `cp_insert` (W=32, 2 x 512 words): 67165 cells, 32816 flip-flops (the sample memory as flip-flops, 32768 of them); `cp_remove`: 520 cells, 28 flip-flops; no latches |

Notes found during the work:
- `err_len` pulses once for every beat where `last` disagrees with the count: a missing `last` gives one pulse, a `last` that is early gives two (at the early beat and at the closing beat). The test checks exactly these counts (3 pulses for one early plus one missing). The text of section 3 (item 1) says one pulse per bad symbol; the behaviour above is the implemented and tested one.
- `run_stream` in `tests/common/stream_tb.py` now also waits until every input word has been accepted. With a back-off, `cp_remove` still consumes discarded samples after the last output sample, and the earlier stop condition left the DUT mid-symbol for the next run (a test bug, not a design bug).
- The sample memory is 2 x 512 x 32 bits of flip-flops in generic synthesis; the FPGA tools should infer block RAM only if the read is registered (open item in section 7).
