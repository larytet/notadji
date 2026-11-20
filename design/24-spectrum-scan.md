# 24 - Spectrum Scan and Channel-Selection Logic

Plan entry: module 24 of `spec/18-development-plan.md`, class L, real-time core with data plane. Requirements: ADA-001 (the ground unit scans the permitted channels with a 50 us dwell per channel and ranks them by interference energy and by decoded video quality), ADA-002 (a channel switch on degraded quality, decision latency of 20 ms or less, execution as MAC-010), ADA-003 (static adaptive channel with a fallback channel list), ADA-010 (strong adjacent-channel signals above -60 dBm are detected, an alternate channel or lower power is preferred, the pilot is told), RF-006 (50 us settling for a hop inside a band). SIM-030 of `17`. Depends on 10 (sequencer events), 11 (radio interface samples) and 18 (energy and gain conventions).

Two parts: a **hardware scan engine** (RTL, measures energy per dwell and keeps a table) and **channel-selection firmware** (portable C, as module 23, decides when and where to switch).

## 1. Scan engine (RTL)

The radio is tuned away from the video channel only for short slots that the sequencer (module 10) schedules in the idle part of the frame (the 5% idle period of MAC-012 or the guard of MAC-001); the slot is: retune to the scan channel, settle, measure for the dwell time, retune back (150 us per channel in all: 50 settle + 50 dwell + 50 back at the RF-006 figure). A scan of 24 channels therefore takes 24 slots (one per frame or per few frames). The engine does the measurement and the bookkeeping, not the timing of the radio (the sequencer owns that).

### 1.1 `scan_meas`

One measurement. `start` (pulse) with `settle_ticks` and `dwell_ticks` (in sample strobes, not clocks, so the measurement is independent of the clock-to-sample ratio): the engine ignores `settle_ticks` samples, then accumulates `|I|^2 + |Q|^2` over `dwell_ticks` samples (`s_valid` strobes; 16-bit signed `I` and `Q`, `s_data` = `{Q, I}`), and delivers `done` (pulse) with `sum[47:0]` (the exact energy sum), `lg[11:0]` (an integer logarithm, see below) and `sat` (never set at the supported counts, see the bound below). `busy` is high between `start` and `done`. A new `start` while busy is ignored and counted in `ovr_cnt`.

Logarithm: `lg = 16 x p + m`, with `p` the position of the leading one of `sum` and `m` the four bits below it (0 to 15): the Mitchell piecewise-linear approximation of `16 log2(sum)`. One unit of `lg` is 0.188 dB (3.0103 / 16); the approximation is within 0.0861 octave (0.26 dB) of the true logarithm and the truncation adds up to one unit.

Bound: 16-bit samples give at most `2 x 2^30 = 2^31` per sample; the accumulator is 48 bits, so up to `2^17 = 131072` dwell samples are summed without overflow; 50 us at 40 MHz is 2000 samples.

### 1.2 `scan_engine`

Sequencing and table. Configuration: `ch_mask[31:0]` (channels enabled for scanning), `n_ch[5:0]` (channels in the plan, at most 32), `settle_ticks`, `dwell_ticks`, `strong_thr[47:0]` (energy sum above which a channel is flagged strong, ADA-010), `home[4:0]` (the video channel, never scanned).

- `slot` (pulse from the sequencer: start the next scan slot): the pointer advances to the next enabled channel other than `home` (wrapping) and `retune_req`/`retune_ch[4:0]` pulse with it; `rx_ready` (from the radio interface, the retune and settle are done) starts the measurement; `done` writes the table entry and pulses `result_valid` with `result_ch`; the engine then asks for the retune back to home (`retune_req` with `retune_ch` = `home`, `back` = 1); the slot ends with `slot_done`.
- Table entry per channel: `last[47:0]`, `lg_last[11:0]`, `max_hold[47:0]` (maximum over the scans since `clear`), `count[15:0]`, `strong` flag. Read port: `rd_ch[4:0]` -> `rd_*` (registered, one clock).
- `scan_cnt[15:0]` counts completed sweeps (a sweep = the pointer wrapped).

