# 19 - Multi-Branch Combiner (Maximum-Ratio Combining)

Plan entry: module 19 of `spec/18-development-plan.md`, class L, data plane. Requirements: PHY-006 (two receive chains with maximum-ratio combining or better at the ground unit), PHY-016 (4 to 8 branches, about 3 dB per doubling minus a correlation loss), ANT-008 and the link-budget array gain of `02`. Depends on module 17 (each branch has its own equaliser) and module 17's reciprocal table.

## 1. Method

Each receive branch `b` has its own front end and equaliser (module 17), so after it the branch delivers, for every data tone, an equalised value `Z_b` (the transmitted constellation point plus noise whose power is `sigma^2 / |H_b|^2`) and the channel quality `csi_b`, proportional to `|H_b|^2` (module 17: 128 at unit gain). Maximum-ratio combining of branches with equal noise power per branch weights each branch by its channel power gain:

- `S = sum_b csi_b` (at most `255 B`, 11 bits for B = 8)
- `Z = (sum_b csi_b Z_b) / S` (per component)
- `csi_out = min(255, S)`: the combined channel quality (powers add; the saturation at 255 is the range of the demapper input, module 14).

The noise power of `Z` is `sigma^2 / sum |H_b|^2`: the signal-to-noise ratios of the branches add (3 dB for two equal branches, 6 dB for four, 9 dB for eight, before the loss from correlated noise or imperfect channel estimates). The division uses the table method of module 17: for `S` in 1..2040, `r = 2^34 / S` is `T[m-256] << (19 - p)` with `p` the highest set bit of `S`, `m` its normalised nine bits and `T[i] = round(2^23/(256+i))`; then `Z = round((sum_b csi_b Z_b) r / 2^34)` saturated to 16 bits per component. `S = 0` gives `Z = 0` and `csi_out = 0`.

Branches are combined **per tone**: the module waits until every branch has its tone (the equalisers run in lockstep but may be a few clocks apart), combines, and emits one output tone; `last` must agree on all branches (a mismatch raises `err_len`).

## 2. Interface

`mrc_combine`, parameter `B` (2 to 8, default 2). Flattened inputs: `s_valid[B-1:0]`, `s_ready[B-1:0]`, `s_data[32B-1:0]` (branch `b` in bits `32b+31 .. 32b`, `{Q, I}`), `s_csi[8B-1:0]`, `s_last[B-1:0]`; outputs `m_valid`, `m_ready`, `m_data[31:0]`, `m_csi[7:0]`, `m_last`, `err_len`. One output register stage (latency 1, full throughput). Inputs are accepted together: `s_ready` of every branch is high only when all branches have `s_valid` and the output can take the tone.

## 3. Test plan

Python model of section 1 (integer arithmetic) and a `numpy` simulation of the array gain with independent noise per branch.

| ID | Test | Pass criterion |
|---|---|---|
| T19-01 | Bit-exact | For B = 2, 4, 8: 20000 random tone sets (random `Z_b`, random `csi_b` including zeros, 255, and sets with `S = 0`): output equals the model, including `csi_out` and saturation |
| T19-02 | Reciprocal accuracy | The combined value is within 0.5% (plus one least-significant bit) of the exact weighted average for all tone sets with `S` from 1 to 2040 |
| T19-03 | Array gain | Independent Rayleigh-like branch gains and noise per branch, a 16QAM constellation: the error vector magnitude of the combined output is lower than that of the best single branch, and the measured SNR gain over a single branch of equal average quality is within 0.7 dB of 3 dB (B = 2), 6 dB (B = 4), 9 dB (B = 8) |
| T19-04 | Branch with csi 0 | A branch with `csi` 0 (erased tone) contributes nothing: the output equals the combination of the other branches |
| T19-05 | Alignment and handshakes | Branches presenting their tones at different times (random valid per branch) and a random sink: no tone is lost, duplicated or mixed between tone indices; `last` passes through; the protocol-stability check passes |
| T19-06 | `last` mismatch | `err_len` pulses when branches disagree on `last`; the stream keeps flowing |
| L-19, S-19 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 4. Deliverables

`rtl/19-combiner/mrc_combine.sv`, `tests/19-combiner/`, results below, row in `design/README.md`.

## 5. Open items

- Noise-power-aware weights (unequal noise on the branches), which needs the noise estimate of each front end in the weight (`csi` then carries `|H|^2 / sigma^2`).
- Combining before the equaliser (a joint channel estimate, which handles correlated noise), and the correlation loss of PHY-016 (depends on the antenna array).
- Soft combining of retransmitted slices (PHY-017) is a separate saturating LLR adder.

## 6. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/19-combiner && tests/common/lint_synth.sh tests/19-combiner`.

| Check | Result |
|---|---|
| T19-01 to T19-06 in 3 configurations (B = 2, 4, 8) | 15 of 15 pass |
| Bit-exact and accuracy (T19-01/02) | 12000 random tone sets per configuration (random values including saturating ones, `csi` 0, 1, 128, 255, and sets with `S` = 0) equal the integer model; the value is within 0.5% (plus 1.5 least-significant bits) of the exact weighted mean for every set |
| Array gain (T19-03), measured | Equal-quality branches with independent noise, 16QAM: combined error vector magnitude -11.76, -14.72 and -17.75 dB against -8.72 dB for a single branch: **3.03, 6.01 and 9.03 dB** gain for B = 2, 4, 8 (ideal 3.01, 6.02, 9.03 dB). With random branch gains (Rayleigh-like, limited to 0.2..1.4) and `csi` = 128 |g|^2 the result equals an ideal floating-point MRC to within 0.01 dB (-8.80, -13.27, -16.73 dB) and is much better than the best single branch (about -3.1 dB) |
| Erased branch, alignment, `last` (T19-04 to T19-06) | A branch with `csi` 0 contributes nothing even with garbage values; branches presenting their tones at different times (valid probabilities 0.2 to 0.9) and a random sink: no tone lost or mixed, output stable while stalled, `last` passes through; a `last` mismatch raises `err_len` |
| Test sensitivity | A deliberate bug (equal weights instead of `csi` weights) failed four of the five tests; the RTL was restored |
| Lint (`verilator -Wall`) | Clean for B = 2, 4 and 8 |
| Yosys generic synthesis (B = 2) | 15485 cells, 43 flip-flops, no latches (13 s) |

Notes:
- The array gain of the test is the ideal one because the branches have independent noise; correlated noise (PHY-016) and imperfect channel estimates reduce it and are not modelled here (section 5).
- As in modules 17 and 18, the multiplier operands were given natural widths (28 x 37 bits) instead of widening every product to 64 bits, which keeps synthesis fast.
