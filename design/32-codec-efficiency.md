# 32 - Custom Codec Efficiency: Profile SL2

Requirements: `requirements/32-codec-efficiency.md` (R32-01 to R32-12). Plan position: after module 31; class XL, research-level, data plane. Builds on module 29 (profile SL1, `fw/29-codec/codec.py`, `design/29-custom-codec.md`). Reference model: C library `fw/32-codec/sl2.c` with a Python wrapper `fw/32-codec/sl2.py`; RTL kernel `rtl/32-codec/dct8x8.sv`.

## 1. What changes against SL1

| Tool | SL1 | SL2 |
|---|---|---|
| Transform | 8 x 8 Walsh-Hadamard, mild frequency weighting | **8 x 8 integer DCT** (the integer matrix of HEVC, 64 83 36 89 75 50 18 rows), flat quantisation |
| Intra | DC only | **DC, vertical, horizontal, plane** (8 x 8, from the unfiltered reconstruction inside the slice) |
| Motion | integer vector, ±8, previous vector as prediction | **quarter-pel** (AVC 6-tap half-pel, bilinear quarter-pel), **median predictor**, search ±8 integer then half then quarter-pel refinement, skip = predicted vector |
| Entropy coding | Exp-Golomb, nnz and run-level | **adaptive binary arithmetic coding with contexts** (flags, vectors, significance map, levels), reset per slice |
| Loop filter | none | **deblocking** of the 8 x 8 edges inside the slice (AVC-style filter, no filtering across the slice boundary) |
| Decisions | thresholds | **RDO** with `lambda = 0.85 x 2^((qp-12)/3)`: skip, inter, four intra modes, with and without residual |
| Rate control | QP bisection and coefficient truncation | same, with the real coder |

Unchanged from SL1: 8 slices per picture, each coded from its own bytes; no dependency on another slice of the same frame; the motion-compensation reference is the same slice rows of the previous reconstructed frame (edge replication at the slice rows); intra refresh slices; foveation (a QP offset per 16 x 16 macroblock, `dqp`); luma only; 16 x 16 macroblocks of four 8 x 8 blocks, raster order.

## 2. Definition (the C model is the reference)

**Transform.** Matrix `T` (8 x 8):

```
64  64  64  64  64  64  64  64
89  75  50  18 -18 -50 -75 -89
83  36 -36 -83 -83 -36  36  83
75 -18 -89 -50  50  89  18 -75
64 -64 -64  64  64 -64 -64  64
50 -89  18  75 -75 -18  89 -50
36 -83  83 -36 -36  83 -83  36
18 -50  75 -89  89 -75  50 -18
```

Forward: `Y = (T X) >> 2` (rounded half up, `+2`), `C = (Y T^T) >> 9` (`+256`); inverse: `Z = (T^T C) >> 7` (`+64`), `X = (Z T) >> 12` (`+2048`) (HEVC 8-bit values). 16-bit intermediate range is guaranteed for 9-bit residuals and coefficients clipped to ±32767.

**Quantisation.** `step(qp) = 2 x 0.625 x 2^(qp/6)` in the coefficient domain (qp 0 to 51). Level `= sign(c) ((|c| R[qp] + f) >> 16)` with `R[qp] = round(65536 / step(qp))`, rounding offset `f` = 21845 (1/3) for intra and 10923 (1/6) for inter blocks; dequantisation `c' = (level D[qp] + 8) >> 4` with `D[qp] = round(16 step(qp))`. (Integers only in the decoder.)

**Intra prediction (8 x 8, neighbours from the unfiltered reconstruction of the current slice; unavailable = outside the slice or the picture).** Mode 0 DC (mean of the available top row and left column, 128 if none, `(sum + n/2) / n`), 1 vertical (needs top), 2 horizontal (needs left), 3 plane (needs top, left and the top-left sample): `a = 16 (L[7] + T[7])`, `b = (17 H + 16) >> 5`, `c = (17 V + 16) >> 5`, `H = sum_{x=0..3} (x + 1)(T[4 + x] - T[2 - x])`, `V = sum_{y=0..3} (y + 1)(L[4 + y] - L[2 - y])` (`T[-1]` = `L[-1]` = the top-left sample), `P(x, y) = clip((a + b (x - 3) + c (y - 3) + 16) >> 5)`. The encoder chooses only available modes.

