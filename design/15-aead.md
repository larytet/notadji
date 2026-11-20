# 15 - Authenticated Encryption (ChaCha20-Poly1305)

Plan entry: module 15 of `spec/18-development-plan.md`, class M, data plane. Requirements: SEC-002 (link encryption ChaCha20-Poly1305 by default, per-slice authentication tag, anti-replay counter, small latency impact), HSI-004 (the link encryption is a hardware block). Depends on module 1 (stream convention). Specification of the algorithm: RFC 8439.

## 1. Purpose and scope

Encrypts a slice frame and authenticates it with the 16-byte Poly1305 tag; the decryptor checks the tag. Design stance: a **hardware block that is fast enough but small**: one ChaCha quarter-round per clock and an 8-bit-digit sequential Poly1305 multiplier, because the required rate (80 Mbit/s, 10 MB/s) is far below what the clock allows. One frame is processed at a time.

Scope: the AEAD transform only. The key (256 bit) and the nonce (96 bit) are inputs; deriving the nonce from the frame number, slice index and direction, the anti-replay window and key management (pairing, SEC-001) belong to the MAC and security layers (modules 22 and later). The nonce must never repeat under one key: the caller guarantees it.

## 2. Frame handling

The input frame is `AAD || payload`: the first `aad_len` bytes (0 to 255, for example the 8-byte slice header of `09`) are authenticated but not encrypted; the rest is the payload. The AEAD construction is exactly RFC 8439 section 2.8: the one-time Poly1305 key is the first 32 bytes of the ChaCha20 block with counter 0, the payload is encrypted with the ChaCha20 keystream starting at counter 1, and the tag is Poly1305 over `pad16(AAD) || pad16(ciphertext) || le64(len AAD) || le64(len ciphertext)`.

- **Encrypt** (`decrypt` = 0): output frame is `AAD || ciphertext || tag` (16 bytes longer than the input), `last` on the final tag byte.
- **Decrypt** (`decrypt` = 1): the input frame is `AAD || ciphertext || tag`; the output frame is `AAD || plaintext` (16 bytes shorter) with `last` on its final byte; the plaintext is released as it is decrypted (cut-through) and a status pulse tells afterwards whether the tag was good (`st_ok`); a consumer discards the frame when `st_ok` is 0 (the same rule as the CRC status of `09`). A decrypt input shorter than `aad_len + 16` bytes gives `st_ok` = 0 (`st_short` = 1) and no output.

## 3. Blocks

- `chacha_block`: sequential ChaCha20 block function (80 quarter-round steps plus an add-back), 64 bytes of keystream per call, about 82 clocks.
- `poly1305`: Poly1305 accumulator `acc <- (acc + block + 2^128) x r mod (2^130 - 5)` processed as 17 byte digits per block (Horner with a lazy reduction), final reduction and addition of `s` for the tag; about 19 clocks per 16-byte block.
- `tail_hold`: delays a byte stream by 16 bytes and presents the last 16 bytes of the frame as a separate tag word (used by decrypt).
- `aead`: the controller: the frame state machine, the byte datapath (XOR with the keystream), the 16-byte MAC block assembly with padding and length block, and the tag output or comparison.

The ChaCha engine prefetches the next keystream block while the current one is used, and the MAC block is submitted while the next one is assembled, so the byte rate is limited mainly by the Poly1305 step (a 16-byte block per about 19 clocks, about 0.85 byte per clock).

## 4. Interface

`aead`: `clk`, `rst_n`, `key[255:0]`, `nonce[95:0]` (little-endian byte strings: byte `k` in bits `8k+7 .. 8k`), `aad_len[7:0]`, `decrypt`, all sampled with the first byte of a frame; `s_axis_*` and `m_axis_*` 8-bit byte streams; `st_valid`, `st_ok`, `st_short` (one-clock pulses at the end of a frame; for encrypt `st_ok` = 1).

## 5. Test plan

The reference is the Python `cryptography` package (`ChaCha20Poly1305` for the whole construction, `Poly1305` and `ChaCha20` for the engines).

