# 07 - Preamble and Pilot Generator

Plan entry: module 7 of `spec/18-development-plan.md`, class S, data plane. Requirements: PHY-007 (pilots at least every 0.25 ms at the highest Doppler setting), PHY-010 (acquisition within 40 us), PHY-001 (FFT 64 to 512, 1024 optional), PHY-013 (programmable numerology). The spec fixes none of the layouts below; this document fixes them for the prototype **[E]** and is the "preamble and pilot layout" item of `17` section 4 and `18` section 5. Depends on module 1.

## 1. Purpose

Generates, in the frequency domain (the input of the IFFT, module 12), the known symbols the receiver needs: a short training symbol for burst detection, AGC and coarse timing and carrier offset; a long training pair for channel estimation and fine offset; and the pilot subcarriers of data symbols for channel tracking. It also provides the tone map (which bins are null, data or pilot), which the symbol assembler (module 16) uses to place mapper output.

## 2. Tone plan [E]

Bin order is IFFT input order: bin b = 0..N-1 carries subcarrier index k = b for b < N/2 and k = b - N otherwise; k = 0 (DC) is always null. Used subcarriers are those with `kmin <= |k| <= kmax`; pilots are at the listed |k| (both signs); all other used tones carry data; all other bins are null (guard). For N up to 256 the plan is the IEEE 802.11 plan with the same subcarrier spacing family (values from memory of the standard, not re-checked: **[E]**); for 512 and 1024 the used range follows the 802.11ax plan and the pilot positions are an own regular choice.

| N | Bandwidth | kmin to kmax | Used | Pilots (|k|) | Data |
|---|---|---|---|---|---|
| 64 | 5 MHz | 1 to 26 | 52 | 7, 21 | 48 |
| 128 | 10 MHz | 2 to 58 | 114 | 11, 25, 53 | 108 |
| 256 | 20 MHz | 2 to 122 | 242 | 11, 39, 75, 103 | 234 |
| 512 | 40 MHz | 3 to 244 | 484 | 12, 42, 72, 102, 132, 162, 192, 222 | 468 |
| 1024 | 80 MHz | 3 to 500 | 996 | 12, 72, 132, 192, 252, 312, 372, 432 | 980 |

Pilot counts are 4, 6, 8, 16, 16 (pilots are counted at both signs: 2 x 2, 2 x 3, 2 x 4, 2 x 8, 2 x 8). The 5 MHz mode uses the 20 MHz plan scaled in index, not in spacing (spacing is constant at 78.125 kHz, `01` PHY-001).

## 3. Symbols

Amplitudes use the mapper scale (RMS 4096 per used tone, `06`): BPSK values are +/-4096; training amplitudes are chosen so that the symbol power equals that of a data symbol.

- **STF (short training)**: one symbol (plus its cyclic prefix, added by module 4) with energy only on subcarriers k that are non-zero multiples of 4 inside the used range. Each such tone carries a QPSK value (+/-5793, +/-5793) (twice the amplitude of a unit tone, since one tone in four is occupied) taken from the PN sequence below. In the time domain this gives four exact repetitions of N/4 samples, which the receiver uses for detection and coarse timing and carrier offset (module 18).
- **LTF (long training)**: two identical symbols; every used tone (data and pilot positions, all of them) carries a BPSK value +/-4096 from the PN sequence. Two identical symbols allow averaging for the channel estimate and a fine offset estimate (module 17, 18).
- **Pilot template of a data symbol**: the bins at pilot positions carry +/-4096 with sign `pn_pol XOR pat(j)`, where `j` is the pilot index in increasing-k order over the whole set of pilots (negative k first), `pat(j) = 1 (negative) if j mod 4 = 3 else 0`, and `pn_pol` is the polarity bit of the current data symbol: one bit of the polarity sequence per data symbol. All other bins of the template carry 0; the tone-type flag says which bins the assembler must fill with data.

PN generators (reset at the start of every symbol for STF and LTF so that all symbols of a kind are identical):
- Tone PN: 9-bit LFSR x^9 + x^5 + 1, seed all ones. Stepping rule: it advances once per occupied tone in increasing bin order b = 0..N-1; for BPSK (LTF) bit 0 gives -4096 and bit 1 gives +4096; for STF two consecutive bits give I then Q the same way.
- Polarity sequence: 7-bit LFSR x^7 + x^4 + 1 (the 802.11 scrambler polynomial), seed all ones, advanced once per data symbol, restarted by the `frame_start` command flag; bit = 1 means polarity -1 (sign flipped), bit 0 means +1.

## 4. Interface

Module `preamble_gen`, no parameters. A command starts one symbol; the output is a stream of N beats (bin 0 first) with `last` on bin N-1.

