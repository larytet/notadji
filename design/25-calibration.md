# 25 - Calibration Engine

Plan entry: module 25 of `spec/18-development-plan.md`, class L, real-time core with data plane. Requirements: CAL-001 (factory tables in non-volatile memory with a CRC and a version), CAL-002 (background calibration without interrupting video: TX LO leakage and IQ through the observation receiver in guard times, RX DC offset in idle slots, RX IQ with a tone on a loop-back path), CAL-003 (re-calibration when the temperature moved by more than 5 deg C since the last one, and every 60 s), CAL-004 (tables per band, channel group and temperature bin, restored on a hop within the RF-006 time), RF-024 (RX image rejection 40 dB or better, RX DC below -80 dBFS), RF-025 (TX LO leakage and image -45 dBc or better), SIM-004 of `17`. Depends on 10 (guard and idle events), 11 (samples) and 18 (conventions).

Three parts: **RTL** (a statistics accumulator `cal_stats` and a correction block `iq_corr`, used in the receive path and in the transmit path), **firmware** (the estimator, the trigger and scheduling logic, the table store with CRC), and a **closed-loop test** that puts the three together against an impairment model.

## 1. Method

**Blind IQ-imbalance estimate.** A wideband OFDM-like signal `x` is circular (`E[x^2]` = 0). With an IQ imbalance to first order `z = x + e x*` (`e` complex, `|e|` small): `E[z^2] = 2 e E[|x|^2]` and `E[|z|^2]` is `E[|x|^2] (1 + |e|^2)`, so `e = E[z^2] / (2 E[|z|^2])` with, in terms of the accumulated sums, `E[z^2] = (S_ii - S_qq + 2j S_iq) / N` and `E[|z|^2] = (S_ii + S_qq) / N`. The correction is `x' = z - e z*`, i.e. `I' = I - (e_r I + e_i Q)`, `Q' = Q - (e_i I - e_r Q)`; the residual error is of order `|e|^2`. The image rejection is `1 / |e|^2` (a residual `e` of 0.01 is 40 dB). No tone and no trigonometry are needed; the signal only has to be circular (a received video burst or the transmitted burst seen by the observation receiver). A tone on a loop-back path (CAL-002) gives the same sums with a non-circular input and is handled by the same hardware but a different estimator (section 5, not implemented).

**DC offset.** Receive: the mean of the samples of an idle slot (noise only): `dc = S_i / N`, `S_q / N`. TX LO leakage: the mean of the observation receiver samples during a transmit burst, minus the receive DC offset known from the idle slot; the leakage is cancelled by adding the negated value in the transmit path (`dc` input of `iq_corr`).

**Temperature and frequency.** The calibration state is a table indexed by band (2 values), channel group (8) and temperature bin (21 bins of 5 deg C from -20 to +85 deg C): 336 entries of 24 bytes; `cal_lookup` is a single index computation.

## 2. RTL

### 2.1 `cal_stats`

Accumulates over a window of samples: `start` (pulse) with `n_samples[23:0]` begins a window, `clear` (pulse) zeroes the sums (windows add up until cleared, so several guard times can contribute to one estimate). Input: `s_valid`, `s_data[31:0]` = `{Q, I}` (16-bit signed). Outputs: `sum_i[39:0]`, `sum_q[39:0]` (signed), `sum_ii[47:0]`, `sum_qq[47:0]` (unsigned), `sum_iq[47:0]` (signed), `count[31:0]` (samples accumulated since `clear`), `busy`, `done` (pulse at the end of each window). Capacity: `2^17` samples of full-scale 16-bit data (`2^47` for the squares) before `ovf` is set; typical use is `2^16`. `start` while busy is ignored (`ovr_cnt`).

### 2.2 `iq_corr`

`s_valid`, `s_data` in; `m_valid`, `m_data` out (pipeline of 3 clocks, one sample per clock); coefficients (registered at a frame boundary by the caller, taking effect on the clock `cfg_valid` is high): `eps_r[15:0]`, `eps_i[15:0]` (Q15, signed, `|e| < 0.5`), `dc_i[15:0]`, `dc_q[15:0]` (signed, subtracted from the input first for the receive path; in the transmit path the caller supplies the negated leakage and `dc_after` = 1 adds it after the matrix), `en`. With `en` = 0 the block passes the samples unchanged. Output saturates to 16 bits.

## 3. Firmware (`cal_mgr`, portable C99, as modules 23 and 24)

