# 09 - Slice Packetiser and Depacketiser

Plan entry: module 9 of `spec/18-development-plan.md`, class S, data plane. Requirements: VID-004 (each slice independently decodable and independently protected: own header, authentication tag, slice-aligned codewords and acknowledgement bit), VID-011 (header protected more strongly than the payload), PHY-005 (slice-aligned codeword packing). Depends on module 1 (FIFO) and module 3 (`crc_engine`). The format below is a prototype choice **[E]** and is the "slice header format" item of `17` section 4 and `18` section 5; the per-slice authentication tag (module 15) is added after this layer and is not part of it.

## 1. Slice frame format

One slice is carried as one frame of bytes: header, payload, payload CRC. Frames are whole bytes; the stream interface is the byte stream of module 1 (`W` = 8).

| Bytes | Field | Meaning |
|---|---|---|
| 0 | `flags` | bits 3..0 the four flag bits given by the encoder (bit 0 intra-refresh slice, bit 1 last slice of the frame, bits 2 and 3 reserved); bits 7..4 format version, 0 in this revision |
| 1, 2 | `frame` | Frame sequence number, 16 bits, little-endian |
| 3 | `idx` | Slice index inside the frame (0 to 33, VID-004) |
| 4, 5 | `len` | Payload length in bytes, 16 bits, little-endian (0 to `MAX_BYTES`) |
| 6, 7 | header CRC | CRC-16/CCITT-FALSE (`03`: poly 0x1021, init 0xFFFF) over bytes 0 to 5, big-endian |
| 8 ... 8+len-1 | payload | Slice bytes as produced by the encoder |
| 8+len ... 11+len | payload CRC | CRC-32/IEEE (zlib) over the payload, little-endian; for `len` = 0 the value is 0 |

Overhead is 12 bytes per slice (about 1% of a 1.2 kB slice). The header is short and self-checking so that a damaged payload still identifies its slice (the receiver can mark the right acknowledgement bit and conceal the right region); the header is intended to be sent with the stronger protection of VID-011 by the PHY framing, which is not done here.

## 2. `slice_pack` (transmit)

Parameter `MAX_BYTES` (default 4096; the largest payload and the depth of the payload buffer). Input: payload byte stream with `last`; sideband `meta_frame[15:0]`, `meta_idx[7:0]`, `meta_flags[3:0]`, sampled with the first byte of each slice. Output: byte stream of the frame above with `last` on the last CRC byte.

Behaviour: the payload goes into a FIFO while its length is counted; at `last` a record (length and metadata) is queued; the output state machine then sends the header, the payload (read from the FIFO through a CRC-32 engine) and the CRC. Store-and-forward: the first output byte leaves after the last payload byte has been written (the length is in the header). The next slice can be written while the previous one is being sent, as long as the FIFO has room (up to four queued records). A slice longer than `MAX_BYTES` is not supported (the input stalls forever); the encoder's rate control (VID-006) bounds the slice size.

## 3. `slice_unpack` (receive)

Input: frame byte stream with `last` (the PHY delivers one frame per slice; bytes after the payload CRC, such as codeword padding, are ignored). Outputs: payload byte stream (`last` on the final payload byte, cut-through: payload bytes are forwarded as they arrive) and one status pulse per input frame.

Status fields: `st_valid` (one clock), `st_hdr_ok` (header CRC good and `len` not above `MAX_BYTES`), `st_crc_ok` (payload CRC good; 0 when the header was bad), `st_trunc` (the frame ended before `8 + len + 4` bytes), `st_frame`, `st_idx`, `st_flags`, `st_len` (from the header; undefined when `st_hdr_ok` is 0).

Rules: if the header CRC fails, the payload is **not** forwarded (nothing is known about it) and the status shows `st_hdr_ok` = 0. If the header is good, the payload is forwarded before its CRC is known; the status, a few clocks after the last payload byte (after the four CRC bytes), says whether it was good, and the consumer discards or conceals a bad slice (VID-010). A frame that ends early gives `st_trunc` = 1 and `st_crc_ok` = 0 (the forwarded part of the payload ends with `last` so the stream is not left open).

## 4. Test plan

Python model of the format (`zlib.crc32`, `binascii.crc_hqx`) builds frames and expected outputs.

| ID | Block | Test | Pass criterion |
|---|---|---|---|
| T9-01 | pack | Random slices (payload 0 to 600 bytes, random metadata), full speed | Output frame equals the model byte for byte, `last` on the final byte |
| T9-02 | pack | Random valid and ready, several slices queued | Same; no loss; stream protocol stable |
| T9-03 | pack | Slice of exactly `MAX_BYTES` and of 1 byte, and zero length | Correct frames (zero length gives CRC 0) |
| T9-04 | pack | Throughput | Back-to-back slices leave the output with no idle clock inside a frame; the gap between frames is at most 2 clocks while data is queued |
| T9-05 | unpack | Frames from the model, full speed and random handshakes | Payload equals the original; status fields equal the metadata; `st_hdr_ok` and `st_crc_ok` set |
| T9-06 | unpack | Padding after the CRC (0 to 40 extra bytes) | Ignored; status unchanged |
| T9-07 | unpack | Single-bit error in every header byte position (all 64 bits) | `st_hdr_ok` = 0 for every one; no payload forwarded |
| T9-08 | unpack | Single-bit error in the payload and in the CRC | `st_hdr_ok` = 1 and `st_crc_ok` = 0 for every tested error (200 random) |
| T9-09 | unpack | Truncated frames (ending inside the header, the payload, the CRC) | `st_trunc` = 1 (or `st_hdr_ok` = 0 inside the header); the stream is closed with `last` when payload bytes were forwarded; the next frame is received correctly |
| T9-10 | unpack | `len` above `MAX_BYTES` with a valid header CRC | `st_hdr_ok` = 0 |
| T9-11 | both | Loop-back (pack followed by unpack): random slices, handshakes | Payload and metadata recovered; `st_crc_ok` = 1 |
| L-09, S-09 | both | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

Configuration: `MAX_BYTES` = 4096 (default) for pack and unpack; a small `MAX_BYTES` = 64 configuration exercises the limits quickly.

## 5. Deliverables

`rtl/09-slice-packetiser/slice_pack.sv`, `slice_unpack.sv`, `tests/09-slice-packetiser/` (with a loop-back wrapper), results below, row in `design/README.md`.

## 6. Open items

- Whether the header should carry a timestamp for latency measurement (LAT-004) and the acknowledgement bitmap fields (MAC-004); they travel in the MAC frame, not in each slice, in this revision.
- The partial-word (`keep`) question raised in modules 1 and 3 does not arise here: the frame is a byte stream; byte-to-word conversion is module 1's width converter.
- Header protection (VID-011) is a PHY/MAC task (code rate of the header codeword), not part of this layer.
