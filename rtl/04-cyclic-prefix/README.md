# Cyclic prefix insert and remove

Module 4 of `spec/18-development-plan.md`. Design spec and test plan: `design/04-*.md`; tests: `tests/04-cyclic-prefix/`.

## Purpose

`cp_insert` adds the guard interval (1/16, 1/8, 1/4) to each OFDM symbol; `cp_remove` strips it, starting a programmable number of samples early (`backoff`).

## Interacts with

Transmit: after the IFFT (12) inside 16. Receive: between the synchroniser (18, `k_back` drives `backoff`) and the FFT (12). The receive side needs symbol framing (`last`) that does not exist yet.