### 1.3 Conversion in firmware

`lg` to dB relative to full scale: `10 log10(sum) = lg x 0.18814` dB re one LSB squared; the power per sample is that minus `10 log10(dwell_ticks)`, and the offset to dBm is a configuration constant of the firmware (the receiver's gain and full-scale calibration, CAL-001).

## 2. Channel-selection firmware (C)

State per channel: smoothed interference level (`lvl_x16`, EWMA, in `lg` units), age of the last scan (ms), `blacklist_until_ms`, `quality` (last known slice-loss rate after use, ppm, with age). For the current channel the live slice-loss rate (ppm, EWMA over the feedback of module 23 / the ACK window of module 22) and the SNR.

Inputs: `cs_scan(ch, lg, t_ms)` for every scan result, `cs_quality(loss_ppm, snr_x10, t_ms)` for the current channel every feedback message, `cs_tick(t_ms)` at least every millisecond. Output: `cs_decision` = `{switch, target, effective_frame, reason}` returned by `cs_tick`.

Rules:
1. **Score** of a channel: `lvl` (lower is better) plus a penalty `adj_pen` if an adjacent channel is flagged strong (ADA-010; the leakage of our own signal into it and of its signal into us), plus a penalty `unknown_pen` if the scan is older than `stale_ms`, plus the remembered `quality` penalty (`loss_ppm` in log units) for channels used in the last `memory_ms`; blacklisted channels and channels outside the enabled set score infinite.
2. **Degradation trigger** for the current channel: the loss rate above `loss_trig_ppm` for `det_ms` (default 10 ms) or the current channel's interference level above its level at the time of selection by `rise_x16` (an interferer appeared) for `det_ms`. The decision is taken in the first `cs_tick` after the trigger holds: the latency from the start of the degradation to the decision is `det_ms` plus the tick period, within the 20 ms of ADA-002 for `det_ms` of 10 ms and ticks of 1 ms.
3. **Choice**: the lowest score among candidates; the switch happens only if it beats the current channel's score by `margin_x16` (hysteresis); candidates must be confirmed by `confirm` consecutive evaluations (default 2) to avoid chasing one noisy scan.
4. **Severity**: loss above `severe_ppm` (default 50%) for `det_ms`: switch to the best candidate without the margin and the confirmation, and not limited by the minimum stay.
5. **Minimum stay** `min_stay_ms` (default 500 ms) between two switches (no ping-pong), except for rule 4. A new channel that shows loss above `severe_ppm` within `probation_ms` after the switch is blacklisted for `blacklist_ms` and the controller goes to the next best (or back to the previous channel if it is the best remaining).
6. **Fallback list** (ADA-003a): if no candidate has a valid score (no scan data yet, all stale or blacklisted), the next channel of the configured fallback list that is not blacklisted is chosen.
7. **Switch timing**: the decision carries `effective_frame` = the current frame number plus `switch_lead` (default 4 frames), so both units retune at the same frame start (execution as MAC-010; the control message belongs to the MAC).
8. **Neighbour report** (ADA-010): `cs_status` returns the flag "strong adjacent signal" and the channel numbers for the pilot display.
9. **Herding**: a link that decides because of interference on its channel adds a per-link pseudo-random delay of 0 to `jitter_ms` (from the link identifier) to its decision, so that several co-located links that see the same interferer do not all move to the same free channel in the same millisecond.

## 3. Test plan

| ID | Test | Pass criterion |
|---|---|---|
| T24-01 | `scan_meas` | Random sample streams with gaps in `s_valid`, settle 0 to 200 and dwell 1 to 2000 samples: `sum` equals the exact numpy sum of the dwell window; `lg` equals the integer model; `done` exactly after the last dwell sample; `start` while busy ignored and counted; extreme samples (-32768) accumulate without overflow for 2000 samples |
| T24-02 | `scan_engine` sequencing | The pointer visits the enabled channels in order, skips `home` and disabled ones, wraps and counts sweeps; `retune_req` and `retune_ch` as specified; every slot ends with the retune back to `home` |
| T24-03 | `scan_engine` table | After random scans the table (`last`, `lg_last`, `max_hold`, `count`, `strong`) equals the Python model for every channel; `clear` resets |
| T24-04 | Timing | The slot takes `settle + dwell` sample strobes between `rx_ready` and `slot_done` (measured), whatever the strobe spacing |
| T24-05 | Ranking | For random spectra the order of the firmware's candidates equals an independent sort by the stated score; blacklisted and disabled channels never chosen |
| T24-06 | Hysteresis | Scan noise of 2 dB sigma on a spectrum with two nearly equal best channels: at most one switch per minute |
| T24-07 | Decision latency | A step in the loss rate to 20% on the current channel: `switch` within 20 ms of the step in 1 ms ticks (in 1000 random trials: the maximum latency is reported); severe loss: decision at `det_ms` |
| T24-08 | Interferer appears | A 20 dB interferer on the current channel (loss follows): the controller leaves for the best clean channel; never to a channel in use by the interferer |
| T24-09 | Probation and blacklist | The chosen channel turns bad right after the switch: blacklisted, next best taken, no more than one switch per `min_stay_ms` except severe |
| T24-10 | Fallback | No scan data: the fallback list is used in order, skipping blacklisted entries |
| T24-11 | Several links | Four co-located links choose among 12 channels with each other as the only interferers (energy on the same channel and 25 dB lower on adjacent ones) plus a jammer that moves every 5 s: after the initial selection the fraction of link-seconds with two links on the same channel is reported; no link switches more than once per `min_stay_ms` except on severe loss |
| T24-12 | Portability | `-std=c99 -Wall -Wextra -Wconversion -Wshadow -Werror -mgeneral-regs-only`; no undefined symbols; under UBSan and ASan a random-input run with invariants (target in range, never blacklisted) |
| L-24, S-24 | Lint and synthesis | RTL `-Wall` clean; no latches; counts recorded |

## 4. Deliverables

`rtl/24-spectrum-scan/{scan_meas,scan_engine}.sv`, `fw/24-channel-selection/{chan_select.h,chan_select.c}`, `tests/24-spectrum-scan/` (cocotb for the RTL, Python harness for the firmware), results below, row in `design/README.md`.

## 5. Open items

- The radio-side timing (retune, settle, return) is executed by the sequencer table (module 10, actions `SET_PLL` and `PULSE`) and the radio's `rx_ready`; the engine assumes `rx_ready` arrives; a missing `rx_ready` is guarded by a timeout (`tmo_ticks`, error flag `err_tmo`).
- Calibration of `lg` to dBm per channel and gain state (CAL-001, module 25).
- Decoded video quality of channels other than the current one is not measurable; the memory of past quality is the only proxy.
- Radar detection (DFS) for regions that need it (ADA-011, optional P2) is not part of this module.
- Not run on the target core (no QEMU/Renode), as in module 23.

## 6. Results (implementation commit)

RTL: cocotb on Verilator (`tests/24-spectrum-scan`, 2 simulations, 4 tests). Firmware: host build, Python harness `test_cs.py` (11 tests), both started by `run_tests.sh`. All pass.

| Test | Result |
|---|---|
| T24-01 | `scan_meas`: 30 dwells (settle 0 to 200, dwell 1 to 2000 strobes, strobe duty 100%, 50% and 20%, random and extreme samples) equal the exact energy sum (also against numpy), the integer logarithm, `done` after exactly `settle + dwell` strobes; 27 starts while busy ignored and counted; `lg` within 0.0861 + 1/16 octave of `log2(sum)`; no saturation for 2000 samples of -32768 |
| T24-02 to T24-04 | `scan_engine`: 5 runs (6 to 32 channels, random masks and home channel, settle 0 to 30, dwell up to 120, strobe duty 100%, 50%, 25%): the pointer visits enabled channels in order skipping `home`, wraps and counts sweeps; `retune_req` and `retune_ch` as specified and every slot ends with the retune back to `home`; the table (`last`, `lg_last`, `max_hold`, `count`, `strong`) equals the exact sum of the strobes of the window; a slot spans `settle + dwell` strobes (at most 6 more in the pipeline); an empty mask gives `no_ch`; a missing `rx_ready` aborts the slot after the timeout with `err_tmo` and the retune back |
| T24-05 | 300 random spectra with disabled, unscanned, stale, strong-adjacent and remembered-bad channels: every score equals the independent formula of section 2 |
| T24-06 | No switch in 5 minutes with 2 dB scan noise and two equal best channels when nothing is degraded; after a real degradation exactly one switch and none in the next 2 minutes |
| T24-07 | 500 trials each: decision latency after a step of the loss to 20% at most 13 ms; to 80% (severe) at most 11 ms (ADA-002: 20 ms; `det_ms` 10, 1 ms ticks, scan noise 2 lg) |
| T24-08 | 100 trials, a 20 dB interferer on the current channel: one switch to a clean channel within 25 ms of its appearance, never to a busy channel |
| T24-09 | The chosen channel turns bad 5 ms after arrival: blacklisted, next best taken 16 ms later (reason probation), no further switch |
| T24-10 | No scan data and a dead link: the fallback list is walked in order (9, 2, 6); a blacklisted entry is skipped |
| T24-11 | 4 links, 12 channels, all starting on channel 0, a jammer moving every 5 s, 60 s: 2 to 4 switches per link, no second with a shared channel (0 of 60 s), no switch within the minimum stay unless severe |
| T24-13 (added) | Interference alternating between two channels every 100 ms: 2 switches in 20 s, shortest gap 501 ms |
| T24-14 (added) | Loss of 6% on the current channel: candidates 48 lg above its level are not taken, candidates 20 lg above are |
| T24-12 | Strict build clean (`-Wall -Wextra -Wconversion -Wshadow -Werror -mgeneral-regs-only`), no undefined symbols, 3237 bytes of code, no data or bss; about 1.2 million random calls in 3 configurations under UBSan and ASan, target channel always in range |
| L-24, S-24 | `-Wall` clean; `scan_meas` 3875 cells (85 flip-flops), `scan_engine` 18818 cells (4214 flip-flops: the 32-entry table is flip-flops), no latches |
| Mutation | `scan_meas` dwell off by one: T24-01 fails; minimum-stay check removed: T24-13 fails; margin check removed: T24-14 fails (the first two firmware mutations passed all tests until T24-13 and T24-14 were added); all restored |

### Defects found and fixed during the tests

1. The scan pointer started after channel 0, so channel 0 was skipped in the first sweep.
2. The first probation fallback walked back to the previous channel, which was the dead one; the order is now best scanned candidate, fallback list, previous channel (last resort).
3. A current channel with no own-level measurement was given a score of 0 (always best), so the link never left it; its score is now taken as just short of the best candidate's.

### Limits

- The interference-to-loss model of the tests (loss doubles per 0.75 dB above a 3 dB excess) and the level constants are assumptions [E]; the penalties and thresholds in `cs_default_cfg` are untuned starting values.
- The current channel's own interference level comes from an idle-slot measurement that the engine does not schedule (it excludes `home`); the firmware accepts it through `cs_scan` for the current channel, and without it only the loss triggers a switch.
- The radio timing (retune, settle, return) is the sequencer's; the engine was tested with a model of `rx_ready`, not against module 11 and 10 together.
- Not run on a target core (no QEMU/Renode); no cycle count. Execution of the switch (MAC-010, gap of one frame or less) and the control message that carries `effective_frame` are not modelled.
- Four links on twelve channels is one scenario; denser reuse (SYS-009: 6 links on 20 MHz channels in 5.8 GHz, 25 on 5 MHz) was not simulated.
