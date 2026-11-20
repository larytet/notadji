# 05 - Interleaver and De-interleaver

Plan entry: module 5 of `spec/18-development-plan.md`, class S, data plane. Requirements: PHY-001 and PHY-005 (the spec names no interleaver; this is a design choice made here), PHY-011 (slice error rate). Depends on module 1.

## 1. Purpose and decision

Burst errors (a faded group of adjacent subcarriers, an interference spike) hit consecutive coded bits; an LDPC decoder copes better when the damaged bits are spread over the codeword. The interleaver permutes the coded elements of one OFDM symbol so that elements that are adjacent in the coded stream are mapped to subcarriers far apart.

Decision **[E]**: a block interleaver with 16 columns per OFDM symbol (the first permutation of IEEE 802.11), generalised to any block length so that the number of data tones does not have to be a multiple of 16 (the numerology of `02` uses tone counts such as 242). The 802.11 second permutation (a cyclic shift inside groups of constellation bits, which alternates reliable and unreliable bit positions) is **not** included: it is defined only when the block length is a multiple of 16 x s and it interacts with the demapper design (module 14) and with the LDPC code structure; it is recorded as an open item. IEEE 802.11n/ac itself uses no bit interleaver with LDPC, so dropping it is a conservative choice; whether the interleaver is needed at all is to be settled by the simulation SIM-002 and SIM-003 (fading channel), and the module is built so it can be bypassed or removed without touching its neighbours.

The same hardware serves two jobs: on the transmit side it permutes bits (element width 1), on the receive side it permutes soft values (LLRs, element width 6 to 8 bits) in the reverse direction.

## 2. Permutation

Block length `n` elements (1 to `MAX_N`). Write the elements in row order into a matrix with 16 columns and `R = ceil(n/16)` rows (the last row holds `full = ((n-1) mod 16) + 1` elements). Input index `k = 16 r + c` (row r, column c). The interleaver output order reads the matrix column by column, skipping empty cells: the position of input element k in the output block is

- `pos(k) = base(c) + r`, with `base(c) = c R` for `c < full` and `base(c) = full R + (c - full)(R - 1)` for `c >= full`.

Columns `c < full` have R rows, the others R - 1 rows. For `n` a multiple of 16 this is exactly the 802.11 first permutation `i = (n/16)(k mod 16) + floor(k/16)`. `pos` is a bijection on 0..n-1 for every n (tested exhaustively in the model for n = 1 to 4096).

- **Interleaver** (`DEINT=0`): element k arrives in order, is written at address `pos(k)`, and the block is read out sequentially 0..n-1.
- **De-interleaver** (`DEINT=1`): elements arrive in order and are written at addresses 0..n-1; the block is read at addresses `pos(0), pos(1), ..., pos(n-1)`, which restores the original order.

The addresses are generated incrementally (no multiplier): the generator keeps the column c, row r and `base`; stepping within a row adds `R` (if `c < full`) or `R - 1` to `base`; at the end of a row (c = 15) c and base restart and r increases.

## 3. Interface

Module `block_interleaver`, parameters `W` (element width, default 1), `MAX_N` (default 4096, power of two not required), `DEINT` (0 or 1).

| Port | Description |
|---|---|
| `clk`, `rst_n` | as in module 1 |
| `n[$clog2(MAX_N+1)-1:0]` | Block length; sampled with the first element of each block and held for that block (values 0 and above `MAX_N` are clamped to 1 and `MAX_N`) |
| `s_axis_*`, `m_axis_*` | Element stream (`W` bits per beat), module 1 convention; the block ends after exactly `n` accepted elements |
| `err_len` | Pulse for every beat where `s_axis_last` disagrees with the count (as in module 4) |

Buffer: two banks of `MAX_N` elements (ping-pong), so a block is read out while the next one is written. Latency: the first element leaves the clock after the last element of the block has been written (a block of delay inherent in an interleaver). Throughput: one element per clock in and out; with both banks full the input is stalled by `ready`.

Sub-block `il_addr_gen` generates the `pos(k)` sequence for a given `n`.

## 4. Test plan

Python reference: `pos(k)` computed directly from the closed form; the interleaver output is `out[pos(k)] = in[k]`; the de-interleaver output is `out[k] = in[pos(k)]`.

| ID | Test | Pass criterion |
|---|---|---|
| T5-01 | Model self-check | `pos` is a bijection for every n from 1 to 4096; for n a multiple of 16 it equals the 802.11 first permutation formula |
| T5-02 | Interleaver, many n | n in {1, 2, 15, 16, 17, 31, 32, 33, 48, 64, 100, 242, 484, 968, 1000, full MAX_N and others at random}, 3 blocks each, full speed: output equals the model |
| T5-03 | De-interleaver, same set | Output equals the model |
| T5-04 | Round trip | Interleaver then de-interleaver (test wrapper) returns the original for random n and random handshakes; also with element width 8 (LLR) |
| T5-05 | Random valid and ready | Both directions match the model; protocol stability check passes |
| T5-06 | n changes per block | A different n for every block, aligned with the first element (the `pre` hook), while the previous block is still being read |
| T5-07 | Throughput | Steady input period equals n clocks per block (no bubbles) for an always-ready sink |
| T5-08 | Bad `last` | `err_len` pulses at the mismatching beats (the count still closes the block); next blocks correct |
| T5-09 | Clamping | n = 0 behaves as n = 1; n above `MAX_N` behaves as `MAX_N` |
| L-05, S-05 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

Configurations: `W=1, MAX_N=1024` and `W=8, MAX_N=512` for both directions plus the round-trip wrapper; `MAX_N=4096` is exercised once in T5-02/T5-03 by the default configuration.

## 5. Deliverables

`rtl/05-interleaver/il_addr_gen.sv`, `block_interleaver.sv`, `tests/05-interleaver/` (with a test-only round-trip wrapper), results below, row in `design/README.md`.

## 6. Open items

- Second permutation and its interaction with the demapper (module 14) and the code structure.
- Whether the interleaver stays in the design at all (decided by SIM-002 and SIM-003 with the fading channel).
- Memory mapping: the buffer is a flip-flop or distributed array with a combinational read in generic synthesis; block RAM needs a registered read (same open item as module 4).
