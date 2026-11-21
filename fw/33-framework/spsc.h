/* spsc - non-blocking single-producer single-consumer ring of fixed-size items (R33-04, HSI-014).
 * Power-of-two capacity, free-running 32-bit indices, release on publish, acquire on read; neither side ever waits for the other. */
#ifndef SPSC_H
#define SPSC_H

#include "fw_types.h"
#include <stdatomic.h>

typedef struct {
    _Alignas(64) _Atomic uint32_t head;      /* written by the producer */
    _Alignas(64) _Atomic uint32_t tail;      /* written by the consumer */
    uint32_t mask, item;
    uint8_t *buf;
} spsc_t;

/* n_items must be a power of two (returns false otherwise); buf holds n_items * item bytes */
static inline bool spsc_init(spsc_t *q, void *buf, uint32_t n_items, uint32_t item)
{
    if (n_items == 0 || (n_items & (n_items - 1u)) != 0 || item == 0) return false;
    atomic_init(&q->head, 0); atomic_init(&q->tail, 0);
    q->mask = n_items - 1u; q->item = item; q->buf = (uint8_t *)buf;
    return true;
}

static inline uint32_t spsc_count(const spsc_t *q)
{
    uint32_t h = atomic_load_explicit(&((spsc_t *)q)->head, memory_order_acquire);
    uint32_t t = atomic_load_explicit(&((spsc_t *)q)->tail, memory_order_acquire);
    return h - t;
}

static inline bool spsc_push(spsc_t *q, const void *item)
{
    uint32_t h = atomic_load_explicit(&q->head, memory_order_relaxed);
    uint32_t t = atomic_load_explicit(&q->tail, memory_order_acquire);
    if (h - t > q->mask) return false;                     /* full */
    memcpy(q->buf + (size_t)(h & q->mask) * q->item, item, q->item);
    atomic_store_explicit(&q->head, h + 1u, memory_order_release);
    return true;
}

static inline bool spsc_pop(spsc_t *q, void *item)
{
    uint32_t t = atomic_load_explicit(&q->tail, memory_order_relaxed);
    uint32_t h = atomic_load_explicit(&q->head, memory_order_acquire);
    if (h == t) return false;                              /* empty */
    memcpy(item, q->buf + (size_t)(t & q->mask) * q->item, q->item);
    atomic_store_explicit(&q->tail, t + 1u, memory_order_release);
    return true;
}

/* test aid: start the free-running indices at v (queue must be empty) */
static inline void spsc_test_set_index(spsc_t *q, uint32_t v)
{
    atomic_store(&q->head, v); atomic_store(&q->tail, v);
}

#endif
