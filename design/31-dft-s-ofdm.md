# 31 - DFT-Spread OFDM Low-PAPR Mode (PHY-014)

Requirements: `requirements/31-dft-s-ofdm.md` (R31-01 to R31-09). Plan position: after module 30; class L, data plane, between the mapper (module 6) and the IFFT (module 12) on the transmit side, and between the equaliser (module 17) and the demapper (module 14) on the receive side. Optional requirement PHY-014, phase P2.

## 1. Decisions

- **Contiguous allocation, no frequency pilots** (from the preliminary PAPR experiment, requirements section 4): `M = 3N/4` constellation points per OFDM symbol, spread by an `M`-point DFT onto the tones `1 <= |k| <= M/2`. `R` = 8 of the `M` points are known BPSK **reference symbols** (positions `j M/R + M/(2R)`, values `+/-4096` or, with `ref_boost` = 1, `+/-8192` from a fixed sign pattern) that give the receiver the common phase and gain of the symbol after the despreading. So a DFT-s symbol carries `M - 8` data symbols: 40, 88, 184, 376 for N = 64, 128, 256, 512.
- **M = 3 x 2^a** (48, 96, 192, 384): `dft_mixed` is three power-of-two FFTs (the engine of module 12, which gets a `MIN_LOG2` parameter, default 6 = unchanged behaviour) and one radix-3 combine stage. Cost: no other `M` is supported.
- **Order of tones.** The DFT output index `p` (0 to M-1) belongs to tone `k = p - M/2` for `p < M/2` and `k = p - M/2 + 1` for `p >= M/2` (frequency order, DC skipped). The bins are produced in bin order (positive tones first), so the output of the DFT is read starting at `p = M/2` (`out_rot = M/2`) and the input of the inverse DFT on the receive side is written starting at `p = M/2` (`in_rot = M/2`).
- **MMSE equalisation in the frequency domain.** The equaliser of module 17 gives the zero-forcing output `Z_k = Y_k / H_k` with `csi_k` (`128 |H_k|^2`). The despreading stage weights it by `g(csi_k) = csi_k / (csi_k + nv)`, a 256-entry table written through a port (the firmware computes it from the noise level `nv`, `dfts_cal.make_gain_lut`), which turns the zero-forcing into the MMSE output; the sum in the IDFT then no longer inherits the noise enhancement of faded tones.
- **Bias and common phase** are removed together: the weighting biases the symbols by the mean gain `a < 1`, and the residual carrier offset rotates them by `theta`; both are measured on the reference symbols (`c = sum_j s_j d_j / (R x 4096)`, a complex number of magnitude `a` and phase `theta`) and removed by one complex multiplication with `1/c` (the reciprocal method of module 17, section 1 step 2).
- **Reference amplitude (`ref_boost`).** The common-phase estimate from 8 reference symbols is noisy at the low SNR of the mode (an experiment before the RTL: phase error about 0.12 rad at 6 dB per symbol), which costs 0.2 to 0.35 dB of BER at equal Eb/N0 with references at the data amplitude. Boosting the references to twice the amplitude removes the cost (below 0.1 dB) but raises the PAPR by 0.5 to 0.8 dB. Both are provided as a per-frame input `ref_boost` (0: 1x, the low-PAPR setting; 1: 2x, the link-margin setting); the receiver divides by the matching constant. The measured trade-off is in the results.
- `csi` of the despread symbols is the same for all of them (every symbol sees the same post-despreading SNR); it is a register `csi_out` (8 bits) set by the firmware (`dfts_cal.csi_eff`).

## 2. `dft_mixed`

`M = 3 L`, `L = 2^a`, `a` = 4 to 7 (`M` = 48, 96, 192, 384). Parameters: `MAXM` = 384. Configuration (sampled with the first input sample of a symbol): `m_sel[1:0]` (0 to 3 for `M` = 48 .. 384), `inverse`, `in_rot[8:0]`, `out_rot[8:0]`.

