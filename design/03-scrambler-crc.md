# 03 - Scrambler and CRC Engines

Plan entry: module 3 of `spec/18-development-plan.md`, class XS, data plane. Requirements: PHY-005 and VID-004 (every slice is independently decodable, so whitening and error detection must not depend on any other slice), VID-011 (header protected more strongly than payload; the header carries its own CRC). The exact polynomials and seeds are not fixed by the spec; this document fixes them for the prototype (**[E]**, revisit when the frame format of `17` section 4 is written).

## 1. Purpose

- **Scrambler:** whitens the bit stream (breaks long runs, keeps the OFDM spectrum flat, avoids PAPR peaks from repeated payload patterns) and is its own inverse.
- **CRC engine:** detects residual errors after LDPC. Used for the slice header (16 bits) and the slice payload (32 bits); the per-slice authentication tag (module 15) protects against forgery, the CRC against accidental errors when encryption is off.

## 2. Stream convention

Same as module 1: `valid`, `ready`, `data`, `last`; frames are whole words (no `keep`). A frame is the words up to and including the one with `last`. Both blocks are **pass-through with zero latency**: `m_axis_valid = s_axis_valid`, `s_axis_ready = m_axis_ready`; only their internal state advances on a transfer. They can sit anywhere in a stream without adding registers.

Bit and byte order: bit 0 of a word is the first bit in time, byte 0 (bits 7..0) is the first byte. This is the order of the Python reference models in the tests.

## 3. `scrambler`

Additive synchronous scrambler: the output is the input XOR a keystream; descrambling is the same operation with the same seed.

| Parameter | Default | Meaning |
|---|---|---|
| `W` | 32 | Word width in bits (any width from 1) |
| `LEN` | 7 | LFSR length |
| `TAPS` | `7'b1001000` | Feedback taps (bit positions of the state XORed together); the default is the 802.11 polynomial x^7 + x^4 + 1 |
| `SEED` | `7'h7F` | State at the start of every frame (must not be zero) |

LFSR (Fibonacci form): feedback `fb = ^(state & TAPS)`, next state `{state[LEN-2:0], fb}`, keystream bit = `fb`. A word consumes `W` keystream bits, LSB first. After the transfer with `last` the state returns to `SEED`, so every frame (every slice) starts from the same state and a lost slice cannot desynchronise the following ones. The state does not advance when no transfer happens (stalls are free).

Properties: with the default polynomial the keystream repeats after 127 bits (maximal length); a second configuration `LEN=15, TAPS=(1<<14)|(1<<13)` (x^15 + x^14 + 1, period 32767) is provided for payloads where 127 bits is too short.

## 4. `crc_engine`

Generic table-free parallel CRC.

| Parameter | Default | Meaning |
|---|---|---|
| `CRC_W` | 32 | CRC width |
| `POLY` | `32'h04C11DB7` | Generator polynomial (MSB-first notation, without the leading term) |
| `INIT` | `32'hFFFFFFFF` | Initial register value |
| `REFIN` | 1 | Input bytes processed LSB first (reflected algorithm) |
| `REFOUT` | 1 | Output bit order reflected |
| `XOROUT` | `32'hFFFFFFFF` | Final XOR |
| `DW` | 32 | Word width in bits, a multiple of 8 |

Two prototype configurations: **CRC-32/IEEE** (the defaults; the same as zlib and Ethernet; used for the slice payload) and **CRC-16/CCITT-FALSE** (`CRC_W=16, POLY=16'h1021, INIT=16'hFFFF, REFIN=0, REFOUT=0, XOROUT=0`; used for the slice header).

Outputs: `crc_value[CRC_W-1:0]` is the finalised CRC (after output reflection and `XOROUT`) of all bytes accepted so far in the current frame (`INIT`-based; before any byte of a frame it shows the empty-frame value); after the `last` transfer it keeps the frame's final CRC until the first transfer of the next frame. `crc_valid` is a one-clock pulse in the clock after the `last` transfer (the clock in which `crc_value` first shows the final value). A transmitter appends `crc_value` (little-endian for CRC-32, big-endian for CRC-16) after the last data beat; a receiver feeds data plus CRC and checks `crc_value == RESIDUE` at `crc_valid`, where `RESIDUE` is `32'h2144DF1C` for CRC-32/IEEE and `16'h0000` for CRC-16/CCITT-FALSE (verified with the Python library functions); parameter `RESIDUE` carries it and output `crc_ok` is `crc_valid && crc_value == RESIDUE`.

## 5. Test plan

References are the Python functions: a bit-serial LFSR model for the scrambler, `zlib.crc32` and `binascii.crc_hqx(data, 0xFFFF)` for the CRCs. Stream driving and the protocol-stability check are those of module 1 (`tests/common/stream_tb.py`).

| ID | Block | Test | Pass criterion |
|---|---|---|---|
| T3-01 | scrambler | Random frames (1 to 20 words), random back-pressure, W=8 and W=32 | Output equals the bit-serial model word for word |
| T3-02 | scrambler | Scramble then descramble through two instances | Identity |
| T3-03 | scrambler | Frame restart | The first word of every frame is scrambled with the keystream from `SEED`, independent of the previous frame's length |
| T3-04 | scrambler | Keystream period | Default polynomial repeats after exactly 127 bits; `LEN=15` repeats after 32767 bits |
| T3-05 | scrambler | Stall | No state change while `valid` and `ready` are not both high; pass-through is zero-latency (`m_axis_valid` equals `s_axis_valid` in the same clock) |
| T3-06 | crc | CRC-32 over random frames, DW=8, 32, 64 | `crc_value` at `crc_valid` equals `zlib.crc32` of the frame bytes |
| T3-07 | crc | CRC-16/CCITT-FALSE, DW=8 and 16 | Equals `binascii.crc_hqx(frame, 0xFFFF)` |
| T3-08 | crc | Check vector | CRC-32 of the ASCII string `123456789` is `0xCBF43926`; CRC-16 is `0x29B1` |
| T3-09 | crc | Running value | After every accepted word `crc_value` equals the library CRC of the bytes so far |
| T3-10 | crc | Residue and `crc_ok` | Frame plus appended CRC gives `crc_ok`; one flipped bit anywhere gives no `crc_ok` (500 random single-bit errors) |
| T3-11 | crc | Back-to-back frames and stalls | Frames of length 1 follow each other without a gap and with random stalls; one `crc_valid` pulse per frame; correct values |
| L-03, S-03 | both | Lint and Yosys synthesis | `-Wall` clean; no latches; cell counts recorded |

Configurations: scrambler `W=8` and `W=32` (default polynomial), `W=16 LEN=15`; CRC-32 with `DW=8,32,64`; CRC-16 with `DW=8,16`.

## 6. Deliverables

`rtl/03-scrambler-crc/scrambler.sv` and `crc_engine.sv`, `tests/03-scrambler-crc/`, results below, row in `design/README.md`.

## 7. Open items

- Partial last words (frames whose byte count is not a multiple of `DW/8`) need a `keep` field; deferred to module 9 (see the open item in `01`).
- Final polynomial and seed choice with the frame format.
