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
interrupt context) runs the registered handler at the top of the next tick. After `sched_start` no task can be added. Tasks run to completion and are not preempted, so a long task delays every other task released at the same tick: any task that shares a tick with 1 ms-deadline tasks is sliced to at most 100 us (the system test showed 50 deadline misses in 10 s from a 0.67 ms calibration task coinciding with the 1 ms tasks every 200 ms; sliced into 20 ms periods the misses are gone at the same average load). The budget of each task is part of its registration and is enforced by the overrun counter.

### 3.3 Queues (R33-04)

`spsc_t`: power-of-two ring of fixed-size items in caller-provided storage; head and tail are `_Atomic uint32_t`; producer publishes with release, consumer reads with
acquire; each side reads the other index once per call, no loop waits for the other core. `mbox_t`: a sequence-locked single-writer value (reader retries a bounded
number of times, then reports "busy"; never blocks the writer).

### 3.4 Crash log (R33-05)

Retained RAM region: header (magic, record size, capacity, version, header CRC) and `capacity` records of 32 bytes: `seq:u32, t_us:u32, type:u16, flags:u16, a0..a3:u32` (24+... laid
out in the code), `crc32:u32` over the record. Writer: record is written with the CRC last, in one `ret_write`; the slot is `(seq - 1) % capacity`. Recovery (`clog_open`): scan all
slots, accept those with a valid CRC and a `seq` consistent with the slot (`seq % capacity == slot`), take the highest `seq` as the tail, verify that the accepted sequence
numbers are contiguous below the tail (a torn record is simply not valid); resume writing at `tail + 1`. A header with a bad CRC re-initialises the log (cleared).
Cost: one 32-byte write and one CRC-32 (two nibble-table lookups per byte) per record. Two instances are used: an event log (faults, state changes, update and pairing events) and a 1 kHz statistics log; with one ring the 1 kHz records would push every event out within 0.25 s (the system test showed it).

### 3.5 Supervision and monitor (R33-06, R33-12)

`sup_t` holds, per supervised task, the last check-in period, the consecutive overrun count and a missed-deadline flag. `sup_tick` (runs in T7 once per period):
(1) reads the scheduler statistics, (2) logs faults (`CLOG_TASK_OVERRUN`, `CLOG_DEADLINE`), (3) raises the safe request after three overruns in a row or any miss, (4) kicks the
hardware watchdog only if every supervised task checked in during the period, (5) writes the heartbeat counter to the mailbox for the monitor.
`sup_monitor_poll` (monitor core, once per frame): reads the heartbeat and the sequencer `missed` register; if neither advanced for two frames it takes the sequencer ownership
word (compare-and-swap main to monitor; the main core is halted first through `SYS_MAIN_HALT`, so there is no concurrent writer), writes the safe table through `seq_drv`, commits and logs `CLOG_MONITOR_SAFE`. The ownership word carries an epoch (bit 0 owner, the other bits count the changes): `seq_load_owned` makes the main core's driver forget what it believes the two banks hold whenever the epoch changed, because the monitor has written them since (without it the main core re-committed the monitor's table after the hand-back, which the system test found); when the heartbeat returns it hands the ownership back
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
branches in X25519; Ed25519 verification handles public data only, and is strict: S must be below the group order, point encodings canonical, public keys of small order refused; a textbook verifier accepts the identity key with an all-zero signature for any message). The constants are generated from their definitions by `scripts/gen_crypto_consts.py`. Pairing: both sides generate an X25519 key pair from `hal.rng`, exchange public keys, compute the shared secret,
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

Run everything: `tests/33-firmware/run_tests.sh` (about 2 minutes); mutation checks: `tests/33-firmware/mutate.py [S1|S2|S3|...]` (a few seconds per mutant).
Changes to the requirements document found while implementing: R33-05 now says CRC-32 (a 16-bit CRC would accept about one torn record in 65,000 torn writes, which the 10,000-case crash test would have hit); the test plan lines that say "Python model" for the thermal steps were implemented as an independent reference state machine inside the test.

### S1 core (hal, simulation backend, scheduler, queues)

