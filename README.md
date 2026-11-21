# notadji

Open, low-latency digital video link for drones: requirements, trade studies and reference material.

- `spec/` - requirements and design documents (Markdown, convertible to one PDF)
- `scripts/fetch_refs.sh`, `scripts/fetch_orgs.sh` - download reference open-source projects (372 repos, about 14 GB) into `reference/`; not committed, see `reference/MANIFEST.tsv` (pinned commits) and `reference/SKIPPED_LARGE.tsv`
- `scripts/link_budget.py`, `scripts/trace_matrix.py`, `scripts/build_pdf.sh` - link budget tables, generated traceability matrix, single-PDF build

## Status

- **Specification** (`spec/`): written and audited; `spec/12-claim-audit-and-feasibility.md` separates what is proven from what is an estimate.
- **Module designs and tests** (`design/`, `rtl/`, `tests/`, `fw/`): all 32 modules of `spec/18-development-plan.md` have a design specification and test plan, and an implementation with passing tests (RTL in SystemVerilog, simulated with Verilator and cocotb; firmware and reference models in Python and C). Per-module results: `design/README.md`.
- **Not done**: nothing has run on a target core or on real hardware; the hard video encoder (module 28) is only a behavioural stand-in; the custom codec has no RTL encoder or decoder (module 29 SL1 needs 6.8 to 7.6 times the bit rate of x264, module 32 SL2 about 1.9 to 2.0 times; luma only, synthetic motion); open results are listed in `design/README.md` (for example PHY-009 and PHY-014 not met as specified).

## Build the PDF

```
scripts/build_pdf.sh
```

Regenerates the traceability matrix, concatenates `spec/0*.md` and writes `build/notadji-spec.md` and `build/notadji-spec.pdf`. Requires `pandoc` and a LaTeX engine (`xelatex`, `pdflatex` or `lualatex`).

Run before every commit: `python3 -I scripts/audit_numbers.py` (recomputes every derived number in the spec and fails if the text disagrees),
`python3 -I scripts/trace_matrix.py` and `python3 -I scripts/claim_register.py` (regenerate the traceability matrix and the evidence register).
`scripts/build_pdf.sh` runs all three and builds the single PDF (needs pandoc and LaTeX).

Document map: see `spec/00-overview.md`. Start with `spec/12-claim-audit-and-feasibility.md` (what is proven, what is an estimate), then `spec/01-system-requirements.md`.
