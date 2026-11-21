#!/bin/bash
# Firmware framework tests (module 33). Usage: ./run_tests.sh [test-name ...]   (default: all t_*.c)
# Host build: gcc, C11, warnings are errors, AddressSanitizer + UBSan. AArch64: clang compile-only of every firmware source.
cd "$(dirname "$0")" || exit 1
FW=${FW:-../../fw/33-framework}
B=${B:-build}; mkdir -p $B
CFLAGS="-std=c11 -O1 -g -Wall -Wextra -Wconversion -Wshadow -Werror -I$FW -I../../fw/23-link-adaptation -I../../fw/25-calibration -fsanitize=address,undefined -fno-sanitize-recover=undefined"
NEED_LIBS=""
fail=0
VEC=$B/vectors.txt; export VEC
python3 gen_vectors.py $VEC >/dev/null || { echo '  FAIL gen_vectors.py'; fail=1; }
tests=("$@"); [ ${#tests[@]} -eq 0 ] && tests=(audit $(ls t_*.c | sed 's/\.c$//'))
for t in "${tests[@]}"; do
  if [ "$t" = audit ]; then echo "=== audit"; ./audit.sh $FW || fail=1; continue; fi
  [ -f "$t.c" ] || { echo "no such test $t"; fail=1; continue; }
  # a test lists the firmware sources it needs on a line: // SRC: a.c b.c
  srcs=$(grep -m1 '^// SRC:' $t.c | sed 's#// SRC:##')
  files=""; for s in $srcs; do files="$files $FW/$s"; done
  extra=$(grep -m1 '^// LIBS:' $t.c | sed 's#// LIBS:##')
  echo "=== $t"
  if [ -n "$ONLY_FULL" ] && grep -q '^// FULLRUN' $t.c; then :; else
  if ! gcc $CFLAGS $t.c $FW/hal_sim.c $files -o $B/$t $extra -lm 2>$B/$t.err; then cat $B/$t.err; fail=1; continue; fi
  if ! $B/$t; then fail=1; fi
  fi
  if grep -q '^// FULLRUN' $t.c; then
    echo "--- $t (full run, plain -O2 build)"
    if ! gcc -std=c11 -O2 -Wall -Wextra -Werror -I$FW -I../../fw/23-link-adaptation $t.c $FW/hal_sim.c $files -o $B/$t.full $extra -lm 2>$B/$t.err; then cat $B/$t.err; fail=1
    elif ! T33_FULL=1 $B/$t.full; then fail=1; fi
  fi
  if grep -q '^// TSAN' $t.c; then
    echo "--- $t (ThreadSanitizer)"
    if ! gcc -std=c11 -O1 -g -Wall -Wextra -Werror -I$FW -fsanitize=thread $t.c $FW/hal_sim.c $files -o $B/$t.tsan $extra -lm 2>$B/$t.err; then cat $B/$t.err; fail=1
    elif ! setarch "$(uname -m)" -R $B/$t.tsan; then fail=1; fi
  fi
done
[ -n "$NO_A64" ] && { [ $fail -eq 0 ] && echo "ALL TESTS PASSED"; exit $fail; }
# AArch64 compile check of the firmware sources (no libc, 64-bit ARM)
echo "=== aarch64 build"
for f in $FW/*.c ../../fw/23-link-adaptation/link_adapt.c; do
  case $(basename $f) in hal_sim.c) continue;; esac
  if ! clang --target=aarch64-none-elf -ffreestanding -DFW_NO_LIBC_HEADERS -std=c11 -O2 -Wall -Wextra -Wconversion -Werror -I$FW -I../../fw/23-link-adaptation -I../../fw/25-calibration -c $f -o $B/$(basename $f .c).a64.o 2>$B/a64.err; then echo "  FAIL $f"; cat $B/a64.err; fail=1; fi
done
size=$(cd $B && ls *.a64.o 2>/dev/null | wc -l)
echo "  $size objects"
python3 a64_report.py $B || fail=1
python3 a64_cost.py $B || fail=1
[ $fail -eq 0 ] && echo "ALL TESTS PASSED" || echo "SOME TESTS FAILED"
exit $fail
