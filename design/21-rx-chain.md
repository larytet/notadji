# 21 - Receive Chain Integration

Plan entry: module 21 of `spec/18-development-plan.md`, class L, data plane. Requirements: PHY-001 to PHY-011 end to end, SYS-002 (latency budget input). Integrates module 18 (synchroniser), 4 (prefix removal by windowing), 12 (FFT), 17 (equaliser), 14 (demapper), 5 (de-interleaver), 20 (LDPC decoder) and module 1 (width conversion) into the first complete receive path, and closes the link against the transmit chain of module 16 through a software channel. Module 19 (branch combiner) is not part of this revision: the chain serves one receive branch.

## 1. Frame processing

Input: the radio sample stream (32-bit `{Q, I}`, one sample strobe at most every second clock; the radio cannot be stopped). Configuration for a frame (stable for its duration): `fft_log2` (7 to 9 in this revision), `cp_sel`, `mod`, `code`, `nsym` (number of data symbols), `ncw` (number of codewords), `nbytes` (payload bytes), `backoff` (FFT window early-start inside the prefix, samples), `thr_sel`, `min_power`. These come from the MAC (module 22): the slot length gives `nsym`, the slice length `ncw` and `nbytes`.

1. **Synchroniser** (module 18): detects the STF, estimates and removes the carrier offset, and pulses `fall` when the STF has ended. The first sample after the STF is `n0 = n_fall - k_back - BIAS` (`BIAS` = 2 samples, the mean marker error measured in `18` at 20 dB and above).
2. **Framer** (new): counts the derotated samples from `fall`; the FFT window of long-training symbol 1 starts at `n0 + Lc - backoff` (`Lc` the prefix length from `cp_sel`), so after `fall` it skips `Lc - backoff - k_back - BIAS - 1` samples (clamped at 0), then takes `N` samples (a window), skips `Lc` samples, takes `N` again, for `2 + nsym` windows (two long-training symbols and the data symbols), marking `last` on the N-th sample of each window. **Limit:** the skip must not be negative; with the default prefix 1/8 this holds for N >= 128 and `backoff` <= 4; N = 64 would need a short history buffer (open item).
3. **FFT** (module 12, forward, all stages shifted: no overflow for any input).
4. **Equaliser** (module 17): the symbol kind comes from a counter of completed input symbols (0: LTF1, 1: LTF2, 2: first data symbol, then 3); it outputs the equalised data tones and `csi`.
5. **Demapper** (module 14) with `llr_shift` chosen from the modulation (13 for BPSK and QPSK, 12 for 16QAM, 11 for 64QAM, 10 for 256QAM) and the LLR serializer.
6. **De-interleaver** (module 5, block length `Ncbps`), one block per data symbol.
7. **LLR trim** (new): passes the first `ncw x N` LLRs of the frame and discards the rest (the zero padding of the last block); a FIFO of 8-bit LLRs (depth 4096) decouples the symbol rate from the decoder.
8. **LDPC decoder** (module 20): one codeword at a time, `max_iter` from the configuration (default 10).
9. **Message to bytes** (new): the decoded K-bit messages are concatenated as a bit stream, grouped into bytes (bit 0 first), and the first `nbytes` bytes are output with `last` on the final byte; the codeword status `m_ok` of every codeword is ANDed into the frame status `frame_ok`, and `iters_max` is the largest iteration count used.
10. After the last byte the synchroniser is re-armed for the next frame.

Unlike the transmit chain, nothing here may stall the sample input: the FIFO and the decoder rate must keep up with the symbol rate; the test reports the FIFO occupancy.

## 2. Interface

`rx_chain`: `clk`, `rst_n`, the configuration inputs above, `s_valid`, `s_data[31:0]` (samples), `m_axis_*` (8-bit bytes with `last`), `frame_ok` (valid with `last`: every codeword decoded with a valid parity check), `iters_max[5:0]`, `det`, `cfo_inc[23:0]` (from the synchroniser), `err` (sticky pulse: sample FIFO overflow, framer skip below zero, `last` mismatch inside the chain).

## 3. Test plan

