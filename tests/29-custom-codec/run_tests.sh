#!/bin/bash
# Module 29: cocotb tests of the RTL kernel, then the reference-codec tests (numpy, PIL, ffmpeg with libx264).
cd "$(dirname "$0")" || exit 1
ROOT=$(cd ../.. && pwd)
source "$ROOT/scripts/sim_env.sh" > /dev/null 2>&1
"$ROOT/tests/common/run_tests.sh" . || rc=1
/usr/bin/python3 test_codec.py || rc=1
exit ${rc:-0}
