# 27 - Display Synchronisation and Scan-Out

Plan entry: module 27 of `spec/18-development-plan.md`, class XL, ground-unit data plane. Requirements: VID-015 (fixed line-synchronised scan-out: the display starts scanning a frame before it is completely decoded), VID-018 (the display scan-out is locked to the received frame timing, pixel clock steered by at least +/-50 ppm with 0.1 ppm resolution; latency varies by no more than 1 ms over a 10 minute flight; no visible glitch), SIM-030 of `17` (partial: needs hardware). Depends on 2 (timestamp counter) and 9 (slice numbering and arrival).

What can and cannot be simulated: the pixel clock itself (a steerable oscillator or PLL), the HDMI, DisplayPort and MIPI DSI transmitters and the display are hard blocks (`17` section 2). This module designs and tests everything **around** them: the video timing generator, the phase measurement, the steering controller (its output is the control word of the oscillator, in units of 0.1 ppm), and the per-line freshness logic that makes an early scan-out possible. The oscillator and the display are modelled in the tests; the result is a verified controller and timing logic, not a verified display chain.

## 1. Blocks

### 1.1 `scan_timing` (pixel clock domain)

Programmable video timing generator. Configuration: `h_active`, `h_fp`, `h_sync`, `h_bp`, `v_active`, `v_fp`, `v_sync`, `v_bp` (16 bits each), `hs_pol`, `vs_pol` (1 = active high), `slip[7:0]` signed (pixel clocks added to, or removed from, the end of the back porch of the first line of the vertical blanking in the next frame, so the sync pulse positions of that line do not move; limited so the back porch stays at least 1 pixel), `en`. Outputs: `hs`, `vs`, `de`, `x[15:0]`, `y[15:0]` (position inside the active area, valid with `de`), `line_start` (pulse at the first pixel of every line), `vs_start` (pulse at the first pixel of the vertical sync: the frame marker used for the phase measurement), `frame_cnt[15:0]`. The frame has `(h_active + h_fp + h_sync + h_bp) x (v_active + v_fp + v_sync + v_bp)` pixel clocks plus the slip. Order within a line: active, front porch, sync, back porch; within a frame: active lines, vertical front porch, sync, back porch (CEA-861 order from the first active pixel).

### 1.2 `phase_meas` (system clock, 200 MHz)