A wrapper `link_top` instantiates the transmit chain (module 16) and the receive chain; a Python channel between them delays the TX samples by a random number of samples, applies a carrier offset, a mild multipath (taps within the prefix) and noise, and feeds the result to the receive chain at one sample every 4 clocks.

| ID | Test | Pass criterion |
|---|---|---|
| T21-01 | Glue blocks | `rx_framer` (skip, window and `last` pattern for several `N`, `cp_sel`, `backoff`), `llr_trim` and `msg_to_bytes` match their Python definitions, including padding and the frame status |
| T21-02 | Noiseless loop | TX bytes through RTL TX, a delay, no noise and no offset, RTL RX: the bytes are recovered for N = 128 and 256, several modulations and codes |
| T21-03 | Carrier offset | Offsets of +/-0.5 and +/-1.5 sub-carrier spacings at 30 dB SNR: bytes recovered; the estimated `cfo_inc` within 0.05 sub-carrier spacings |
| T21-04 | Noise | 25 dB SNR (per sample, QPSK/16QAM): bytes recovered in at least 9 of 10 frames; at a lower SNR the frame error rate rises as expected (measured and recorded) |
| T21-05 | Multipath | Two-tap channel (second tap 0.4 at a delay of 5 samples, within the prefix): bytes recovered |
| T21-06 | Frames in a row | Three frames with different configurations and `rearm`: all recovered |
| T21-07 | Latency and rates | First byte out relative to the end of the last symbol; FIFO occupancy high-water mark; decoder busy time per codeword: recorded and compared with the symbol period |
| L-21, S-21 | Lint and synthesis | `-Wall` clean; no latches; counts recorded (Yosys may not complete for the full chain; reported as in `17`) |

## 4. Deliverables

`rtl/21-rx-chain/{rx_framer,llr_trim,msg_to_bytes,rx_chain}.sv`, `tests/21-rx-chain/` (wrapper, channel, tests), results below, row in `design/README.md`.

## 5. Open items

- N = 64 (history buffer for a negative skip), N = 512 timing, the branch combiner in the chain (module 19), pilot-based timing and fine carrier tracking inside the frame, the LTF-based timing refinement (module 18 open item), and several frames in flight.
- Real-time margins: the sample FIFO and decoder occupancy at the highest rates (module 20 throughput).

## 6. Results (implementation commit)

Simulation: `tests/21-rx-chain` (Verilator, cocotb). The wrapper `link_top` holds the transmit chain (module 16) and the receive chain; a Python channel delays the captured TX samples by a random 60 to 300 samples, applies a two-tap multipath, a carrier offset and white noise, and feeds the receiver at 4 or more clocks per sample. All 7 configurations pass (glue blocks, noiseless and offset loop, noise, rate sweep, five-frame sequence).

