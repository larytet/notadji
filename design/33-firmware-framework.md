# 33 - Firmware framework for the real-time control core

Requirements: `requirements/33-firmware-framework.md` (R33-01..R33-13). Code: `fw/33-framework/`. Tests: `tests/33-firmware/`.

## 1. Target and assumptions

- Core: 64-bit ARM (AArch64, Cortex-A53 class on the phase B Zynq UltraScale+ device; the same source must also run on a later ASIC core). Data model LP64.
  No cross linker or emulator is on the build host, so the code is developed and tested on x86-64 (also LP64, little-endian, same integer widths) and checked
  for AArch64 with `clang --target=aarch64-none-elf -ffreestanding -c` (code size, warnings, no libc dependence). Anything that depends on the core
  (MPU set-up, interrupt entry, caches, exclusive loads) stays outside the framework behind `hal_ops`.
- Bare-metal, single-threaded control loop per core, run-to-completion tasks released by the 1 ms frame tick (from the sequencer `frame_start`) and
  by deferred interrupt events. No heap, no recursion, no floating point except in the DPD solve already in module 26.
- Two control cores: the main core (control tasks) and a monitor core (heartbeat watch, safe table). They share only SPSC queues, mailboxes and one
  ownership word (R33-04, R33-12).
- Time: `uint64_t` cycle counter (HAL), `uint32_t` microseconds derived from it for modules 23..27 (they take `t_us` as `uint32_t`; wrap handled there).
- Fixed width types everywhere; no `long`, no pointer-to-integer casts; structures that go on the air or into retained memory are serialised byte by byte
  (no struct overlay), so padding and endianness do not matter.

## 2. Development steps (one commit and push per step)

| Step | Subsystem | Files | Requirements |
|---|---|---|---|
| S0 | Requirements review, this design and the test plan | `requirements/33-*.md`, this file | all |
| S1 | Core: types, register map, HAL interface and simulation backend, scheduler with accounting, SPSC queue and mailbox | `fw_types.h`, `regmap.h`, `hal.h`, `hal_sim.[ch]`, `sched.[ch]`, `spsc.h`, `mbox.h` | R33-01..04 |
| S2 | Crash log and supervision, sequencer driver, monitor core and safe table | `crashlog.[ch]`, `seq_drv.[ch]`, `sup.[ch]` | R33-05, 06, 12 (monitor) |
| S3 | MAC feedback path and rate retarget | `mac_fb.[ch]`, `rate_ctl.[ch]` (uses `link_adapt`) | R33-07, 08 |
| S4 | Thermal and RF protection, power loop, recalibration triggers | `thermal.[ch]`, `rf_prot.[ch]` | R33-09 |
| S5 | Host protocol parsers | `crc.[ch]`, `hostproto.[ch]` | R33-10 |
| S6 | Crypto and pairing: SHA-2, HMAC, HKDF, X25519, Ed25519 verify, pairing, region limiter | `sha2.[ch]`, `curve25519.[ch]`, `pair.[ch]`, `region.[ch]` | R33-11 |
| S7 | Update: A/B image slots, trial boot, rollback; whole-system task set, load and fault-injection tests, AArch64 build and size record | `update.[ch]`, `tests/33-firmware/sys_*.c` | R33-12, 03, 13 |

Each step: code, tests of the step, all earlier tests, lint (`-Werror` x86-64 and AArch64), update of section 8 (results), commit, push.

## 3. Architecture

```
                    +--------------- main core ---------------+      +------ monitor core ------+
 frame_start irq -> | sched: tick -> tasks by priority         |      | sup_monitor_poll()       |
 slot irqs ------> |  T1 mac_fb  (1 kHz)   feedback -> LA ->    |      |  heartbeat stale 2 frames|
                    |         seq_drv commit, modem regs        |<---->|  or sequencer `missed`   |
                    |  T2 rate_ctl (per frame)                  | mbox |  -> take ownership,      |
                    |  T3 rf_prot (1 kHz) + fast trip (irq)     |      |     commit safe table    |
                    |  T4 thermal (100 Hz)                      |      +--------------------------+
                    |  T5 hostproto (poll DMA ring)             |
                    |  T6 cal/dpd/chan_select (modules 23..26)  |      retained RAM: crash log (CRC per record)
                    |  T7 sup (checkins, watchdog kick)         |      flash: slot A, slot B, boot record
                    +------------------------------------------+
                       hal_ops: regs, cycles, retained RAM, flash, rng, wdog
```

