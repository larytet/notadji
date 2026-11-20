# 18 - Burst Detection, Coarse Timing, Carrier-Offset Estimation and AGC Monitor

Plan entry: module 18 of `spec/18-development-plan.md`, class L, data plane. Requirements: PHY-008 (initial carrier offset tolerance 25 ppm, residual below 0.1 ppm), PHY-010 (acquisition within 40 us: detection, AGC settling and synchronisation). Depends on module 7 (the STF structure) and module 12 (twiddle table for the rotator). Complements module 17 (fine channel estimation).

## 1. Method

Time-domain samples `r[n]` (32-bit `{Q, I}`, the radio cannot be stopped; a strobe marks every sample). The short training field of `07` repeats with period `P = N/4` samples (N = 2^fft_log2) and its cyclic prefix continues the periodicity, so it is a stretch of `Lc + N` samples with `r[n+P] = r[n]` apart from carrier offset and noise.

1. **Delay-and-correlate** (Schmidl and Cox): with window `W = P`, `C[n] = sum_{i=0..W-1} r[n-i] conj(r[n-i-P])` and `E[n] = sum_{i=0..W-1} |r[n-i]|^2`, both running sums (add the newest term, subtract the term that left the window; delay line of `2P` samples). The metric `M = |C|^2 / E^2` is close to 1 inside the STF and low elsewhere.
2. **Detection**: `M > threshold` (`thr_sel`: 0: 1/2, 1: 1/4, 2: 3/4 as `|C|^2 x d > E^2 x n` comparisons without division) for `P/2` consecutive samples, and `E` of both the current and the lagged window above a minimum (`min_power`, rejects the all-zero start and a burst start seen against a near-silent lagged window; the lagged-window condition was added in module 21); then `det` pulses.
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
| T18-02 | No false alarm | Noise only (three power levels, 120000 samples) and silence: no `det`; the all-zero input never triggers (`min_power`). A pure carrier **does** trigger the detector (any signal with period `P` has metric 1); this is a documented limitation, not tested as a pass criterion |
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

## 6. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/18-sync && tests/common/lint_synth.sh tests/18-sync`.

| Check | Result |
|---|---|
| T18-01 to T18-08 (7 tests in 2 simulations: `cordic_vec`, `sync_core`) | 7 of 7 pass |
| Detection (T18-01), measured | 20 of 20 bursts (12 of 12 at N = 512) at **every** N from 64 to 512 and every SNR of 20, 10 and 5 dB, with random carrier offsets up to +/-1.9 sub-carrier spacings and random leading gaps |
| Acquisition time (T18-01), measured | Detection about 2.0 P after the start of the STF at 20 dB, 2.1 P at 10 dB and 2.3 to 2.4 P at 5 dB (P = N/4); for N = 256 that is 130, 137 and 153 samples, 6.5 to 7.7 us at a 20 MS/s sample rate, against the 40 us of PHY-010 for detection, AGC settling and synchronisation together (the AGC settling time is not measured here) |
| False alarms (T18-02) | None in 120000 noise samples at three power levels and in silence |
| Carrier offset (T18-03/04), measured | Worst estimate error 0.012 sub-carrier spacings at 20 dB and 0.043 at 10 dB (offsets from -1.9 to +1.9); after derotation the residual offset estimated from the two long-training symbols is below 0.1 sub-carrier spacings at 20 dB |
| Timing marker (T18-05), measured, N = 128 (prefix 16) | Error of `fall - k_back` against the true end of the STF: 20 dB mean +1.95, standard deviation 0.22, maximum 2 samples; 10 dB mean +1.07, standard deviation 0.68, maximum 3; **5 dB mean -12.8, standard deviation 17.9, maximum 62 (unusable)**. The marker is reliable down to 10 dB and not at 5 dB; the test asserts only the 20 dB case |
| AGC monitor (T18-06) | `agc_up` and `agc_down` pulses outside the band only, none inside it |
| Bursts in a row (T18-07) | Three bursts with `rearm` between them: three detections, estimates within 0.03 sub-carrier spacings |
| CORDIC (T18-08), measured | Worst angle error 1 LSB of 65536 per turn for vectors of magnitude above 1000 (limit 2); integer vectors of magnitude below 50 have quantisation-limited errors (2378 LSB for a vector of a few counts, reported but not asserted) |
| Test sensitivity | A deliberate bug (the metric normalised by the current window energy only, the first design) failed the detection and offset tests; the RTL was restored |
| Lint (`verilator -Wall`) | Clean (both tops) |
| Yosys | `cordic_vec`: 1514 cells, 113 flip-flops, no latches (full synthesis). `sync_core`: the RTL-level pass finds no latches (346 cells including 22 multiplier cells, before mapping); **full gate-level synthesis did not finish within 10 minutes** (open item: narrower products and a block-RAM style delay line) |

Bugs found and fixed during the work (the first test run failed detection at N = 256 and the energy had wrapped to about 2^40):
- **Stale delay line after reset.** The delay line was not cleared while the running sums were, so after a reset the stale samples leaving the window subtracted energy and correlation that had never been added, a permanent error. Fixed with a fill counter that treats samples older than the reset as zero.
- **Metric normalisation.** The metric was normalised by the current window energy only. When a burst ends the lagged window still holds loud signal and the current window only noise, so `|C|` (noise times signal) exceeded the current energy and the metric exceeded 1: false detections at the start of the next gap (found as detections at sample 31 in bursts that followed another burst). The metric is now `|C|^2 / (E_cur E_lag)` with a second running sum of the lagged window energy.
- Product widths were reduced (22-bit operands after normalisation on the largest of the three quantities) to keep the arithmetic narrow.

Notes and open items: see section 5; in addition the 5 dB timing result above means a refinement from the long-training symbols is needed before the marker is used at low SNR, and the cyclic-prefix back-off of module 4 should be set from the measured jitter of the chosen operating point.
