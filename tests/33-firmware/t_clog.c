// SRC: crashlog.c crc.c
/* T33-07: crash log write and recover */
#include "tcheck.h"
#include "hal_sim.h"
#include "crashlog.h"

#define CAP 16u
#define SIZE (CLOG_HDR_SIZE + CAP * CLOG_REC_SIZE)

static hal_sim S;

TEST(basic_and_wrap)
{
    clog_t c; clog_rec r; uint32_t i;
    hal_sim_init(&S, 1);
    CHECK(clog_open(&c, &S.hal, 64, SIZE));
    CHECK(c.reinit);
    CHECK_EQ(c.cap, CAP);
    CHECK_EQ(clog_count(&c), 0);
    for (i = 1; i <= 40; i++) { hal_sim_advance_us(&S, 10); clog_append(&c, CLOG_USER, (uint16_t)i, i, i * 2, i * 3, i * 4); }
    CHECK_EQ(clog_count(&c), CAP);
    CHECK(clog_get(&c, 0, &r)); CHECK_EQ(r.seq, 40 - CAP + 1); CHECK_EQ(r.a[1], r.seq * 2); CHECK_EQ(r.flags, r.seq);
    CHECK(clog_get(&c, CAP - 1, &r)); CHECK_EQ(r.seq, 40); CHECK_EQ(r.t_us, 400);
    CHECK(!clog_get(&c, CAP, &r));
    /* reopen: everything is found again */
    { clog_t d; CHECK(clog_open(&d, &S.hal, 64, SIZE)); CHECK(!d.reinit); CHECK_EQ(d.recovered, CAP); CHECK_EQ(d.next_seq, 41); CHECK_EQ(d.oldest, 25);
      clog_append(&d, CLOG_USER, 0, 0, 0, 0, 0); CHECK(clog_get(&d, CAP - 1, &r)); CHECK_EQ(r.seq, 41); }
}

TEST(small_region_and_range)
{
    clog_t c;
    hal_sim_init(&S, 1);
    CHECK(!clog_open(&c, &S.hal, 0, 40));
    CHECK(!clog_open(&c, &S.hal, SIM_RET_SIZE - 32, 200));
    CHECK(clog_open(&c, &S.hal, 0, CLOG_HDR_SIZE + CLOG_REC_SIZE));
    CHECK_EQ(c.cap, 1);
}

typedef struct { uint16_t type, flags; uint32_t a[4]; } gold;

TEST(random_crash_recovery)
{
    uint32_t it, bad = 0, torn_cases = 0;
    tc_rs = 777;
    for (it = 0; it < 10000; it++) {
        clog_t c, d; gold g[200]; uint32_t n_pre = (uint32_t)(tc_rand() % 60), n_post = 1u + (uint32_t)(tc_rand() % 4), i, total, W, lo, hi;
        int64_t budget; uint32_t j;
        hal_sim_init(&S, 1);
        clog_open(&c, &S.hal, 0, SIZE);
        for (i = 0; i < n_pre; i++) {
            g[i].type = (uint16_t)(1 + tc_rand() % 20); g[i].flags = (uint16_t)tc_rand();
            for (j = 0; j < 4; j++) g[i].a[j] = (uint32_t)tc_rand();
            clog_append(&c, g[i].type, g[i].flags, g[i].a[0], g[i].a[1], g[i].a[2], g[i].a[3]);
        }
        /* reset after a random number of bytes in the next appends */
        budget = (int64_t)(tc_rand() % (n_post * CLOG_REC_SIZE + 1u));
        S.ret_budget = budget;
        for (i = n_pre; i < n_pre + n_post; i++) {
            g[i].type = (uint16_t)(1 + tc_rand() % 20); g[i].flags = (uint16_t)tc_rand();
            for (j = 0; j < 4; j++) g[i].a[j] = (uint32_t)tc_rand();
            clog_append(&c, g[i].type, g[i].flags, g[i].a[0], g[i].a[1], g[i].a[2], g[i].a[3]);
        }
        total = n_pre + n_post;
        W = n_pre + (uint32_t)(budget / (int64_t)CLOG_REC_SIZE);          /* records completely written */
        if (W > total) W = total;
        if (S.ret_cut && budget % CLOG_REC_SIZE) torn_cases++;
        hal_sim_power_cycle(&S);
        CHECK(clog_open(&d, &S.hal, 0, SIZE));
        if (d.recovered == 0 && W == 0) continue;
        hi = d.next_seq - 1u; lo = d.oldest;
        /* recovered run is contiguous, ends at the last complete record (a torn record whose last byte happened to match counts as complete) */
        if (!(hi == W || (hi == W + 1u && hi <= total))) { bad++; continue; }
        /* the record in progress (number hi + 1) may have destroyed the oldest record of a full ring; otherwise nothing is missing */
        {
            uint32_t l0 = hi > CAP ? hi - CAP + 1u : 1u;
            if (!(lo == l0 || (hi >= CAP && lo == l0 + 1u))) bad++;
        }
        if (d.recovered != hi - lo + 1u) bad++;
        for (i = lo; i <= hi; i++) {
            clog_rec r;
            if (!clog_get(&d, i - lo, &r) || r.seq != i || r.type != g[i - 1u].type || r.flags != g[i - 1u].flags ||
                memcmp(r.a, g[i - 1u].a, sizeof r.a) != 0) { bad++; break; }
        }
        /* writing continues after the recovery with the next number */
        clog_append(&d, CLOG_USER, 0, 1, 2, 3, 4);
        { clog_rec r; if (!clog_get(&d, clog_count(&d) - 1u, &r) || r.seq != hi + 1u) bad++; }
    }
    CHECK_EQ(bad, 0);
    CHECK(torn_cases > 1000);
}

