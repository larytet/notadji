# 26 - Peak-to-Average Reduction and Digital Pre-Distortion

Plan entry: module 26 of `spec/18-development-plan.md`, class XL, data plane. Requirements: PHY-009 (clipping with filtering plus DPD so that the PA meets RF-014 and RF-015 with a back-off of at most 7 dB for 64QAM and 6 dB for QPSK/16QAM), RF-014 (TX EVM -32 dB at 64QAM, -35 dB at 256QAM at 3 dB below maximum power, after DPD), RF-015 (ACLR -45 dBc at the adjacent channel after DPD at the average power for 64QAM), CAL-005 (adaptation from the observation receiver, converged in 200 ms from a cold start, tracking at 10 Hz or faster), HSI-004 (the DPD correlation accumulation is a hardware block). SIM-004 of `17`. Depends on 11 (sample interface), 21 (the signal being sent) and 25 (observation receiver calibration).

Both blocks work on the **oversampled** stream that goes to the radio (the DAC side): the spectral regrowth of the PA is up to about three times the signal bandwidth, so DPD at the symbol rate cannot correct it. The oversampling ratio `OS` is 4 in the tests (80 MS/s for a 20 MHz channel); the interpolation filter from the OFDM output (module 4/12 output) to this rate is not part of this module (the test builds the oversampled signal in Python); the blocks themselves are rate-agnostic and count only clocks per sample.

## 1. Architecture

`x` (Q15 complex, from the transmit chain at `OS` times the sample rate) -> **CFR** (`cfr_clip` + `cfr_fir`, one or two stages) -> **DPD** (`dpd_mp`) -> radio. The observation receiver returns the PA output `y`; a capture of `N` samples of the DPD output `u` and of `y` (time-aligned and gain-normalised by firmware) goes to `dpd_corr`, which accumulates the correlation matrix and vector for a least-squares fit; the firmware (`dpd_fw.c`) solves the ridge-regularised system and writes the coefficients.

### 1.1 `cfr_clip`

Soft clipper with a programmable gain table: `m2 = I^2 + Q^2` (Q30); `idx = min(255, m2 >> 22)`; output `x x g[idx] / 2^15` with `g` 256 entries of Q15 loaded through a write port (`wr_en`, `wr_idx`, `wr_g`). The table for threshold magnitude `a` is `g[i] = min(1, a / sqrt(m2_i))` at the middle of each bin (`scripts/gen_cfr_tables.py`, also used by the tests). Latency 2 clocks. Throughput one sample per clock.

### 1.2 `cfr_fir`

Linear-phase low-pass filter that removes the clipping products outside the signal band: `TAPS` (odd, default 63) real Q15 coefficients (symmetric, generated into `cfr_coef.svh` by the same script, Kaiser window, pass band edge 0.115 and stop band edge 0.165 cycles per sample for `OS` = 4), complex data. Direct form with folded symmetry; output rounded and saturated. `gain` stage compensates the filter loss (unity pass-band gain by design).

One clip-and-filter pass re-grows some peaks; two passes (`cfr_clip` -> `cfr_fir` -> `cfr_clip` -> `cfr_fir`) is the default configuration (module `cfr_chain`).

### 1.3 `dpd_mp`

Memory polynomial, orders 1, 3, 5 and memory `M` = 3: `u[n] = sum_{j=0..2} sum_{m=0..2} a[j][m] b_j[n - m]`, with `b_0 = x`, `b_1 = x r`, `b_2 = x r^2`, `r = |x|^2` (Q15). Coefficients `a` are complex Q4.12 (1.0 = 4096) held in a 9-entry register file with a write port and a `commit` strobe that swaps the file in one clock. Parameter `NCM` complex multiply-accumulate units (1, 3 or 9): a sample takes `ceil(9 / NCM) + 4` clocks; the engine accepts a sample when idle (`s_ready`). Output Q15, saturated. At 200 MHz `NCM` = 9 gives a sample every 5 clocks (40 MS/s: not enough for 80 MS/s: two parallel engines or time sharing of the multipliers at 400 MHz are needed; reported as a limit).

### 1.4 `dpd_corr`

HSI-004's hardware accumulation. A stream of pairs `(y, u)` (`y` the normalised PA output sample, `u` the DPD output that produced it): from `y` it forms the same 9 basis values (delay line of `M` bases), and accumulates the Hermitian matrix `R = sum phi phi^H` (upper triangle, 45 complex entries) and the vector `c = sum phi u^*` (9 entries) in 48-bit accumulators, one complex MAC per clock (54 clocks per sample). `clear`, `s_valid/s_ready`, `done` after `n` samples, and a read port (`rd_idx`, `rd_re`, `rd_im`) for the 54 entries. For `N` = 4096 the accumulation takes 221 000 clocks (1.1 ms at 200 MHz).

This is the **indirect learning** architecture: the post-distorter fitted on `y` (with `u` as target) is copied as the pre-distorter.

## 2. Firmware (`dpd_fw`)

