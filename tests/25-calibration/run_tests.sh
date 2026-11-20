#!/bin/bash
# Module 25: cocotb tests of cal_stats, iq_corr and the closed loops, then the firmware tests (host build).
cd "$(dirname "$0")" || exit 1
ROOT=$(cd ../.. && pwd)
source "$ROOT/scripts/sim_env.sh" > /dev/null 2>&1
"$ROOT/tests/common/run_tests.sh" . || rc=1
python3 test_cal_fw.py || rc=1
exit ${rc:-0}