TEST(corruption)
{
    clog_t c, d; uint32_t i; uint8_t b;
    hal_sim_init(&S, 1);
    clog_open(&c, &S.hal, 0, SIZE);
    for (i = 1; i <= 10; i++) clog_append(&c, CLOG_USER, 0, i, 0, 0, 0);
    /* a bit flip in record 6: the newest run (7..10) survives, 1..5 are no longer contiguous with it */
    S.ret[CLOG_HDR_SIZE + 5 * CLOG_REC_SIZE + 13] ^= 0x10;
    clog_open(&d, &S.hal, 0, SIZE);
    CHECK_EQ(d.next_seq, 11); CHECK_EQ(d.oldest, 7); CHECK_EQ(d.recovered, 4); CHECK_EQ(d.dropped_torn, 1);
    /* header damage: log cleared */
    b = S.ret[2]; S.ret[2] = (uint8_t)(b ^ 1u);
    clog_open(&d, &S.hal, 0, SIZE);
    CHECK(d.reinit); CHECK_EQ(clog_count(&d), 0);
    /* different region size at the same place: treated as a different log */
    clog_append(&d, CLOG_USER, 0, 1, 1, 1, 1);
    clog_open(&c, &S.hal, 0, SIZE + 2u * CLOG_REC_SIZE);
    CHECK(c.reinit);
}

TEST(every_byte_is_covered)
{
    /* a flip of any single bit in any byte of a record makes it invalid */
    clog_t c, d; uint32_t byte, bit;
    for (byte = 0; byte < CLOG_REC_SIZE; byte++) for (bit = 0; bit < 8; bit++) {
        hal_sim_init(&S, 1);
        clog_open(&c, &S.hal, 0, SIZE);
        clog_append(&c, CLOG_USER, 1, 1, 2, 3, 4); clog_append(&c, CLOG_USER, 2, 5, 6, 7, 8);
        S.ret[CLOG_HDR_SIZE + CLOG_REC_SIZE + byte] ^= (uint8_t)(1u << bit);    /* second record */
        clog_open(&d, &S.hal, 0, SIZE);
        if (d.next_seq != 2 || d.recovered != 1) { CHECK(0); return; }          /* only record 1 remains */
    }
    CHECK(1);
}

TEST(seq_exhaustion)
{
    clog_t c; clog_rec r;
    hal_sim_init(&S, 1);
    clog_open(&c, &S.hal, 0, SIZE);
    clog_append(&c, CLOG_USER, 0, 1, 0, 0, 0);
    c.next_seq = 0xFFFFFFFEu; c.oldest = c.next_seq - 1u;
    clog_append(&c, CLOG_USER, 0, 2, 0, 0, 0);          /* seq 0xFFFFFFFE */
    clog_append(&c, CLOG_USER, 0, 3, 0, 0, 0);          /* would be 0xFFFFFFFF: start over */
    CHECK_EQ(clog_count(&c), 1);
    CHECK(clog_get(&c, 0, &r)); CHECK_EQ(r.seq, 1); CHECK_EQ(r.a[0], 3);
}

int main(void)
{
    RUN(basic_and_wrap); RUN(small_region_and_range); RUN(random_crash_recovery); RUN(corruption); RUN(every_byte_is_covered); RUN(seq_exhaustion);
    TC_DONE();
}
