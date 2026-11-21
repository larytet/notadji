// SRC: seq_drv.c crc.c
/* T33-10: sequencer driver: validation, write and read-back, commit-only path, timing guard, race detection */
#include "tcheck.h"
#include "hal_sim.h"
#include "seq_drv.h"

static hal_sim S;

static uint32_t mk_table(seq_entry *t, uint32_t n, uint32_t end_time)
{
    uint32_t i; uint32_t tm = 0;
    for (i = 0; i + 1 < n; i++) { tm += 1u + (uint32_t)(tc_rand() % 50u); t[i].time = tm; t[i].act = (uint8_t)(1u + tc_rand() % 5u); t[i].arg = (uint16_t)tc_rand(); }
    t[n - 1].time = end_time > tm ? end_time : tm; t[n - 1].act = SEQ_ACT_END; t[n - 1].arg = 0;
    return n;
}

static bool bank_equals(const hal_sim *s, uint32_t bank, const seq_entry *t, uint32_t n)
{
    uint32_t i;
    for (i = 0; i < n; i++) {
        uint64_t e = ((uint64_t)t[i].time << 24) | ((uint64_t)t[i].act << 16) | t[i].arg;
        if (s->bank[bank][i] != e) return false;
    }
    return true;
}

TEST(validation)
{
    seq_entry t[70]; uint32_t i;
    CHECK_EQ(seq_validate(t, 0), SEQ_ERR_EMPTY);
    mk_table(t, 5, 1000); CHECK_EQ(seq_validate(t, 5), SEQ_OK);
    mk_table(t, 5, 1000); t[2].time = t[1].time - 1; CHECK_EQ(seq_validate(t, 5), SEQ_ERR_UNSORTED);
    mk_table(t, 5, 1000); t[4].act = SEQ_ACT_NOP; CHECK_EQ(seq_validate(t, 5), SEQ_ERR_NO_END);
    mk_table(t, 5, 1000); t[2].act = SEQ_ACT_END; CHECK_EQ(seq_validate(t, 5), SEQ_ERR_END_NOT_LAST);
    mk_table(t, 5, 1000); t[1].act = 9; CHECK_EQ(seq_validate(t, 5), SEQ_ERR_ACTION);
    mk_table(t, 5, 1000); t[4].time = 0x1000000u; CHECK_EQ(seq_validate(t, 5), SEQ_ERR_TIME_RANGE);
    mk_table(t, 5, 1000); t[4].time = 8; for (i = 0; i < 4; i++) t[i].time = 0; CHECK_EQ(seq_validate(t, 5), SEQ_ERR_TIME_RANGE);   /* END before the minimum frame */
    mk_table(t, 65, 100000); CHECK_EQ(seq_validate(t, 65), SEQ_ERR_TOO_DEEP);
    mk_table(t, 64, 100000); CHECK_EQ(seq_validate(t, 64), SEQ_OK);
}

TEST(write_and_readback)
{
    int k;
    tc_rs = 99;
    for (k = 0; k < 200; k++) {
        seq_drv_t d; seq_entry t[SEQ_DEPTH]; uint32_t n = 2u + (uint32_t)(tc_rand() % (SEQ_DEPTH - 1)), inactive;
        hal_sim_init(&S, 1); seq_drv_init(&d, &S.hal);
        mk_table(t, n, 5000000u);
        inactive = (hal_rd(&S.hal, SEQ_STATUS) & 1u) ^ 1u;
        CHECK_EQ(seq_load_unguarded(&d, t, n), SEQ_OK);        /* the 1000-clock safe frame is too short for the guard with a long table */
        CHECK(bank_equals(&S, inactive, t, n));
        hal_sim_clocks(&S, 1000);                              /* safe frame ends: the table becomes active */
        CHECK_EQ(hal_rd(&S.hal, SEQ_STATUS) & 1u, inactive);
        CHECK_EQ(hal_rd(&S.hal, SEQ_FRAME_LEN), t[n - 1].time > SEQ_MIN_FRAME ? t[n - 1].time : SEQ_MIN_FRAME);
    }
}

TEST(commit_only_path)
{
    seq_drv_t d; seq_entry t[10], u[10]; uint32_t i;
    hal_sim_init(&S, 1); seq_drv_init(&d, &S.hal);
    mk_table(t, 10, 20000); mk_table(u, 10, 20000);
    CHECK_EQ(seq_load(&d, t, 10), SEQ_OK);                      /* bank 1: written */
    hal_sim_clocks(&S, 1000);
    CHECK_EQ(seq_load(&d, t, 10), SEQ_OK);                      /* bank 0 holds the safe table: written */
    hal_sim_clocks(&S, 20000);
    CHECK_EQ(d.n_written, 2);
    for (i = 0; i < 20; i++) { CHECK_EQ(seq_load(&d, t, 10), SEQ_OK); hal_sim_clocks(&S, 20000); }
    CHECK_EQ(d.n_written, 2); CHECK_EQ(d.n_skipped, 20);        /* the same table every frame: only the commit is written */
    CHECK_EQ(hal_rd(&S.hal, SEQ_MISSED), 0);                    /* and a commit each frame keeps `missed` at zero */
    CHECK_EQ(seq_load(&d, u, 10), SEQ_OK);                      /* a changed table is written in full */
    CHECK_EQ(d.n_written, 3);
    hal_sim_clocks(&S, 20000);
    CHECK(bank_equals(&S, hal_rd(&S.hal, SEQ_STATUS) & 1u, u, 10));
}

