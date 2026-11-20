# Scrambler and CRC engines

Module 3 of `spec/18-development-plan.md`. Design spec and test plan: `design/03-*.md`; tests: `tests/03-scrambler-crc/`.

## Purpose

`scrambler`: PRBS whitening of a stream. `crc_engine`: parameterised CRC (header and slice CRC, default CRC-32) with a good/bad status.

## Interacts with

Works on the byte stream before the transmit chain. Used with 09 (slice header and slice CRC) and, on the transmit side, before 15 and 16. Built on module 1 streams.
