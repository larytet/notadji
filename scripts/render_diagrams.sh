#!/bin/bash
# Render every Graphviz source in spec/diagrams/*.dot to SVG and PNG (PNG is what the PDF build embeds).
set -eu
cd "$(dirname "$0")/../spec/diagrams"
command -v dot >/dev/null || { echo "graphviz (dot) not installed"; exit 1; }
for f in *.dot; do
  dot -Tsvg "$f" -o "${f%.dot}.svg"
  dot -Tpng -Gdpi=130 "$f" -o "${f%.dot}.png"
  echo "rendered $f"
done
