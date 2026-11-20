# 17 - Channel Estimator, Equaliser and Pilot Tracking

Plan entry: module 17 of `spec/18-development-plan.md`, class L, data plane. Requirements: PHY-003 and PHY-007 (channel tracking inside a frame with pilots), PHY-016 (diversity, later), PHY-017, and the channel-quality input of the demapper (`14`). Depends on module 7 (tone plan, training and pilot values) and module 12 (the frequency-domain symbols come from the FFT). This revision implements a **one-tap-per-tone zero-forcing equaliser with common phase and gain tracking from the pilots**; it does not smooth the estimate across frequency or interpolate across time (open items).

## 1. Method

All arithmetic is integer fixed point; the amplitude scale is that of module 6 (RMS 4096 per tone, so an ideal training or pilot tone is +/-4096 on the I axis). The channel `H` is carried in Q12 (1.0 = 4096).

1. **Channel estimate** from the two long-training symbols (LTF, `07`; identical, every used tone +/-4096): for every used bin `k` with the reference sign `s_k` (+1 or -1), `H_k = round((Y1_k + Y2_k) s_k / 2)` (Q12), saturated to 16 bits. Averaging two symbols halves the noise power.
2. **Equaliser coefficient** `G_k = 1/H_k` (Q12) as `conj(H_k) x R(|H_k|^2)` with the reciprocal `R(x) = 2^40 / x` evaluated by a normalised 256-entry table: with `p` the position of the highest set bit of `x`, `m` the nine bits `x >> (p-8)` (256..511), `R = T[m-256] << (25 - p)` (right shift when `25 - p` is negative), `T[i] = round(2^23 / (256 + i))`, saturated to `2^31 - 1`; so `G_k = round(conj(H_k) R / 2^16)` saturated to 16 bits per component (a deep fade gives at most 8x gain). The table error is below 0.2%.
3. **Channel quality** `csi_k = min(255, |H_k|^2 >> 17)` (1.0 gives 128), the weight the demapper needs (`14`).
4. **Data symbol, pass 1**: for every used bin `W_k = round(Y_k G_k / 2^12)` (complex product, saturated to 16 bits per component). For the pilot bins the common correction is measured: `csum = sum over pilots of s_j W_j` (the reference sign `s_j` of the pilot in this symbol, including the polarity of `07`).
5. **Common correction** `c = csum x rn / 2^16` (Q12; `rn = 2^16 / npilots`: 16384, 10923, 8192, 4096 for 4, 6, 8, 16 pilots; because `W_j s_j` is about `4096 c`, `csum / npilots` is `c` in Q12) and `g = 1/c` by the same reciprocal method as step 2.
6. **Data symbol, pass 2**: for every data bin `Z_k = round(W_k g / 2^12)`; output `Z_k` with `csi_k`, in bin order, `last` on the last data bin.

This removes the common phase rotation and common gain change of each data symbol (residual carrier offset, phase noise, a gain step) and the frequency-selective part of the channel once per frame; a channel that changes shape inside the frame is not tracked (open item).

## 2. Interface

Module `equalizer`, parameter `MAX_LOG2` (default 9): `clk`, `rst_n`, `fft_log2[3:0]` (6 to `MAX_LOG2`), `kind[1:0]` (0 LTF first symbol, 1 LTF second symbol, 2 first data symbol of a frame (pilot polarity restarts), 3 later data symbol; both sampled with the first bin of every symbol), `s_axis_*` (32-bit `{Q, I}` bins in natural order, `last` on bin N-1), `m_axis_*` (32-bit `{Q, I}` equalised data tones), `m_csi[7:0]` (aligned with the data), `err_len` (pulse when `last` disagrees with the bin count). The tone plan and the reference signs come from an internal instance of the preamble generator (module 7). LTF symbols produce no output; the channel estimate is complete after the second LTF symbol and is kept until the next frame's first LTF.

Time budget: a data symbol needs N bins in, a pass over N bins out and a few clocks; N = 512 is about 1100 clocks against the 2880-clock symbol period at 200 MHz.

## 3. Test plan

A bit-exact Python model of section 1; a channel simulation with `numpy` (random multipath, common phase rotation, noise).

| ID | Test | Pass criterion |
|---|---|---|
| T17-01 | Reciprocal and table | The RTL table equals `round(2^23/(256+i))`; `R(x)` of the model matches the formula over a sweep of `x` and has a relative error below 0.5% against `2^40/x` for `x` from 2^10 to 2^31 |
| T17-02 | Bit-exact | For every N from 64 to 512, random multipath channels, LTF1, LTF2 and several data symbols with random common phase rotations: every output `Z_k` and `csi_k` equals the model |
| T17-03 | Equalisation accuracy | With a noiseless channel the equalised data tones are within 2% of the transmitted constellation points (error vector magnitude below -34 dB) after the common phase rotation of up to +/-60 degrees per symbol |
| T17-04 | Noisy channel | With noise at 25 dB per-tone SNR the error vector magnitude is within 2 dB of the value expected from the noise and the channel gains (measured and recorded) |
| T17-05 | CSI | `csi` is proportional to the channel power gain `|H|^2` (128 at unit gain) within one least significant bit for a flat channel with gains 0.25 to 2.0 |
| T17-06 | Deep fade | A tone with `|H|` of 0.02 is clipped by the gain limit (no overflow, no wrap) and gets `csi` 0; the other tones are unaffected |
| T17-07 | Frame sequence and handshakes | Two frames in a row (the second with a different channel) with random valid and ready: every output equals the model; the estimate of the first frame does not leak into the second |
| T17-08 | Bad `last` | `err_len` pulses; the symbol is closed by the count and the next symbol is processed correctly |
| T17-09 | Cycle count | Clocks per data symbol for each N recorded (bound: below 2880 for N up to 512) |
| L-17, S-17 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 4. Deliverables

