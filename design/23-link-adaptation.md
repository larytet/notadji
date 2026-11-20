# 23 - Link-Adaptation Controller

Plan entry: module 23 of `spec/18-development-plan.md`, class L, real-time core firmware. Requirements: MAC-005 (MCS, power and slice budget change within 2 ms of the feedback), PHY-012 (at least 4 MCS adaptation steps per second, up to one per frame), MAC-004 (the feedback content), SYS-004 (quality ladder follows the MCS), VID-006 (per-slice bit budget retargeted from the MCS in force, never above 105%), HSI-011 (a stalled controller leads to the safe schedule: lowest MCS, reduced power), PHY-011 (1e-3 slice error target). SIM-030 of `17`. Depends on module 22 (feedback and ACK bitmap arrive through the MAC).

Scope: **firmware** for the real-time core of the air unit, written as portable C99 with no operating system, no heap, no floating point and no library calls, so that it builds for the target core (Cortex-R class, to be chosen in T-18) unchanged. Verification here is on the host: the controller is compiled as a shared library and driven by a Python channel model. SIM-030 asks for QEMU or Renode with RTL co-simulation; neither is installed (`17` section 1) and no target toolchain is available, so execution on the target core, cycle counts and the 2 ms bound measured on silicon are **not** covered; the worst-case path length is bounded by construction and reported.

## 1. Inputs, outputs and state

Feedback message (one per uplink slot, at most every 1 ms, at least every 4 ms in in-band mode):

| Field | Meaning |
|---|---|
| `t_us` | Time of arrival, microseconds (32-bit, wraps) |
| `snr_x10` | Receiver SNR estimate in 0.1 dB (from the LTF/pilots, `csi` of module 17), signed 16-bit |
| `n_slices`, `n_lost` | Slices accounted in this message and those reported lost in the ACK bitmap (module 22) after the retransmission rule (refresh list), each 8-bit |
| `mcs_rec` | The ground unit's recommendation (255: none); used as an upper bound only |

Configuration (`la_cfg`): MCS table (index, bits per symbol times code rate in 1/256 units, required SNR for the slice-error target in 0.1 dB, ladder rung), `mcs_min`, `mcs_max` (from region/mode), `per_target_ppm` (default 1000, PHY-011), `up_hys_x10` (0.5 dB), `up_dwell_us` (minimum time between two upward steps; default one frame), `down_dwell_us` (0), `olla_step_x100` (outer-loop step), power limits `pwr_min_x4`, `pwr_max_x4` (in 0.25 dB steps), `pwr_margin_x10`, `pwr_headroom_x10`, `fb_timeout_us` (default 10 ms), slice budget parameters (`dl_sym_per_frame`, `data_tones`, `slices_per_frame`, `video_share_x256`).