`dpd_solve(R_acc, c_acc, N, ridge, a_out)`: converts the accumulators to float32 (scaled by `2^-30 / N`), forms the full Hermitian `R`, adds `ridge x trace(R) / 9` to the diagonal, solves `R a = c` by complex Cholesky (9 x 9, about 2 kflop), quantises the result to Q4.12, limits each coefficient (`|a| < 7.99`) and returns an error code if the factorisation fails (not positive definite). `dpd_update`: damped update `a <- a + mu (a_new - a)` (mu = 1 at start, 0.5 later) and a convergence test on the change. `dpd_align` (gain and delay alignment of `y` against `u` by a coarse correlation search over +/-8 samples with a complex gain estimate) is part of the firmware. Single-precision floating point is used (the real-time core is assumed to have an FPU, Cortex-R5F class; the other firmware modules are integer).

## 3. Test plan

| ID | Test | Pass criterion |
|---|---|---|
| T26-01 | `cfr_clip` | Bit-exact against the integer model for random samples and random tables; unity gain below the threshold; above it the output magnitude is within 1.5% of the threshold for magnitudes up to 3x the threshold; the table write port works while streaming |
| T26-02 | `cfr_fir` | Bit-exact against the model for random streams (31 and 63 taps); impulse response equals the coefficients; measured gain in the pass band within 0.05 dB and in the stop band at least 50 dB down (tones through the RTL) |
| T26-03 | CFR chain | Python OFDM source (64QAM, N = 256, 4x oversampled, 300 symbols): peak-to-average ratio at the 1e-3 CCDF point before and after; the RTL chain equals the model on a 5000-sample stream; EVM and in-band/out-of-band powers of the CFR output measured after decimation. Pass: reduction of at least 2.5 dB at 1e-3 with the EVM of the CFR alone at -38 dB or better and the out-of-band power within 3 dB of the unclipped signal's |
| T26-04 | `dpd_mp` | Bit-exact against the integer model for `NCM` = 1, 3 and 9, random coefficients (including saturation) and samples; the clocks per sample equal `ceil(9 / NCM) + 4`; `commit` swaps all coefficients at once (no sample sees a mixture); identity coefficients (`a[0][0]` = 1) pass the input through within 1 LSB |
| T26-05 | `dpd_corr` | All 54 accumulators equal exact integer sums from numpy for random `(y, u)` streams of 2000 samples and for extreme values; `done` and the 54-clock rhythm |
| T26-06 | Solver | The C solver recovers known coefficients from synthetic data (noise-free: error below 1e-3 in Q4.12 units after quantisation; at 40 dB observation SNR: coefficient error below the expected statistical bound); agrees with `numpy.linalg.lstsq` on the same accumulators; a singular matrix (all-zero input) returns the error code |
| T26-07 | System with a PA model | Memory-polynomial/Rapp PA with AM/PM and memory (a model [E], section 5), 64QAM OFDM at 7 dB back-off and QPSK/16QAM at 6 dB: ACLR and EVM without correction, with CFR only, with DPD only, with both; the adaptation from cold start: iterations to converge, the time per iteration (capture, `dpd_corr` clocks, solver flops) and the total against the 200 ms of CAL-005; tracking: a 1 dB gain change of the PA is re-converged in 3 iterations. Pass: EVM -32 dB or better and ACLR -45 dBc or better at 64QAM with the 7 dB back-off, CAL-005 timing met by the model |
| T26-08 | RTL in the loop | One adaptation iteration with the RTL `dpd_mp` (as predistorter) and the RTL `dpd_corr` (accumulation) and the C solver against the Python-only iteration: same coefficients within 1 LSB |
| L-26, S-26 | Lint and synthesis | `-Wall` clean; no latches; counts recorded (DSP-block estimate from the multiplier count) |

## 4. Deliverables

`rtl/26-papr-dpd/{cfr_clip,cfr_fir,cfr_chain,dpd_mp,dpd_corr}.sv`, `scripts/gen_cfr_tables.py`, `fw/26-dpd/{dpd_fw.h,dpd_fw.c}`, `tests/26-papr-dpd/`, results below, row in `design/README.md`.

## 5. Open items

- The PA model is an assumption (`Rapp` with `p` = 2, saturation 1.0, AM/PM `0.3 r^2` radians, memory taps 1, 0.12, -0.04); real PAs, in particular Doherty or envelope-tracked ones (T-14), need measured data and probably higher orders or a lookup-table DPD; the structure is the standard memory polynomial.
- The interpolation to `OS` times the symbol rate, the observation-receiver capture memory and alignment hardware, and the gain/delay alignment in hardware are not designed here (alignment is firmware).
- Throughput: `dpd_mp` at `NCM` = 9 gives 40 MS/s at 200 MHz; 80 MS/s needs two lanes or a faster clock.
- Back-off policy and power control (RF-031) belong to the transmit power control.
- Not run on a target core; the Cholesky solver is floating point.
