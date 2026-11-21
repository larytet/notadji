// SRC:
// LIBS: -pthread
/* T33-06: mailbox: the reader sees only consistent values; the writer is never delayed by the reader */
#include "tcheck.h"
#include "mbox.h"
#include <pthread.h>

static mbox_t M;
static _Atomic int stop;
static uint64_t writes;

static void fill(uint32_t k, uint32_t *w)
{
    w[0] = k; w[1] = ~k; w[2] = k * 3u; w[3] = k ^ 0xA5A5A5A5u;
}

static void *writer(void *a)
{
    uint32_t k = 0, w[4];
    (void)a;
    while (!atomic_load(&stop)) { fill(++k, w); mbox_write(&M, w, 4); writes++; }
    return NULL;
}

TEST(consistent_reads)
{
    pthread_t t; uint64_t ok = 0, fail = 0, bad = 0, i; uint32_t last = 0;
    mbox_init(&M);
    atomic_store(&stop, 0);
    pthread_create(&t, NULL, writer, NULL);
    for (i = 0; i < 3000000; i++) {
        uint32_t w[4], s = mbox_read(&M, w, 4), e[4];
        if (!s) { fail++; continue; }
        fill(w[0], e);
        if (memcmp(w, e, sizeof e) != 0) bad++;
        if (s < last) bad++;                        /* the sequence value never goes back */
        last = s; ok++;
    }
    atomic_store(&stop, 1);
    pthread_join(t, NULL);
    CHECK_EQ(bad, 0);
    CHECK(ok > 1000);
    CHECK(writes > 1000);                           /* the writer ran freely while the reader was busy */
    printf("    reads ok %llu, gave up %llu, writes %llu\n", (unsigned long long)ok, (unsigned long long)fail, (unsigned long long)writes);
}

TEST(single_thread)
{
    mbox_t m; uint32_t w[4] = {1,2,3,4}, r[4] = {0,0,0,0};
    mbox_init(&m);
    CHECK_EQ(mbox_read(&m, r, 4), 0);               /* never written */
    mbox_write(&m, w, 4);
    CHECK_EQ(mbox_read(&m, r, 4), 2);
    CHECK_EQ(r[3], 4);
    w[3] = 9; mbox_write(&m, w, 4);
    CHECK_EQ(mbox_read(&m, r, 4), 4); CHECK_EQ(r[3], 9);
}

int main(void) { RUN(single_thread); RUN(consistent_reads); TC_DONE(); }
