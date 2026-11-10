#!/bin/bash
# Concatenate the spec into one Markdown file and (if pandoc is installed) one PDF.
# Usage: scripts/build_pdf.sh   -> build/notadji-spec.md and build/notadji-spec.pdf
set -eu
cd "$(dirname "$0")/.."
mkdir -p build
python3 -I scripts/trace_matrix.py >/dev/null
python3 -I scripts/claim_register.py >/dev/null
python3 -I scripts/audit_numbers.py >/dev/null
out=build/notadji-spec.md
: > "$out"
for f in spec/[0-9]*.md; do
  cat "$f" >> "$out"
  printf '\n\n\\newpage\n\n' >> "$out"
done
echo "wrote $out"
if command -v pandoc >/dev/null; then
  engine=""
  for e in xelatex pdflatex lualatex; do command -v "$e" >/dev/null && engine="$e" && break; done
  if [ -n "$engine" ]; then
    pandoc "$out" -o build/notadji-spec.pdf --pdf-engine="$engine" -V geometry:margin=2cm -V fontsize=9pt \
      --toc --toc-depth=2 -V colorlinks=true && echo "wrote build/notadji-spec.pdf"
  else
    echo "pandoc found but no LaTeX engine; try: pandoc $out -o build/notadji-spec.html && print to PDF from a browser"
  fi
else
  echo "pandoc not installed: install pandoc (and texlive-xetex) for the PDF, or convert $out with any Markdown tool"
fi
