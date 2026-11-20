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