### 3.1 HAL (R33-01)

`hal_ops` is a table of function pointers (`reg_rd32/wr32`, `cycles`, `ret_read/ret_write`, `flash_read/program/erase`, `rng`, `wdog_kick`), passed to every
module that needs it (no global). `regmap.h` holds the versioned register map (`HAL_REGMAP_VERSION`): sequencer (`SEQ_*`), MAC and modem (`MAC_*`), RF front end (`RF_*`),
sensors (`SENS_*`), timestamp unit, interrupt status. `hal_sim` implements the sequencer exactly as module 10 describes it at frame level (two banks, commit swaps at
frame end, `missed` counts frames without a commit, `force_safe`) and keeps a log of every register write with the cycle number, so the tests can check what the
firmware did and when.

### 3.2 Scheduler (R33-02, R33-03)

```c
typedef struct { const char *name; void (*fn)(void *); void *arg; uint32_t period_us, deadline_us; uint32_t budget_cycles; uint8_t prio; ... stats } task_t;
```
Static table of at most 16 tasks. `sched_tick(s, now_cycles)` releases every task whose period elapsed (release time = nominal, so late service is a deadline
miss, not a drift), runs them to completion in priority order, measures cycles per run with `hal.cycles`, updates max, sum, runs, overruns (cycles > budget),
deadline misses (finish after release + deadline), and the busy time for the load figure. Deferred interrupt events: `sched_post(s, event)` (atomic bit set from
interrupt context) runs the registered handler at the top of the next tick. After `sched_start` no task can be added.

### 3.3 Queues (R33-04)

`spsc_t`: power-of-two ring of fixed-size items in caller-provided storage; head and tail are `_Atomic uint32_t`; producer publishes with release, consumer reads with
acquire; each side reads the other index once per call, no loop waits for the other core. `mbox_t`: a sequence-locked single-writer value (reader retries a bounded
number of times, then reports "busy"; never blocks the writer).

### 3.4 Crash log (R33-05)

Retained RAM region: header (magic, record size, capacity, version, header CRC) and `capacity` records of 32 bytes: `seq:u32, t_us:u32, type:u16, flags:u16, a0..a3:u32` (24+... laid
out in the code), `crc16:u16` over the record. Writer: record is written with the CRC last, in one `ret_write`; the slot is `seq % capacity`. Recovery (`clog_open`): scan all
slots, accept those with a valid CRC and a `seq` consistent with the slot (`seq % capacity == slot`), take the highest `seq` as the tail, verify that the accepted sequence
numbers are contiguous below the tail (a torn record is simply not valid); resume writing at `tail + 1`. A header with a bad CRC re-initialises the log (cleared).
Cost: one 32-byte write and one CRC-16 (table driven) per record.

### 3.5 Supervision and monitor (R33-06, R33-12)

`sup_t` holds, per supervised task, the last check-in period, the consecutive overrun count and a missed-deadline flag. `sup_tick` (runs in T7 once per period):
(1) reads the scheduler statistics, (2) logs faults (`CLOG_TASK_OVERRUN`, `CLOG_DEADLINE`), (3) raises the safe request after three overruns in a row or any miss, (4) kicks the
hardware watchdog only if every supervised task checked in during the period, (5) writes the heartbeat counter to the mailbox for the monitor.
`sup_monitor_poll` (monitor core, once per frame): reads the heartbeat and the sequencer `missed` register; if neither advanced for two frames it takes the sequencer ownership
word (compare-and-swap main to monitor), writes the safe table through `seq_drv`, commits and logs `CLOG_MONITOR_SAFE`; when the heartbeat returns it hands the ownership back
after the main core acknowledges. The safe table is built once at boot from the lowest MCS and the minimum power by the main core and kept in the monitor's memory (a dead main core
cannot corrupt it; the table has its own CRC, checked before every commit).

`seq_drv`: writes a table (entries `{time:24, action:8, arg:16}`) into the inactive bank, checks sorted order, one `END`, depth, then commit; returns before the
frame end only if the commit was early enough (the driver reads `tick` and refuses a commit in the last 2 us of the frame as the module 10 test T10-03 shows it would apply one frame later).

### 3.6 MAC feedback and rate retarget (R33-07, R33-08)

