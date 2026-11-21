#!/bin/bash
# Module 30: cocotb simulations, then the model statistics (T30-05).
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
D="$ROOT/tests/30-soft-combining"
"$ROOT/tests/common/run_tests.sh" "$D" || exit 1
if [ -z "${SKIP_STATS:-}" ]; then
  (cd "$D" && python3 stats_combining.py > stats_combining.log 2>&1; tail -1 stats_combining.log; grep -q "STATS PASSED" stats_combining.log) || exit 1
fi
