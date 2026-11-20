# 02 - Timestamp Unit

Plan entry: module 2 of `spec/18-development-plan.md`, class XS, data plane. Requirements: HSI-003 (one 64-bit timestamp counter at 200 MHz or faster, 5 ns resolution, latched at every pipeline stage boundary and exposed on the trace port), LAT-004 (each block reports its measured latency through a timestamp tap), MAC-003 (air-ground time alignment within 1 us; the counter must accept a load and a small correction).

## 1. Purpose

A single free-running counter in the data-plane clock domain, a latch register per tap point, and a trace stream that carries every tap event with its timestamp to the debug port. It is the evidence source for the latency budget (`02`): the latency of a stage is the difference between two tap timestamps of the same frame or slice.

## 2. Interface

Module `timestamp_unit`, parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `NTAPS` | 16 | Number of tap inputs (2 or more) |
| `TRACE_DEPTH` | 64 | Depth of the trace FIFO, power of two |

Ports (clock `clk`, synchronous active-low reset `rst_n`):

| Port | Dir | Description |
|---|---|---|
| `tap_evt[NTAPS-1:0]` | in | One-clock pulse per event; the stage that owns the tap drives it when a frame, slice or word crosses its boundary |
| `ts_now[63:0]` | out | Current counter value (for blocks that stamp their own headers) |
| `load_valid`, `load_value[63:0]` | in | Set the counter to `load_value` (used at link start or after a synchronisation message) |
| `adj_valid`, `adj_delta[31:0]` | in | Add a signed delta to the counter in the same clock as the normal increment (slew correction, MAC-003); `load_valid` has priority over `adj_valid` |
| `tap_ts_flat[NTAPS*64-1:0]` | out | Last timestamp latched by each tap |
| `tap_cnt_flat[NTAPS*16-1:0]` | out | Number of events seen by each tap (wraps at 65536) |
| `snap_req` | in | Pulse: copy the counter into `snap_ts` (atomic 64-bit read for software) |
| `snap_ts[63:0]` | out | The copied value |
| `m_axis_valid`, `m_axis_ready`, `m_axis_data[63+ID_W:0]`, `m_axis_last` | out/in | Trace stream, one record per event: `{tap id, 64-bit timestamp}` with `ID_W = $clog2(NTAPS)`; `last` is always 1 |
| `trace_drop[15:0]` | out | Count of events not written to the trace stream (saturating); the per-tap latch and counter still record them |

## 3. Behaviour

1. The counter increments by one every clock after reset (it resets to 0). At 200 MHz one count is 5 ns; the counter wraps after about 2900 years, so wrap-around is not a design concern, but the logic is correct across the 64-bit wrap (tested).
2. In the clock where `tap_evt[i]` is high, tap i latches the value `ts_now` shows in that clock and its event counter increments. All taps are independent; any number may fire in the same clock.
3. Trace records: when several events fire in the same clock, one record per clock enters the trace FIFO, chosen by lowest tap index; the remaining events of that clock are lost to the trace stream only and counted in `trace_drop` (their latch and counter are still updated). When the trace FIFO is full a record is dropped and counted the same way. A record's timestamp is the value in the clock of its event.
4. `snap_req` copies the current counter value into `snap_ts` in the next clock.
5. `load_valid` replaces the counter with `load_value` at the next clock (the next value shown is `load_value`); `adj_valid` makes the next value `ts_now + 1 + adj_delta` (delta sign-extended). Both are used while the data plane is running; the unit does not stop counting.
6. Clock domain: everything runs in `clk`. Taps from other clock domains must be synchronised by their owner into one-clock pulses in `clk` before they reach the unit (documented for later modules; the cost is a few clocks of uncertainty in the stamp, which is small against the 5 ns resolution of the budget only if the crossing is a gray or handshake pulse synchroniser).

Timing estimate [E]: a 64-bit incrementer with a 32-bit signed add meets 200 MHz in a Zynq UltraScale+ fabric using the carry chains; to be confirmed with Vivado (not yet available). If it fails, the counter is split into a low 32-bit part and a high part with a registered carry.

## 4. Test plan

cocotb tests against a Python model of the counter, sampled every clock (at the falling edge plus 1 ns, as in module 1).

| ID | Test | Pass criterion |
|---|---|---|
| T2-01 | Free run after reset | `ts_now` is 0 after reset release and increments by exactly 1 every clock for 10000 clocks |
| T2-02 | Single tap latches the right value | For 200 random single events on random taps, `tap_ts_flat[i]` equals the model's `ts_now` of the event clock; the event counter increments by one |
| T2-03 | Simultaneous events | Several taps in the same clock all latch the same value and count; exactly one trace record (lowest index) is written; `trace_drop` increases by the number of lost records |
| T2-04 | Trace stream content and order | Records read from the stream equal the model's list `{id, ts}` in order, `last` is 1, with random back-pressure |
| T2-05 | Trace FIFO overflow | With the stream not ready and more events than `TRACE_DEPTH`, `trace_drop` counts exactly the excess, the latch registers still show the last event of each tap, and the stream resumes in order when drained |
| T2-06 | `load_valid` | The next count equals `load_value`, then continues by one; `load_valid` wins over `adj_valid` in the same clock |
| T2-07 | `adj_valid` | Next value is `ts_now + 1 + delta` for positive, negative and zero deltas; checked against the model over 100 random adjustments |
| T2-08 | 64-bit wrap | Load `2^64 - 5`; the counter wraps through 0 and keeps counting; a tap event across the wrap latches correctly |
| T2-09 | `snap_req` | `snap_ts` holds the counter value of the request clock and does not change until the next request |
| T2-10 | Reset in the middle | After a reset pulse, counter, latches, event counters, trace FIFO and `trace_drop` are cleared |
| L-02, S-02 | Lint and synthesis | Verilator `-Wall` clean; Yosys generic synthesis with no latches; cell count recorded |

Configurations: `NTAPS=16, TRACE_DEPTH=64` (default) and `NTAPS=4, TRACE_DEPTH=4` (small, exercises overflow and the one-bit id).

## 5. Deliverables

`rtl/02-timestamp/timestamp_unit.sv` (uses the stream FIFO of module 1), `tests/02-timestamp/` (configs, tests), results added to this file, the row in `design/README.md`.

## 6. Open items

- Whether the 64 bits of timestamp are all needed in the trace record (a 40-bit record at 5 ns still covers 91 minutes); kept at 64 to match HSI-003 until the trace port bandwidth is known.
- Clock-domain crossing of taps from the radio-interface clock: handled by module 11, not here.
