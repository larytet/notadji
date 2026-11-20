# 20 - LDPC Decoder

Plan entry: module 20 of `spec/18-development-plan.md`, class L, data plane. Requirements: PHY-005, PHY-011 (slice error rate), PHY-015 (decoder throughput of at least 155 Mbit/s of information, codeword decode within 10 us; the spec counts three decoder instances at 200 MHz), PHY-017 (more iterations in the enhanced ground unit). Decodes the eight codes of module 13; takes the 8-bit log-likelihood ratios of module 14 (positive = bit 0) after the de-interleaver of module 5.

## 1. Algorithm and architecture

**Layered normalised min-sum** (one layer per block row of the base matrix, posterior values updated after every layer), normalisation factor 3/4, 8-bit signed LLRs saturated to -127..+127, up to `max_iter` iterations with early termination. The code is quasi-cyclic, so the `Z` rows of a block row (Z = 27 or 81) are processed in parallel: one block column per clock for each of two passes per layer.

State: `post[j][b]` the posterior LLR of bit `b` of variable block `j` (24 blocks of Z); per layer and row the check-to-variable messages in compressed form: the two smallest magnitudes `m1`, `m2` (7 bits), the entry index of `m1` (5 bits) and one sign bit per entry (24 bits).

Per layer `i` with entries `e = 0 .. d-1` (the non-empty base entries, block column `col_e` and cyclic shift `s_e`):
- **Pass A** (one entry per clock, for all rows `r` in parallel): `x = post[col_e][(r + s_e) mod Z]`; `c_old` = the old message of this entry (magnitude `scale(m1 or m2)`, `m2` when `e` is the stored index, with the stored sign); `v = sat8(x - c_old)`; update the running `m1`, `m2`, index of the minimum and sign product with `|v|` and `sign(v)`; remember `sign(v)` per entry. Also the parity of the hard decisions of `x` over the row.
- **Pass B** (one entry per clock): recompute `v`; the new message has magnitude `scale(m2 if e == index else m1)` and sign (sign product XOR `sign(v)`); `post <- sat8(v + c_new)`; remember whether the hard decision changed. At the end of the layer the new `m1, m2, index, signs` replace the stored ones.
- `scale(m) = (3 m) >> 2`.

**Stopping**: after a complete iteration, stop successfully when every row parity of every layer was even and no hard decision changed during the iteration (`dec_ok` = 1); otherwise stop after `max_iter` iterations with `dec_ok` = 0. The hard decisions are `post < 0` (bit 1). `iters` reports the number of iterations used (the convergence-detecting iteration counts).

**Entry lists**: when the code select changes the decoder scans the base matrix once (via the ROM of module 13 for the information columns and the dual-diagonal rule for the parity columns: block column `kb`: shift `x` in rows 0 and `mb-1`, shift 0 in row `mb/2`; block column `kb + c`: shift 0 in rows `c-1` and `c`) into per-layer entry lists; later codewords of the same code reuse them.

Timing estimate **[E]**: one iteration takes `2 E` clocks plus a few per layer with `E` the number of non-empty base entries (88 to 120 depending on the code, about 90 for N = 648 rate 1/2), so one iteration of a rate 1/2 code is about 200 clocks and ten iterations 2000 clocks: with N = 1944 (972 information bits) that is about 100 Mbit/s at 200 MHz for one instance with ten iterations and more with early termination; N = 648 rate 1/2 gives about a third of that. The 155 Mbit/s of PHY-015 therefore needs the three instances the spec assumes (or fewer iterations); the measured figures are in the results.

## 2. Interface

`ldpc_dec`: `clk`, `rst_n`, `code[2:0]` (as module 13; sampled with the first LLR of a codeword), `max_iter[5:0]` (sampled likewise; 0 is treated as 1), `s_axis_*` (8-bit signed LLR per beat in codeword bit order, N beats, `last` on the final one; `err_len` pulses if `last` disagrees with the count), `m_axis_*` (decoded information bits as 32-bit words, bit `b` of the message in bit `b mod 32` of word `b / 32`, ceil(K/32) words, `last` on the final word; bits above K are zero), `m_ok` (with the first output word: `dec_ok`), `m_iters[5:0]` (likewise). One codeword at a time.

## 3. Test plan

A Python model of the algorithm above, bit-exact (integer arithmetic, same order of layers and entries); the code tables of module 13 (`ldpc_codes.json`) and its Python encoder; AFF3CT for the statistical comparison.

| ID | Test | Pass criterion |
|---|---|---|
| T20-01 | Bit-exact | For all 8 codes, noisy codewords at several SNRs (including high, where decoding fails): the DUT output words, `m_ok` and `m_iters` equal the model for every frame |
| T20-02 | Noise-free and low noise | Noise-free LLRs (full-scale) decode to the message in one iteration pair (`iters` <= 2) for all codes; 20 frames of low-noise input per code decode correctly |
| T20-03 | Error correction | At an SNR where the model's frame error rate is between 10% and 40%, the DUT corrects every frame that the model corrects (follows from T20-01) and the measured frame error rate over 100 frames per code is within the 95% confidence interval of the model's |
| T20-04 | Comparison with AFF3CT | The frame error rate of the Python model (same quantisation) over 400 frames at three SNRs for the N = 648 rate 5/6 standard code and one own-design code is within 0.5 dB of AFF3CT's layered normalised min-sum (the script `check_decoder.py`; results recorded) |
| T20-05 | Early termination and iteration limit | The number of iterations is at most `max_iter`; a valid codeword with small noise stops early; a frame with heavy noise stops at the limit with `m_ok` = 0 |
| T20-06 | Handshakes, back-to-back codewords, different codes | Random valid and ready, two to six codewords in a row with different codes (the entry lists rebuild); all equal the model; `err_len` on a wrong `last` and recovery |
| T20-07 | Cycle count | Clocks per codeword (load, iterations, output) for every code at the same noise; information throughput at 200 MHz recorded and compared with PHY-015 |
| L-20, S-20 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 4. Deliverables

`rtl/20-ldpc-decoder/ldpc_dec.sv`, `tests/20-ldpc-decoder/` (model, tests, AFF3CT comparison script), results below, row in `design/README.md`.

## 5. Open items

- Throughput: the three-instance assumption of PHY-015 and a two-codeword pipelined variant; a faster entry scan; storage of the check-node state in block RAM (flip-flops here).
- Precision study (6-bit LLRs, different normalisation, offset min-sum) against the frame error rate target of 1.2e-5 per codeword (SIM-002).
- Soft combining of retransmitted slices (PHY-017: a saturating LLR add before the decoder).
