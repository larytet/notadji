# FFT and IFFT

Module 12 of `spec/18-development-plan.md`. Design spec and test plan: `design/12-*.md`; tests: `tests/12-fft/`.

## Purpose

Memory-based radix-2 engine for 64 to 1024 points, run-time size, inverse flag and per-stage scaling. `fft_twiddle_rom` holds the twiddles.

## Interacts with

IFFT inside 16 (transmit). FFT on receive between 4 (`cp_remove`) and 17 (equaliser). The tests of 18 (sync) reuse its twiddle ROM.
