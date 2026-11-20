# Soft demapper

Module 14 of `spec/18-development-plan.md`. Design spec and test plan: `design/14-*.md`; tests: `tests/14-demapper/`.

## Purpose

Folded max-log LLR for BPSK to 256QAM with channel-quality weighting; `llr_serializer` turns the 8-LLR beat into an 8-bit stream.

## Interacts with

Takes equalised tones and `csi` from 17. Output goes through 5 (de-interleaver) to the LDPC decoder (20, planned). Inverse of 6.
