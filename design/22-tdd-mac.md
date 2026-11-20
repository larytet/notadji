# 22 - TDD MAC Engine

Plan entry: module 22 of `spec/18-development-plan.md`, class L, data plane with real-time core. Requirements: MAC-001 (in-band TDD frame, 1, 2 or 4 ms, guard from the propagation delay), MAC-002 (all airtime scheduled, no contention), MAC-003 (air and ground aligned within 1 us), MAC-004 (per-slice ACK bitmap in the uplink), MAC-006 (selective retransmission only when the deadline can still be met), MAC-011 (timing advance from the round-trip delay, 0.1 us resolution, range as a by-product), VID-021 (a slice lost and too late for retransmission is reported for an intra refresh). SIM-021 of `17`. Depends on 2 (timestamp), 9 (slice sequence numbers), 10 (sequencer events) and 21 (arrival-time measurement of the uplink burst).

Scope: the **hardware part** of the MAC: frame timing, slot windows, timing-advance loop, schedule computation, acknowledgement window and retransmission decision. The split-band mode (MAC-012) uses the same acknowledgement and retransmission blocks with a different timer configuration (no uplink slot in the video band: `ul_ticks` = 0). Pairing, MCS selection (module 23) and the radio hop sequence (module 10) are not part of this module.

## 1. Units and timing model

One tick is one data-plane clock, 5 ns at 200 MHz (HSI-003); `TPU` = ticks per microsecond = 200 (a parameter, so that tests can scale time down). Both units run free on their own clock; the air unit (AU) owns the frame, the ground unit (GU) follows it.

With one-way propagation delay `d` (3.336 us per km) and round-trip delay `R = 2d`:

- AU time `0` is the frame start; the AU transmits the downlink (DL) during `[0, DL)`.
- The GU detects the DL preamble `d` later; it sets its local counter to `sync_pos` (the detection latency in ticks, constant) at that moment, so its local counter equals AU time minus `d`.
- The AU wants the uplink (UL) burst to arrive at AU time `U = DL + G` (`G` the DL to UL guard). The GU transmits at local time `U - TA` with `TA = R`: the burst takes `d` to arrive, the GU clock lags by `d`, so it arrives at `U - R + d + d = U`.
- The guard: `G = R + 2 x turn` (`turn` = 10 us, MAC-001): the GU must switch receive to transmit after the DL ends (GU local `DL`) and before `U - TA`, so the GU's gap between the end of the DL and its transmit start is `U - TA - DL = G - R = 2 x turn`: one `turn` for its receive-to-transmit switch, and one for the AU's transmit-to-receive switch (the AU stops transmitting at `DL` and listens from `U`).
- **Finding (gap in MAC-001 / `02` section 4):** the table of `02` counts the guard once and has no uplink-to-downlink turn-around at the AU (the AU's UL window ends at the frame end `F`, and it must be transmitting again at `F`). This design reserves `turn` at the end of the frame: `DL = F - UL - G - turn`. The downlink share drops by 10 us per frame (1.0% at 1 ms, 0.25% at 4 ms); the figures in `02` should be restated by about that much.

## 2. Blocks

### 2.1 `mac_frame_timer`

One instance per unit. `role` 0 = AU (master), 1 = GU (follower).

| Port | Dir | Description |
|---|---|---|
| `clk`, `rst_n` | in | |
| `role` | in | 0 AU, 1 GU |
| `frame_ticks[23:0]` | in | Frame length `F` |
| `dl_ticks[23:0]` | in | Downlink length `DL` |
| `ul_start[23:0]` | in | `U` in AU time (`DL + G`) |
| `ul_ticks[23:0]` | in | UL burst window length (0 disables the slot) |
| `turn_ticks[15:0]` | in | Turn-around time, for the configuration check |
| `ta_ticks[23:0]` | in | Timing advance (GU only; AU ignores it) |
| `sync_pos[23:0]` | in | Counter value at a preamble detection when aligned (GU) |
| `miss_limit[3:0]` | in | Frames without synchronisation before `link_lost` |
| `sync_valid` | in | Preamble detected (pulse, GU) |
| `frame_start` | out | Pulse in the clock the counter wraps to 0 |
| `frame_no[15:0]` | out | Frame counter (wraps) |
| `cnt[23:0]` | out | Position in the frame |
| `tx_en`, `rx_en` | out | Radio windows of this unit |
| `ul_win` | out | Window where this unit's UL burst is (AU receives, GU transmits) |
| `sync_err[23:0]` | out | Signed counter slip at the last synchronisation (ticks) |
| `link_lost` | out | `miss_limit` frames without a synchronisation (GU; AU always 0) |
| `cfg_err` | out | The slot plan is inconsistent (see below) |

Behaviour. The counter runs `0 .. F-1` and `frame_no` counts wraps. AU: `tx_en` = `cnt < DL`; `rx_en` = `ul_win` = `U <= cnt < U + UL`. GU: `rx_en` = `cnt < DL`; `tx_en` = `ul_win` = `U - TA <= cnt < U - TA + UL`. On `sync_valid` (GU) `sync_err = cnt - sync_pos` (signed, taken modulo `F` into `[-F/2, F/2)`) and `cnt` is loaded with `sync_pos + 1`; the missed-frame counter clears. At every wrap the counter increments; `link_lost` rises when it reaches `miss_limit`. `cfg_err` (registered, checked every frame start) is set when any of these hold: `DL + turn > U - TA` for the GU (no time to switch to transmit), `U + UL + turn > F` for the AU (no time to switch to transmit before the next frame), `U < DL + turn` for the AU, `TA > U`, `F = 0`.

### 2.2 `mac_sched`

Registered computation of the slot plan from the round-trip delay.

| Port | Description |
|---|---|
| `rtt_ticks[23:0]`, `update` | Measured round-trip delay; a pulse latches a new plan (the caller pulses at a frame start) |
| `turn_ticks[15:0]` | `turn` |
| `frame_ticks`, `dl_ticks`, `ul_start`, `ul_ticks`, `guard_ticks`, `cls[1:0]` | The plan; `cls` 0, 1, 2 for 1, 2, 4 ms |

Class by `R`: up to 7 km (`R` <= 46.7 us) class 0, up to 15 km (`R` <= 100.1 us) class 1, beyond class 2, with hysteresis of 2 us (a class changes only when `R` is more than 2 us beyond the threshold). Frame `F` = 1000, 2000, 4000 us; `UL` = 95, 150, 272 us (7, 11, 20 symbols of the table in `02`); `G = R + 2 turn`; `U = F - UL - turn`; `DL = U - G`. (`DL = F - UL - G - turn`, section 1.) The `TPU` parameter scales the constants.

### 2.3 `ta_ctrl`

Closed-loop timing advance in the GU. The AU measures, from its UL preamble detection (module 18 with the timestamp unit), how late the burst arrived relative to `U` and returns the signed error `e` in the DL header. The GU applies `TA <- clamp(TA + e)`, quantised to `RES` ticks (0.1 us = 20 ticks, MAC-011) by rounding to nearest; the full error is applied at once (the measurement is exact to a tick, the only noise source is the detector, which module 18 bounds to a few samples). `meas_valid`, `meas_err[23:0]` in; `ta_ticks[23:0]` out; `range_dm[19:0]` out = `TA x 1499 / TPU` decimetres (7.495 dm per tick at 200 ticks per microsecond; the fixed-point factor `1499 x 1024 / TPU` is exact to 0.01%); parameter `TPU` as in `mac_sched`; `ta_max` is a clamp (default `200 x TPU` ticks, the round-trip delay at 30 km). `ta_set_valid`/`ta_set[23:0]` presets `TA` (software, or a coarse acquisition value).

### 2.4 `ack_window`

Receiver side of the acknowledgement: tracks which of the last 64 slices were received intact. `ev_valid`, `ev_seq[15:0]`, `ev_ok` (a slice with a valid header; `ev_ok` = CRC ok and tag ok, from modules 9 and 15). The window is `[hi - 63, hi]` where `hi` is the highest sequence number seen (sequence compare modulo 65536 with a signed difference); a new `hi` shifts the window, and the new bits not set by an event are 0 (lost or not yet arrived). Events older than the window are ignored (counted in `late_cnt`). `fb_req` pulse: `fb_valid`, `fb_hi[15:0]`, `fb_bits[63:0]` snapshot (bit `i` = slice `hi - 63 + i` received), for the uplink feedback message (MAC-004).

### 2.5 `retx_ctrl`

Transmitter side. A 64-entry table indexed by `seq mod 64` holds the slices that may need retransmission: `{valid, seq, deadline[31:0], retx_count}`.

- `sent_valid`, `sent_seq`, `sent_deadline[31:0]` (display deadline in ticks of `ts_now[31:0]`) register a slice (a retransmission of the same sequence number keeps its entry).
- `fb_valid`, `fb_hi[15:0]`, `fb_bits[63:0]` (from the GU, via module 8/10) start a sweep over the 64 window positions, one per clock. For each position with a table entry of matching `seq`: bit 1 frees the entry (acknowledged). Bit 0 and `seq <= fb_hi - holdoff` (slices newer than `holdoff` may still be in flight; default 2) is **lost**: if `retx_count < max_retx` and `now + tx_ticks + owd_ticks <= deadline` (`now` = `ts_now[31:0]`, signed difference; `tx_ticks`, `owd_ticks` configuration: estimated airtime of a slice and one-way delay) the sequence number goes to the retransmission queue and `retx_count` increments; otherwise the entry is freed and the sequence number goes to the refresh queue (VID-021, `drop_cnt` increments). An entry with `seq < fb_hi - 63` (older than the window, no information) is freed and counted in `stale_cnt`.
- Outputs: `rtx_valid`, `rtx_ready`, `rtx_seq[15:0]` (queue depth 16; overflow drops the oldest into the refresh path) and `rf_valid`, `rf_ready`, `rf_seq[15:0]` (depth 16).
- A sweep needs 64 clocks; `fb_valid` while busy is held off with `fb_ready` low.

## 3. Test plan

Python models of every block; a cocotb harness per block, plus a two-unit system test with a delay line.

| ID | Test | Pass criterion |
|---|---|---|
| T22-01 | AU timer windows | For `F` = 1000, 2000, 4000 us (scaled `TPU` = 10): `tx_en`, `rx_en`, `ul_win` and `frame_start` equal the model clock by clock over three frames; `frame_no` counts |
| T22-02 | GU timer windows with timing advance | The GU windows move with `TA` exactly; a changed `TA` takes effect at the next frame start |
| T22-03 | Synchronisation | `sync_valid` at the aligned position: `sync_err` 0; at +/-50 ticks: error reported, counter reloaded; missing syncs: `link_lost` after `miss_limit` frames and clears on the next; jitter of the event inside a frame never creates a second `frame_start` |
| T22-04 | Configuration check | The inconsistent plans listed in section 2.1 each raise `cfg_err`; the plans from `mac_sched` for 0 to 30 km never do |
| T22-05 | Schedule | At `TPU` = 200 for 5, 7, 10, 15 and 30 km: frame, `UL`, `G`, `U`, `DL` equal the formulae and the table of `02` (guard 53, 67, 87, 120, 220 us) to a tick; class changes with hysteresis (sweep range up and down: no change inside the 2 us band) |
| T22-06 | Timing-advance loop | `TA` starts at 0 (or a wrong preset): after one measurement `TA` is within `RES/2` of the true round-trip delay for round-trip delays 0 to 200 us; clamp at `ta_max`; `range_dm` within 1% of the true range above 100 m |
| T22-07 | ACK window | Random arrival order with loss, duplicates, reordering inside and outside the window and sequence wrap: `fb_hi` and `fb_bits` equal the model at random snapshot times; `late_cnt` right |
| T22-08 | Retransmission | Random sent, feedback and clock streams: the retransmission and refresh sequences equal the model exactly (deadline rule, `holdoff`, `max_retx`, stale entries, queue overflow); no sequence number appears in both queues for the same feedback |
| T22-09 | Two-unit system | An AU and a GU timer with a delay line of `d` = 0, 16.7, 50, 100 us (up to 100 us one way, 30 km; `TPU` = 10), the GU synchronising on every AU frame start through the line and `ta_ctrl` closed with the AU's measured arrival error: after the first correction the UL burst arrives inside the AU receive window with offset 0 +/- `RES/2` (MAC-003: within 1 us); at no clock do the AU's `tx_en` and `rx_en` overlap, the GU's `tx_en` and `rx_en` overlap, or the arriving UL window overlap the AU's DL transmit (including the turn-around gap `turn`); `cfg_err` never rises; the same with `d` stepping from 16.7 to 50 us (aircraft moving): re-converged within 2 frames |
| T22-10 | End to end acknowledgement | A transmitter stream with random slice loss (5%) feeds `ack_window` through a model channel; the feedback goes to `retx_ctrl`: every lost slice with enough time left appears in the retransmission queue exactly once per feedback, others in the refresh queue; sequence numbers wrap |
| L-22, S-22 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 4. Deliverables

`rtl/22-tdd-mac/{mac_frame_timer,mac_sched,ta_ctrl,ack_window,retx_ctrl}.sv`, `tests/22-tdd-mac/` (models, harnesses, system test), results below, row in `design/README.md`.

## 5. Open items

- Initial acquisition (the GU has no `TA` and no sync): a wide UL window and a coarse preset from the round-trip delay of the first exchange; here only the preset input exists.
- The AU measures the UL arrival error with the synchroniser (module 18) and reports it in the DL header; the header format and the uplink feedback message layout (CSI summary, MCS recommendation, RSSI, ACK bitmap, `fb_hi`) belong to the control-protocol definition (modules 23 and 8).
- Split-band mode and hop timing (MAC-010, MAC-012), gaze field (MAC-013), 1 kHz RC channel (MAC-008).
- Clock-rate difference between the two units (frequency offset of the sample clocks): the GU re-synchronises every frame, so only drift within one frame matters (20 ppm of 4 ms is 0.08 us); not simulated.

## 6. Results (implementation commit)

Simulation: `tests/22-tdd-mac` (Verilator, cocotb), 9 simulations (the scaled-time ones use `TPU` = 10, `RES` = 1), every test passes. The block tests compare with clock-accurate Python models (`mac_model.py`); T22-09 and T22-10 use independent checks on the physics and on the outcome.

| Test | Result |
|---|---|
| T22-01 to T22-04 | `mac_frame_timer` equals the model clock by clock (counter, `frame_start`, `frame_no`, `tx_en`, `rx_en`, `ul_win`, `sync_err`, `link_lost`, `cfg_err`) in 12 random runs of 3000 clocks (both roles, consistent and random plans, random synchronisation events); directed edge positions for 1 and 2 ms frames, with and without timing advance, match the formulae |
| T22-05 | `mac_sched` at 200 ticks per microsecond: 5, 7, 10, 15, 30 km give frames 1, 1, 2, 2, 4 ms, UL 95, 95, 150, 150, 272 us, guard 53.4, 66.7, 86.7, 120.1, 220.2 us (the table of `02`: 53, 67, 87, 120, 220); downlink share 0.842, 0.828, 0.877, 0.860, 0.874 (the table: 0.852, 0.838, 0.882, 0.865, 0.877: lower by the reserved turn-around, section 1); 400 random range steps equal the model; the hysteresis sequence 46, 47, 48, 49, 48, 47, 46, 45, 44, 47, 49 us gives classes 0 0 0 1 1 1 1 1 0 0 1 |
| T22-06 | `ta_ctrl`: 600 random measurements and presets equal the model at both tick rates; after one correction the residual is at most `RES/2` (10 ticks = 0.05 us at 200 ticks per microsecond); range within 1% above 100 m; clamp at `ta_max` |
| T22-07 | `ack_window`: 3 x 6000 clocks (sequence bases 0, 65400, 30000: wrap) with reordering up to 90 positions back, loss, duplicates equal the model |
| T22-08 | `retx_ctrl`: 4 runs of 9000 clocks equal the clock-accurate model (retransmission and refresh sequences, counters, `busy`); runs 3 and 4 starve both queues' consumers to exercise queue-full behaviour |
| T22-09 | Two timers with a delay line (`TPU` = 10): one-way delay 0, 16.7, 50 and 100 us (frames 1, 1, 2, 4 ms): the first burst arrives late by exactly the round trip (TA = 0), after the first correction every burst arrives with 0 ticks (0.0 us) error; no clock with AU transmit and receive both on, GU transmit and receive both on, an arriving burst overlapping the AU downlink, or `cfg_err`; TA equals the round trip, range 0, 5.0, 15.0 and 30.0 km. With the delay growing 0.1 us per frame for 12 frames the burst is late by at most 2 ticks (0.2 us, the growth) and no violation occurs |
| T22-10 | `ack_window` + `retx_ctrl` over a lossy channel (500 slices, sequence wrap, 30 tick one-way delay, deadline 600 ticks, `max_retx` 2): at 5% loss all 500 delivered, 22 retransmitted; at 20% loss 495 delivered, 88 retransmitted, 18 sent to refresh, the 5 never delivered are all in the refresh list; no slice retransmitted more than twice or without time left; 13 slices were refreshed although a late copy arrived (the retransmission was in flight when the deadline passed) |
| L-22 | `-Wall` clean for all five blocks |
| S-22 | Yosys generic: `mac_frame_timer` 2501 cells, `mac_sched` 508, `ta_ctrl` 1976 (the divide by `RES`), `ack_window` 1314 (178 flip-flops), `retx_ctrl` 20969 (6145 flip-flops: the 64-entry table is flip-flops; a block-RAM version needs a registered read), no latches |
| Mutation | `retx_ctrl` lost condition `age <= 0` changed to `< 0`: T22-08 fails; GU window start shifted by one tick: T22-01 to T22-04 fail; both restored |

### Defects found and fixed during the tests

1. **Tail loss was invisible.** The window feedback only reports up to the highest slice the receiver has seen; a lost slice newer than every received slice is "in flight" for ever (500 slices, 1 never resolved at 20% loss). `retx_ctrl` now has `tmo_ticks`: an entry unacknowledged for that long counts as lost (the sent time is stored and restarted on a retransmission).
2. **A sent slice and the sweep touching the same table entry in one clock:** the sweep's free could remove the newly written entry; the write now has priority and the counters are combined.
3. **Timing advance and plan must change together.** Applying a new `TA` while the old plan is active gives `cfg_err` (the GU has no time to switch to transmit: `U - TA < DL + turn`) until the plan is recomputed. The test applies the correction and the new `rtt_ticks` in the same clock at the frame start; a real unit needs one control message that carries both with an effective frame number (open item).
4. Range output depended on the 200 MHz tick; now parameterised by `TPU`.

### Limits

- A sudden change of the round trip by 20 us in one frame (not physical: it is 3 km in one millisecond) makes the first burst after the step overrun its slot into the next downlink; the loop recovers one frame later. Real drift at 300 km/h is 0.3 ns per frame.
- The AU's arrival-time measurement is taken by the testbench from the exact clock; in hardware it comes from the synchroniser of module 18 (marker spread of a few samples at 10 dB and above), so `RES` and the 1 us margin of MAC-003 are consistent only above that SNR.
- The acknowledgement window is 64 slices; a frame with more slices than that between two feedbacks loses the oldest bits (they are counted as stale by the transmitter).
- Verified only in simulation with ideal clocks; clock offset between the units (20 ppm) is not modelled.