`scripts/gen_recip_rom.py`, `rtl/17-equalizer/recip_rom.sv` (generated), `rtl/17-equalizer/equalizer.sv`, `tests/17-equalizer/`, results below, row in `design/README.md`.

## 5. Open items

- Smoothing of `H` across neighbouring tones (noise reduction) and a second reference symbol average over more symbols.
- Tracking a changing channel shape inside a frame (pilot interpolation in time and frequency) and a per-pilot slope for timing drift.
- Diversity: the combiner (module 19) takes several branches; this module serves one branch (or the combined signal).
- Noise-variance aware `csi` (it is proportional to `|H|^2` only, assuming equal noise on all tones).

## 6. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/17-equalizer`; the table with `python3 -I scripts/gen_recip_rom.py`.

| Check | Result |
|---|---|
| T17-01 to T17-09 (8 tests in 2 simulations: `recip_rom`, `equalizer`) | 8 of 8 pass |
| Reciprocal (T17-01) | The ROM equals `round(2^23/(256+i))` for all 256 entries; the worst relative error of `2^40/x` over 20000 random operands is 0.38% (limit 0.5%); saturation at `2^31 - 1` for small operands |
| Bit-exact (T17-02) | Equal to the integer model for N = 64, 128, 256, 512, two channels each (noiseless and noisy), three data symbols with random common phase rotations (+/-1 rad), every output sample and `csi`; `last` only on the final data tone |
| Accuracy, noiseless (T17-03), measured | Error vector magnitude -60 dB (N = 64) and -50 dB (N = 256, 512) after common phase rotations of +50, -60 and +20 degrees per symbol (limit -34 dB); the floor is the Q12 and 16-bit quantisation |
| Accuracy with noise (T17-04), measured | At 25 dB per-tone SNR the DUT error vector magnitude is -21.3 to -22.8 dB, within 0.11 dB of a floating-point equaliser of the same structure on the same inputs (limit 1 dB) |
| CSI (T17-05) | `csi` equals `floor(128 |H|^2)` within one least significant bit for gains 0.25 to 2.0 (2.0 saturates at 255 as designed) |
| Deep fade (T17-06) | A tone with `|H|` = 0.02: no overflow, `csi` 0, the other tones within 3% error vector magnitude |
| Frames, handshakes, bad `last` (T17-07, T17-08) | Two frames with different channels and random handshakes equal the model; a wrong `last` raises `err_len` and the next frame is processed correctly |
| Cycle count (T17-09), measured | Clocks per data symbol: N = 64: 128, N = 128: 255, N = 256: 511, N = 512: 1022 (limit 2880) |
| Test sensitivity | A deliberate bug (the pilot sign reversed in the common-phase measurement) failed five of the seven equaliser tests; the RTL was restored |
| Lint (`verilator -Wall`) | Clean (both tops) |
| Yosys | `recip_rom`: 740 cells, no latches (full technology-independent synthesis). `equalizer`: the RTL-level pass (`proc`) finds no latches and reports 685 cells (about 11 flip-flop and 18 multiplier cells before memory mapping) and 6 memories; **full gate-level synthesis did not finish within 15 minutes** because of the six 512-entry behavioural memories with asynchronous reads (open item: block-RAM style memories with registered reads) |

Bugs found and fixed during the work:
- **Signedness.** `rn` and the reciprocal result were unsigned, and one unsigned operand makes a whole SystemVerilog product unsigned: negative pilot sums were treated as huge positive numbers and the arithmetic shift became logical. The first test run showed all equalised values exactly 8 times too large (the correction was wrong while the channel quality was right). Fixed with explicit signed copies.
- **Product width.** Every product was written inside a `64'(...)` cast, which makes the multiplications 64 bits wide (about 18 wide multipliers and a Yosys run that never finished). The products now have their natural widths (16x16, 16x33, 24x16); results are unchanged (the same test numbers were reproduced).
- A negation applied before widening would have wrapped for -32768; it is applied after widening.

Notes:
- The reference signs and tone types come from an internal preamble generator (module 7), so the equaliser and the transmit chain always agree on the tone plan.
- The estimate is one tap per tone with common correction only; it does not track a channel whose shape changes inside the frame (section 5).