Measures the latency between the received frame timing event `rx_fs` (a pulse from the MAC, module 22, at the time the frame's first slice position is due, derived from the timestamp counter) and the display marker `disp_vs` (the `vs_start` pulse synchronised into the system clock domain by the caller). `period[23:0]` is the nominal frame period in clocks, `target[23:0]` the wanted latency in clocks. On each `disp_vs` it outputs `err` = `(clocks since rx_fs) - target`, wrapped into `[-period/2, period/2)`, with `err_valid`; `lost` is set when no `rx_fs` was seen for two periods (and cleared by the next one). A positive error means that the display runs late.

### 1.3 `pi_steer` (system clock, one update per frame)

Fixed-point proportional-integral controller. `err_valid`, `err[23:0]` in; `kp[15:0]` (Q16, units of 0.1 ppm per clock of error), `ki[15:0]` (Q24, 0.1 ppm per clock of error accumulated per update), `ppm_max[11:0]` (default 500 = 50 ppm), `slew_max[7:0]` (largest change of the output per update, 0.1 ppm units), `hold` (holdover: output and integrator frozen), `en`, `preset_valid` / `preset[15:0]` (loads the integrator, from the stored value of the last flight). Output `ctl[15:0]` signed in units of 0.1 ppm (positive: speed the display clock up), `ctl_valid`. `u = (err x kp >> 16) + (acc >> 24)`; `acc += err x ki` clamped so that `acc >> 24` stays within +/-`ppm_max` (anti-windup); the output is `u` limited to +/-`ppm_max` and then slew-limited against the previous output.

### 1.4 `line_sel` (memory clock)

Decides, per display line, whether the line of the current frame has been decoded in time. The decoder reports each completed slice as a range of lines (`wr_valid`, `wr_line[10:0]`, `wr_n[10:0]`); the current frame's lines are marked fresh in a bitmap of 2048 bits. A request (`rd_req`, `rd_line[10:0]`) returns on the next clock `use_cur` (1: read the line from the buffer being written, 0: read the previous frame's buffer, which is the concealment of a late line) and `buf_sel` (the frame buffer index to read from). `swap` (pulse at the display's frame start) toggles the buffer roles, clears the bitmap and latches `stale_cnt` (lines shown from the previous frame in the frame that just ended) and `cur_cnt`. Counters `late_wr_cnt` count slices that arrive after their lines were already scanned.

### 1.5 Start-time rule (firmware)

The scan-out of the frame starts `L` after the received frame timing. For a slice `k` that covers lines `a_k ..` and is decoded at time `T_k` after the frame timing, the line `a_k` is scanned at `L + a_k t_line`; the slice is on time if `T_k <= L + a_k t_line`. `L` is chosen as the smallest value that keeps the late-line fraction below a limit given the measured distribution of `T_k - a_k t_line` (a percentile, updated per frame, with a margin); `target` of `phase_meas` is `L`. The calculation is firmware and is evaluated in the test with a model of the decode times.

## 2. Test plan

| ID | Test | Pass criterion |
|---|---|---|
| T27-01 | `scan_timing` | For 1080p60 (2200 x 1125), 720p60 (1650 x 750), 1080p30 and a custom mode: every output equals the Python model clock by clock over 3 frames (`hs`, `vs`, `de`, `x`, `y`, `line_start`, `vs_start`, `frame_cnt`), both polarities; the frame length is exact; a `slip` of +/-k changes the next frame by exactly k clocks; slip beyond the front porch is clamped |
| T27-02 | `phase_meas` | Equal to the model for random sequences of `rx_fs` and `disp_vs` pulses (jitter, missing and doubled pulses, drift of the display relative to the reference over many periods): `err`, `err_valid`, `lost` |
| T27-03 | `pi_steer` | Bit-exact against the model for random error sequences and parameters (saturation, slew limit, anti-windup, hold, preset); `ctl` never exceeds +/-`ppm_max` or changes by more than `slew_max` per update |
| T27-04 | `line_sel` | Equal to the model for random slice arrival orders and scan requests over several frames: `use_cur`, `buf_sel`, `stale_cnt`, `cur_cnt`, `late_wr_cnt`; the buffer toggles at `swap` |
| T27-05 | Clock steering loop | Plant model: the display pixel-clock oscillator with an initial offset of up to +/-40 ppm against the reference (two 20 ppm crystals), temperature drift of 1 ppm per minute, control quantised to 0.1 ppm, reference timing jitter of 0.1 us (20 clocks) sigma and, in a second run, uniformly +/-1 us (the MAC-003 bound), 10 minute flight (36 000 frames) using the bit-exact `pi_steer` and `phase_meas` models: the latency deviation from the target after lock stays within +/-1 ms (VID-018) and within +/-50 us in the 0.1 us case; lock time; the steering never leaves +/-50 ppm and moves by no more than 0.2 ppm per frame; with a 1 ppm residual error the deviation would be 0.6 ms over 10 min (the figure of `07`): reported against it; a reference outage of 10 s: holdover drift is reported; an initial offset of 40 ppm without the integrator preset locks in a time that is reported |
| T27-06 | Early scan-out | Slices decoded with a modelled time distribution (a mean per slice and a jitter, `T_k` growing with the slice index): the firmware's start-time rule gives the minimum `L` for a late-line fraction below 1e-3; reported against the wait-for-complete-frame latency (`L` of the last slice plus the scan time) as the latency saved; the measured late-line fraction from `line_sel` in a simulation of 2000 frames |
| L-27, S-27 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 3. Deliverables

`rtl/27-display-sync/{scan_timing,phase_meas,pi_steer,line_sel}.sv`, `fw/27-display/{start_rule.h,start_rule.c}` (the start-time rule), `tests/27-display-sync/` (models, cocotb tests, loop and latency simulations), results below, row in `design/README.md`.

## 4. Open items

- The pixel clock oscillator or PLL, the HDMI/DP/MIPI transmitters, the frame buffer in DDR (bandwidth, arbitration) and the display are not simulated; `ctl` is the interface to the oscillator (DAC word of a VCXO, or the fractional word of a PLL; the 0.1 ppm resolution has to be provided by it: a plain PLL fractional divider does not, a voltage-controlled crystal with a 16-bit DAC does) and is to be verified on the evaluation boards (`13`).
- Display variable refresh rate (VRR) as an alternative to clock steering is not considered.
- The clock-domain crossing of `vs_start` into the system domain (two-flop synchroniser plus pulse stretcher) is a library item and is assumed to add at most 2 system clocks of uncertainty.
- Not run on a target core; `start_rule` is firmware with integer arithmetic only.

## 5. Results (implementation commit)

RTL: cocotb on Verilator (4 simulations, `tests/27-display-sync`); loop and early scan-out simulations: `test_sys.py` (host build of the firmware, numpy). `run_tests.sh` runs both. All pass.

Deviations from the plan: the standard 1080p60 mode was compared with the model for three lines only (a frame is 2.5 million clocks of per-clock Python checking); the frame period is checked on a small mode with the same code path (`mid`, 96 x 50) and the 720p60 mode ran one complete frame. The `slip` adds to the **end of the back porch** of the first blanking line (section 1.1 was corrected). `T27-06` compares against the wait-for-complete-frame time with the model of decode times only; the line freshness block is checked against its model in T27-04 and driven with the same arrival pattern in a short consistency run.

| Test | Result |
|---|---|
| T27-01 | `scan_timing`: every output (`hs`, `vs`, `de`, `x`, `y`, `line_start`, `vs_start`, `frame_cnt`) equals the model on every clock for a tiny mode (6 frames with random slips), `mid` (4 frames, period exactly 4800 clocks), 720p60 (one full frame, 1 237 500 clocks) and the first three lines of 1080p60 (2200 x 1125 = 2 475 000 clocks per frame); both polarities; slips of +5, -3, 0, +100, -100 change every frame period by exactly the clamped amount (the negative slip is limited to `h_bp - 1`); disabled: outputs inactive |
| T27-02 | `phase_meas` equals the model on every clock for 6 runs (periods 1 to 4000, drift, missing and spurious pulses): `err`, `err_valid`, `lost` |
| T27-03 | `pi_steer` equals the model for 8 parameter sets (3426 updates; saturation, slew limit, anti-windup, hold, preset, disable); |ctl| within `ppm_max`, no step above `slew_max` |
| T27-04 | `line_sel` equals the model over 12 frames of random slice arrivals with 5% of the slices never arriving: `use_cur`, `buf_sel`, `rd_valid`, `late_wr_cnt`, and the latched `stale_cnt`/`cur_cnt`; the last frame showed 384 lines fresh and 696 from the previous frame (the arrivals of that test are deliberately late) |
| T27-05 | Steering loop (bit-exact `pi_steer` model, kp 0.005 ppm per clock, ki 0.00004 ppm per clock per frame, 36 000 frames, control quantised to 0.1 ppm, thermal drift 1 ppm per minute, reference jitter 0.1 us sigma): initial offset +40 / -40 / +25 / 0 ppm: peak deviation 67 / 68 / 26 / 0 us, after lock (15.6, 15.7, 9.4 s) within 1.0 us; the steering word reaches 50.0 ppm (the limit) for the 40 ppm offsets (overshoot of the integrator: the clamp holds) and never changes by more than 0.2 ppm per frame; uniform +/-1 us reference jitter (the MAC-003 bound): peak 27 us, 2 us after lock; a fixed 1 ppm residual would give 600 us over 10 minutes (the figure of `07`); a 10 s reference outage (holdover): 3 us during it; integrator preset to the true offset: peak 0 us. All far inside the 1 ms of VID-018 |
| T27-06 | Early scan-out, 30 slices of 36 lines, decode time with a lognormal jitter of about 0.15 ms: decoder at 0.2 ms per slice: start offset 1.43 ms against 6.95 ms for waiting for the whole frame (saves 5.52 ms), late-line fraction 3.3e-05; 0.5 ms per slice: 1.49 ms against 15.65 ms (saves 14.16 ms), 2.3e-04; 0.7 ms per slice (slower than the 0.53 ms the display needs per slice): 6.29 ms against 21.45 ms, 1.5e-04. The firmware rule (`start_rule.c`, integer arithmetic) keeps the late fraction below 3e-3 (target 1e-3 at z = 3.1) |
| L-27, S-27 | `-Wall` clean; no latches; `scan_timing` 1456 cells, `phase_meas` 1066, `pi_steer` 7179, `line_sel` 23376 cells (2144 flip-flops: the 2048-bit bitmap) |
| Mutation | slew limit removed in `pi_steer`: T27-03 fails; `buf_sel` inverted in `line_sel`: T27-04 fails; both restored |

### Limits

- The oscillator, the display transmitters, the frame buffer and the display are not simulated; the 0.1 ppm resolution and +/-50 ppm range must come from the hardware (voltage-controlled crystal with a 16-bit DAC, or a PLL with a sigma-delta fractional word that can do 0.1 ppm); this is the first item to check on the evaluation board.
- The loop gains were chosen for 0.1 us jitter and a 60 Hz frame rate; lock takes 10 to 16 s from a 25 to 40 ppm offset (a preset from the previous flight removes it); a faster acquisition would use a higher gain until the error is small.
- Reference jitter above 1 us, a missing reference at start-up and frame-rate changes (120 Hz, 30 Hz) were not simulated; the period is a parameter of `phase_meas`.
- The test of the early scan-out uses a decode-time model; real decoders have frame-dependent times (intra and refresh frames).
