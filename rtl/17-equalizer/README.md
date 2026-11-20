# Channel estimator and equaliser

Module 17 of `spec/18-development-plan.md`. Design spec and test plan: `design/17-*.md`; tests: `tests/17-equalizer/`.

## Purpose

One-tap zero-forcing equaliser from the two LTF symbols with common phase and gain tracking from the pilots; outputs equalised data tones and per-tone `csi`. `recip_rom` is the reciprocal table.

## Interacts with

After 12 (FFT); output to 14. Uses an internal instance of 7 for tone plan and reference signs. Needs a per-symbol `kind` and `last` from a receive controller that does not exist yet.