| Port | Description |
|---|---|
| `clk`, `rst_n` | as in module 1 |
| `cmd_valid`, `cmd_ready` | Command handshake; `cmd_ready` is high when no symbol is being produced |
| `cmd_kind[1:0]` | 0: STF, 1: LTF, 2: pilot template of a data symbol (3 reserved, treated as 2) |
| `cmd_log2[3:0]` | log2 of N (6 to 10, clamped) |
| `cmd_frame_start` | With a kind-2 command: restart the polarity sequence at this symbol (first data symbol of a frame). Ignored for kinds 0 and 1 |
| `m_axis_valid`, `m_axis_ready`, `m_axis_data[33:0]`, `m_axis_last` | `{type[1:0], q[15:0], i[15:0]}`; type 0 null, 1 data, 2 pilot; I in bits 15..0 and Q in bits 31..16 (as in `06`) |

Behaviour: after a command is accepted, N beats follow (one bin per clock when the sink is ready). For STF and LTF the `type` field is 2 on occupied bins (they carry known values), 0 elsewhere; for kind 2 it is 2 on pilot bins, 1 on data bins, 0 elsewhere. A new command can be accepted while the last beat is accepted (back-to-back symbols without a gap are allowed).

## 5. Test plan

Python reference models of the tone plan, the two LFSRs and the symbols, written from sections 2 and 3; `numpy` (already in the test environment) for the time-domain check.

| ID | Test | Pass criterion |
|---|---|---|
| T7-01 | Tone plan | For N = 64, 128, 256, 512, 1024: counts of null, data and pilot bins in a kind-2 symbol equal the table (52/48/4, 114/108/6, 242/234/8, 484/468/16, 996/980/16 used/data/pilots); DC and guard bins are null; the set is symmetric in |k| except for the pilot sign pattern |
| T7-02 | STF equals the model and has period N/4 | Beat-by-beat equality for every N; the inverse DFT (numpy) of the received vector repeats exactly four times (maximum difference between repetitions below 1 unit after rounding) |
| T7-03 | LTF | Equals the model for every N; the two LTF symbols (two commands) are identical; all used tones have amplitude 4096 |
| T7-04 | Pilot template | Values and signs equal the model over 300 consecutive data symbols (the polarity sequence cycles with period 127); `frame_start` restarts it |
| T7-05 | Energy | The energy of an LTF symbol equals the number of used tones times 4096^2 exactly; the energy of an STF symbol is within 10% of it (the number of tones that are multiples of 4 is not exactly a quarter of the used tones, so the match is exact only for large N) |
| T7-06 | Handshakes | Random `m_axis_ready` and command timing: output equals the model; back-to-back commands produce no extra gap; `cmd_ready` low while a symbol is in progress |
| T7-07 | Per-symbol N | Different N and kind for every command; every symbol correct |
| T7-08 | Clamping and reserved | `cmd_log2` below 6 behaves as 6 and above 10 as 10; kind 3 behaves as kind 2 |
| L-07, S-07 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 6. Deliverables

`rtl/07-preamble-pilot/preamble_gen.sv`, `tests/07-preamble-pilot/` (numpy installed in the test virtual environment), results below, row in `design/README.md`.

## 7. Open items

- The tone plan and the preamble layout are prototype choices; the channel-estimation and acquisition studies (SIM-003, SIM-011) may change them, and the pilot spacing in frequency should follow the delay spread of the target channels.
- The 5 MHz mode shares the 64-point plan; whether it needs a different pilot set is open.
- Time-domain preamble length against PHY-010 (40 us): STF plus two LTF symbols with the 1/8 prefix at N = 256 is 3 x 14.4 us = 43.2 us on air; the detection part of the 40 us budget is the STF only, to be confirmed by SIM-011.

## 8. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/07-preamble-pilot && tests/common/lint_synth.sh tests/07-preamble-pilot`.

| Check | Result |
|---|---|
| T7-01 to T7-08 (7 tests, one configuration) | 7 of 7 pass: tone counts and exact pilot positions for N = 64 to 1024; STF equals the model and its inverse DFT (numpy) repeats four times for every N; LTF identical in both symbols; pilot template over 300 symbols with period 127 and restart on `frame_start`; every (kind, N) combination twice, shuffled, under three handshake patterns; gap-free back-to-back symbols; clamping and reserved values |
| Test sensitivity | A pilot position moved by one (75 changed to 76 for N = 256) is caught by three tests after the tests were tightened. The first version of the tests caught it in only one (the tone-count test checked counts, not positions, and the mixed-command test did not cover every pair); both were corrected |
| Lint (`verilator -Wall`) | Clean |
| Yosys generic synthesis | 420 cells, 34 flip-flops, no latches |

Notes:
- The polarity LFSR state of the generator persists between commands; the first data symbol of a frame must carry `cmd_frame_start`. One of my test runs failed for exactly that reason (a test that replayed a command list without restarting the sequence), which is the intended behaviour.
- The tone plan for 128 and 256 points and the pilot positions for 64 to 256 points are from memory of the IEEE 802.11 plans and have not been re-checked against the standard; 512 and 1024 points use own pilot positions (section 2).
- STF values: +/-5793 on both axes; LTF and pilots: +/-4096 on the I axis.
