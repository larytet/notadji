# Slice packetiser and depacketiser

Module 9 of `spec/18-development-plan.md`. Design spec and test plan: `design/09-*.md`; tests: `tests/09-slice-packetiser/`.

## Purpose

`slice_pack` adds the slice header (frame, index, flags, length) and CRC; `slice_unpack` checks them and reports status.

## Interacts with

Feeds 15 (encryption) and then 16 (transmit chain) on transmit; follows the LDPC decoder (20) and 15 (decrypt) on receive. Uses 3 (CRC). Status goes to the MAC (22) and video path (28, 29).
