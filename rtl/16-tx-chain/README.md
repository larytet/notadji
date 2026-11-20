# Transmit chain integration

Module 16 of `spec/18-development-plan.md`. Design spec and test plan: `design/16-*.md`; tests: `tests/16-tx-chain/`.

## Purpose

Byte stream to OFDM samples: framing, LDPC, interleave, map, pilots, IFFT, cyclic prefix, with the glue blocks (`msg_bits_pack`, `cw_to_bits`, `sym_blocker`, `bit_packer`, `tx_assembler`) and the frame controller.

## Interacts with

Integrates 4, 5, 6, 7, 12 and 13. Input from 9 and 15; output to 11. Gated by 10.
