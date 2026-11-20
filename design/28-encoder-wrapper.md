# 28 - Video Path Phase A: Wrapper Around the Hard Encoder

Plan entry: module 28 of `spec/18-development-plan.md`, class XL, data plane. Requirements: VID-003 (AVC and HEVC, codec-agnostic at slice level), VID-004 (slice-based, each slice independently decodable and protected), VID-005 and VID-021 (rolling intra-refresh; reactive slice refresh: a slice reported lost is re-coded in intra mode in the next frame), VID-006 (per-slice bit budget retargeted from the MCS in force; no slice above 105% of its budget, **verified on the encoded bitstream**), VID-020 (rate, refresh and reference parameters take effect within one slice time, unsupported values rejected, never silently replaced). Plan test reference: TG-VID of `08` (measured on the boards: **cannot be simulated**). Depends on 9 (slice framing) and 22 (the refresh list).

Scope and honesty about what can be verified: the encoder itself is a hard unit (the video codec unit of the Zynq UltraScale+ EV devices, `13` phase A, or an external encoder). Its coding efficiency, latency, its real adherence to a slice budget, its slice-structure options and its response time to commands are exactly what the evaluation boards must measure and are **not** established here. This module designs and tests the logic around it: the Annex-B slice splitter, the slice tagging, the **bitstream-level budget monitor** (the check of VID-006 that does not trust the encoder's own readback), the rate-control and refresh command interface, and the mapping from lost-slice sequence numbers to intra-refresh commands. The tests use a behavioural stand-in for the encoder (`enc_model.py`) whose output format follows Annex-B; its sizes are drawn from assumed distributions.

## 1. Blocks

### 1.1 `nal_split`

Input: the encoder's byte stream (`s_valid`, `s_ready`, `s_data[7:0]`; Annex-B: NAL units separated by `00 00 01` or `00 00 00 01`). Output: one NAL unit per frame of bytes on `m_*` (`last` on the final byte), start code and leading and trailing zero bytes removed, with the sideband `nal_type[5:0]` and `is_slice` valid with the first byte (parameter `CODEC`: 0 AVC, where the type is `byte0[4:0]` and slices are types 1 and 5; 1 HEVC, where the type is `byte0[6:1]` and slices are types 0 to 9 and 16 to 21), and `is_idr` (AVC type 5, HEVC 19 and 20). Emulation-prevention bytes (`00 00 03`) are payload and pass unchanged: they cannot form a start code. A NAL unit is closed at the next start code, so its last byte leaves one start code later than the byte arrives (the splitter holds at most 3 bytes back); a final `flush` input closes the last NAL unit of a stream. `err_overflow` counts NAL units longer than `MAX_NAL` (default 65535, truncated).

### 1.2 `slice_tag`

Tags every slice NAL with `frame[15:0]`, `idx[7:0]` and `flags[3:0]` (the sideband format of module 9: bit 0 intra, bit 1 last slice of the frame) and passes non-slice NAL units (parameter sets, SEI, delimiters) to a separate output port `ps_*` for transmission in the control stream. Frame boundaries come from a delimiter NAL (type 9 in AVC, 35 in HEVC) or from the sideband `frame_sync` of the encoder, whichever is configured (`frame_src`); `slices_per_frame` is a register (8 to 34). The slice index is the arrival counter inside the frame; a frame with a different number of slices than configured raises `err_count` and resynchronises at the next boundary. Flag bit 0 is the **commanded** intra state of that slice index (`intra_mask` latched at the frame start) OR'd with `is_idr`.

### 1.3 `budget_mon`

For every slice it measures the byte count of the NAL unit against the budget sampled at the first byte (`budget[15:0]`, bytes, from the rate-control interface) and reports: `size[15:0]`, `ratio_q8` (size x 256 / budget), `over` (pulse when `size x 100 > budget x 105`), and keeps `max_ratio_q8`, `n_slices`, `n_over`, `n_zero_budget`. The comparison uses the bitstream length as it enters the packetiser (the NAL unit without start code), not any encoder statistic. Optionally (`rate_buf_limit`) a second check: the number of bytes waiting between the encoder and the packetiser must not exceed one budget (VID-006 "rate buffer of at most 1 slice"); `err_buf` counts violations from `fifo_level`.

### 1.4 `refresh_map`

Receives lost slice sequence numbers `seq[15:0]` from the refresh queue of module 22 (`rf_valid`, `rf_ready`, `rf_seq`) and converts them into the intra-refresh command `intra_mask[63:0]` (bit `idx`) for the next frame. The sequence numbering is `seq = frame x S + idx` (modulo 65536, `S` = `slices_per_frame`); the block keeps `first_seq` of the last 16 frames (recorded at each frame start) and finds the frame by comparison, so no division is needed. A request for a slice of a frame older than 16 frames is dropped and counted (`n_old`); one for the current frame is applied to the next frame; the mask is latched by `frame_start` (requests that arrive after it apply one frame later) and cleared when latched. `n_req`, `n_applied` count requests and distinct bits set. The refresh also feeds the rolling intra-refresh wave of VID-005 (a configurable column of slices forced intra every `wave_period` frames, `wave_mask` register).

### 1.5 `rc_hook`

The rate-control interface to the encoder: `target_bytes[15:0]` and `update` (pulse) follow the slice budget from module 23 (`budget_in`, `budget_valid`); validation: a budget of 0 or above the configured maximum is rejected with `err_rc` and the previous value stays (VID-020: never silently replaced). `update` is issued within 4 clocks of a valid budget. `qp_bias[7:0]` (foveation or global bias, VID-023) and `intra_mask` are passed through registered with the same rule (a value out of range is rejected and counted).

### 1.6 `enc_wrap`

Integration: `nal_split` -> `slice_tag` (+ `budget_mon` in parallel) -> module 9 `slice_pack`; the refresh path and the rate-control hook as above. Parameter-set NAL units go to the port `ps_*` (to be sent at start-up and with every IDR, by the control stream).

## 2. Test plan

| ID | Test | Pass criterion |
|---|---|---|
| T28-01 | `nal_split` | Random Annex-B streams from the encoder model (3- and 4-byte start codes, leading and trailing zeros, payload with `00 00 03` sequences and long zero runs, NAL units of 1 to 5000 bytes, AVC and HEVC): the output NAL units equal the model's byte for byte with the right `nal_type`, `is_slice`, `is_idr`; random `valid` and `ready` |
| T28-02 | `slice_tag` | Frame and slice numbering from delimiters and from `frame_sync`; the flags (intra from the mask and from IDR, last slice); wrong slice counts raise `err_count` and resynchronise; non-slice NAL units reach the `ps` port intact |
| T28-03 | `budget_mon` | Sizes against budgets at the 105% boundary (exactly 105%, one byte over, zero budget): `over`, `ratio_q8`, `max_ratio_q8`, counters equal the model; the buffer check |
| T28-04 | `refresh_map` | Random lost sequence numbers over many frames (including the wrap of the 16-bit number and old requests): the commanded masks equal the model; latching at `frame_start`; counters |
| T28-05 | `rc_hook` | Valid budgets reach `target_bytes` within 4 clocks; zero and oversize values rejected with `err_rc`, previous value kept; `qp_bias` range check |
| T28-06 | End to end | Encoder model with rate control (slice sizes follow the budget with an assumed distribution) -> `enc_wrap` -> `slice_pack` -> `slice_unpack`: every slice payload equals the NAL unit; headers carry the right frame, index and flags; a loss pattern fed back through the refresh path produces intra slices in the next frame (intra slices of the model are larger by a factor, and the monitor sees them); the monitor's `n_over` is zero when the model honours the budget and equals the count of injected oversize slices otherwise; 2000 frames |
| L-28, S-28 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 3. Deliverables

`rtl/28-encoder-wrapper/{nal_split,slice_tag,budget_mon,refresh_map,rc_hook,enc_wrap}.sv`, `tests/28-encoder-wrapper/` (encoder model, tests), results below, row in `design/README.md`.

## 4. Open items (all to be measured on the evaluation boards)

- Whether the hard unit can be configured for 8 to 34 independent slices without cross-slice dependencies (VID-004), with per-slice rate control, with intra refresh per slice on command (VID-021) and with parameter changes inside one slice time (VID-020); the VCU documentation and the source review S-4 to S-7 list limits to be confirmed.
- Real slice-size statistics against the budget (the 105% bound), encoder latency, and the rate-buffer behaviour. If the hard unit cannot meet them the custom encoder of module 29 is the fall-back (VID-027).
- The decoder side on the ground unit (a hardware or software decoder, plan row 28) and the concealment are not part of this module.
- Parameter-set transport and the IDR at start-up and after a link loss.
- Not run on a target core.

## 5. Results (implementation commit)

Simulation: cocotb on Verilator (`tests/28-encoder-wrapper`, 7 simulations: `nal_split` for AVC and HEVC, `slice_tag`, `budget_mon`, `refresh_map`, `rc_hook`, and `enc_link` = `enc_wrap` followed by the depacketiser of module 9). All pass. The encoder is `enc_model.py`, a stand-in (Annex-B output, slice sizes drawn from assumed distributions); **nothing here characterises the hard encoder**.

Changes against the plan, found by the tests:

- The intra mask and the budget of a frame are **queued** at the encoder input (`cmd_start`) and used when the frame leaves the encoder (`bs_start`), because the encoder has a latency of at least one frame; the first version applied the newest value and tagged every slice with the wrong frame's intra flag. `tag_mask` is the head of the queue (visible before the pop) so that the tagger, which latches it at the boundary, sees the right entry.
- `budget_mon` compares each slice with the budget **commanded for its frame** (`budget_tag`), not with the value in force when the slice appears.
- `rc_hook` now counts two invalid values in one clock as two errors.
- `budget_mon` uses a combinational 24-bit division for `ratio_q8` (one clock after `done`); for synthesis it must be a multi-cycle path or pipelined (it is not on a data path).

| Test | Result |
|---|---|
| T28-01 | `nal_split`: 6 streams of 3 frames each for AVC and for HEVC (3- and 4-byte start codes, 0 to 2 trailing zeros, payload with `00 00 03` sequences and zero runs, NAL units of 1 to 1500 bytes, random valid and ready): every NAL unit equals the model byte for byte with the right type, slice and IDR flags |
| T28-02 | `slice_tag`: frame and slice numbering from delimiter NAL units and from the sync pulse, flags (commanded intra, IDR, last slice), 7- and 9-slice frames counted as errors, parameter sets and SEI routed to the `ps` port |
| T28-03 | `budget_mon`: 72 slices including exactly 105% (not over), one byte more (over), zero budget, size and budget extremes: `over`, `ratio_q8`, `max_ratio_q8`, counters equal the exact integer model; the buffer check counts a slice once |
| T28-04 | `refresh_map`: 3 configurations (S = 8; S = 12 with a rolling wave of 20 frames; S = 34), 400 random steps each, sequence numbers around the 16-bit wrap, requests for frames older than 16 counted: masks, delayed tag masks and the three counters equal the model |
| T28-05 | `rc_hook`: 300 random commands: valid budgets and QP bias reach the outputs one clock later (the limit was 4), 149 invalid values rejected with the previous value kept |
| T28-06 | End to end, 121 frames of 8 slices (budgets 300 to 600 bytes changing every 20 frames, one frame of encoder latency, 5% slice loss reported through the refresh path one frame later, rolling wave of 40 frames): all 968 slice payloads, headers (frame, index, flags) equal the model; 82 intra slices commanded and flagged; the monitor counted 88 oversize slices, **equal to the number the model produced** (injected 1.3x slices plus intra slices at 1.7x to 2.6x, which a real encoder must hold to the budget by quantisation: the monitor sees them as violations); largest size/budget 2.61; 138 parameter-set and delimiter NAL units routed to the `ps` port intact |
| L-28, S-28 | `-Wall` clean; no latches; `nal_split` 396 cells, `slice_tag` 467, `budget_mon` 5278 (the divider), `refresh_map` 6397, `rc_hook` 249, `enc_wrap` 120 361 cells (34 719 flip-flops: the payload buffer of the packetiser) |
| Mutation | `budget_mon` boundary `>` changed to `>=`: T28-03 fails; start-code detection changed to three zero bytes: T28-01 fails; both restored |

### Limits

- The hard encoder was not simulated or characterised (section 4): slice structure, the adherence to a per-slice budget (the model's intra slices exceed it, and a real encoder has to be configured so that they do not), latency, response time to commands and rate-buffer behaviour are all open and are the purpose of the board measurements.
- The slice index is the arrival counter inside the frame, so the encoder must emit the slices of a frame in order and complete; a lost or reordered slice NAL unit is only noticed through `err_count`. Parameter sets are routed out but their transport (start-up, every IDR, after a link loss) is not designed here.
- The 16-bit sequence numbering `seq = frame x S + idx` is a convention that module 22's refresh queue has to follow.
- Only the AVC and HEVC NAL-unit header types are recognised; the HEVC test used two-byte headers with a fixed second byte.
- Not run on a target core.
