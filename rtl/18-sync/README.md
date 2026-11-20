# Burst detection, timing and carrier-offset synchroniser

Module 18 of `spec/18-development-plan.md`. Design spec and test plan: `design/18-*.md`; tests: `tests/18-sync/`.

## Purpose

`sync_core`: STF autocorrelation detector, coarse timing, CFO estimate and derotation, AGC monitor. `cordic_vec` provides the angle. **Work in progress.**

## Interacts with

Takes samples from 11; derotated output and `k_back` go to 4 (`cp_remove`) and then 12 and 17. `rearm` comes from the sequencer (10) or firmware; `agc_up/down` are for firmware. No back-pressure, so a FIFO is needed after it.