Outputs (`la_out`, returned by `la_on_feedback` and `la_tick`; the caller writes them into the next frame's event table of module 10 and the encoder rate hook):

| Field | Meaning |
|---|---|
| `mcs` | MCS index for the next frame |
| `pwr_x4` | Transmit power setting in 0.25 dB units |
| `slice_budget` | Payload bytes per slice for the encoder (VID-006) |
| `rung` | Quality ladder rung 0, 1, 2 (SYS-004), with 2 dB hysteresis |
| `outage` | The effective SNR is below the lowest MCS threshold for `outage_us` (starts the link-loss procedure) |
| `safe` | Feedback timeout: safe schedule in force |
| `changed` | Any of `mcs`, `pwr_x4`, `slice_budget` differs from the previous output |

State: filtered SNR (fast attack, slow release), the outer-loop offset, the last step time, counters.

## 2. Algorithm

1. **SNR filter** (all integer): `snr_f` follows the measurement at once when it falls (a drop of more than 1 dB takes effect in the same message), and rises with a weight of 1/4 per message (a fade is real, a spike is noise).
2. **Outer loop** (OLLA): `snr_eff = snr_f - offset`. For every slice of the message: a lost slice adds `olla_step` to `offset`; an acknowledged slice subtracts `olla_step x per_target / (1 - per_target)`. At equilibrium the slice-loss rate equals `per_target` whatever the bias of the SNR estimate; `offset` is limited to +/-10 dB.
3. **MCS choice**: the highest `m <= mcs_max` (and `<= mcs_rec` if given) with `thr[m] <= snr_eff` for a step down, and `thr[m] + up_hys <= snr_eff` for a step up. Down steps may jump several indices at once and are immediate; up steps are one index at a time and at least `up_dwell` apart. The scan is over at most 16 table entries.
4. **Power loop**: below `mcs_max` and below `pwr_max`: raise power by 1 dB (4 units) per message while the next MCS is within `pwr_margin` of reachable (power rises SNR one for one); at `mcs_max` with `snr_eff` more than `thr + pwr_headroom` above the threshold: lower power by 1 dB per message down to `pwr_min`. A power change adds its dB to the filtered SNR and the filter is re-based, so the loop does not chase its own change.
5. **Slice budget**: `slice_budget = dl_sym_per_frame x data_tones x rate(mcs) x video_share / slices_per_frame / 8` bytes (integer, rounded down); the encoder is bound to 105% of this (VID-006), checked there, not here.
6. **Rung**: the highest rung whose MCS threshold set is held (ladder from the MCS table), with 2 dB of hysteresis on the way up.
7. **Outage**: `snr_eff` below `thr[0] - 1 dB` for `outage_us` (default 20 ms).
8. **Timeout** (`la_tick`, called at least every 1 ms): no feedback for `fb_timeout_us`: lowest MCS, `pwr_max`, `safe` = 1, until a feedback arrives (the next message restarts from the lowest MCS and climbs by the dwell rules). A message with `n_slices` = 0 counts as feedback.

Each call runs in bounded time: no loop other than the table scan (at most 16 entries) and the per-message slice accounting, which is done in closed form (`n_lost` and `n_slices - n_lost` multiplied, not iterated).

### 2.1 Changes made while testing (the algorithm as implemented)

- Added configuration `down_hys_x10` (0.3 dB: a step down needs `thr[cur] > snr_eff + down_hys`), `olla_neg_limit_udb` (the offset may not go below -4 dB), `probe_window_us` (200 ms) and `probe_max_us` (8 s).
- **Explained losses are not evidence of bias.** When a message reports losses and the measurement is more than 0.5 dB below the filtered SNR (or the fall exceeds 6 dB), the filter follows the measurement at once and that message's losses are not added to the outer-loop offset; an abrupt fall also clears a negative (optimistic) offset. Without this, a fade filled the offset with +10 dB penalties that took seconds to unwind (goodput 190 against 840 for the best fixed MCS on a Rayleigh trace).
- **Two kinds of step up.** A step justified by the measurement alone (`snr_f` minus any positive offset reaches `thr[next] + up_hys`) is taken after `up_dwell` (one frame). A step that only the outer loop's negative offset allows is a **probe**: at most one per `probe_window`, and after a failed probe (a step down within the window with no fall of the filtered SNR) the wait before the next probe is multiplied by 4 up to `probe_max` (halved after every successful probe). Without this the controller probed the next MCS every second on a static channel at 3 dB (the limit cycle of every outer loop).

## 3. Interface (C)

```
void la_init(la_state *s, const la_cfg *c, uint32_t t_us);
void la_on_feedback(la_state *s, const la_cfg *c, const la_fb *fb, la_out *o);
void la_tick(la_state *s, const la_cfg *c, uint32_t t_us, la_out *o);
uint32_t la_slice_budget(const la_cfg *c, uint8_t mcs);
```

Header `fw/23-link-adaptation/link_adapt.h`, source `link_adapt.c`. Types are fixed width; no global state.

## 4. Test plan

A Python harness (`ctypes`) loads the compiled library; the channel model (SNR process, SNR measurement error, slice losses from a steep waterfall `p = min(1, 1e-3 x 10^(2 (thr - snr)))`, one decade per 0.5 dB [E]) is independent of the controller.

| ID | Test | Pass criterion |
|---|---|---|
| T23-01 | Table and budget | The MCS table is monotonic in rate and threshold; `la_slice_budget` equals an independent Python computation for every MCS and several configurations; the rung map is monotonic |
| T23-02 | Static channel | Constant SNR at 40 values from 0 to 30 dB: the MCS is the highest whose threshold (plus the hysteresis for the climb) is met, and stays there (no switches after the climb) |
| T23-03 | Step down | A sudden drop of 15 dB: the MCS is at the right index in the same feedback (no later than the first message after the drop), i.e. within the 2 ms of MAC-005 when the feedback period is at most 1 ms |
| T23-04 | Climb and rate | A sudden rise: the MCS rises one index per `up_dwell` (one frame); at least 4 steps per second are possible and never more than one per frame |
| T23-05 | Noisy measurement | SNR measurement error sigma 1.5 dB on a constant channel: at most 1 MCS switch per second after convergence, against several per second for a controller without the filter and hysteresis (comparison run in the test) |
| T23-06 | Outer loop | The SNR estimate biased by +3 dB and -3 dB: the slice-loss rate over 200 000 slices converges to within a factor 2 of the target (`per_target` raised to 1e-2 for the test so that the statistics are reachable) and the offset ends near the bias |
| T23-07 | Power loop | At `mcs_max` with large headroom: power steps down 1 dB per message to the limit that keeps the headroom; with the SNR falling below the headroom it rises again; below `mcs_max` and below the limit: power rises; limits respected; the SNR re-base prevents oscillation (no more than 2 direction changes over a constant channel) |
| T23-08 | Timeout and safe mode | No feedback for 10 ms: lowest MCS and maximum power, `safe` = 1 at the first `la_tick` after the timeout; first message after: normal operation resumes from the lowest MCS |
| T23-09 | Outage | SNR below the lowest threshold for more than 20 ms: `outage` = 1 and cleared when the SNR recovers |
| T23-10 | Fade trace | A recorded-style fading trace (Rayleigh-like fade, 100 Hz Doppler, 30 s): slice loss rate against `per_target`, mean rate against the best fixed MCS, number of MCS changes per second; reported |
| T23-11 | Portability | Builds with `-std=c99 -Wall -Wextra -Wconversion -Werror` and `-mgeneral-regs-only` (no floating-point instructions); the object has no undefined symbols (no library calls, no heap); `size` reports the code and data size |
| T23-12 | Determinism | The same input sequence gives the same outputs on two runs; no uninitialised state (built with `-fsanitize=undefined,address` for the run of T23-02 to T23-09) |

## 5. Deliverables

`fw/23-link-adaptation/{link_adapt.h,link_adapt.c}`, `tests/23-link-adaptation/` (Python harness, channel model, build script, `run_tests.sh`), results below, row in `design/README.md`.

## 6. Open items

- The MCS thresholds in the default table are estimates [E] (`02`, `scripts/link_budget.py` for the three lowest; the others by the usual gap-to-capacity pattern). They are to be replaced by the SNRs at slice error 1e-3 from the full-chain simulation (module 21 with the throughput fixes) and AFF3CT (SIM-002).
- Execution on the target core, cycle counts and the 2 ms bound on silicon (SIM-030 with QEMU or Renode; not available here).
- Joint adaptation of the uplink MCS (MAC-007) and of the video-band/control band in split-band mode (MAC-012); multi-link and hop decisions belong to module 24.

## 7. Results (implementation commit)

Host build (gcc, x86-64), Python harness `tests/23-link-adaptation/test_la.py` (`run_tests.sh`), 12 tests, all pass. The channel model is independent of the controller (steep waterfall: 1e-3 at the threshold, one decade per 0.5 dB [E]).

| Test | Result |
|---|---|
| T23-01 | Table monotonic in threshold, rate and rung; `la_slice_budget` within 2 bytes of the exact rational value for 10 MCS in 4 configurations |
| T23-02 | 21 static SNRs from 0 to 30 dB, 20 s each: the MCS is the ideal one 97% of the time on average (at least 75% at every SNR), never more than one above and at most two below it (a failed probe), at most 8 switches in 10 s, slice loss at most 1% for SNR at or above the lowest threshold |
| T23-03 | Drops from 28 dB to 2, 8, 13 and 19 dB: the MCS in the **first** feedback message after the drop is the right one for the new SNR (and stays at it or one above); with feedback every 1 ms this is inside the 2 ms of MAC-005 (the decision is made in the call that handles the message; transmission on the next frame start adds the frame time, not modelled here) |
| T23-04 | A rise from 5 to 28 dB: 8 steps up within the first second (at least 4 per second), never more than one index per step, never two steps closer than one frame; ends at MCS 9 |
| T23-05 | Measurement noise sigma 1.5 dB: 10 switches in 20 s (0.5 per second); a controller without filter and hysteresis would switch 411 times per second; slice loss 0.03% |
| T23-06 | SNR estimate biased by +3 dB (too high): without the outer loop every slice is lost, with it the loss rate settles at 1.0% = the 1% target set for this test (offset +1.9 to +2.1 dB); biased by -3 dB (too low): rate recovered from 768 to 1030 (at 18 dB) with 0.05% loss |
| T23-07 | Constant 38 dB: power falls 1 dB per 10 ms (11 dB in total, from setting 120 to 76 quarter-dB units) until the true SNR is 27.0 dB (the top threshold), one step at a time; after a 10 dB fall it rises again to the maximum; the floor is respected; one direction change on a constant channel |
| T23-08 | Safe schedule exactly 10 ms after the last message (lowest MCS, maximum power); the next message ends it and the climb restarts from the lowest MCS |
| T23-09 | Outage after 21 ms below the lowest threshold minus 1 dB; cleared 20 ms after the SNR returns (the rise filter) |
| T23-10 | 100 Hz Doppler, 22 dB mean, 30 s. **Rician K = 10 dB**: slice loss 2.4%, goodput 1129 against 1116 for the best fixed MCS (6) and 1241 for a per-millisecond genie, 71 MCS changes per second. **Rayleigh**: slice loss 5.8%, goodput 587 against 841 for the best fixed MCS and 1121 for the genie, 195 changes per second. The controller does not beat a well-chosen fixed MCS in deep Rayleigh fading with a 4 ms coherence time and 1 ms feedback; it does in the line-of-sight case that a drone link mostly has |
| T23-11 | `-std=c99 -Wall -Wextra -Wconversion -Wshadow -Werror -mgeneral-regs-only -ffreestanding`: clean; no undefined symbols; no floating-point instructions; 2620 bytes of code, no data, no bss (x86-64 -O2) |
| T23-12 | Two runs identical; 2 million random messages in 4 configurations (clock wrapping, random recommendations, extreme counts) under UBSan and ASan with output invariants: no violation |
| Mutation | Fast-fall path disabled: T23-03 fails; sign of the acknowledgement credit flipped: T23-02, 03, 04, 05 fail; both restored |

### Limits

- Not run on the target core: no QEMU, Renode or ARM toolchain here (SIM-030 not met). The 2 ms bound of MAC-005 is argued from the structure (bounded loops: at most 16 table entries; no division except one 64-bit division at initialisation), not measured in cycles.
- The MCS thresholds are estimates [E]; the slice-loss waterfall slope of the test channel is an assumption. Results hold for that model; the controller adapts to the real thresholds only through the outer loop (within +/-4 dB negative and +10 dB positive).
- Rayleigh-fading behaviour is poor (see T23-10); for pedestrian-speed ground units with strong fading a longer filter and fixed-MCS fallback should be configurable. The Doppler of the real drone link (PHY-007, 3.5 kHz) is far above the feedback rate: the controller then works on the average SNR, which the tests do not cover.
- Slice losses are an input (`n_lost`); where they come from (module 22's refresh list) and the exact meaning of `snr_x10` (a CSI summary) are fixed by the control-protocol definition.
