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

Ports: `clk`, `rst_n`; `mode` (0 bypass, 1 combine); `code[2:0]`, `key_seq[15:0]`, `key_cw[7:0]`, `maxit[5:0]` (sampled with the first LLR of a codeword; `code` and `maxit` come out again as the sideband `m_code`, `m_maxit`, valid with every LLR of the codeword, so that the decoder sees them aligned with its first LLR despite the 2 clocks of latency); `s_axis_valid/ready/data[7:0] (signed)/last`; `m_axis_valid/ready/data[7:0]/last`; `res_valid`, `res_ok` (one pulse per decoded codeword, in input order); `drop_seq_valid`, `drop_seq[15:0]`, `drop_all`; status `n_hit`, `n_miss`, `n_evict`, `n_ovf` (16-bit counters), `occupancy`.

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

## 8. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/30-soft-combining/run_tests.sh` (7 simulations, then the statistics script), `tests/30-soft-combining/mutate.sh`, `tests/common/lint_synth.sh tests/30-soft-combining`. Files: `rtl/30-soft-combining/{llr_combiner,ldpc_dec_array,soft_rx_decode}.sv`, `tests/30-soft-combining/`.

| Test | Result |
|---|---|
| T30-01 | Random streams (60 codewords of N = 648 and 1944, keys from a small set, `res_ok` random, bypass changes, random valid and ready; also `DEPTH` = 3 / `PEND` = 2 with 40 codewords): every output LLR, the sideband and the counters equal the model (27 hits, 25 misses, 1 replacement in the large configuration; 9 hits, 26 misses, 13 replacements in the small one) |
| T30-02 | Directed: a failed codeword is kept and combined with the next reception (a + b), a decoded one is freed (the next is a miss), a codeword with another `code` and the same key misses, `drop_seq` and `drop_all` remove entries, the oldest entry is replaced when `DEPTH` is exceeded, and with `PEND` = 2 and no results the first LLR of the third codeword waits (`n_ovf` counts the stall) |
| T30-03 | Saturation: 127 + 127 gives 127, 127 + (-127) gives 0, -128 inputs are clamped to -127, a three-reception sum equals hand-computed values (independent of the model) |
| T30-04 | `soft_rx_decode` (combiner and the real decoder of module 20) on codes 0 and 7, 12 frames at an Eb/N0 where about half the single receptions fail, 10 and 20 iterations: decoder output, `m_ok`, `m_iters` equal the model of (combine, decode) for every reception; 6 frames decoded at once, **6 failed the first reception and were decoded from the combination, 5 of them would also have failed on the second reception alone**; the occupancy returns to zero; bypass gives the plain decoder result and creates no entry; `drop_seq` removes the retained entry |
| T30-05 | Model statistics, 240 frames per point (N = 648) and 96 (N = 1944), rate 1/2, Eb/N0 per reception, FER 10% point: **one reception 2.19 dB, two combined -0.88 dB (gain 3.07 dB), three combined -2.49 dB (gain 4.68 dB)** for N = 648; 2.25, -0.87 (gain 3.12), -2.27 (gain 4.52) for N = 1944 (10 iterations); with 20 iterations the gains are 3.06 and 3.09 dB. The gain is the theoretical 3 dB of two equal receptions (R30-08 asks 2.0). **20 against 10 iterations: 0.18 dB (N = 648) and 0.41 dB (N = 1944) at FER 10%** (R30-09: FER(20) <= FER(10) at every point within 3 sigma: holds). |
| T30-06 | Array: ordered results and `m_ok`, `m_iters` equal the model for mixed codes (random handshakes) for P = 1, 2, 3, 4. Information throughput at 200 MHz with an always-valid source of one LLR per clock (8 codewords): N = 1944 R5/6: **126 Mbit/s with P = 1, 161 Mbit/s with P = 2, 3, 4** (2013 clocks per codeword, the LLR input rate); N = 1944 R1/2: 58 (P = 1), 93 Mbit/s (P >= 2, 2087 clocks); N = 648 R1/2: 42, 66, 87, 84 Mbit/s for P = 1, 2, 3, 4. 20 iterations against 10 change the throughput by at most 6% for P >= 2 (the frames mostly converge early at these SNRs; N = 1944 R1/2 with P = 2 goes from 2087 to 2444 clocks per codeword). |
| M-30 | Seven mutants of `llr_combiner` (no saturation; never free on success; key match ignoring `cw`; `drop_seq` ignored; replacement of the lowest index instead of the oldest; hit not added; result `ok` ignored): all seven fail at least two tests |
| L-30, S-30 | `-Wall` clean for `llr_combiner`, `ldpc_dec_array` (P = 1, 2) and `soft_rx_decode`; Yosys on `llr_combiner`: 304516 cells, 125204 flip-flops (the 8 x 1944 x 8 bit memory as flip-flops), no latches; the array and the top contain the decoder of module 20 and are not synthesised (Yosys does not finish for the decoder, see module 20) |

### What this means

- **Chase combining works as specified**: the gain of two receptions is the theoretical 3 dB (3.1 dB measured), three receptions 4.5 dB; the cost is a 2-clock latency and one memory of `DEPTH` x 1944 bytes.
- **More iterations help little at the waterfall**: 0.2 to 0.4 dB for doubling from 10 to 20 iterations. PHY-017's "at least twice the iterations" is therefore a modest gain; the soft combining (3 dB) is the large part. The cost in decoder time is small when the frames converge early and up to 17% more clocks per codeword (N = 1944 R1/2, P = 2) when they do not.
- **PHY-015 finding:** an array of two decoders at one LLR per clock reaches 161 Mbit/s of information only for R5/6 (N = 1944), because the input rate (one LLR per clock) bounds the decoded rate at `R x 200` Mbit/s (R = 3/4: 150 Mbit/s, R = 1/2: 100 Mbit/s, measured 93 because of the load and output gaps). A rate of 155 Mbit/s at R <= 3/4 needs two LLRs per clock into the decoder (the de-interleaver output and the demapper serializer are the 1-LLR-per-clock bottleneck already noted in module 21). The decoder itself is not the limit once P >= 2.

### Limits

- Chase combining only; the retransmission must carry the same bits (section 4 of the requirements: nonce from the sequence number; a refresh is a new slice and misses).
- The combiner is not wired into `rx_chain` (module 21) and the MAC flag for an identical retransmission does not exist yet (module 22); the tests drive it with the decoder directly.
- Statistics are with the bit-exact model of module 20 (AWGN, BPSK-equivalent LLRs at a fixed scale), 96 to 240 frames per point; the 10% crossing has an uncertainty of about 0.1 dB.
- `DEPTH` x 1944 bytes was not mapped to block RAM (flip-flops here).