Uplink feedback message (little-endian, defined here because no document defined it): byte 0 `0xFB`, 1 `seq`, 2..3 `snr_x10` (int16), 4 `mcs_rec` (255 none), 5 `rssi_dbm` (int8),
6 `n_slices` (1..64), 7 flags (bit 0 = ground unit reports a deadline-miss burst), then `ceil(n_slices/8)` bytes of ACK bitmap (bit = 1 acknowledged), then CRC-16/MCRF4XX over everything
before it (2 bytes). The parser validates length, type, `n_slices`, CRC and a sequence-number window (duplicates and stale messages dropped); it builds `la_fb` (lost = zero bits after
subtracting slices that the retransmission rule dropped by design: the message carries only the final state), calls `la_on_feedback`, and `mac_apply` writes MCS, power and slice budget
to the modem registers and the next sequencer table (shadow registers, one commit). `rate_ctl` computes per-slice byte targets: `budget * thermal_pct / 100`, minus the telemetry share, split
over the slices of a frame with the remainder given to the earliest slices (so the frame total is exact and no slice exceeds the budget).

### 3.7 Thermal and RF protection (R33-09)

- Thermal: four sensors, raw 0.25 deg C. Validity check (range -40..150 deg C, stuck detector: identical raw value for 2 s while the others move by more than 1 deg C). An invalid
  sensor reads as the shutdown threshold minus 1 step (treated as hot). Hottest valid reading, with a step table `{enter, leave}` per level (hysteresis, min dwell 1 s): L0 normal, L1 TX
  power backoff 3 dB, L2 bitrate 70%, L3 bitrate 40% and half the frame rate, L4 shutdown request. Recalibration due when |T - T_cal| >= 5 deg C or 60 s passed (CAL-003).
- RF: reflection coefficient `G = sqrt(Prev / Pfwd)` from the two detector readings in 0.01 dB steps converted to linear power with a 256-entry table, `VSWR = (1 + G) / (1 - G)` in Q8, integer
  square root. States: OK, FOLDBACK (VSWR > 3 for 2 consecutive samples; power backoff 6 dB; recovers below 2.5 for 10 ms), TRIP (VSWR > 6 once confirmed by 2 samples at 250 us spacing inside the
  1 ms period is not possible, so trip is on **one** sample above 6:1 with Pfwd above the detector floor, and the PA enable line is cleared in the same call; recovery after 100 ms below 4).
  ANT-004 flags: gross mismatch (>= 10:1), detuned (3..10 and a change of at least 1.0 within 100 ms), low-forward-power (detector floor, no verdict). CAL-008: |VSWR - VSWR_cal| > 0.5 raises recalibration.
- Power loop (CAL-006): integrator with gain `1/4` on the error in 0.25 dB steps, saturating gain code, anti-windup; called by the sequencer pulse every 10 us in a burst.

### 3.8 Host protocol (R33-10)

`crc16_mcrf4xx` (poly 0x1021 reflected, init 0xFFFF, no final xor) and `crc8_dvb_s2` (poly 0xD5). `hp_poll(hp, ring, max_bytes)` consumes at most `max_bytes` from an SPSC byte ring and runs
a byte-wise state machine with three protocols (MAVLink 2 start `0xFD`, MSP v1 `$M<`/`$M>`, MSP v2 `$X<`/`$X>`); a complete, checked frame is pushed to the output queue (header
fields plus payload copy, 280 bytes max); on a CRC error the parser restarts one byte after the start byte of the failed frame (it re-scans the buffered bytes, so a start byte inside a
corrupted frame is not lost). MAVLink CRC extra comes from a caller-supplied table (message id to byte). Signed MAVLink frames: the 13-byte signature is skipped, not verified.

### 3.9 Security (R33-11)

SHA-256, SHA-512, HMAC-SHA256, HKDF-SHA256; X25519 and Ed25519 verification on the 16-limb signed 64-bit field representation of TweetNaCl (constant-time selection, no secret-dependent
branches in X25519; Ed25519 verification handles public data only). Pairing: both sides generate an X25519 key pair from `hal.rng`, exchange public keys, compute the shared secret,
derive `K = HKDF(secret, salt = H(pkA || pkB), info = "pair-v1")` into link key (32 B), authentication key (32 B) and a short code `n = u32(HKDF output) mod 10^6`: the user compares the code
on both screens (this authenticates the public keys: an attacker who substitutes keys on each side gets two different codes with probability 1 - 10^-6 per attempt, and the pairing allows
three attempts). `region_verify` checks a signed table (`magic, version, region id, band mask, max power per band in 0.25 dB, dwell, DFS flag, valid-from counter, signature`) and
`region_limit` clamps every request; entitlement tables use the same format with a different magic.

