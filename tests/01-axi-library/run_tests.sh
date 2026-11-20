#!/bin/bash
# Run every cocotb configuration of module 1. Usage: run_tests.sh  (from this directory)
# name | top | test module | -G parameters | environment for the test
set -u
cd "$(dirname "$0")"
ROOT=$(cd ../.. && pwd)
CONFIGS=(
  "skid|axis_skid|test_skid|-GW=32|"
  "fifo|axis_fifo|test_fifo|-GW=16 -GDEPTH=16|"
  "wc_8_32|axis_width_conv|test_wc|-GIN_W=8 -GOUT_W=32|IN_W=8 OUT_W=32"
  "wc_32_8|axis_width_conv|test_wc|-GIN_W=32 -GOUT_W=8|IN_W=32 OUT_W=8"
  "wc_16_64|axis_width_conv|test_wc|-GIN_W=16 -GOUT_W=64|IN_W=16 OUT_W=64"
  "wc_64_16|axis_width_conv|test_wc|-GIN_W=64 -GOUT_W=16|IN_W=64 OUT_W=16"
  "wc_8_8|axis_width_conv|test_wc|-GIN_W=8 -GOUT_W=8|IN_W=8 OUT_W=8"
  "cdc|axis_cdc_fifo|test_cdc|-GW=16 -GAW=4|"
  "regfile|axil_regfile|test_regfile|-GN=16 -GADDR_W=8 -GRO_MASK=240|"
)
rm -f results_*.xml
fail=0
for c in "${CONFIGS[@]}"; do
  IFS='|' read -r name top mod gargs envs <<< "$c"
  echo "=== $name ($top $gargs)"
  # shellcheck disable=SC2086
  env PYTHONPATH="$PWD" $envs make -f sim.mk ROOT="$ROOT" TOPLEVEL="$top" COCOTB_TEST_MODULES="$mod" \
      SIM_BUILD="$PWD/sim_build/$name" COCOTB_RESULTS_FILE="$PWD/results_$name.xml" GARGS="$gargs" \
      > "sim_$name.log" 2>&1
  python3 check_results.py "results_$name.xml" || fail=1
done
if [ $fail = 0 ]; then echo "ALL TESTS PASSED"; else echo "SOME TESTS FAILED"; exit 1; fi
