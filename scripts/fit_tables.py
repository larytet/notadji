#!/usr/bin/env python3
"""Rewrite the separator line of every pipe table in a Markdown file so that pandoc gives wide text columns more of the page width.

Pandoc takes the relative column widths of a pipe table from the dash counts of the separator line when a row is wider than the
page. Hand-written separators (|---|---|) give every column the same share, so a 5-column requirements table spends 60% of its
width on the short ID, priority, phase and verification columns. This script sets the dash counts from the content: the longer
the text of a column, the more width it gets, with a floor for short columns. It only changes the build copy, not spec/*.md.
Usage: python3 -I scripts/fit_tables.py build/notadji-spec.md
"""
import re
import sys
from pathlib import Path

SEP = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def fit(text: str) -> tuple[str, int]:
    lines = text.split("\n")
    out = list(lines)
    n_tables = 0
    i = 1
    while i < len(lines):
        if SEP.match(lines[i]) and lines[i - 1].lstrip().startswith("|"):
            header = cells(lines[i - 1])
            ncol = len(header)
            if len(cells(lines[i])) == ncol:
                rows = []
                j = i + 1
                while j < len(lines) and lines[j].lstrip().startswith("|"):
                    rows.append(cells(lines[j]))
                    j += 1
                if all(len(r) == ncol for r in rows):
                    weights = []
                    for c in range(ncol):
                        lens = [len(header[c])] + [len(r[c]) for r in rows]
                        mean = sum(lens) / len(lens)
                        w = 0.5 * mean + 0.5 * max(lens)
                        if max(lens) <= 12:
                            w = max(w, 1.8 * max(lens))  # short columns (IDs) must not wrap
                        weights.append(max(6.0, min(110.0, w)))
                    total = sum(weights)
                    dashes = [max(3, round(100 * w / total)) for w in weights]
                    out[i] = "|" + "|".join("-" * d for d in dashes) + "|"
                    n_tables += 1
                i = j
                continue
        i += 1
    return "\n".join(out), n_tables


if __name__ == "__main__":
    path = Path(sys.argv[1])
    new, n = fit(path.read_text())
    path.write_text(new)
    print(f"fitted {n} tables in {path}")