- **`cal_stats_to_coeff`**: from the sums and `N` returns `dc_i`, `dc_q` (`S/N`, rounded) and `eps_r`, `eps_i` in Q15 by the formula of section 1 (64-bit integer arithmetic; rejects `N` below a minimum, signal power below a floor, and `|e|` above `eps_max` = 0.25: a window with a non-circular content, for example a pure tone, must not be applied).
- **Tables**: `cal_entry` = `{version, band, group, tbin, valid, dc_rx_i, dc_rx_q, eps_rx_r, eps_rx_i, dc_tx_i, dc_tx_q, eps_tx_r, eps_tx_i, tx_gain_x16, rx_gain_x16, crc32}`; `cal_table_check` validates the CRC-32 (IEEE, reflected 0xEDB88320) and the version of every entry and marks bad ones invalid (CAL-001); `cal_lookup(band, group, temp_x10)` returns the nearest valid bin (the same bin, then the neighbours outward; `none` if no entry is valid, in which case the neutral default is used and a flag is raised).
- **Triggers** (`cal_tick(now_ms, temp_x10, window, ...)`): a job is due when the temperature differs from the temperature of the last calibration of the working entry by more than 5.0 deg C (CAL-003), or 60 s have passed, or the band or channel group changed and the restored entry is older than its limit. Jobs: `RX_DC` (needs window `IDLE`), `TX_LO` (needs `GUARD_TX`, after an `RX_DC` exists), `TX_IQ` (needs `GUARD_TX`), `RX_IQ` (needs `RX_BURST` or `IDLE` with a circular source). A job is only issued when its window flag is set, never twice in one window, and at most one job per `min_gap_ms`; the result returns through `cal_result(job, sums, n)`.
- **Update law**: new coefficients are blended into the working entry by an IIR step `c += (c_new - c) / 2^k` (`k` = 2 in the first update after a hop or a power-up, 3 otherwise) so that one noisy window cannot disturb the video; rejected windows leave the entry unchanged and increment a counter. The entry is marked dirty for the non-volatile save (not done here).
- **Restore on a hop** (CAL-004): `cal_lookup` plus the register write list `cal_regs(entry, out[])` (at most 8 register values) is a bounded, loop-free path.

## 4. Test plan

| ID | Test | Pass criterion |
|---|---|---|
| T25-01 | `cal_stats` | Random streams with gaps, several windows added up, `clear`, window of 1 to 70000 samples: all five sums, `count` and `done` equal numpy exactly; extreme samples (-32768) at 65536 samples without overflow; `start` while busy counted |
| T25-02 | `iq_corr` | Bit-exact against the integer Python model for random samples and coefficients (including saturation); `en` = 0 passes through; coefficient update takes effect on the stated clock; one sample per clock throughput; against the float formula within 1 LSB |
| T25-03 | Estimator accuracy | For random `e` (|e| up to 0.15, i.e. image rejection from 16 dB), DC up to 2000 LSB and circular Gaussian signals of 4096, 16384 and 65536 samples: the C estimator's `e` error is within 3 / sqrt(2N) times the signal-dependent noise bound and the residual image rejection after correction is at least 40 dB for N = 65536 and at least 30 dB for N = 4096; DC error within 1 LSB at N = 65536 |
| T25-04 | Sanity rejection | A pure tone, a two-tone signal, a DC-only window, an all-zero window, N below the minimum: rejected (no coefficient change) and counted |
| T25-05 | Closed loop in RTL | The impaired signal (gain imbalance, phase imbalance, DC, thermal noise at 30 dB SNR) through `cal_stats` (RTL) -> the C estimator -> `iq_corr` (RTL): image rejection against the signal improves from 20 to 30 dB before to 40 dB or better after, DC below -80 dBFS (RF-024), over 20 random impairments |
| T25-06 | Transmit side | The same loop for the transmit path through an observation receiver that has its own (already corrected) impairments: LO leakage -45 dBc or better and sideband -45 dBc or better (RF-025) for 20 random impairments, with the leakage separated from the receive DC |
| T25-07 | CRC and tables | CRC-32 equals Python `zlib.crc32` on random data; a single flipped bit in any field of any entry is detected; a wrong version is detected; lookup returns the nearest valid bin in both directions and `none` with no valid entry; neutral default used and flagged |
| T25-08 | Triggers | A temperature ramp of 0.1 deg C per second over 600 s: jobs at 5.0 deg C steps and at 60 s intervals, never more than one per `min_gap_ms`, jobs only in their windows; a step of 12 deg C triggers one set of jobs; no job without its window; band change triggers a restore and a refresh when the entry is old |
| T25-09 | Update law | Noisy windows (N = 4096): the entry converges, its jitter after 20 updates is below the single-window jitter divided by 3; a rejected window leaves it unchanged; after a hop the first update uses the faster step |
| T25-10 | Hop restore path | `cal_lookup` + `cal_regs` for random hops return the right entry and 8 register values; the path has no loop over the table (checked by the instruction count of the host build for all inputs: constant to within 10%) |
| T25-11 | Portability | `-std=c99 -Wall -Wextra -Wconversion -Wshadow -Werror -mgeneral-regs-only`, no undefined symbols; random inputs under UBSan and ASan |
| L-25, S-25 | Lint and synthesis | RTL `-Wall` clean; no latches; counts recorded |

## 5. Deliverables

`rtl/25-calibration/{cal_stats,iq_corr}.sv`, `fw/25-calibration/{cal_mgr.h,cal_mgr.c}`, `tests/25-calibration/` (cocotb with ctypes for the loop, Python harness for the firmware), results below, row in `design/README.md`.

## 6. Open items

- The tone on a loop-back path for RX IQ (CAL-002) and the gain/phase-frequency-dependent imbalance (a per-sub-band correction): the block corrects a frequency-flat imbalance only; the tests use a flat one.
- TX power versus frequency and temperature (RF-011) tables are stored and restored by this module but the measurement loop (a power detector, not a sample path) is not part of it.
- Non-volatile storage drivers, factory calibration procedure and the DPD seed coefficients (CAL-001, module 26).
- Not run on a target core (no QEMU/Renode).