### 3.10 Update (R33-12)

Flash layout: boot record (two copies with CRC and a generation counter), slot A, slot B. Image: header (`magic, version, rollback_index, length, sha256(payload), signature(header fields + hash)`) then payload.
`upd_begin/upd_chunk/upd_finish`: chunks are written in order at a stored offset (resume after interruption from the offset in the boot record), a chunk is read back and compared; `upd_finish` verifies hash
and signature and the rollback index against the monotonic counter (anti-rollback), then writes the boot record: target slot, state TRIAL, boot counter 0. `upd_boot_select`: valid boot record with the
highest generation; TRIAL slot is chosen while its boot counter is below 3 (the counter is incremented before the jump); after the third unconfirmed boot the previous slot is selected and the
trial slot is marked bad; `upd_confirm` (called when the link has run for 10 s) makes the slot the permanent one. Every flash program and erase can be interrupted by the test harness.

## 4. Test plan

Host build `tests/33-firmware/run_tests.sh`: each `t_*.c` is compiled with `gcc -std=c11 -O1 -g -Wall -Wextra -Wconversion -Werror -fsanitize=address,undefined` and linked with the firmware sources
(thread tests also with `-pthread`; one extra run of the queue test with `-fsanitize=thread`); crypto and CRC vectors come from `gen_vectors.py` (Python `cryptography` and `zlib`/own CRC reference) at test time; then every firmware
source is compiled with `clang --target=aarch64-none-elf -ffreestanding -O2 -Wall -Wextra -Werror -c` and the section sizes are printed.