**Motion.** Vector in quarter-pel units. Luma sample interpolation as in AVC (clause 8.4.2.2.1): half-pel `b = clip((E - 5F + 20G + 20H - 5I + J + 16) >> 5)` horizontally, `h` vertically, centre `j = clip((j1 + 512) >> 10)` from the unrounded intermediate values, quarter positions = rounding average `(u + v + 1) >> 1` of the two nearest integer/half samples (the standard table); sample coordinates clamped to the slice rows and the picture columns. **Vector prediction**: neighbours A (left 8 x 8 block), B (above), C (above right, or D above left when C is not yet coded or outside), all inside the slice; a neighbour that is intra or unavailable is "not inter"; if exactly one of A, B, C is inter its vector is the prediction, otherwise the component-wise median of the three (a not-inter neighbour counts as (0, 0)). The vector difference is coded. **Skip**: inter with the predicted vector and no residual.

**Deblocking.** After a slice is reconstructed, vertical then horizontal 8 x 8 block edges inside the slice (not the first row of the slice, not the left picture edge) are filtered with the AVC filters: boundary strength `bS` = 4 if either block is intra and the edge is a macroblock edge, 3 if intra at an internal edge, 2 if either block has coded coefficients, 1 if the vectors differ by 4 quarter-pels or more in a component, else 0 (no filtering); `qp_av = (qp_p + qp_q + 1) >> 1`, `alpha`, `beta`, `tc0` from the AVC tables at `indexA = indexB = clip(qp_av + offset, 0, 51)`, `offset` = a 4-bit signed field of the slice header (the encoder tries 0 and -2 / +2 only if tuned; default 0). The filtered picture is the reference of the next frame; intra prediction uses the unfiltered samples.

**Entropy coder.** Binary range coder with 32-bit range, carry-propagating low register (as LZMA), probabilities of bit 0 as the mean of a fast (shift 4) and a slow (shift 7) estimator, 16 bit each, clamped to [32, 65504]; bypass bins at p = 1/2. Bits of the slice: the 1-byte header (`type` 1 bit, `qp` 6 bits, `has_dqp` 1 bit) then the coder bytes (flushed with 5 bytes). Syntax per block (contexts are arrays indexed as stated, all reset to 1/2 at the start of the slice):
- per macroblock when `has_dqp`: `dqp` as zero flag (1 ctx), sign (1 ctx), magnitude minus 1 unary up to 6 (6 ctx) and Exp-Golomb-1 escape (bypass);
- per block in P slices: `skip` flag (ctx = number of skipped left/above blocks in the slice, 0 to 2), then `intra` flag (ctx = number of intra left/above blocks);
- intra block: mode as two bins (first bin ctx 0, second ctx 1 + first bin);
- inter block: vector difference per component: zero flag (ctx per component), sign (ctx per component), magnitude minus 1 unary up to 8 (ctx per component and bin), Exp-Golomb-0 escape (bypass);
- residual (not for skip): `cbf` flag (ctx = 2 x intra + number of left/above blocks with coded coefficients), then for the 63 first scan positions `sig` (ctx = position + 63 x intra) and, if significant, `last` (same ctx pattern); position 63 is significant by inference; levels in reverse scan order: first bin `abs > 1` (ctx by number of earlier levels equal to 1 and greater than 1, as CABAC: 0 if some level > 1 else min(4, 1 + eq1)), further unary bins up to 14 (ctx 5 + min(4, gt1)), Exp-Golomb-0 bypass escape, sign bypass. Scan order: the diagonal order of SL1.