| ID | Test | Pass criterion |
|---|---|---|
| T15-01 | `chacha_block` | For random keys, nonces and counters the 64 keystream bytes equal the `ChaCha20` stream of the reference (zeros encrypted) |
| T15-02 | `poly1305` | For random one-time keys and messages that are multiples of 16 bytes, the tag equals `Poly1305.generate_tag` of the reference; the maximum-value edge cases (blocks of 0xFF, keys with all bits set) are included |
| T15-03 | Encrypt, whole construction | For AAD of 0 to 20 bytes and payloads of 0 to 300 bytes (including 0, 1, 15, 16, 17, 63, 64, 65, 127, 128, 129), random key and nonce, the output frame equals `AAD || ciphertext || tag` of the reference |
| T15-04 | Decrypt | The output frame equals `AAD || plaintext`; `st_ok` = 1 |
| T15-05 | Tamper detection | A single flipped bit anywhere in `AAD || ciphertext || tag` (200 random positions) gives `st_ok` = 0; the nonce or key change gives `st_ok` = 0 |
| T15-06 | Short decrypt input and empty payload | Fewer than `aad_len + 16` bytes gives `st_short` = 1 and `st_ok` = 0 (including a frame of 16 bytes or more whose AAD would be cut short) and no stuck state; a 16-byte frame with `aad_len` = 0 (empty message) verifies; AAD-only frames encrypt and decrypt; the next frame is processed correctly |
| T15-07 | Handshakes and back-to-back frames | Random valid and ready, several frames in a row with different keys, nonces, AAD lengths and modes: all equal the reference |
| T15-08 | Throughput | Bytes per clock for a 1200-byte payload recorded; at least 0.5 byte per clock |
| T15-09 | `tail_hold` | The held-back stream equals the input minus the last 16 bytes, the tail word equals the last 16 bytes, `last` on the final payload byte, shorter input flagged |
| L-15, S-15 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 6. Deliverables

`rtl/15-aead/{chacha_block,poly1305,tail_hold,aead}.sv`, `tests/15-aead/`, results below, row in `design/README.md`. The `cryptography` package is installed in the test virtual environment (`scripts/sim_env.sh`).

## 7. Open items

- Side-channel resistance (constant-time behaviour is inherent in the datapath; no countermeasure against power analysis is attempted).
- The 8-byte truncated tag option and tag length negotiation.
- Nonce construction and anti-replay window (MAC layer).
- A pipelined ChaCha20 for 4K-class rates if needed (one quarter-round per clock gives about 140 MB/s).

## 8. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/15-aead && tests/common/lint_synth.sh tests/15-aead`.

| Check | Result |
|---|---|
| T15-01 to T15-09 (9 tests in 4 simulations: `chacha_block`, `poly1305`, `tail_hold`, `aead`) | 9 of 9 pass: 30 random ChaCha20 blocks equal the reference stream; 44 Poly1305 cases (random and all-ones extremes) equal `Poly1305.generate_tag`; the whole construction equals `ChaCha20Poly1305` of the `cryptography` package for AAD of 0, 1, 8, 13, 16, 20 bytes against payloads of 0, 1, 15, 16, 17, 63, 64, 65, 127, 128, 129, 200 bytes in both directions; 200 random single-bit errors and wrong key or nonce all rejected; short and empty frames; 60 frames with random handshakes and per-frame key, nonce, AAD length and mode |
| Throughput (T15-08), measured | 1208 bytes in 1703 clocks: 0.709 byte per clock, 1135 Mbit/s at 200 MHz (requirement: 80 Mbit/s) |
| Test sensitivity | A deliberate bug (the prefetch race described below reintroduced) is caught by the handshake test T15-07 (and only by it); the RTL was restored |
| Lint (`verilator -Wall`) | Clean (all four tops) |
| Yosys generic synthesis | `chacha_block` 5341 cells / 1417 flip-flops; `poly1305` 10212 / 786; `tail_hold` 598 / 263; `aead` 20135 / 4455; no latches |

Bugs found and fixed during the work (each a real RTL fault, found by the tests against the reference library):
- **Keystream prefetch race.** In the clock in which the ChaCha engine pulses `done`, its `busy` is already low and `kn_valid` is not yet set, so the controller started a second prefetch; that run later overwrote an unused keystream block and the second 64 bytes of a frame were encrypted with the wrong block. It appeared only when input or output was slow (always-ready tests consume a block before it is overwritten); found by the random-handshake test. Fix: prefetch is also blocked in the `done` clock.
- **Lost one-clock events.** `tail_hold` reports an empty frame (exactly 16 bytes) and a short frame with one-clock pulses; if the cipher engine was still busy finishing a prefetch the event was lost and no status was produced. The controller now latches both events until it is idle.
- **Short decrypt input.** A frame of 16 bytes or more but shorter than `aad_len + 16` would have been authenticated with a truncated AAD; it is now flagged `st_short`.
- A test mistake: the ChaCha test set `start` right after a rising edge (not aligned to the falling edge), so the engine never saw it.

Notes:
- The nonce, anti-replay window and key schedule are outside this module (section 1); the decrypt output is released before the tag is checked (cut-through), like the CRC status of module 9: a consumer must drop the frame when `st_ok` is 0.
- One frame is processed at a time; the next frame's first byte must not be offered before the status of the previous frame (the tail holder can absorb bytes earlier, but a second empty or short event before the first status would overwrite the latched one).
