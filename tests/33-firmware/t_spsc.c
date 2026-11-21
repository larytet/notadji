// SRC:
// LIBS: -pthread
// TSAN: yes
/* T33-05: SPSC queue, two threads, wrap of the 32-bit indices, and the mailbox in t_mbox.c */
#include "tcheck.h"
#include "spsc.h"
#include <pthread.h>

#define N_ITEMS 10000000ull
static spsc_t Q;
static uint64_t qbuf[1024][2];
static uint64_t bad_order, bad_content, popped;

static void *producer(void *a)
{
    uint64_t i;
    (void)a;
    for (i = 0; i < N_ITEMS; i++) {
        uint64_t v[2] = { i, ~i };
        while (!spsc_push(&Q, v)) { }
    }
    return NULL;
}

static void *consumer(void *a)
{
    uint64_t exp = 0;
    (void)a;
    while (exp < N_ITEMS) {
        uint64_t v[2];
        if (!spsc_pop(&Q, v)) continue;
        if (v[0] != exp) bad_order++;
        if (v[1] != ~v[0]) bad_content++;
        exp++; popped++;
    }
    return NULL;
}

TEST(two_threads)
{
    pthread_t p, c;
    CHECK(spsc_init(&Q, qbuf, 1024, 16));
    spsc_test_set_index(&Q, UINT32_MAX - 5000u);          /* the indices wrap during the run */
    pthread_create(&p, NULL, producer, NULL);
    pthread_create(&c, NULL, consumer, NULL);
    pthread_join(p, NULL); pthread_join(c, NULL);
    CHECK_EQ(popped, N_ITEMS);
    CHECK_EQ(bad_order, 0);
    CHECK_EQ(bad_content, 0);
    CHECK_EQ(spsc_count(&Q), 0);
}

TEST(full_and_empty_return_at_once)
{
    spsc_t q; uint32_t buf[8], v, i;
    CHECK(spsc_init(&q, buf, 8, 4));
    CHECK(!spsc_pop(&q, &v));
    for (i = 0; i < 8; i++) { v = i; CHECK(spsc_push(&q, &v)); }
    v = 99; CHECK(!spsc_push(&q, &v));                    /* full: returns false, nothing overwritten */
    CHECK_EQ(spsc_count(&q), 8);
    for (i = 0; i < 8; i++) { CHECK(spsc_pop(&q, &v)); CHECK_EQ(v, i); }
    CHECK(!spsc_pop(&q, &v));
    /* push/pop interleaving across the 32-bit wrap */
    spsc_test_set_index(&q, UINT32_MAX - 2u);
    for (i = 0; i < 100; i++) { uint32_t w; v = i; CHECK(spsc_push(&q, &v)); CHECK(spsc_pop(&q, &w)); CHECK_EQ(w, i); }
}

TEST(bad_init)
{
    spsc_t q; uint8_t b[64];
    CHECK(!spsc_init(&q, b, 0, 4)); CHECK(!spsc_init(&q, b, 6, 4)); CHECK(!spsc_init(&q, b, 8, 0));
}

int main(void)
{
    RUN(two_threads); RUN(full_and_empty_return_at_once); RUN(bad_init);
    TC_DONE();
}