TEST(late_guard)
{
    seq_drv_t d; seq_entry t[64], act[2]; uint32_t c0;
    hal_sim_init(&S, 1); seq_drv_init(&d, &S.hal);
    S.reg_cost = 30;                                            /* 100 ns per register access at 300 MHz */
    act[0].time = 100; act[0].act = SEQ_ACT_PULSE; act[0].arg = 1; act[1].time = 200000; act[1].act = SEQ_ACT_END; act[1].arg = 0;
    CHECK_EQ(seq_load(&d, act, 2), SEQ_OK);                     /* 2 * 40 + 200 = 280 clocks needed, the safe frame has 1000 */
    mk_table(t, 64, 200000);
    c0 = S.commits;
    CHECK_EQ(seq_load(&d, t, 64), SEQ_ERR_LATE);                /* 64 * 40 + 200 = 2760 clocks > 1000 */
    CHECK_EQ(S.commits, c0);                                    /* nothing committed */
    CHECK(S.bank[1][2] == 0 && S.bank[1][63] == 0);             /* nothing of the long table written */
}

static void goto_tick(uint32_t tick)      /* advance to the given tick of the running frame (this frame if still ahead, else the next) */
{
    uint32_t len = hal_rd(&S.hal, SEQ_FRAME_LEN), cur = hal_rd(&S.hal, SEQ_TICK);
    hal_sim_clocks(&S, (tick + len - cur) % len);
}

TEST(margin_and_commit_only_guard)
{
    seq_drv_t d; seq_entry t[10], u[10]; uint32_t n_w;
    hal_sim_init(&S, 1); seq_drv_init(&d, &S.hal);
    mk_table(t, 10, 2000); mk_table(u, 10, 2000);
    CHECK_EQ(seq_load(&d, t, 10), SEQ_OK);                      /* needs 10 * 40 + 200 = 600 of the 1000 clocks of the safe frame */
    hal_sim_clocks(&S, 1000);                                   /* swap: 2000-clock frames of t */
    CHECK_EQ(seq_load(&d, t, 10), SEQ_OK);                      /* the other bank holds the safe table: written */
    hal_sim_clocks(&S, 2000);                                   /* swap again; the inactive bank now holds t */
    n_w = d.n_written;
    goto_tick(1600);                                            /* 400 clocks left in the frame */
    CHECK_EQ(seq_load(&d, t, 10), SEQ_OK);                      /* commit only: 0 + 200 needed, 400 available */
    CHECK_EQ(d.n_written, n_w);
    goto_tick(0);                                               /* next frame (after the swap) */
    goto_tick(1600);
    CHECK_EQ(seq_load(&d, u, 10), SEQ_ERR_LATE);                /* a different table needs 600 > 400 */
    goto_tick(1850);                                            /* 150 left: below the margin even for a commit only */
    CHECK_EQ(seq_load(&d, t, 10), SEQ_ERR_LATE);
}

TEST(race_detected_without_guard)
{
    seq_drv_t d; seq_entry a[2], t[64];
    hal_sim_init(&S, 1); seq_drv_init(&d, &S.hal);
    S.reg_cost = 30;
    a[0].time = 0; a[0].act = SEQ_ACT_NOP; a[0].arg = 0; a[1].time = 3000; a[1].act = SEQ_ACT_END; a[1].arg = 0;
    CHECK_EQ(seq_load_unguarded(&d, a, 2), SEQ_OK);
    hal_sim_clocks(&S, 1000);                                   /* a is active (3000-clock frames) */
    mk_table(t, 64, 3000);
    hal_sim_clocks(&S, 200);                                    /* tick well inside the frame */
    hal_wr(&S.hal, SEQ_COMMIT, 1);                              /* something pending: a swap will happen at the frame end */
    hal_sim_clocks(&S, 2000);                                   /* tick ~ 2300 of 3000 */
    CHECK_EQ(seq_load_unguarded(&d, t, 64), SEQ_ERR_RACE);      /* 64 entries take ~ 5000 clocks: the swap happens in the middle */
    CHECK(!d.known[0] && !d.known[1]);
}

TEST(guard_with_no_end_table)
{
    /* a running table without END never ends the frame: there is no deadline */
    seq_drv_t d; seq_entry t[3];
    hal_sim_init(&S, 1); seq_drv_init(&d, &S.hal);
    S.bank[0][0] = ((uint64_t)10 << 24) | ((uint64_t)SEQ_ACT_NOP << 16);   /* no END in the active bank */
    CHECK_EQ(hal_rd(&S.hal, SEQ_FRAME_LEN), 0);
    mk_table(t, 3, 5000);
    CHECK_EQ(seq_load(&d, t, 3), SEQ_OK);
}

int main(void) { RUN(validation); RUN(write_and_readback); RUN(commit_only_path); RUN(late_guard); RUN(margin_and_commit_only_guard); RUN(race_detected_without_guard); RUN(guard_with_no_end_table); TC_DONE(); }
