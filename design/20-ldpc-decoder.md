# 20 - LDPC Decoder

Plan entry: module 20 of `spec/18-development-plan.md`, class L, data plane. Requirements: PHY-005, PHY-011 (slice error rate), PHY-015 (decoder throughput of at least 155 Mbit/s of information, codeword decode within 10 us; the spec counts three decoder instances at 200 MHz), PHY-017 (more iterations in the enhanced ground unit). Decodes the eight codes of module 13; takes the 8-bit log-likelihood ratios of module 14 (positive = bit 0) after the de-interleaver of module 5.

## 1. Algorithm and architecture

**Layered normalised min-sum** (one layer per block row of the base matrix, posterior values updated after every layer), normalisation factor 3/4, 8-bit signed channel LLRs (-127..+127), **9-bit posterior and extrinsic values (-255..+255)** and 7-bit message magnitudes (the posterior needs more range than the channel LLR: with 8-bit posteriors a frame with saturated inputs converged to the complement codeword, see the results), up to `max_iter` iterations with early termination. The code is quasi-cyclic, so the `Z` rows of a block row (Z = 27 or 81) are processed in parallel: one block column per clock for each of two passes per layer.

State: `post[j][b]` the posterior LLR of bit `b` of variable block `j` (24 blocks of Z); per layer and row the check-to-variable messages in compressed form: the two smallest magnitudes `m1`, `m2` (7 bits), the entry index of `m1` (5 bits) and one sign bit per entry (24 bits): the sign of the **outgoing message** of that entry, that is the sign product of the row XOR the sign of the entry's own input.

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

## 6. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/20-ldpc-decoder`; AFF3CT comparison: `python3 tests/20-ldpc-decoder/check_decoder.py`.

| Check | Result |
|---|---|
| T20-01 to T20-08 (5 tests, one simulation) | 5 of 5 pass |
| Bit-exact (T20-01) | 20 frames over all 8 codes at moderate and high noise (and four saturating stress frames): the decoded words, `m_ok` and `m_iters` equal the integer model |
| Noise-free and low noise (T20-02) | Full-scale noise-free LLRs decode in at most 2 iterations for all 8 codes; 24 low-noise frames decode correctly |
| Error correction against an independent reference (T20-03) | 24 frames of codes 3 and 12 near and below the waterfall: the RTL decodes the same 8 frames correctly as a **floating-point** layered normalised min-sum of the same structure (8 of 24 for both); iteration limits respected; heavy noise stops at the limit with `m_ok` = 0; light noise stops early (at most 3 iterations) |
| Sequence and handshakes (T20-06) | Six codewords with different codes (the entry lists rebuild), random valid and ready: all equal the model; a wrong `last` raises `err_len` and the next codeword is correct |
| Saturated-input regression (T20-08) | The frame whose 146 of 648 channel LLRs are saturated, which an 8-bit posterior decoded to the complement codeword, decodes to the sent message in 2 iterations |
| Cycle count (T20-07), measured | About 159 to 185 clocks per iteration (the scan of the base entries and the two passes per layer); examples at 200 MHz with the iterations the frame needed: N = 648 R1/2 1931 clocks (8 iterations, 34 Mbit/s), R3/4 1324 (4, 73 Mbit/s); N = 1944 R1/2 3565 (10, 55 Mbit/s), R3/4 2650 (4, 110 Mbit/s), R5/6 2830 (5, 114 Mbit/s). **A single instance does not reach the 155 Mbit/s of PHY-015**; the three instances assumed by the spec, or a faster architecture, are needed (open item) |
| Model against AFF3CT (T20-04, `check_decoder.py`), measured | Frame error rate of the bit-exact model over 100 frames against AFF3CT's layered normalised min-sum with the same matrix: N = 648 R5/6 (standard): 3.2 dB 0.28 against 0.455, 3.6 dB 0.05 against 0.107, 4.0 dB 0/100 against 0.0139; N = 648 R1/2 (own): 1.8 dB 0.13 against 0.185, 2.2 dB 0.03 against 0.041, 2.6 dB 0.01 against 0.0039 (one error in 100 frames). The fixed-point decoder is at or better than AFF3CT at every point but the last, where one error is within the statistical uncertainty; AFF3CT's default normalisation is weaker than the factor 3/4 used here |
| Test sensitivity | A deliberate bug (the stored message signs reverted to the input signs) failed three tests (bit-exact, correction, sequence); the RTL was restored |
| Lint (`verilator -Wall`) | Clean (no latch warnings) |
| Yosys | **Not completed**: even the structural `proc` pass did not finish within 200 seconds for this design (about 12 x 81 x 40 bits of check-node state and nested row loops, flip-flop arrays); the no-latch check rests on the Verilator lint (open item: block-RAM storage and fewer parallel rows to make the design synthesisable in reasonable time) |

Bugs found and fixed during the work. Two of them are algorithmic and could not be seen by comparing the RTL with its model, because the model shared them; the independent floating-point reference exposed both:
- **Wrong stored sign.** The per-entry sign stored for the next iteration was the sign of the incoming value `v`; the check-to-variable message sign is the sign product XOR the entry's own sign. The fixed-point decoder then decoded 4 of 12 frames at 3.5 dB where the floating-point decoder decoded 11 of 12 and AFF3CT about 80% (even with a hugely wide, fine quantisation it stayed at 6 to 7 of 16, which showed that the cause was logic, not precision). Fixed in the model and the RTL (`sg <= lns XOR {24{lsp}}`).
- **Posterior range.** With an 8-bit posterior, saturated channel LLRs made a layered iteration collapse: after iteration 1 the hard decisions were right, in iteration 2 the posteriors reduced by earlier layers went negative once the old (large) messages were subtracted and the decoder converged, with `ok` set, to the complement of the sent codeword (the all-ones vector is a codeword of these codes). Fixed with a 9-bit posterior and extrinsic range (-255..+255) and 7-bit message magnitudes; the frame is kept as a regression vector.
- A test-generator error: LLRs scaled by 1/sigma^2 grow with the SNR and saturate at high SNR; the demapper's LLRs do not (they depend on the channel gain only), so the default generator now uses a fixed 24 per unit amplitude and the saturating generator is kept as a stress case.

Notes:
- The throughput gap is the main finding for the plan: PHY-015 as written (155 Mbit/s) needs about three instances of this decoder at ten iterations, or an architecture that processes more than one block column per clock.
- The decoder assumes the de-interleaver output order (module 5) and the LLR sign convention of module 14 (positive = bit 0).