| Test | Result |
|---|---|
| T21-01 glue | `rx_framer` (N = 128, 256, 512; cp_sel 1, 2; backoff 0, 2, 4): window start and `last` pattern as defined, negative skip flagged; `llr_trim` and `msg_to_bytes` (K = 324, 540, 972; random backpressure) equal the Python definitions |
| T21-02 noiseless | N = 128 and 256, BPSK/QPSK/16QAM/64QAM/256QAM, codes 0, 1, 3, 4, cp_sel 1 and 2: every frame recovered, `frame_ok` = 1, 1 decoder iteration, `err` = 0 |
| T21-03 carrier offset | +/-0.5 and +/-1.5 sub-carrier spacings at 30 dB: bytes recovered, estimate error 0.001 to 0.0024 spacings (limit 0.05) |
| T21-04 noise | QPSK rate 2/3 (code 1): 10 of 10 frames at 25, 18, 14 and 11 dB; 16QAM code 1: 10 of 10 at 25, 21 and 18 dB. No lower SNR was swept, so the frame-error knee is not located; the 25 dB criterion (9 of 10) is met |
| T21-05 multipath | taps 1.0 and 0.4 at 5 samples, N = 256, cp_sel 1, QPSK and 16QAM: recovered |
| T21-06/08 frames in a row | five frames with different N, prefix, modulation and code, no reset, 60 dB: all recovered; three more at 30 dB with 0.3 spacing offset |
| T21-07 rate | N = 256, cp_sel 1, rate 2/3, 30 dB: QPSK, 16QAM and 64QAM frames are recovered with a sample strobe every 4 clocks and no overrun (`err` = 0); FIFO high-water 288 to 927 LLRs of 4096; 1 decoder iteration. Rates below 4 clocks per sample were not established (the only run at 3 clocks was made before the trim fix and failed); the other tests use the larger of 4 and 1.15 x `(Ncbps + 2N)/(N + Lc)` clocks per sample |
| T21-07 latency | the first byte leaves before the last sample has arrived (a codeword decodes while later symbols are still received); the last byte leaves 2.7 to 2.9 thousand clocks after the last sample (about 2 symbol periods at 4 clocks per sample) |
| L-21 | `rx_framer`, `llr_trim`, `msg_to_bytes`, `rx_chain`: no warnings from `-Wall` in the module 21 files |
| S-21 | Yosys generic synthesis: `rx_framer` 423 cells, `llr_trim` 471 cells, `msg_to_bytes` 343 cells, no latches. `rx_chain` and `link_top` were not synthesised (the sub-blocks 17, 18, 20 do not finish, see their results). `tests/common/lint_synth.sh` on this directory fails because it loads the whole source list and Yosys 0.71 hits an assertion in its Verilog front end on one of the earlier modules; the three glue blocks were synthesised directly |
| Mutation | `llr_trim` restart disabled: T21-01 trim test fails; `rx_framer` BIAS 2 changed to 3: T21-01 framer test fails; both restored |

### Defects found by the integration tests and fixed

1. **FFT scale.** The equaliser expects tones at +/-4096, i.e. the receive FFT must shift only 3 stages (a transmitter that shifts `N`-3 stages gives 8 x the tone amplitude after an unnormalised FFT). With all stages shifted (the first draft) the channel quality `csi` was 0 and every LLR 0. The receive FFT now uses `shift_mask` = 0x007. The signal level at the FFT input is assumed to be that of the transmitter (the AGC of module 18 must deliver it); a strong in-band blocker could overflow the FFT (`ovf_cnt` is available).
2. **LLR trim restart.** The trim counter was cleared by `frame_done`, but the padding LLRs of the last block can still arrive after the last codeword has been decoded; they then counted as the first LLRs of the next frame and shifted every codeword boundary (the second frame failed all bytes). The trim now restarts itself after `nsym x Ncbps` inputs (`frame_llr`).
3. **Early detection (module 18).** On a near-noiseless input a one-sample "burst start" could satisfy the metric while the lagged window held almost nothing, giving a detection 63 samples into the burst and a carrier estimate of 1.1 spacings. The detector now also requires the lagged window energy above `min_power` (`sync_core.sv`); module 18's seven tests still pass.
4. Test-side: frame status is registered about 130 to 500 clocks after the last byte (the remaining message bits of the last codeword are still serialised), so the tests read it late; `rx_backoff` is 4 bits (capped at 15).

### Limits (measured, not fixed here)

- The serial path equaliser output to serializer (1 LLR per clock) and the equaliser holding a whole symbol limit the sustainable sample rate: about `(Ncbps + 2N) / (N + Lc)` clocks per sample (4.5 for 16QAM at N = 256). The test feeds at the larger of 4 clocks and 1.15 times that. A wider serializer or a double-buffered equaliser is needed for higher rates.
- The decoder is a single instance (module 20 throughput 34 to 114 Mbit/s class); the FIFO absorbed the bursts in every run above, but no run used the highest codes at the highest sample rates.
- N = 64 is unsupported (negative skip), N = 512 timing, receive diversity (module 19) and tracking inside the frame remain open as listed in section 5.
- Window start is `backoff` samples before the estimated symbol boundary; `backoff` = a quarter of the prefix (max 15) was used. The marker spread below about 10 dB (module 18) was not exercised; the noise sweep stops at 11 dB.
