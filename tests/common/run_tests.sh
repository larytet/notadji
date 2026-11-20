#!/bin/bash
# Shared cocotb runner. Usage: tests/common/run_tests.sh tests/NN-name   (after: source scripts/sim_env.sh)
# The module directory holds:
#   configs.txt  one line per simulation: name|top|test module|-G parameters|environment (KEY=VAL ...)
#   sources.txt  RTL source globs relative to the repository root (one per line)
set -u
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
D=$(cd "$1" && pwd)
cd "$D" || exit 1
SRC=$(while read -r g; do [ -n "$g" ] && ls $ROOT/$g; done < sources.txt | tr '\n' ' ')
rm -f results_*.xml
fail=0
while IFS='|' read -r name top mod gargs envs; do
  [ -z "$name" ] && continue
  case "$name" in \#*) continue;; esac
  echo "=== $name ($top $gargs)"
  # shellcheck disable=SC2086
  env PYTHONPATH="$D:$ROOT/tests/common" $envs make -f "$ROOT/tests/common/sim.mk" ROOT="$ROOT" SRCS="$SRC" TOPLEVEL="$top" \
      COCOTB_TEST_MODULES="$mod" SIM_BUILD="$D/sim_build/$name" COCOTB_RESULTS_FILE="$D/results_$name.xml" GARGS="$gargs" \
      > "sim_$name.log" 2>&1
  python3 "$ROOT/tests/common/check_results.py" "results_$name.xml" || fail=1
done < configs.txt
if [ $fail = 0 ]; then echo "ALL TESTS PASSED"; else echo "SOME TESTS FAILED"; exit 1; fi
