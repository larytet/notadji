#!/bin/bash
# Regression of every module: lint, synthesis check and cocotb tests.
# Usage: tests/run_all.sh [module-dir ...]   (default: all tests/NN-* directories; after: source scripts/sim_env.sh)
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
dirs=("$@")
[ ${#dirs[@]} -eq 0 ] && dirs=(tests/[0-9][0-9]-*)
rc=0
for d in "${dirs[@]}"; do
  echo "##### $d"
  if [ -f "$d/run_tests.sh" ]; then ( cd "$d" && ./run_tests.sh ) > /tmp/run_all_$$.log 2>&1; else tests/common/run_tests.sh "$d" > /tmp/run_all_$$.log 2>&1; fi
  r=$?
  echo "  tests: $(grep -c '  pass' /tmp/run_all_$$.log) passed, $(grep -c '  FAIL' /tmp/run_all_$$.log) failed"
  [ $r -ne 0 ] && { rc=1; grep -E "FAIL" /tmp/run_all_$$.log | head; }
  if [ -f "$d/tops.txt" ]; then tests/common/lint_synth.sh "$d" > /tmp/run_all_ls_$$.log 2>&1 || rc=1; echo "  lint clean: $(grep -c 'lint .*clean' /tmp/run_all_ls_$$.log)/$(wc -l < $d/tops.txt), synth ok: $(grep -c 'no latches' /tmp/run_all_ls_$$.log)/$(wc -l < $d/tops.txt)"; fi
done
[ $rc -eq 0 ] && echo "ALL MODULES PASSED" || echo "SOME MODULES FAILED"
exit $rc
