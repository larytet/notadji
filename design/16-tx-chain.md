# 16 - Transmit Chain Integration

Plan entry: module 16 of `spec/18-development-plan.md`, class M, data plane. Requirements: PHY-001 to PHY-005, PHY-007, PHY-013 (the first end-to-end transmit path). Integrates modules 1 (conversion), 4 (cyclic prefix), 5 (interleaver), 6 (mapper), 7 (preamble and pilots), 12 (IFFT) and 13 (LDPC encoder). Not included here: scrambling and CRC (modules 3 and 9 sit before this chain on the byte stream), encryption (15), the radio interface (11) and the timeline (10).

## 1. PHY framing defined here [E]

The spec does not define how a slice frame maps onto codewords and OFDM symbols; this section does, for the prototype.

1. **Frame**: one byte stream (a slice frame of `09`, possibly encrypted by `15`), bits taken LSB first within each byte.
2. **Codeword packing** (VID-004 / PHY-005, slice-aligned): the frame's bit string is cut into messages of K bits (K of the selected code, `13`); the last message is padded with zero bits to K. Every slice therefore occupies a whole number of codewords. The receiver learns the true length from the slice header (`09`).
3. **Coded bit stream**: the N-bit codewords in order, bit 0 of a codeword first.
4. **Symbol blocks**: the coded bit stream is cut into blocks of `Ncbps = Nd x nb` bits (`Nd` data tones of the symbol, `nb` bits per tone for the modulation); the last block of the frame is padded with zero bits. Data tones per FFT size (`07`): 48, 108, 234, 468 for N = 64, 128, 256, 512; `Ncbps` must not exceed 4096 (the interleaver of `05`), which limits the chain to N <= 512.
5. **Per symbol**: the block is interleaved (module 5, 16 columns), grouped into `nb`-bit words (bit 0 first), mapped (module 6), placed on the data tones; pilots and nulls come from the tone plan of module 7 (`kind` 2, polarity restarted at the first data symbol of a frame); the 16-bit I and Q spectrum goes through the inverse FFT (module 12, shift mask from the configuration) and the cyclic prefix is added (module 4).
6. **Frame on air**: the preamble symbols of module 7, each through IFFT and prefix: STF, LTF, LTF; then the data symbols. The output is the sample stream (32-bit words `{Q, I}`), `last` on the final sample of the frame.

Configuration (stable for the whole frame, sampled when the frame starts): `fft_log2` (6 to 9), `cp_sel`, `mod` (0 to 4), `code` (as `13`), `shift_mask` (the IFFT scaling, `12` section 4).

## 2. Glue blocks (new in this module)

| Block | Function |
|---|---|
| `msg_bits_pack` | Bit stream (one bit per beat, `last` on the final bit of the frame) to 32-bit message words, K bits per codeword (last word padded), zero padding of the final codeword generated internally; flag `m_frame_last` on the words of the final codeword |
| `cw_to_bits` | Codeword words (32-bit, N bits valid) to a bit stream, N bits per codeword with `last` at the codeword end, frame flag carried from the message side |
| `sym_blocker` | Bit stream to blocks of `Ncbps` bits (`last` at the end of each block), zero padding after the final bit of the frame, a pulse per completed block with the frame-final flag |
| `bit_packer` | `nb` bits to one tone word (8-bit, low `nb` bits), `last` on the last tone of a block |
| `tx_assembler` | Merges the tone plan stream of module 7 with the mapper samples: null bins give 0, data bins take the next mapper sample, pilot and training bins take the value from module 7 |
| `tx_chain` | The top: wiring of the blocks above and the modules 1, 4, 5, 6, 7, 12, 13, plus the frame controller |

Frame controller: after the first input byte of a frame it commands the preamble symbols (kinds 0, 1, 1), then one kind-2 command per completed symbol block (the first with `frame_start`); it counts blocks until the frame-final block is known (`nsym`); it counts output symbols and sets `m_axis_last` on the last sample of symbol number `3 + nsym`; new input bytes are refused from the last byte of a frame until its last sample has left (one frame at a time).

## 3. Interface

`tx_chain`: `clk`, `rst_n`, configuration inputs above, `s_axis_*` (8-bit bytes with `last`), `m_axis_*` (32-bit samples `{Q, I}` with `last`), `err` (sticky pulse on a malformed condition: `last` mismatch in a submodule, or `Ncbps` above 4096).

## 4. Test plan

A Python golden model of the whole chain written from section 1 (using the models of the earlier modules: LDPC encoding with the generated base matrices, `pos()` of the interleaver, the mapper constellation, the tone plan and preamble symbols, the bit-exact FFT model and the cyclic-prefix rule) predicts every output sample.

| ID | Test | Pass criterion |
|---|---|---|
| T16-01 | Glue blocks individually (cocotb, small vectors) | `msg_bits_pack`, `cw_to_bits`, `sym_blocker`, `bit_packer`, `tx_assembler` match their Python definitions, including padding and flags |
| T16-02 | Whole chain, bit-exact | For several frames over the combinations (N = 64, 128, 256; modulation 0 to 4; several codes and cyclic prefixes): all output samples equal the golden model |
| T16-03 | Closed loop with an ideal receiver | The output samples of T16-02 are demodulated in floating point (remove prefix, FFT with `numpy`, divide by the scaling), the data tones are hard-demapped, de-interleaved, and the codeword parity checks (`H c = 0`) pass and the recovered bytes equal the sent bytes |
| T16-04 | Frame structure | Sample counts per symbol equal `N + N/(prefix divisor)`; total equals `(3 + nsym)` symbols; `last` only on the final sample; the preamble symbols are the first three |
| T16-05 | Frame back to back, random handshakes | Several frames in a row with different configurations and random valid and ready: all equal the model; the input is refused while a frame drains |
| T16-06 | Padding | Frames whose length is not a multiple of K bits and whose coded length is not a multiple of `Ncbps` are padded with zeros exactly as in section 1 (checked through the model and the closed loop) |
| T16-07 | Throughput and latency | Samples per clock and the delay from the first byte to the first sample recorded |
| L-16, S-16 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 5. Deliverables

`rtl/16-tx-chain/*.sv`, `tests/16-tx-chain/` (golden model, tests), results below, row in `design/README.md`.

## 6. Open items

- Scrambling inside the chain (module 3 is applied to the byte stream outside); whether the PAPR reduction (module 26) belongs between the IFFT and the prefix.
- Header protection (VID-011) with a lower code rate for the first codeword: not in this revision.
- Several frames in flight (the chain accepts one frame at a time).
- N = 1024 (the `Ncbps` limit of the interleaver).
