#!/bin/bash
# Usage: tests/common/lint_synth.sh tests/NN-name   (after: source scripts/sim_env.sh)
# Reads tops.txt in the module directory (one top module name per line) and sources.txt.
# Lint: verilator -Wall must report nothing. Synth: Yosys generic synthesis, no latches; prints the cell and flop counts.
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
D=$(cd "$1" && pwd); cd "$D" || exit 1
SRC=$(while read -r g; do [ -n "$g" ] && ls $ROOT/$g; done < sources.txt | tr '\n' ' ')
rc=0
while read -r t; do
  [ -z "$t" ] && continue
  out=$(verilator --lint-only -Wall --top-module "$t" $SRC 2>&1 | grep -E '^%(Warning|Error)')
  if [ -n "$out" ]; then echo "lint $t: FAIL"; echo "$out"; rc=1; else echo "lint $t: clean"; fi
  if yosys -q -p "read_verilog -sv $SRC; hierarchy -top $t; synth -flatten -top $t; tee -o synth_$t.txt stat; select -assert-none t:\$dlatch t:\$_DLATCH_?_ t:\$_DLATCH_??_" > synth_$t.log 2>&1; then
    cells=$(grep -E "^ +[0-9]+ +cells" synth_$t.txt | head -1 | awk '{print $1}')
    ffs=$(grep -E "DFF" synth_$t.txt | awk '{s+=$1} END{print s+0}')
    echo "synth $t: $cells cells, $ffs flip-flops, no latches"
  else echo "synth $t: FAIL"; tail -5 synth_$t.log; rc=1; fi
done < tops.txt
exit $rc