**Rate control.** For a slice budget the encoder finds the smallest QP (0 to 51) whose coded slice is within the budget by bisection (each probe is a complete encode, including RDO); if QP 51 still does not fit, the highest-frequency levels are zeroed progressively until it fits (down to an all-skip slice); the result is within the budget by construction whenever the budget is above the all-skip size (a few bytes).

**RDO per 8 x 8 block.** Candidates: skip, inter (vector from the search, refinement by `SAD + sqrt(lambda) bits(mvd)`; start points: zero vector and the predicted vector), intra modes available; for each candidate with residual also the variant with the residual dropped; cost `J = SSD(reconstruction, source) + lambda R` with `R` from the probability tables of a snapshot of the contexts (`-log2 p`, no encoding); the best candidate is then coded for real. The reconstruction is exactly what the decoder will produce (transform, dequantisation, prediction, clipping).

## 3. Test plan

| ID | Test | Pass criterion |
|---|---|---|
| T32-01 | Transform and quantiser | Forward then inverse DCT of random and extreme blocks (residuals ±255) without quantisation reproduces the input within 1; integers only; the C transform equals an independent Python implementation of the definition |
| T32-02 | Closed loop | 30 frames, 8 slices, fixed QP, foveation on and off, forced intra slices, refresh waves, all tools on and each tool off in turn (7 configurations): the decoder's reconstruction equals the encoder's, bit for bit |
| T32-03 | Slice independence | As T29-03: subsets of the slices removed (single, even, half, all but one, random): the remaining slices decode to the same pixels as in the full decode; corrupting one slice's bytes leaves the others unchanged (no cross-slice context, prediction or filter dependency) |
| T32-04 | Rate bound | Budgets from 150 to 6000 bytes per slice: no slice above 105% of its budget whenever the budget is above the all-skip size; the number of encodes per slice reported; sizes and PSNR reported |
| T32-05 | Rate and distortion, ablation | PSNR against bit rate for SL2 (QP 18 to 40), x264 (QP 20 to 44), and SL2 with one tool off at a time (Hadamard instead of DCT, DC-only intra, integer vectors, bypass bins instead of contexts, no deblocking, no RDO); bpp at 35 dB and 38 dB by interpolation; ratio to x264; cumulative build-up from the all-off configuration. SL2 against the target of 2.0 (R32-08) |
| T32-06 | Reactive refresh | As T29-06: lost slice recovers in the next frame when refreshed; 5% loss rate cost |
| T32-07 | Foveation | As T29-07: bits saved at equal centre PSNR |
| T32-08 | RTL kernel | `dct8x8` (forward and inverse, one sample per clock) equals the C model for random, constant and extreme blocks |
| T32-09 | Complexity | Operation counts per pixel (transform, interpolation, filter, coder bins per pixel, encoder search); memory; compared with SL1 |
| M-32 | Mutation | Transform constant changed, interpolation tap, MV median, deblocking tc0, context index reuse across slices, intra plane constant: each fails T32-01/02/03 or changes the ablation numbers |
| L-32, S-32 | Lint and synthesis | RTL `-Wall` clean, no latches; C compiled with `-Wall -Wextra` clean |

## 4. Deliverables

`fw/32-codec/{sl2.c,sl2.h,sl2.py}`, `rtl/32-codec/dct8x8.sv`, `tests/32-codec-efficiency/` (tests, ablation, x264 comparison reusing `tests/29-custom-codec/{seqgen,x264cmp}.py`), results below, a row in `design/README.md`.

## 5. Open items

- Chroma, B-frames, multiple references, partitions below 8 x 8 and above (16 x 16 for skip/inter), trellis quantisation, more intra modes (diagonal), weighted prediction: all are in x264 and not in SL2; they would close part of the remaining gap.
- No RTL encoder or decoder beyond the transform kernel: motion search with quarter-pel refinement, RDO (several trial encodes) and the context coder are the expensive parts; a hardware version would use a predictive QP and a restricted mode set (to be derived from the ablation).
- Real flight video; subjective quality.
