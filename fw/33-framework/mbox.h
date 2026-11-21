/* mbox - single-writer latest-value mailbox (sequence lock). The writer never waits; a reader that keeps colliding with the writer
 * gives up after MBOX_RETRIES and reports failure (R33-04). Data is carried in atomic words so that torn reads are detected, not undefined. */
#ifndef MBOX_H
#define MBOX_H

#include "fw_types.h"
#include <stdatomic.h>

#define MBOX_WORDS   16u
#define MBOX_RETRIES 8u

typedef struct {
    _Atomic uint32_t seq;                     /* odd while the writer is updating */
    _Atomic uint32_t w[MBOX_WORDS];
} mbox_t;

static inline void mbox_init(mbox_t *m)
{
    uint32_t i;
    atomic_init(&m->seq, 0);
    for (i = 0; i < MBOX_WORDS; i++) atomic_init(&m->w[i], 0);
}

/* n words, n <= MBOX_WORDS */
static inline void mbox_write(mbox_t *m, const uint32_t *src, uint32_t n)
{
    uint32_t i, s = atomic_load_explicit(&m->seq, memory_order_relaxed);
    atomic_store_explicit(&m->seq, s + 1u, memory_order_relaxed);
    atomic_thread_fence(memory_order_release);
    for (i = 0; i < n && i < MBOX_WORDS; i++) atomic_store_explicit(&m->w[i], src[i], memory_order_relaxed);
    atomic_store_explicit(&m->seq, s + 2u, memory_order_release);
}

/* returns the sequence value (even, increases with every write) or 0 if no consistent copy was obtained */
static inline uint32_t mbox_read(const mbox_t *m, uint32_t *dst, uint32_t n)
{
    uint32_t r, i;
    for (r = 0; r < MBOX_RETRIES; r++) {
        uint32_t s1 = atomic_load_explicit(&((mbox_t *)m)->seq, memory_order_acquire);
        if (s1 & 1u) continue;
        for (i = 0; i < n && i < MBOX_WORDS; i++) dst[i] = atomic_load_explicit(&((mbox_t *)m)->w[i], memory_order_relaxed);
        atomic_thread_fence(memory_order_acquire);
        if (atomic_load_explicit(&((mbox_t *)m)->seq, memory_order_relaxed) == s1) return s1;
    }
    return 0;
}

#endif
