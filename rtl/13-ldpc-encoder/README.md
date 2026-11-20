# LDPC encoder

Module 13 of `spec/18-development-plan.md`. Design spec and test plan: `design/13-*.md`; tests: `tests/13-ldpc-encoder/`.

## Purpose

Quasi-cyclic LDPC encoder for 8 codes (real 802.11n 648-bit rate 5/6 and own designs); `ldpc_code_rom` holds the code tables.

## Interacts with

Inside 16, fed by the message packer from the byte stream (9, 15). The matching decoder (module 20) is not written yet and will share the code tables.
