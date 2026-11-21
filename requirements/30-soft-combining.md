# R30 - Soft combining of retransmitted slices and heavier decoding (PHY-017)

Source: `spec/01` PHY-017: *"[GU] Heavier decoding in the enhanced ground configuration: at least twice the LDPC iterations of the basic unit and soft (chase) combining of retransmitted slices (MAC-006), within the demodulation-plus-decoding latency of the budget in `02`; the decoder area grows to hold the latency."* Priority O (optional), phase P2. Related: MAC-006 (selective retransmission only before the display deadline), PHY-011 (codeword error rate 1.2e-5), PHY-015 (decoder throughput), LAT-003/LAT-004.

## 1. Scope

In scope: a block that adds the log-likelihood ratios (LLRs) of a retransmitted codeword to those retained from the earlier reception(s), in front of the LDPC decoder of module 20; the policy of what is retained and for how long; the decoder iteration setting of the enhanced unit; a way to add decoder capacity so that the heavier decoding stays within the latency (an array of decoder instances).

Out of scope: the decision to retransmit (module 22 `retx_ctrl`), the transmission of the retransmission, incremental redundancy (different puncturing of the same codeword; chase combining only), the demodulator and de-interleaver (modules 14 and 5, unchanged), integration into the receive chain top level (listed as an open item).

## 2. Definitions

- **Basic unit**: `max_iter` = 10, the value used for the measurements of module 20 (T20).
- **Enhanced unit**: `max_iter` >= 20 (at least twice the basic unit); the decoder register is 6 bits wide (up to 63).
- **Codeword identity (key)**: the pair (slice sequence number `seq[15:0]`, codeword index within the slice `cw[7:0]`), plus the code select of module 13 (`code[2:0]`).
- **Chase combining**: the retransmission carries the same coded bits as the original (same code, same codeword boundaries, same scrambling and ciphertext); the per-bit LLRs of the receptions add.

## 3. Requirements

| ID | Requirement | Acceptance criterion | Verified by |
|---|---|---|---|
| R30-01 | For a codeword whose key matches a retained entry, the combiner shall output, for every LLR position, the saturating sum (to -127..+127) of the incoming LLR and the retained LLR. | Output equals the integer model for every position, key pattern and saturation case. | T30-01, T30-03 |
| R30-02 | A codeword with no retained entry (or a different `code`) shall pass unchanged. | Output equals input; the miss counter increments. | T30-01 |
| R30-03 | The combiner shall retain the LLRs that went into the decoder (the combined values) until the decoder reports success for that codeword; on success the entry shall be freed; on failure it shall stay for a later retransmission. | After a success report the next codeword with the same key is a miss; after a failure report it is a hit. Results are matched to codewords in input order. | T30-02, T30-04 |
| R30-04 | The combiner shall drop all entries of a slice on command (`drop_seq`), and all entries on `drop_all`, to implement MAC-006 (slice past its deadline, no further retransmission). | After the command the keys of the dropped slice miss. | T30-02 |
| R30-05 | The combiner shall hold at least `DEPTH` codewords of up to 1944 LLRs (`DEPTH` a synthesis parameter, default 8; sizing in the design). When all entries are in use the oldest shall be replaced and counted. | Eviction replaces the oldest entry; eviction counter increments; behaviour equals the model. | T30-02 |
| R30-06 | The combiner shall not reduce throughput: one LLR per clock sustained, back-pressure honoured, added latency at most 2 clocks per codeword. No change of the decoder interface. | Back-to-back codewords with random valid and ready equal the model; measured latency. | T30-01, T30-06 |
| R30-07 | A bypass mode shall make the block transparent (basic unit). | In bypass mode the output equals the input and no entry is created. | T30-01 |
| R30-08 | Chase combining of two receptions of the same codeword shall give a gain in signal-to-noise ratio of at least 2.0 dB at a codeword error rate of 10% (theory for two equal-SNR receptions: 3 dB). | Frame error rate of two combined receptions at SNR s equals that of one reception at s + g with g >= 2.0 dB (model, N = 648 and N = 1944). | T30-05 |
| R30-09 | The enhanced iteration setting (20 iterations) shall lower the frame error rate against the basic setting (10 iterations) at the same SNR, and the cost (clocks per codeword) shall be reported. | FER(20) <= FER(10) at all measured points; the clocks per codeword reported. | T30-05 |
| R30-10 | An array of `P` decoder instances shall decode `P` codewords concurrently, accept codewords in order and deliver results in order, so that the heavier decoding can be kept within the latency by adding area. | Output of the array equals the single-instance model for any `P`; throughput grows with `P` until the input rate (one LLR per clock) is the limit; measured. | T30-06 |
| R30-11 | The block combination (combiner, decoder, result feedback) shall decode a codeword that the decoder alone does not decode, from two receptions that individually fail. | Integration test in RTL with real decoder: frames whose single receptions fail and whose combination decodes. | T30-04 |
| R30-12 | The constraints that chase combining puts on other layers shall be written down. | Section 4 of this file and the design file list them. | review |

## 4. Constraints on other layers (to be honoured by the MAC and the security layer)

1. A retransmission that is meant to be combined shall carry exactly the same coded bits: same MCS and code (modulation may differ; LLRs are per coded bit), same codeword boundaries, same scrambler seed, same ciphertext. The nonce of the authenticated encryption (module 15) must therefore be derived from the slice sequence number and not from the frame in which it is sent. Re-sending identical ciphertext under the same nonce is safe; sending *different* plaintext under the same nonce is not.
2. A **refresh** (module 22, new content for the same screen area) is a new slice with a new sequence number and a new nonce; it is never combined (it will simply miss).
3. The slice CRC and the AEAD tag are checked on the decoded slice as now; the combiner only improves the decoder input.
4. The key `seq` is 16 bits and wraps; entries are dropped on the deadline (R30-04) well before the wrap, and the code select is part of the match, so a stale entry cannot be combined into a different codeword.

## 5. Assumptions and open points

- LLR magnitudes of different receptions are on the same scale (the demapper `llr_shift` is the same, or the receiver corrects for it); the equaliser `csi` already weights by channel gain, which is the right weighting for maximal-ratio style combining.
- The decoder latency of the enhanced setting: see the design (clocks per iteration); the 10 us codeword-decode figure of PHY-015 is not reachable by iterations alone, the array of instances is the means.
- Memory: DEPTH x 1944 x 8 bit (15.5 kB per entry at 8 bit; 124 kB for 8 entries) should map to block RAM; the RTL here uses a registered-read memory array.
