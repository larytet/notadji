#!/bin/bash
# Module 27: cocotb tests of the RTL blocks, then the loop and early scan-out simulations (host build of the firmware).
cd "$(dirname "$0")" || exit 1
ROOT=$(cd ../.. && pwd)
source "$ROOT/scripts/sim_env.sh" > /dev/null 2>&1
"$ROOT/tests/common/run_tests.sh" . || rc=1
python3 test_sys.py || rc=1
exit ${rc:-0}
