#!/bin/bash
# Source audit of the memory orders in the cross-core primitives. Missing release/acquire cannot be seen by a test on an x86-64 host (strong ordering;
# ThreadSanitizer did not report the relaxed variant either), so the required orders are checked in the source. Usage: audit.sh <fw dir>
FW=${1:-../../fw/33-framework}
fail=0
need() { # file, fixed string
  if ! grep -qF -- "$2" "$FW/$1"; then echo "  FAIL audit: $1 lacks: $2"; fail=1; fi
}
need spsc.h 'atomic_store_explicit(&q->head, h + 1u, memory_order_release);'
need spsc.h 'atomic_store_explicit(&q->tail, t + 1u, memory_order_release);'
need spsc.h 'uint32_t t = atomic_load_explicit(&q->tail, memory_order_acquire);'
need spsc.h 'uint32_t h = atomic_load_explicit(&q->head, memory_order_acquire);'
need mbox.h 'atomic_store_explicit(&m->seq, s + 2u, memory_order_release);'
need mbox.h 'atomic_thread_fence(memory_order_acquire);'
need mbox.h 'atomic_thread_fence(memory_order_release);'
need sup.h 'mon_owner_of(atomic_load_explicit(owner, memory_order_acquire)) == MON_OWNER_MAIN'
need sup.c '| MON_OWNER_MAIN, memory_order_release);'
[ $fail -eq 0 ] && echo "  pass  audit"
exit $fail