- T33-01 (8 tests, 35 checks): the simulated sequencer reproduces the module 10 rules at clock level: safe table after reset (1000-clock frames), minimum frame 16, `missed` counting and clearing at a swap, writes only into the inactive bank, a commit takes effect at this frame end only when written at least one clock before the END clock (a commit in the END clock waits one frame), time conversion between the 300 MHz core and the 200 MHz fabric, retained-RAM and flash fault injection.
- T33-02..04 (6 tests, 42 checks): priority order and exact periods over 10^5 ticks, a three-period stall gives one run, two skipped periods and one recorded miss (never a burst of catch-up runs), accounting equal to the test's own tally for 20,000 random task costs (runs, sum, maximum, overruns; load within 0.1%), overrun streaks, stack painting, 10^5 posted events from a second thread each run exactly once.
- T33-05/06: SPSC queue with 10^7 items between two threads with the 32-bit indices wrapping during the run, also under ThreadSanitizer (run with `setarch -R`: this kernel's address-space layout makes the sanitizer abort otherwise); mailbox: 3 million reads against a free-running writer give no torn value, the sequence never goes back; the reader gives up on about 80% of the attempts while the writer runs flat out (62 million writes), and the writer is never delayed.
- Mutation: 16 of 16 mutants killed. Two findings: (1) the missing release and acquire orders of the queue and the mailbox cannot be seen by any test on this x86-64 host (strong memory ordering) and ThreadSanitizer did not report the relaxed variant either, so `audit.sh` checks the required orders in the source (a source check, not a behaviour test); (2) mutants that change `hal_sim_clocks` in only one of its two copies of the frame-end rule are equivalent and were dropped.

### S2 crash log, sequencer driver, supervision, monitor core

- T33-07 (10,038 checks): 10,000 random crash cases (reset after a random number of bytes of the next one to four appends, ring of 16 records, up to 59 earlier records): the recovered records are always a contiguous run that ends at the last complete record, the content equals what was written, at most the record in progress and the oldest one it was overwriting are missing, writing continues with the next number; 4,000+ of the cases were torn (cut inside a record). Every single-bit flip of every byte of a record invalidates it (256 cases), a damaged header clears the log, a different size is a different log, and the numbering restarts instead of wrapping at 2^32 records.
- T33-08: static AArch64 instruction count (`a64_cost.py`, estimates, IPC 0.75 and 120 cycles for the 32-byte retained-RAM write assumed): `clog_append` is 398 instructions, about 650 cycles, 0.22% of a 300 MHz core at 1 kHz (budget 1500).
- T33-09 (43 checks): 10^6 normal periods: no request, one kick per period, empty log; three overruns in a row raise the request and log it once (again at six and nine); a deadline miss is reported once; a missing check-in withholds the kick and is logged once per episode.
- T33-10 (854 checks): all error classes of the table validator; 200 random tables (2 to 64 entries) read back identically from the simulated banks and run with the right frame length; an unchanged table needs only the commit (20 frames, `missed` stays 0); the timing guard refuses a table that cannot be written before the frame end (nothing written, nothing committed) and a commit within 200 clocks of the END; a forced bad write reports the bank race.
- T33-11 (45 checks): 10^5 frames with a living main core: no takeover, ownership stays; a stall is taken over within three frames, the main core is halted, the safe table runs, the main core is released after the hold time and gets the ownership back when its heartbeat is back, the main table returns; a main core that does not return is halted again and the safe table stays; a core that runs but does not commit tables (`missed` reaches 2) is taken over too; a damaged copy of the safe table is not committed (logged).
- Mutation: 20 of 20 mutants killed (the first run left two survivors, `seq-guard` and `seq-skip`, which showed that the guard margin and the commit-only path were not tested; `margin_and_commit_only_guard` was added).

### S3 feedback path and rate retarget

- T33-12 (parser): 20,000 random messages round-trip; every one of about 25,000 single-bit flips over 200 messages is rejected; length errors, `n_slices` 0 and 65, wrong type; sequence window: duplicates and older messages dropped, 1 to 127 ahead accepted across the 8-bit wrap, counters correct; 500 corrupted messages all rejected, counted and logged.
- T33-13: 3,000 messages with 5% corruption: the MCS, power and budget registers always equal the output of an independent `link_adapt` instance run on the same messages; registers are written only when something changed; limits (power back-off, transmit inhibit) are applied on top; the safe schedule on request and the feedback timeout work. Latency (`a64_cost.py`, bound, not measurement): 24,432 instructions, 33,000 cycles (111 us) plus a 1 ms poll period gives 1.11 ms against the 2 ms of MAC-005.
- T33-14: 100,000 random budgets, thermal factors, telemetry shares and slice counts: the targets sum exactly to `min(budget x slices x pct / 100 - telemetry)`, none exceeds the slice budget, earlier slices get the remainder, only changed registers are written; cost about 1,200 cycles for 8 changed slices (budget 4,000).
- Mutation: 17 of 17 killed after test additions (the first run showed that `fb_lost` was only checked against itself and that the `MAC_APPLY` write was not checked).

### S4 thermal and RF protection

- T33-15 (45 checks): 200,000 random temperature samples at 100 Hz: the level equals an independent reference state machine at every sample; entry skips levels at once, exit is one level per dwell (1 s) and only below the leave threshold (5 deg C hysteresis); a wobble of 1 deg C around a threshold changes the level at most twice in 2,000 samples; an invalid sensor (no response, out of range) or a stuck one (exactly constant for 2 s while another sensor moved more than 1 deg C) reads as hot (level 3), all invalid gives shutdown; the hardware trip latches level 4 and holds it; re-calibration is requested at power-up (also at a reading of 0 deg C), after a change of 5 deg C (exactly 5.00 included) and after 60 s.
  Finding: with perfectly constant test readings the stuck detector flagged healthy sensors, because a sensor that does not change for 2 s while the others drift by 1 deg C is exactly its definition. Real converters jitter by one step, and the tests that model temperature traces now do the same. The false-alarm rate on a real board is an open item (needs measured sensor noise); the failure is on the safe side (throttling).
- T33-16 (VSWR and protection): error of the VSWR from the two detector readings against floating point: at most 0.028 over 1.05:1 to 10:1, 0.004 over 1.2 to 2:1, 0.006 around 3:1 (requirement 0.3 at 3:1); fold-back by 6 dB after two consecutive samples above 3:1 (one is ignored); trip in the same call as the first sample above 6:1 (PA enable cleared, so within the 1 ms sample period); recovery from fold-back after 10 ms below 2.5:1 with a dead zone between 2.5 and 3:1; after a trip a 100 ms hold, then a probe burst at reduced power: five good samples (below 4:1) lead back to fold-back and normal recovery, a bad antenna gives a new trip, a probe without forward power times out into a new trip; no verdict below the detector floor; antenna flags (gross at 10:1, detuned when worse than the calibration reference by 1.0 or more, no signal); calibration trigger when the VSWR differs from the reference by 0.5 for 10 samples in a row.
- T33-17 (power loop): the integrator (gain 1/4, rounding away from zero so that no dead band is left) settles within 6 steps (60 us at 10 us per step) for steps of +/-3 dB with and without one step of detector delay, then stays within one step for 10,000 steps; saturation clamps the integrator, so it leaves the limit at once when the target becomes reachable (no wind-up).
- Glue (`t_protect`, 38 checks): detector and sensor registers drive the limits of the MAC control and the PA enable line; thermal and RF back-offs add (limited to 30 dB); a trip reaches the modem registers (budget 0) in the same call; state changes and sensor failures are written to the crash log once.
- Mutation: 39 of 39 mutants killed (the first run needed two more tests: probe samples and the detune margin; a classification bug in the mutation script, which called sanitizer reports "build errors", was fixed).

### S5 host protocol

- T33-19 (13.4 million checks): the encoders equal independent bitwise references; 100,000 frames of the three protocols (12.7 million bytes, payloads up to 255 bytes, MAVLink 2 with trimmed payloads) with random garbage between them, biased to contain false start bytes: every frame recovered exactly once and in order, nothing invented (the parser counted 16 CRC failures and 236,000 header rejections on the garbage); a single flipped bit in any of 30 back-to-back frames (300 repetitions) loses exactly that frame; the work per call stays within the byte budget (at most 64 bytes pulled per call in the test); signed MAVLink frames (the 13 signature bytes are skipped even when they contain start bytes), unknown incompatibility flags and unknown message ids (dropped and counted), 24-bit ids, the longest payloads, MSP v1 empty and error frames, jumbo and over-long frames refused, bad direction; with a full output queue frames wait in the window and none is lost (40 of 40 delivered through a 16-entry queue).
- Mutation: 14 of 14 mutants killed. The window-full branch (a candidate that cannot complete) is unreachable with the 640-byte window and 280-byte maximum frame and is kept as a defence.

### S6 crypto, pairing, region tables

- T33-20: SHA-256 and SHA-512 equal `hashlib` on 149 messages each (lengths 0 to 139 and up to 1000), the published abc, empty-message, RFC 4231 and RFC 5869 vectors pass; 400 HMAC cases (keys of 0 to 139 bytes, longer than the block too) and 200 HKDF cases (output up to 8,160 bytes, with and without salt) equal the `cryptography` package; the hash of a 300-byte message is the same for every two-way split, 500 random three-way splits and byte-wise feeding; HKDF refuses output above 255 blocks.
- T33-21: RFC 7748 vectors (both key pairs and the shared secret), the iteration tests with 1 and 1,000 iterations, 500 random scalar and point pairs and 200 base-point multiplications against `cryptography`; the bits the clamping clears do not change the result.
- T33-22: RFC 8032 test vectors 1 and 2, 120 random messages (0 to 1,000 bytes) signed by the library are accepted; in the full run every bit of the signature, the public key and the message of 6 signatures is flipped (4,712 flips): none is accepted (the sanitizer build samples 240 bits). Strictness: S + L is refused, the identity key with an all-zero signature (the classic forgery against lax verifiers) is refused, the five small-order encodings are refused as keys, and non-canonical y in the key or in R is refused.
  Cost: 12.9 ms per verification on an x86-64 host at -O2 (109 ms under the sanitizers); on a 300 MHz in-order core a factor of 4 to 6 [E, not measured] gives 50 to 80 ms: boot verifies the active image once (one signature and one SHA-256 over the payload), and an update twice.
  Finding: the textbook code shifts a negative value to the left (`c << 16`), which is undefined in C and was reported by UBSan; it is a multiplication now.
- T33-23: 1,000 honest pairings agree on the link key, authentication key and six-digit code (the two keys differ, the private key is wiped); the man in the middle (a key pair towards each side) ends with equal codes in 0 of 1,000 attempts and never with equal keys (the chance is 10^-6 per attempt); two units that both believe they are the initiator get different keys; three wrong comparisons wipe the keys and lock the pairing for 60 s (a success resets the counter); an all-zero public key and a low-order key are refused.
- Derivation of the pairing keys and code against an independent computation (X25519, SHA-256 of the transcript, HKDF with the label, code) for 20 random key pairs (`gen_vectors.py`).
- T33-24: signed region and entitlement tables: all 800 single-bit flips of a table are rejected; a table signed by another key, a flipped key bit, a validly signed table of the other kind, a version below the stored counter and wrong lengths are rejected; the limiter never exceeds the signed power limit nor raises a request, refuses disabled bands, over 100,000 random requests.

- Mutation: 32 of 32 mutants killed. Mutants that cannot be observed were dropped: an empty HKDF salt of length 0 (the HMAC pads an empty key with zeros, the same as the 32 zero bytes), a compare of 31 instead of 32 bytes of the recomputed R (a signature differing only in the sign bit changes the hash), and the check for non-canonical key encodings (every alias that can be built is also a small-order key or fails the final compare; the check stays as defence). First rounds left mutants alive that showed missing tests: the code of the pairing was only range-checked (now compared with the independent vectors) and a few mutants did not compile.

### S7 update, whole-system run

- T33-25 (A/B update): signed images in two slots with a trial-boot counter: three unconfirmed trial boots, the fourth falls back to the old image (marked bad, a new update may use the slot again); a confirmation makes the image permanent and raises the anti-rollback counter (the same version is allowed again, an older one is refused); images with a wrong hash, wrong signature, wrong magic, an announced size that differs from the header or a length above the slot are refused and the running image is not touched; chunk discipline (order, size, no start). **Power cut at each of the 51 flash operations of an update (53 cut points, including cuts in the middle of a program and of an erase): the next start always selects a valid, signed image; 51 of the 53 resumed from the stored session to completion, 2 had already switched to the new image; the trial counter, rollback and confirmation record writes were cut in turn as well (40 cut points over 4 boots) and the system stayed bootable and updatable.** Flipped bits in the active image or its header send the boot to the other slot, damage in both gives "no image".
- Mutation (update, sequencer ownership, safe hold): 25 of 25 mutants killed; the first round left alive: the CRC of the boot record (a cut write is complete in the fields that matter, so a flipped bit in flash is the only way to see it: `corrupt_boot_record_falls_back_to_the_previous_one`), the size check of a signed header with an absurd length (`oversized_image_in_a_slot`), the clearing of a finished update session (`finished_session_is_forgotten`: a new image of the same size with a resume request would otherwise continue at the end of the old one) and the ownership refusal of `seq_load_owned` (`main_cannot_write_while_the_monitor_owns`). Dropped as unobservable: the epoch step at the takeover (the step at the release is enough because the main core cannot load in between) and the clearing of the hold flag (the time test decides).
- T33-26 (whole system, 300 MHz model core, task set of `spec/13` section 2 at 1080p120 with the pessimistic feedback-path bound of 34,001 cycles per message, 10 s): load 20.5% (limit 50%), no deadline miss, no overrun, no skipped period, no supervision event; the link adapts up with good feedback, 9,000+ host frames pass through the MSP parser. Fault run: ten times the feedback budget for five frames gives the deadline-miss records, the overrun streak and the safe request, and the MCS falls to the lowest rungs and stays there for 100 ms; an open antenna for one period clears the PA enable in that very frame, probes after 100 ms and recovers; a PA at 100 deg C gives level 2 (bitrate 70%) within 30 ms and back to level 0 after the dwell; a stopped main core is taken over within 3 frames (main core halted, safe table running), released after the hold time, and the main table returns; the event log shows the events in that order.
  Findings of this test, each of which changed the design (section 3 and the requirements): (1) one ring for events and for the 1 kHz statistics kept 255 records, 0.25 s, so the fault records were gone; two rings now; (2) a calibration task of 200,000 cycles (0.67 ms) per 200 ms made 50 deadline misses in 10 s for the 1 ms tasks (run to completion); sliced to 20,000 cycles per 20 ms the misses disappear at the same average load; (3) a safe schedule requested by supervision lasted only until the next feedback message because the link adaptation leaves its safe state on feedback; it is held for 100 ms now; (4) after the monitor handed the sequencer back, the main core's driver believed the bank held its own table and re-committed the monitor's: the ownership word has an epoch now and the driver forgets on every change (the bank-parity test in `t_monitor` covers six start positions).
- T33-27 (build): all 15 firmware sources and `link_adapt.c` compile for AArch64 (`clang --target=aarch64-none-elf -ffreestanding`, `-Wall -Wextra -Wconversion -Werror`) and for the host under the sanitizers; the only undefined symbols are `memcpy`, `memmove`, `memset` and `memcmp` (the first AArch64 build of the host protocol parser failed on an undeclared `memmove`, found by this check). Code and constant data sizes are printed by `run_tests.sh`: 47 KB in total, of which `curve25519` 16 KB, `sha2` 6 KB, `mac_fb` 3.7 KB, `update` 3.2 KB, `sup` 2.7 KB, `link_adapt` 2.5 KB, `hostproto` 2.3 KB; the rest under 2 KB each.

### Open items after step S7

- Nothing has run on an AArch64 core or on an instruction-set simulator (none on the build host): instruction timing, caches, the exclusive monitors under the queues, interrupt entry, the MPU (HSI-015) and the boot flow (HSI-007) are untested. Cycle costs are static AArch64 instruction counts at an assumed IPC of 0.75 and an assumed 100 cycles per register access, or the estimates of `spec/13`; HSI-006 (measured WCET) stays open until a target core exists.
- The monitor core assumes a hardware halt of the main core (`SYS_MAIN_HALT`) and the main core's heartbeat through shared memory; the sequencer RTL has no hardware safe-table bank (module 10 open item).
- The stuck-sensor rule can false-alarm on a very quiet sensor (the failure is on the safe side); the real rate needs measured sensor noise. Thermal thresholds, VSWR thresholds and the detector floor are defaults to be set from the front-end design.
- Over-the-air update: only the storage side (chunks, resume, verification, trial boot) exists; the transfer protocol over the link (acknowledgements, rate) is not specified. Pairing: the attempt counter is in RAM (a reset clears it); the ECDH pairing has no persistent key storage yet. The Ed25519 public key for images and tables is a parameter; in the product it belongs in the immutable boot code or fuses.
- Timing side channels were not measured; X25519 has no secret-dependent branches or indices by construction only.
- The memory-order mutants of the queues and the mailbox are caught only by the source audit; a run on a weakly ordered core (the AArch64 target) would test them.

### Summary of module 33

7 steps, 15 firmware sources (about 3,000 lines with the headers and generated constant tables; 47 KB of AArch64 code and constants), 19 test programs, 163 seeded defects all caught, a source audit for the memory orders, and a whole-system run. The suite takes about 5 minutes (`tests/33-firmware/run_tests.sh`). Not done: execution on a real or emulated AArch64 core (see the open items).
