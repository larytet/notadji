#!/bin/bash
# Module 32: RTL kernel simulation, then the codec tests (T32-01 .. T32-09), then the mutation checks.
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
D="$ROOT/tests/32-codec-efficiency"
"$ROOT/tests/common/run_tests.sh" "$D" || exit 1
(cd "$D" && python3 test_sl2.py > sl2_results.log 2>&1; tail -1 sl2_results.log; grep -q "SL2 TESTS PASSED" sl2_results.log) || exit 1
if [ -z "${SKIP_MUTATION:-}" ]; then (cd "$D" && python3 mutate.py | tail -1) ; fi
