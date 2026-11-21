# 30 - Soft Combining of Retransmitted Slices and Decoder Array (PHY-017)

Requirements: `requirements/30-soft-combining.md` (R30-01 to R30-12). Plan position: after module 29; class M, data plane, ground-unit receive path between the de-interleaver (module 5) and the LDPC decoder (module 20). Optional requirement PHY-017, phase P2.

## 1. Purpose and decisions

Chase combining adds the LLRs of the receptions of the same codeword. With two equal-SNR receptions the combined LLR has twice the signal-to-noise ratio (3 dB). The retained LLRs are those that went into the decoder, so a third reception adds to the sum of the first two.

Decisions **[E]**:
- **Saturating 8-bit sum** (-127..+127), the decoder's input width, so the decoder is unchanged. The decoder is nearly scale invariant (normalised min-sum), so saturating costs a little at very high confidence only, where the codeword is already decodable.
- **Combine at codeword granularity**, key = (`seq`, `cw`, `code`). Slice-level retention would store all 86 codewords of a slice for every slice in flight; retaining only *failed* codewords (freed on success, R30-03) keeps the memory small: a slice fails rarely (PHY-011: 1e-3), and at the code-word error rate of 1.2e-5 per codeword the expected retained set is a few codewords.
- **Free on success, keep on failure**: the decoder reports `ok` per codeword; entries are written for every codeword (the cost is one write per LLR) and freed when the result arrives. No write-enable decision before the decoder result is needed, so no latency is added to the decoder path.
- **Replacement of the oldest entry** when full; counted in `n_evict`. **Drop on deadline** (MAC-006) by `drop_seq`.
- **Decoder iterations** are the existing `max_iter` input (6 bits): basic unit 10, enhanced unit 20 (or more). The cost is measured (clocks per codeword). The latency is held by an **array of `P` decoder instances** (`ldpc_dec_array`): codewords are dealt to instances round-robin and the results merged in order. Throughput saturates at the input rate (1 LLR per clock), which is also a finding for PHY-015 (see results).

## 2. Block `llr_combiner`

Parameters: `DEPTH` (retained codewords, default 8), `NMAX` (1944), `PEND` (pending results, default 8).

Ports: `clk`, `rst_n`; `mode` (0 bypass, 1 combine); `code[2:0]`, `key_seq[15:0]`, `key_cw[7:0]` (sampled with the first LLR of a codeword); `s_axis_valid/ready/data[7:0] (signed)/last`; `m_axis_valid/ready/data[7:0]/last`; `res_valid`, `res_ok` (one pulse per decoded codeword, in input order); `drop_seq_valid`, `drop_seq[15:0]`, `drop_all`; status `n_hit`, `n_miss`, `n_evict`, `n_ovf` (16-bit counters), `occupancy`.

State: per slot `valid`, `seq`, `cw`, `code`, `stamp` (16-bit allocation stamp); a memory of `DEPTH x NMAX` signed bytes with registered read; the pending FIFO (depth `PEND`) of `{used, slot, seq, cw}` pushed with every codeword (`used` = 0 in bypass); an allocation counter.

Order of events within one clock (the model uses the same order):
1. If a first LLR is accepted: lookup. In bypass mode: no lookup, no entry (push `used` = 0). Otherwise a hit is a valid slot with equal `seq`, `cw` and `code`; on a miss a free slot is allocated, or the slot with the largest age (`alloc - stamp`) is replaced (`n_evict`); the slot gets the key and a new stamp; push to the pending FIFO. If the pending FIFO is full the first LLR is not accepted (`s_axis_ready` low) and `n_ovf` counts the stall cycles.
2. If `res_valid`: pop the pending FIFO; if `used` and the slot is valid with the same key and `res_ok`, free the slot; otherwise nothing (a failed codeword stays, a replaced slot is ignored).
3. If `drop_seq_valid`: free all slots with `seq` = `drop_seq`; `drop_all` frees all slots.

