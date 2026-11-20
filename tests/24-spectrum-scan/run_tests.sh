#!/bin/bash
# Module 24: cocotb tests of the scan engine, then the channel-selection firmware tests (host build).
cd "$(dirname "$0")" || exit 1
ROOT=$(cd ../.. && pwd)
source "$ROOT/scripts/sim_env.sh" > /dev/null 2>&1
"$ROOT/tests/common/run_tests.sh" . || rc=1
python3 test_cs.py || rc=1
exit ${rc:-0}
