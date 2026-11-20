# Timestamp unit

Module 2 of `spec/18-development-plan.md`. Design spec and test plan: `design/02-*.md`; tests: `tests/02-timestamp/`.

## Purpose

64-bit free-running counter with latch registers per pipeline tap and a trace output, giving per-stage timing evidence for the latency budget (LAT-004).

## Interacts with

Taps sit on the boundaries of the data-plane blocks (4 to 18) and the sequencer (10). Read out by firmware through the module 1 register file.
