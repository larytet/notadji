# Preamble and pilot generator

Module 7 of `spec/18-development-plan.md`. Design spec and test plan: `design/07-*.md`; tests: `tests/07-preamble-pilot/`.

## Purpose

Generates the tone plan: short training field (STF), long training fields (LTF), pilots with polarity sequence, null and data-tone positions for FFT sizes 64 to 512.

## Interacts with

Used by 16 (preamble and pilots on transmit), by 17 (an internal instance supplies the reference tones and pilot signs) and as the STF that 18 detects.
