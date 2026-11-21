#!/bin/bash
# Module 31: cocotb simulations, then the link-level simulations (T31-05 to T31-07).
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
D="$ROOT/tests/31-dft-s-ofdm"
"$ROOT/tests/common/run_tests.sh" "$D" || exit 1
if [ -z "${SKIP_LINK:-}" ]; then
  (cd "$D" && python3 test_link.py all > link.log 2>&1; tail -1 link.log; grep -q "LINK PASSED" link.log) || exit 1
fi