Algorithm (the model is the definition; `rnd15(v) = (v + 16384) >> 15`, arithmetic shift):
1. The `i`-th input sample is written to `x[(i + in_rot) mod M]`.
2. For `r` = 0, 1, 2: `x_r[m] = x[3m + r]`, `m` = 0 .. L-1, goes through the FFT of module 12 (size L, forward or inverse as configured, `shift_mask` = the first `s_M` stages, `s_M` = 2, 3, 3, 4 for M = 48, 96, 192, 384), giving `Y_r[k]`.
3. For `k` = 0 .. L-1: `A = Y_0[k]`, `B = Y_1[k] W^k`, `C = Y_2[k] W^{2k mod M}` where `W^n = cos(2 pi n/M) -/+ j sin(2 pi n/M)` (forward/inverse) in Q15 (`rnd15` per component); `T = B + C`, `D = B - C`, `U = A - ((T + 1) >> 1)`, `V = rnd15(D x 28378)` per component (28378 = round(32768 sqrt(3)/2)); forward: `X[k] = A + T`, `X[k+L] = U - jV`, `X[k+2L] = U + jV`; inverse: `X[k+L] = U + jV`, `X[k+2L] = U - jV` (with `-jV = (V.im, -V.re)`).
4. `out[n] = sat16(rnd14(X[(n + out_rot) mod M] c_M))` with `rnd14(v) = (v + 8192) >> 14` and `c_M` = round(16384 x 2^{s_M} / sqrt(M)) = 9459, 13377, 9459, 13377: the transform is unitary up to rounding (RMS in = RMS out).
Saturation events are counted (`ovf_cnt`, including those of the FFT).

