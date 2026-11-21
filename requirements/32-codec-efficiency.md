# R32 - Efficiency of the custom codec (VID-027), profile SL2

Source: `spec/01` VID-027 (custom codec option on the same slice interface) and the measured result of module 29 (`design/29-custom-codec.md` section 6): profile SL1 needs **6.8 to 7.6 times the bit rate of x264 at equal PSNR** on the test sequence. The listed causes were: no sub-pixel motion compensation, an 8 x 8 Hadamard instead of a DCT, DC-only intra prediction, Exp-Golomb run-length coding without context modelling, no deblocking. This module removes those causes one by one and measures what each tool buys, with the aim of **bringing the efficiency closer to x264**. Related: VID-004 (independent slices), VID-005/021 (refresh), VID-006 (hard slice budget), VID-023 (foveation map), VID-007/008 (latency), LAT-004.

## 1. Scope

In scope: a new profile **SL2** of the reference model (a C library with a Python wrapper, because the encoder searches heavily), with the tools of section 3; the ablation (what each tool is worth); the comparison with x264 on the module 29 test sequence; an RTL kernel for the new transform; the unchanged properties of module 29 (closed loop, slice independence, hard budget, reactive refresh, foveation) re-verified for SL2.

Out of scope: chroma (luma only, as in module 29; the x264 comparison stays on luma, chroma flat), B-frames and multiple reference frames (they cost latency or memory and are not in the low-latency case), a hardware encoder or decoder (no RTL beyond the transform kernel), audio, real flight video.

## 2. Definitions

- **Efficiency** = bits per pixel (bpp) at equal luma PSNR, read by interpolation at 35 dB and 38 dB on the rate-distortion curves of the same 12-frame, 320 x 256 sequence as module 29 (`tests/29-custom-codec/seqgen.py`), 8 slices of 32 rows, P frames after one I frame, no B-frames.
- **Ratio to x264** = SL bpp divided by x264 bpp (`libx264`, preset medium, `-tune zerolatency`, 8 slices, constant QP, as module 29). SL1 reference value from module 29: 6.8 (35 dB), 7.6 (38 dB).
- **Slice-local**: every dependency (intra prediction, motion vector prediction, context adaptation, deblocking) stays inside the slice; the motion-compensation reference is the same slice rows of the previous reconstructed frame (module 29 rule).

## 3. Requirements

| ID | Requirement | Acceptance criterion | Verified by |
|---|---|---|---|
| R32-01 | The transform shall be an 8 x 8 integer DCT with exact integer inverse (no floating point in the decoder), replacing the Hadamard. | Forward then inverse without quantisation reproduces the block within 2 levels (the HEVC integer transform is not exactly invertible: measured 1 level for all but 1 in 2000 uniform random blocks, 2 levels for patterns of extreme +/-255 values; the Hadamard path stays exact); the decoder uses integers only. | T32-01 |
| R32-02 | Intra prediction shall offer directional and gradient modes (at least DC, vertical, horizontal, plane) from the reconstructed neighbours inside the slice. | Mode coded per block; closed loop exact. | T32-02 |
| R32-03 | Motion compensation shall have quarter-pel luma accuracy (6-tap half-pel and bilinear quarter-pel interpolation as in AVC), a median motion-vector predictor from slice-local neighbours, and skip blocks that take the predicted vector. | Decoder reconstruction equals the encoder's bit for bit. | T32-02 |
| R32-04 | The entropy coder shall be an adaptive binary arithmetic coder with context modelling of the block modes, vectors and coefficients; the contexts are reset at the start of every slice. | Closed loop exact; a slice decodes from its own bytes alone. | T32-02, T32-03 |
| R32-05 | An in-loop deblocking filter shall act on the 8 x 8 block edges inside a slice and never across a slice boundary. | Closed loop exact; independence test unchanged. | T32-02, T32-03 |
| R32-06 | Mode, vector and quantisation decisions shall use a rate-distortion cost with the lambda of the QP (RDO). | Ablation shows the gain. | T32-05 |
| R32-07 | The module 29 properties shall hold for SL2: (a) decoder reconstruction equals the encoder's in every frame, (b) any subset of slices decodes to the same pixels as the full decode (no cross-slice parse or filter dependency), (c) no slice exceeds its byte budget by more than 5% whenever the budget is above the all-skip size (hard bound by QP search and coefficient truncation), (d) a lost slice is refreshed as intra in the next frame, (e) the foveation map (a QP offset per macroblock) works. | Tests of module 29 repeated for SL2. | T32-02 .. T32-04, T32-06, T32-07 |
| R32-08 | **Efficiency target:** at equal PSNR SL2 shall need at most **2.0 times** the bit rate of x264 at 35 dB and 38 dB (SL1: 6.8 and 7.6). The achieved ratio is the result; if the target is not met it is reported as not met. | Measured on the sequence of section 2. | T32-05 |
| R32-09 | The contribution of each tool shall be measured (ablation: SL2 with one tool switched off at a time, and the cumulative build-up from SL1-like settings), so that the decision on what to keep for hardware can be made. | Table in the results. | T32-05 |
| R32-10 | The new transform shall have an RTL kernel (8 x 8, forward and inverse, one sample per clock in and out, like `wht8x8`), bit-exact against the model, lint clean, no latches. | RTL equals the model for random and extreme blocks. | T32-08 |
| R32-11 | The complexity of SL2 shall be reported per pixel (encoder and decoder operations, memory) and compared with SL1, so that the hardware cost of the efficiency is visible. | Table in the results. | T32-09 |
| R32-12 | The rate-control rule (smallest QP within the budget) shall use the real SL2 coder; the number of encodes per slice shall be reported (hardware cannot afford many). | Reported. | T32-04 |

## 4. Assumptions and limits stated in advance

- The comparison with x264 is luma only and on photographs with synthetic motion and noise (sigma 2); noise-like content favours neither codec but low-latency x264 settings in practice give a higher rate; the measured ratio applies to this content only.
- x264 uses tools SL2 will not have (multiple partitions down to 4 x 4, B-frames are off but multiple references, trellis quantisation, CABAC with more contexts, weighted prediction, many intra modes). A ratio near 1.3 to 2 is the expectation, not 1.0.
- SL2 stays a reference model: the C encoder searches (full integer search of +/-8, then refinement; several QP probes per slice) are not a hardware design.
