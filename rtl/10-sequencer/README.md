# Frame-timeline sequencer

Module 10 of `spec/18-development-plan.md`. Design spec and test plan: `design/10-*.md`; tests: `tests/10-sequencer/`.

## Purpose

Replays a table of timed events every frame: control lines, pulses, gain and PLL values. Keeps running if the CPU stalls; `force_safe` overrides outputs.

## Interacts with

Outputs `lines`, `pulses`, `pll_val` go to 11 (pin map and radio control). Its pulses are expected to gate the transmit and receive paths (16, 18). Table written by firmware through 1; timestamps from 2.
