#!/bin/bash
# Module 26: cocotb tests of the RTL blocks, then the model-level and system tests (system Python: scipy is needed for the filter design).
cd "$(dirname "$0")" || exit 1
ROOT=$(cd ../.. && pwd)
source "$ROOT/scripts/sim_env.sh" > /dev/null 2>&1
"$ROOT/tests/common/run_tests.sh" . || rc=1
/usr/bin/python3 test_sys.py || rc=1
exit ${rc:-0}
