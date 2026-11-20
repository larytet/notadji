# Constellation mapper

Module 6 of `spec/18-development-plan.md`. Design spec and test plan: `design/06-*.md`; tests: `tests/06-mapper/`.

## Purpose

BPSK, QPSK, 16QAM, 64QAM and 256QAM mapping of bit words to 32-bit `{Q,I}` points (RMS 4096 per tone).

## Interacts with

Inside 16, before the tone assembler and IFFT (12). Inverse operation: 14 (demapper), which uses the same amplitude scale as 17 and 18.
