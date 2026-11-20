# 18 - Burst Detection, Coarse Timing, Carrier-Offset Estimation and AGC Monitor

Plan entry: module 18 of `spec/18-development-plan.md`, class L, data plane. Requirements: PHY-008 (initial carrier offset tolerance 25 ppm, residual below 0.1 ppm), PHY-010 (acquisition within 40 us: detection, AGC settling and synchronisation). Depends on module 7 (the STF structure) and module 12 (twiddle table for the rotator). Complements module 17 (fine channel estimation).

## 1. Method

Time-domain samples `r[n]` (32-bit `{Q, I}`, the radio cannot be stopped; a strobe marks every sample). The short training field of `07` repeats with period `P = N/4` samples (N = 2^fft_log2) and its cyclic prefix continues the periodicity, so it is a stretch of `Lc + N` samples with `r[n+P] = r[n]` apart from carrier offset and noise.

1. **Delay-and-correlate** (Schmidl and Cox): with window `W = P`, `C[n] = sum_{i=0..W-1} r[n-i] conj(r[n-i-P])` and `E[n] = sum_{i=0..W-1} |r[n-i]|^2`, both running sums (add the newest term, subtract the term that left the window; delay line of `2P` samples). The metric `M = |C|^2 / E^2` is close to 1 inside the STF and low elsewhere.
2. **Detection**: `M > threshold` (`thr_sel`: 0: 1/2, 1: 1/4, 2: 3/4 as `|C|^2 x d > E^2 x n` comparisons without division) for `P/2` consecutive samples, and `E` above a minimum (`min_power`, rejects the all-zero start); then `det` pulses.
3. **Coarse carrier offset**: `angle(C)` over the plateau is `2 pi f P Ts` (the sign convention of `r[n] conj(r[n-P])`); a sequential CORDIC (vectoring mode, 14 iterations) gives the angle as a 16-bit phase (65536 = 2 pi); the per-sample phase step is `angle / P`; the range is +/- half an STF subcarrier spacing times `N / (2P)`... i.e. +/- 2 sub-carrier spacings for P = N/4.
4. **Derotation**: a numerically controlled oscillator with a 24-bit phase accumulator (2^24 = 2 pi) rotates every sample by `exp(-j phi n)` from the detection on (twiddles of module 12, Q15, rounded and saturated); before detection the step is zero.
5. **End-of-STF marker**: the metric falls when the window slides past the end of the STF stretch. `fall` pulses at the first sample where `M` drops below the threshold after a detection; the STF ended about `K` samples earlier, so the receiver takes `n_fall - K` as the first sample after the STF (the start of the long-training prefix); `K` is an output constant (`k_back`) equal to `W / 4` for the default threshold, to be calibrated by the test (the measured mean offset and jitter are in the results). The receive chain places the FFT window with a back-off inside the cyclic prefix (`04` `backoff`) so that a few samples of error do not matter.
6. **Power monitor (AGC)**: the average power `E / W` is compared every `W` samples with `agc_lo` and `agc_hi`; `agc_up` (power below the low limit) or `agc_down` (above the high limit) pulse to the radio gain control; the loop itself (step size, settling) is firmware (`13`).

## 2. Interface

Module `sync_core`, parameter `MAX_LOG2` (default 9: delay line of `2 x 128` samples at N = 512). Inputs: `clk`, `rst_n`, `fft_log2[3:0]`, `thr_sel[1:0]`, `min_power[31:0]`, `agc_lo[31:0]`, `agc_hi[31:0]`, `rearm` (pulse: clear the detector for a new burst), `s_valid`, `s_data[31:0]`. Outputs: `m_valid`, `m_data[31:0]` (derotated samples, a fixed small latency), `det` (pulse), `cfo_inc[23:0]` (phase step per sample, signed, 2^24 = 2 pi; valid after `det`), `cfo_angle[15:0]` (the 16-bit angle), `fall` (pulse), `k_back[7:0]`, `metric_ok` (debug: the threshold comparison), `agc_up`, `agc_down`, `locked` (between `det` and `rearm`).

## 3. Test plan

Time-domain test signals are built from the golden model of module 16 (the STF and LTF symbols with prefix as transmitted), embedded in noise with a random leading gap, a carrier offset and noise; the DUT result is checked against the truth.

| ID | Test | Pass criterion |
|---|---|---|
| T18-01 | Detection | For N = 64, 128, 256, 512, SNR 20, 10 and 5 dB, random leading gaps: `det` fires once per burst, after the start of the STF and before the end of the STF stretch, in 50 of 50 bursts at 20 and 10 dB and at least 45 of 50 at 5 dB |
| T18-02 | No false alarm | Noise only (SNR irrelevant, three power levels) and a pure carrier: no `det` in 200000 samples; the all-zero input never triggers (`min_power`) |
| T18-03 | Carrier offset estimate | For offsets of +/-0.1, +/-0.5, +/-1, +/-1.9 sub-carrier spacings and SNR 20 and 10 dB: the estimate error of the per-sample phase step is below 2% of a sub-carrier spacing (20 dB) and below 5% (10 dB); measured and recorded |
| T18-04 | Derotation | After detection the derotated STF and LTF show a residual phase slope below the tolerance of the equaliser: the residual offset (estimated again from the output samples) is below 0.1 sub-carrier spacing |
| T18-05 | Timing marker | `n_fall - k_back` minus the true end of the STF: mean and standard deviation over 100 bursts at 20, 10 and 5 dB recorded; the 99th percentile magnitude is below 25% of the prefix length at 20 dB |
| T18-06 | AGC monitor | Power steps up and down across `agc_lo` and `agc_hi` give `agc_down` / `agc_up` within `W` samples and no pulses inside the band |
| T18-07 | Rearm and bursts in a row | Three bursts with different offsets and gaps, `rearm` between them: three detections with correct estimates |
| T18-08 | CORDIC | The angle of 5000 random vectors is within 2 least significant bits (of 65536 per turn) of `atan2` and the all-quadrant behaviour is correct |
| L-18, S-18 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 4. Deliverables

`rtl/18-sync/cordic_vec.sv`, `sync_core.sv`, `tests/18-sync/` (signal generator, tests), results below, row in `design/README.md`.

## 5. Open items

- Fine timing and fine frequency from the two long-training symbols (lag N), and the sampling clock offset; the equaliser (module 17) removes the residual common phase per symbol.
- The 40 us acquisition budget (PHY-010) against the STF length: the detector needs about `P/2` plateau samples after the correlator window fills (`2P` samples); the exact figure is measured in T18-01 and compared with the budget in the results.
- A frequency-domain or LTF-based timing refinement if the marker jitter turns out too large at low SNR.
- Selectable window length `W` (the shorter the faster, the noisier).