| ID | Test | Pass criterion |
|---|---|---|
| T33-01 | HAL sim sequencer: write table, commit, frame advance, stall, `force_safe` | Behaviour equal to the module 10 test cases T10-02, 03, 04, 05, 08 reproduced at frame level |
| T33-02 | Scheduler order and release | Priority order at equal release; exact periods over 10^5 ticks; no double release after a late tick (a 3-period stall gives one run and a recorded miss) |
| T33-03 | Scheduler accounting | Max, sum, overruns and misses equal the values from the test's own tally for random task costs; load figure within 0.1% of the tally |
| T33-04 | Deferred events | Events posted from a second thread run exactly once each at the next tick, none lost (10^6 posts) |
| T33-05 | SPSC queue, two threads, 10^7 items, also under ThreadSanitizer | Sequence check passes; full and empty return at once; wrap of the 32-bit indices exercised by starting near `UINT32_MAX` |
| T33-06 | Mailbox | Reader sees only consistent values under a writer thread (checksum field); never blocks the writer |
| T33-07 | Crash log write and recover, 10^4 random cases | Recovered records are a gap-free prefix in order; a reset at any byte offset of the record in progress loses at most that record; wrap keeps the newest `capacity` records; corrupted header re-initialises |
| T33-08 | Crash log cost | Cycle count of one append on the model (CRC loop count x cost) below 1500 cycles (0.5% of a core at 1 kHz) |
| T33-09 | Supervision | Injected overrun x3, injected deadline miss, missing check-in: log entry, safe request and absent watchdog kick in the specified period; 10^6 normal periods: no request, kicks every period |
| T33-10 | Sequencer driver | Unsorted, missing END, too deep and late commits are refused; accepted tables read back identically from the sim banks |
| T33-11 | Monitor core | Heartbeat stops: safe table committed after 2 frames and ownership taken; heartbeat resumes: ownership returned; heartbeat alive: no commit in 10^5 frames; CRC-damaged safe table: not committed, fault logged |
| T33-12 | Feedback parser | Valid messages parsed; flipped bit anywhere (every bit position) rejected; bad length, `n_slices` 0 and 65, duplicate and stale `seq` dropped; counters correct |
| T33-13 | Feedback to register commit | MCS, power and budget in the sim registers equal the `link_adapt` outputs for the same inputs run directly; cycle cost for the worst message below 2 ms at 300 MHz (600,000 cycles) by the cost model |
| T33-14 | Rate retarget | Per-slice targets sum to the exact frame budget, none above the slice budget, thermal step 2 lowers them within one frame, cost below 4000 cycles per frame |
| T33-15 | Thermal | Step entry and exit with hysteresis and dwell against a Python model on random temperature traces; failed and stuck sensor treated as hot; recalibration triggers (5 deg C, 60 s) |
| T33-16 | VSWR | Error at most 0.3 at 3:1 and at most 0.1 from 1.2 to 2:1 against floating point over 1..10:1; fold-back and trip thresholds and hysteresis; trip within one call; ANT-004 flags; CAL-008 trigger |
| T33-17 | Power loop | Settles within 10 steps (100 us) for steps of +/-3 dB with detector quantisation of 0.25 dB; no limit cycle larger than 1 step in 10^4 steps; anti-windup after saturation |
| T33-18 | CRC check values | CRC-16/MCRF4XX("123456789") = 0x6F91, CRC-8/DVB-S2 = 0xBC; agreement with a bitwise reference on 10^5 random buffers |
| T33-19 | MAVLink and MSP parsing | 10^5 random frames of all three protocols with random garbage between them: every intact frame recovered once, none invented; one corrupted byte loses only that frame; bounded bytes per call; MAVLink payload truncation (trailing zeros) handled |
| T33-20 | Hashes and MACs | FIPS 180 and RFC 4231 and RFC 5869 vectors; 2000 random messages against `hashlib`/`hmac`; incremental and one-shot calls agree for every split of a message |
| T33-21 | X25519 | RFC 7748 vectors, the 1 and 1000 iteration tests, 500 random scalar/point pairs against `cryptography` |
| T33-22 | Ed25519 verify | RFC 8032 vectors; 300 random signed messages accepted; every one of 4096 single-bit flips in signature, message and key rejected; non-canonical S and small-order keys rejected |
| T33-23 | Pairing | Two instances agree on keys and code in 1000 runs; man in the middle gives different codes (all 1000 runs differ in the code or in the keys, probability of a code match about 10^-6 per run is checked statistically); three wrong attempts lock the pairing for a timeout |
| T33-24 | Region limiter | Valid signed table accepted; any bit flip rejected; version older than the counter rejected; requests above the limit are clamped for 10^5 random requests; entitlement magic cannot be used as a region table |
| T33-25 | Update with power cuts | Every flash operation of a complete update (all chunks, finish, boot record) cut in turn, then boot select: a valid, signed image is always selected; the interrupted update resumes and completes; bad hash, bad signature, old rollback index rejected; three failed trial boots roll back |
| T33-26 | Whole-system run | Task set of `13` section 2 at the 1080p120 workload on the 300 MHz model core for 10 s of model time: load at most 50%, no miss, no overrun; with a fault injected (stalled feedback task, VSWR spike, hot sensor, stalled main core) the expected actions and log entries appear in order |
| T33-27 | Build checks | x86-64 and AArch64 compile clean with `-Werror`; no unresolved libc symbol in the AArch64 objects (`nm`); sizes recorded |
| T33-M | Mutation checks | Seeded defects (off-by-one in the ring full test, missing release fence, CRC init, hysteresis sign, wrong slot in recovery, skipped signature check, trial counter not incremented) are each caught by at least one test |

## 5. Interfaces to modules 23..27

`link_adapt` (`la_on_feedback`, `la_tick`), `cal_mgr`, `dpd_fw`, `chan_select`, `start_rule` stay unchanged; the framework only calls them from tasks. They already take `t_us` and use fixed-width types
(checked by the AArch64 build in T33-27).

## 6. Open items

- No real AArch64 execution: instruction timing, cache and exclusive-monitor behaviour of the queues, MPU and interrupt entry are not tested; cycle costs come from a model (cycles per operation,
  documented in `sched_model.h`), not from the core.
- The sequencer RTL has no hardware safe-table bank: the monitor core is the firmware substitute (see requirements review).
- Hardware watchdog and the RF detectors are modelled by the HAL sim.

## 7. Risks

Hand-written big-number code (Ed25519) is the highest risk; mitigation is the vector and cross-library tests of T33-21/22 and the bit-flip test. Constant-time behaviour is by construction (no secret-dependent
branches or indices in X25519), not measured.

## 8. Results

(filled in per step)
