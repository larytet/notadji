# ChaCha20-Poly1305 AEAD

Module 15 of `spec/18-development-plan.md`. Design spec and test plan: `design/15-*.md`; tests: `tests/15-aead/`.

## Purpose

Per-slice authenticated encryption: `chacha_block`, `poly1305`, `tail_hold` and the controller `aead`. Decrypt releases plaintext before the tag check (`st_ok`).

## Interacts with

Between 9 (slice header as AAD) and 16 on transmit; after the LDPC decoder and before 9 (`slice_unpack`) on receive. Key, nonce and replay counter come from firmware.
