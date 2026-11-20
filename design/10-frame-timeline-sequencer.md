# 10 - Frame-Timeline Sequencer

Plan entry: module 10 of `spec/18-development-plan.md`, class M, data plane. Requirements: HSI-001 (the data plane keeps forwarding video, feedback and the safe schedule for at least 1 s after both processors stall), HSI-002 (a hardware sequencer executes hops, turn-arounds, PA enable, gain steps and slice slots from a table committed at least one frame ahead; no software action in the microsecond path), SW-001, MAC-003 (frame timing). Depends on module 1 (conventions) and module 2 (the sequencer's event pulse is a timestamp tap). `13` section 1 gives the principle.

## 1. Purpose

A small hardware engine that replays a table of timed events once per frame. The CPU writes the table for the next frame into the inactive bank and commits it; at the frame boundary the sequencer swaps banks. If the CPU does not commit, the sequencer replays the last committed table: the radio keeps its timing without software. After reset, before any table was committed, it runs a safe empty frame. A hardware `force_safe` input (thermal trip, PA fault, VSWR protection) overrides the control lines at any time.

## 2. Table format

48-bit entries `{time[23:0], action[7:0], arg[15:0]}`, up to `DEPTH` entries (default 64, power of two) per bank, sorted by time. `time` is a number of clocks since the frame start (24 bits: 83.9 ms at 200 MHz). One entry must have action `END` (15); the first `END` reached closes the frame (its `time` is the frame length) and entries after it are ignored.

| Action | Code | Effect (registered, visible the clock after execution) |
|---|---|---|
| NOP | 0 | None (still counts as an event pulse) |
| SET_LINES | 1 | `lines <= lines | arg` |
| CLR_LINES | 2 | `lines <= lines & ~arg` |
| PULSE | 3 | `pulses[arg[3:0]]` is high for one clock (preamble trigger, slice slot, hop trigger, calibration strobe, ...) |
| SET_GAIN | 4 | `gain_val <= arg` (gain step) |
| SET_PLL | 5 | `pll_val <= arg` (frequency profile index) |
| END | 15 | Frame end: the tick counter restarts, `lines` return to 0, a pending table is swapped in |

`lines[15:0]` are level outputs (the assignment is a board/phase decision: TX enable, RX enable, PA enable, antenna switch bits, LNA bypass, ...). The meaning of the 16 lines and 16 pulses is defined by module 11 and the front-end specification, not here. `lines` are cleared at every frame start so a missed CLR cannot leave a transmitter on across frames.

## 3. Behaviour

- The tick counter counts clocks from the frame start while `run` is high; when `run` is low everything freezes (outputs hold).
- Entries execute in order. An entry executes in the first clock where `tick >= time`; two entries with the same time (or a late entry) therefore execute in consecutive clocks, one per clock. Keep times distinct by at least one clock where the order of simultaneous events is not wanted.
- END executes in the clock where `tick = max(time, MIN_FRAME) - 1` (or later), so the frame is exactly `max(time, MIN_FRAME)` clocks long (`MIN_FRAME` = 16 clocks, so a bad table cannot make the sequencer spin faster than that). The first clock of the next frame has tick 0.
- `frame_start` is a one-clock pulse in the first clock of each frame (tick = 0).
- `evt_pulse` is a one-clock pulse for every executed entry (including NOP; excluding END) to be connected to a tap of the timestamp unit (module 2).
- Table loading: `wr_en`, `wr_addr`, `wr_data` write an entry into the **inactive** bank only (the bank not used by the running frame); `commit` marks the inactive bank as pending; at the next frame end a pending bank becomes active (swap) and the old active bank becomes the loadable one. A commit takes effect at the next frame end if it is given at least one clock before the clock in which END executes; a commit in the END clock (or later) takes effect a frame later. Without a commit the same table is replayed and the counter `missed` increments at every frame end (saturating at 65535); `missed` is cleared by a commit being accepted at a frame end.
- Reset: bank 0 holds the safe table (a single `END` at time `SAFE_PERIOD`, default 1000 clocks, 5 us at 200 MHz); `lines` = 0. The data plane therefore starts in a defined, radio-off state.
- `force_safe`: while high, `lines` outputs are `SAFE_LINES` (default 0: everything off) and `pulses` are suppressed; the timeline, `gain_val` and `pll_val` continue; when low again the outputs show the table state (`lines` are the register value the table has built, so a TX enable set before the fault is visible again if its CLR has not executed; the sequencer does not hide the fault from the control core, which reads the `forced` status).
- Status outputs: `frame_cnt[31:0]` (frames started since reset), `missed[15:0]`, `active_bank`, `pending`, `tick[23:0]`, `forced`.

## 4. Interface

Parameters: `DEPTH` (64), `SAFE_PERIOD` (1000), `SAFE_LINES` (16'h0000). Ports: `clk`, `rst_n`, `run`, `force_safe`, `wr_en`, `wr_addr[$clog2(DEPTH)-1:0]`, `wr_data[47:0]`, `commit`, outputs `lines[15:0]`, `pulses[15:0]`, `gain_val[15:0]`, `pll_val[15:0]`, `evt_pulse`, `frame_start`, `frame_cnt[31:0]`, `missed[15:0]`, `active_bank`, `pending`, `tick[23:0]`, `forced`.

## 5. Test plan

A cycle-accurate Python model of section 3 steps once per clock; every output and status is compared with the model in every clock.

| ID | Test | Pass criterion |
|---|---|---|
| T10-01 | Playback of random sorted tables (all actions, random times), 3 frames each | Outputs equal the model in every clock |
| T10-02 | CPU stall: commit one table, then do nothing for 50 frames | The frame repeats identically 50 times; `missed` counts 49; no output differs between frames |
| T10-03 | Update mid-frame | Writes to the inactive bank during a frame do not change the running frame; a commit mid-frame takes effect at the next frame end; commit in the last clock before END takes effect, one clock later does not |
| T10-04 | Reset state | After reset `lines` = 0 and frames of `SAFE_PERIOD` clocks run; `frame_cnt` increments |
| T10-05 | `force_safe` | `lines` equal `SAFE_LINES` and `pulses` are 0 while forced; the timeline and counters continue; table state shows again afterwards |
| T10-06 | Same-time and late entries | Executed one per clock in table order, matching the model |
| T10-07 | `run` low | Everything frozen; resumes with no lost or repeated event |
| T10-08 | Minimum frame length | An `END` at time 0, 5 or 16 gives 16-clock frames; time 100 gives 100 |
| T10-09 | Back-to-back commits and several banks swaps | Alternating tables are executed in order; `active_bank` toggles at each swap |
| T10-10 | Table with no END (all entries consumed) | The sequencer keeps the last state and waits for an END that never comes: documented behaviour (the frame never ends); the test checks that `force_safe` still works and that a new table committed cannot take effect, which is why the CPU driver must always write an END (a watchdog is an open item) |
| L-10, S-10 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

Configuration: `DEPTH` = 64 (default) and `DEPTH` = 8 (to exercise table-full and pointer wrap).

## 6. Deliverables

`rtl/10-sequencer/frame_sequencer.sv`, `tests/10-sequencer/` (model and tests), results below, row in `design/README.md`.

## 7. Open items

- A formal proof with SymbiYosys of the safety properties (lines are zero in the first clock of every frame; `force_safe` always forces `SAFE_LINES`) is not done in this module.
- A table without `END` hangs the frame (T10-10); a hardware watchdog that forces a frame end after a maximum length is proposed (not implemented).
- Event times are in clocks; tying the frame start to the air-ground time alignment (MAC-003) needs the timestamp unit's adjust function and is added with the MAC module.
- Timing closure at 200 MHz of the table read and compare path needs Vivado (not available).
