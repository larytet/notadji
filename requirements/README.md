# Requirement specifications for the extension modules (30 and later)

The system requirements are in `spec/01-system-requirements.md`. The modules 30 and later refine one optional requirement
each into testable module requirements (`Rnn-mm`) with an acceptance criterion; the design and test plan is in
`design/NN-*.md`, the implementation in `rtl/`, `fw/` and `tests/`.

| Module | File | Source requirement |
|---|---|---|
| 30 | `30-soft-combining.md` | PHY-017 (soft combining of retransmitted slices, more decoder iterations) |
| 31 | `31-dft-s-ofdm.md` | PHY-014 (DFT-spread OFDM low-PAPR mode) |
| 32 | `32-codec-efficiency.md` | VID-027 (custom codec), module 29 efficiency (profile SL2) |