Interface: `s_axis_*` (32-bit `{Q, I}`, `last` on the M-th), `m_axis_*` likewise, `ovf_cnt`, `err_len`. Architecture: input RAM `x` (M words) written as samples arrive; a feeder reads `x[3m + r]` into the FFT for `r` = 0, 1, 2 back to back (the FFT's ping-pong buffers overlap the three transforms); a collector writes the FFT outputs to `y[r L + k]`; the combiner (one pass over `k`, two complex multipliers and the radix-3 butterfly, a few clocks per `k`) writes the result into an output RAM; the output streams from it with the rotation. The input RAM accepts the next symbol as soon as the feeder is done.

Twiddle table: `rtl/31-dft-s-ofdm/dfts_twiddle_rom.sv` generated by `scripts/gen_dfts_twiddle.py` (cosine and sine of `2 pi n/M`, Q15, for the four M).

## 3. `dfts_tx`

Input: `M - 8` mapper samples per symbol (`s_axis`, `{Q, I}`, RMS 4096) with `fft_log2` (6 to 9) and `ref_boost` (both sampled with the first sample). It inserts the eight reference symbols, runs the forward `dft_mixed` (`out_rot = M/2`) and emits the **N bins in bin order**: bin 0 zero, bins 1 .. M/2 and N-M/2 .. N-1 from the DFT, all other bins zero, `last` on bin N-1 (the stream the IFFT of module 12 takes; the cyclic prefix and everything after are unchanged).

## 4. `dfts_rx`

Input: N bins in bin order with `fft_log2` and `ref_boost` (sampled with the first bin), `{Q, I}` zero-forcing equalised tones with `csi[7:0]` (from the equaliser, or zero outside the used set; only the bins `1 <= |k| <= M/2` are used). Each used bin is weighted `round(Z g(csi) / 256)` (`g` from the table, 9 bits, 256 = 1.0; the table is written with `lut_we`, `lut_addr[7:0]`, `lut_data[8:0]` and is 256 after reset), pushed into the inverse `dft_mixed` (`in_rot = M/2`, natural output order) and collected in a symbol buffer; the reference symbols are accumulated, `c` and `1/c` formed (a dozen clocks), and the `M - 8` data symbols are output multiplied by `1/c` (`round(d g / 2^12)`, saturated) with `m_csi = csi_out`. `m_axis` carries `M - 8` samples per symbol with `last` on the final one (the demapper of module 14 follows).

## 5. Test plan

Python models: `dfts_model.py` (bit-exact `dft_mixed`, `dfts_tx`, `dfts_rx`; the FFT model of module 12), floating-point references with `numpy`, the PAPR and link simulation `ds_link.py`, and the calibration helper `dfts_cal.py` (gain table, `csi_out`).

| ID | Test | Pass criterion |
|---|---|---|
| T31-01 | `dft_mixed` bit-exact | For M = 48, 96, 192, 384, both directions, random 16-bit inputs (several amplitude ranges, extremes), several `in_rot` and `out_rot`: RTL output equals the model, `ovf_cnt` equals |
| T31-02 | `dft_mixed` accuracy | Error against the unitary floating-point DFT (`numpy`): rms below 0.5% of the signal rms; forward then inverse restores the input to 0.5% |
| T31-03 | `dfts_tx` | Bit-exact against the model for N = 64 .. 512 and random data; the bins outside the used set are zero; the used bins equal the floating-point DFT of the symbol vector (reference symbols in place) within 0.5% rms; the reference symbols sit at the defined positions |
| T31-04 | `dfts_rx` | Bit-exact against the model with random weights, `csi`, phase rotations and a gain table; transmit (`dfts_tx`, the table of the model) then receive over an ideal channel with a common rotation of up to 1 rad and gain 0.5 to 1.5 returns the data symbols with an error vector magnitude below -35 dB |
| T31-05 | PAPR (R31-03) | 20000 symbols per case (model, bit-exact with the RTL for 200 symbols per case): the PAPR at a CCDF of 1e-3 of the 4x oversampled data symbols of plain OFDM (module 7 tone plan with pilots) and of DFT-s-OFDM, BPSK / QPSK / 16QAM, N = 64 .. 512; the difference is the result; cases below 3 dB are reported as not met |
| T31-06 | AWGN BER (R31-04) | Uncoded BER of DFT-s (the fixed-point model, MMSE table for the noise level) against plain OFDM at equal Eb/N0 for BPSK, QPSK, 16QAM: within 0.2 dB at BER 1e-2 (the edge tones and reference symbols cost a fixed energy fraction, accounted for in Eb/N0) |
| T31-07 | Multipath, coded (R31-05) | LDPC code 0 (N = 648, R = 1/2) with QPSK and code 4 (N = 1944), 2-tap channel (second tap -6 dB, delay 4 samples) and a 6-tap exponential channel: frame error rate against Eb/N0 for OFDM, DFT-s with MMSE weighting and DFT-s with zero forcing (table of ones); the Eb/N0 at FER 10% of each and the differences are reported |
| T31-08 | Module 12 unchanged | The tests of module 12 pass with the `MIN_LOG2` parameter at its default |
| T31-09 | Symbol-level loop | Mapper (module 6) to `dfts_tx` to the IFFT (module 12) to the cyclic prefix (module 4), a numpy channel (multipath, noise, common phase), the numpy FFT with the LTF channel estimate (the equaliser model), `dfts_rx` and the demapper (module 14): the recovered hard decisions equal the model's and the bit errors at high SNR are zero |
| T31-10 | Clocks per symbol | `dft_mixed` period and latency for each M, `dfts_tx` and `dfts_rx` symbol period, reported against 2880 clocks (200 MHz, 14.4 us) |
| M-31 | Mutation checks | Wrong rotation, wrong radix-3 sign, reference positions off by one, weights not applied: each fails at least one test |
| L-31, S-31 | Lint and synthesis | `-Wall` clean; Yosys no latches (the FFT instance may not complete, as module 12) |

## 6. Deliverables

`scripts/gen_dfts_twiddle.py`, `rtl/31-dft-s-ofdm/{dfts_twiddle_rom,dft_mixed,dfts_tx,dfts_rx}.sv`, `rtl/12-fft/fft_core.sv` (parameter `MIN_LOG2`), `tests/31-dft-s-ofdm/`, results below, a row in `design/README.md`.

## 7. Open items

- **Integration into `tx_chain` (module 16) and `rx_chain` (module 21)** is not done: it needs `Ncbps = (M-8) nb` in the symbol blocker and interleaver, a "no pilot" data-symbol mode in the equaliser (module 17, whose pilot phase correction would act on empty pilot bins) and in the tone plan of module 7, and a mode bit in the frame header (MAC). The symbol-level loop (T31-09) uses the same blocks around the real mapper, IFFT, cyclic prefix and demapper.
- The gain table and `csi_out` come from firmware (the noise level estimate); no estimator is part of this module.
- The effect of the lower PAPR on the PA back-off (a DPD loop with DFT-s signals, module 26) is not measured.
- 64QAM and 256QAM stay on plain OFDM; the 80 MHz mode (N = 1024) is not supported.

## 8. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/31-dft-s-ofdm/run_tests.sh` (five simulations, then the link-level simulations of `test_link.py`), `tests/31-dft-s-ofdm/mutate.sh`, `tests/common/lint_synth.sh tests/31-dft-s-ofdm`. Files: `rtl/31-dft-s-ofdm/{dft_mixed,dfts_tx,dfts_rx,dfts_twiddle_rom}.sv`, `scripts/gen_dfts_twiddle.py`, the parameter `MIN_LOG2` of `rtl/12-fft/fft_core.sv`, `tests/31-dft-s-ofdm/`.

| Test | Result |
|---|---|
| T31-01 | `dft_mixed` bit-exact against the model: 26 symbols over M = 48, 96, 192, 384, both directions, several `in_rot` and `out_rot`, amplitudes from 4000 to extreme full-scale (791 saturation events, counted identically), random valid and ready, configuration changing in the middle of symbols |
| T31-02 | Accuracy against the unitary floating-point DFT: rms error 0.026% (M = 48) to 0.066% (M = 384) forward and inverse; forward then inverse restores the input to 0.036% to 0.092% (limit 0.5%) |
| T31-03 | `dfts_tx` bit-exact for N = 64 to 512 (10 back-to-back symbols with changing N, `ref_boost` changing per symbol, random handshakes); the bins outside the used set are zero; the used bins equal the floating-point DFT of the symbol vector within 0.014% to 0.051% rms (both boost settings) |
| T31-04 | `dfts_rx` bit-exact (random weights table, random `csi`, rotations up to 1 rad, gains 0.5 to 1.5, noise, both boost settings); transmit then receive over an ideal channel with common rotation and gain returns the data symbols with an error vector magnitude of **-51.9 to -64.8 dB** (limit -35 dB) |
| T31-05 | PAPR, 20000 symbols per case, below |
| T31-06 | AWGN BER, below |
| T31-07 | Coded FER over multipath, below |
| T31-08 | `fft_core` with the new parameter `MIN_LOG2` at its default of 6: the tests of module 12 (three configurations) pass unchanged |
| T31-09 | Symbol-level loop with the real blocks: `mapper` -> `dfts_tx` -> `fft_core` (IFFT) -> `cp_insert` equals the chain of the models sample for sample (N = 64 to 512, three modulations, three prefixes; 2 symbols back to back each); `dfts_rx` -> `demapper` equals the models for 4 configurations; transmit, numpy channel (2 taps, 25 dB, random common rotation), receive: **0 bit errors** in 3 symbols of each configuration (3 to 4 modulations) |
| T31-10 | `dft_mixed`: latency 198 / 438 / 966 / 2118 clocks and symbol period **149 / 341 / 773 / 1733 clocks** for M = 48 / 96 / 192 / 384 against the 2880 clocks of a symbol at 200 MHz; `dfts_tx` has the same periods; the receiver (same engine plus 8 idle clocks and a few for the correction) keeps the same rate |
| M-31 | Seven mutants (no output rotation in the transmitter, radix-3 sign, reference position off by one, weighting not applied, scale constant 13377 -> 13376, no common correction, input rotation missing): all seven fail 3 to 12 tests or assertions |
| L-31, S-31 | `-Wall` clean for `dft_mixed`, `dfts_tx`, `dfts_rx`, `ds_tx_top`, `ds_rx_top`; Yosys: the RTL-level pass (`proc`, `opt`) finds no latches in the three blocks; **full gate-level synthesis did not finish** (the radix-3 combine as one combinational stage with 10 multipliers and arrays read with variable indices; module 12's FFT inside is itself heavy): pipelining the combine and block-RAM style memories are the open items |

### T31-05 PAPR at a CCDF of 1e-3 (4x oversampled, 20000 symbols per case; plain OFDM with the module 7 tone plan and pilots against DFT-s with 8 reference symbols)

| N | modulation | OFDM | DFT-s, references 1x | gain | DFT-s, references 2x | gain |
|---|---|---|---|---|---|---|
| 64 | BPSK | 10.61 | 8.32 | 2.29 | 8.63 | 1.98 |
| 64 | QPSK | 10.45 | 7.54 | 2.91 | 7.80 | 2.65 |
| 64 | 16QAM | 10.44 | 8.37 | 2.07 | 8.15 | 2.30 |
| 128 | BPSK | 11.03 | 8.76 | 2.26 | 9.56 | 1.46 |
| 128 | QPSK | 10.93 | 7.83 | **3.10** | 8.46 | 2.47 |
| 128 | 16QAM | 10.97 | 8.75 | 2.22 | 8.80 | 2.17 |
| 256 | BPSK | 11.00 | 9.08 | 1.91 | 10.04 | 0.96 |
| 256 | QPSK | 11.22 | 8.07 | **3.15** | 8.78 | 2.44 |
| 256 | 16QAM | 11.23 | 9.00 | 2.23 | 9.27 | 1.96 |
| 512 | BPSK | 11.53 | 9.34 | 2.19 | 10.42 | 1.12 |
| 512 | QPSK | 11.48 | 8.21 | **3.27** | 8.95 | 2.53 |
| 512 | 16QAM | 11.60 | 9.25 | 2.35 | 9.47 | 2.13 |

The fixed-point spectrum (the RTL) and the floating-point DFT give the same per-symbol PAPR to 0.002 dB (48 symbols).

### T31-06 uncoded BER in AWGN (N = 256, ideal channel knowledge; Eb/N0 counts the data symbols only)

| modulation | Eb/N0 | theory | plain OFDM | DFT-s 1x | DFT-s 2x | shift 1x / 2x against OFDM (dB) |
|---|---|---|---|---|---|---|
| BPSK | 4.0 | 1.25e-2 | 1.27e-2 | 1.35e-2 | 1.25e-2 | +0.09 / -0.02 |
| BPSK | 5.5 | 3.86e-3 | 3.87e-3 | 3.87e-3 | 3.66e-3 | 0.00 / -0.06 |
| QPSK | 4.0 | 1.25e-2 | 1.29e-2 | 1.50e-2 | 1.29e-2 | +0.21 / 0.00 |
| QPSK | 5.5 | 3.86e-3 | 4.08e-3 | 4.78e-3 | 3.84e-3 | +0.16 / -0.06 |
| 16QAM | 7.0 | 1.70e-2 | 1.65e-2 | 2.02e-2 | 1.73e-2 | +0.34 / +0.08 |
| 16QAM | 9.0 | 4.39e-3 | 4.70e-3 | 6.26e-3 | 5.01e-3 | +0.33 / +0.07 |

### T31-07 coded FER, LDPC N = 648 R = 1/2, QPSK, N_fft = 256, block fading per codeword, 120 codewords per point; Eb/N0 at FER 10% (dB)

| channel | plain OFDM | DFT-s MMSE, 1x refs | DFT-s MMSE, 2x refs | DFT-s zero forcing, 1x refs |
|---|---|---|---|---|
| flat (AWGN) | 2.29 | 3.08 (+0.79) | 2.53 (+0.24) | 3.10 (+0.81) |
| 2 taps (0 dB, -6 dB, 4 samples) | 2.90 | 4.07 (+1.16) | 3.45 (+0.55) | 5.02 (+2.12) |
| 6 taps, exponential, random | below 4 (FER 0.083 at 4 dB) | 5.10 | 4.64 | above 12 |

### What this means

- **The PAPR target of 3 dB below plain OFDM is met only for QPSK at N = 128 to 512 with references at the data amplitude (3.10 to 3.27 dB); it is not met for BPSK (1.9 to 2.3 dB), for 16QAM (2.1 to 2.35 dB) or for QPSK at N = 64 (2.91 dB).** Doubling the reference amplitude costs 0.5 to 0.8 dB of that gain everywhere. A spectral shaping filter was tried in a preliminary experiment and moved the gains by less than 0.5 dB. The `[E]` figure of PHY-014 is therefore optimistic for BPSK and 16QAM in this design; a real gain of 2 to 3 dB is what the mode delivers.
- **The cost of the mode.** Uncoded, in AWGN, the DFT-s link equals OFDM within 0.1 dB when the references are boosted (0.2 to 0.34 dB with 1x references, the price of the noisy common-phase estimate from 8 symbols). Coded, over multipath, plain OFDM is better by 0.2 to 1.2 dB with the 2x references (and by 0.8 to 1.2 dB with 1x): the despreading collects the noise of faded tones (MMSE weights limit it; zero forcing is 1.4 to 2.1 dB worse than MMSE on the 2-tap channel and fails on the long channel), while coded OFDM exploits the diversity directly. The throughput is also lower: 100%, 89%, 82%, 82% of the plain OFDM data tones for N = 64 to 512, and 8 of M tones carry references.
- **So the mode is a power-limited-PA tool, not a free lunch.** It trades about 0.5 dB (2x refs) to 1 dB of link margin and 11 to 18% of the rate for 3 dB of PAPR in the one favourable case (QPSK, N >= 128) and about 2 dB otherwise; whether that pays depends on the PA study (T-14) and on the back-off it actually buys (not measured here: no DPD loop with DFT-s signals).
- **Hardware.** The transform engine takes 1733 clocks per symbol at N = 512 (60% of the 2880 available), 149 clocks at N = 64; one engine serves the transmitter and one the receiver.

### Limits

- Not integrated into `tx_chain` / `rx_chain` (section 7); the frame header needs a mode bit and the gain table, `csi_out` and `ref_boost` need firmware; ideal channel knowledge in the link simulations (no LTF estimation noise, no timing or frequency error); coded results for one code and one modulation (QPSK, N = 648), 120 codewords per point (an uncertainty of about 0.15 dB on the 10% point).
- 64QAM and 256QAM and N = 1024 are not supported by this mode; the mixed-radix size is fixed to M = 3N/4.
- The effect on the PA back-off, the spectrum mask and the DPD (module 26) with DFT-s signals is not measured.
