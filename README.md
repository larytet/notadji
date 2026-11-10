# notadji

Open, low-latency digital video link for drones: requirements, trade studies and reference material.

- `spec/` - requirements and design documents (Markdown, convertible to one PDF)
- `scripts/fetch_refs.sh`, `scripts/fetch_orgs.sh` - download reference open-source projects (372 repos, about 14 GB) into `reference/`; not committed, see `reference/MANIFEST.tsv` (pinned commits) and `reference/SKIPPED_LARGE.tsv`
- `scripts/link_budget.py`, `scripts/trace_matrix.py`, `scripts/build_pdf.sh` - link budget tables, generated traceability matrix, single-PDF build

## Build the PDF

```
scripts/build_pdf.sh
```

Regenerates the traceability matrix, concatenates `spec/0*.md` and writes `build/notadji-spec.md` and `build/notadji-spec.pdf`. Requires `pandoc` and a LaTeX engine (`xelatex`, `pdflatex` or `lualatex`).