Datapath, two stages: stage A (accept when the output register is free or being taken): the slot and index address the memory (read starts), the LLR, `last`, `hit` are registered. Stage B: `y = hit ? sat127(x + stored) : x`; written back to the same address and presented at the output register. Latency 2 clocks, one LLR per clock sustained; `s_axis_ready` is combinational from `m_axis_ready` (single skid-free pipeline: all stages advance together).

## 3. Block `ldpc_dec_array`

`P` instances of `ldpc_dec` (module 20). `code` and `max_iter` go to all instances (each samples them with the first LLR of its codeword). Codeword `n` goes to instance `n mod P`; `s_axis_ready` is the ready of that instance. Outputs are merged in the same order: the output selects instance `n mod P` for codeword `n`, passes its words, then advances after `last`. `m_ok` and `m_iters` follow the selected instance. `err_len` is the OR. A new codeword waits only while its instance is still busy, so up to `P` codewords are in the decoder at the same time.

`soft_rx_decode` (top): combiner followed by the array; `res_valid` is the first output word handshake and `res_ok` is `m_ok`.

## 4. Test plan

Python model of the combiner (the event order of section 2, driven by what the testbench observes on the DUT's handshakes, so that the model sees the same clock order), the bit-exact LDPC model of module 20 (`dec_model.py`), the encoder of module 16.

| ID | Test | Pass criterion |
|---|---|---|
| T30-01 | Bit-exact, random | 400 codewords of N = 648 and 1944 with keys from a small set (many hits), random `res_ok`, random valid and ready, drop events and bypass changes: every output LLR equals the model; counters equal; protocol stability |
| T30-02 | Policy, directed | Failure keeps and success frees; `drop_seq` and `drop_all`; replacement of the oldest with `DEPTH` + 1 failing codewords; a different `code` with the same key misses; reuse of a freed slot; pending FIFO full stall |
| T30-03 | Saturation | Sums beyond 127 and below -127 saturate; input -128 treated as -127 range check; a three-reception sum |
| T30-04 | RTL integration with the real decoder | `soft_rx_decode` (P = 1) on code 0 (N = 648 R1/2) and code 7: frames received twice with independent noise at an Eb/N0 where one reception often fails; decoder output, `m_ok`, `m_iters` equal the model of (combine then decode) for every frame; at least one frame fails alone twice and decodes combined |
| T30-05 | Statistics (model) | FER against Eb/N0 for N = 648 R1/2 and N = 1944 R1/2: one reception, two combined, three combined, 10 against 20 iterations; the equivalent SNR gain of two combined receptions at FER 10% is reported (R30-08 >= 2.0 dB); FER(20) <= FER(10) (R30-09) |
| T30-06 | Array | `P` = 1, 2, 3, 4: ordered results equal the single-instance model for 12 codewords of mixed codes; clocks per codeword and information throughput at 200 MHz measured for 10 and 20 iterations |
| M-30 | Mutation checks | (a) no saturation, (b) never free on success, (c) key match ignoring `cw`, (d) result order not respected: each makes at least one test fail |
| L-30, S-30 | Lint and synthesis | `-Wall` clean; Yosys: no latches (the combiner; the array is as large as `P` decoders and is expected not to complete, as module 20) |

## 5. Deliverables

`rtl/30-soft-combining/{llr_combiner,ldpc_dec_array,soft_rx_decode}.sv`, `tests/30-soft-combining/`, results below, a row in `design/README.md`.

## 6. Open items

- Wiring `soft_rx_decode` into the receive chain of module 21 and the retransmission flag of module 22 (the MAC must say "identical retransmission" and use a nonce derived from the sequence number): not done here.
- Memory sizing: `DEPTH` x 1944 bytes; block-RAM mapping not verified (Yosys / Vivado).
- Incremental redundancy (different puncturing) would gain more than chase combining at high code rates; out of scope.
- Combining of LLRs of different demapper scales (different `llr_shift`) is assumed equal.
