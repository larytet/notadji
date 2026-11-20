# Block interleaver and de-interleaver

Module 5 of `spec/18-development-plan.md`. Design spec and test plan: `design/05-*.md`; tests: `tests/05-interleaver/`.

## Purpose

Spreads burst errors across subcarriers; one module, `DEINT` selects the direction, element width `W` is a parameter (1 bit on transmit, 8-bit LLRs on receive).

## Interacts with

Transmit: between the symbol blocker and the mapper inside 16. Receive: after the demapper and `llr_serializer` (14), before the LDPC decoder (20, planned).
