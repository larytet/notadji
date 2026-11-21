// SRC: sched.c sup.c crashlog.c crc.c seq_drv.c
/* T33-11: monitor core: stall detection, takeover with the safe table, release, damaged table */
#include "tcheck.h"
#include "hal_sim.h"
#include "sup.h"

#define FRAME_CLK 200000u          /* 1 ms at 200 MHz */

static hal_sim S;
static clog_t LG;
static mbox_t HB;
static mon_t MON;
static seq_drv_t DRV;
static _Atomic uint32_t OWNER;
static seq_entry mainT[3], safeT[3];
static uint32_t hb_count;
static bool main_alive;
static uint32_t main_commits;

static void tables(void)
{
    mainT[0].time = 1000; mainT[0].act = SEQ_ACT_SET_LINES; mainT[0].arg = 3;
    mainT[1].time = 90000; mainT[1].act = SEQ_ACT_CLR_LINES; mainT[1].arg = 3;
    mainT[2].time = FRAME_CLK; mainT[2].act = SEQ_ACT_END; mainT[2].arg = 0;
    safeT[0].time = 1000; safeT[0].act = SEQ_ACT_SET_LINES; safeT[0].arg = 1;      /* lowest rate, lower power: other arguments */
    safeT[1].time = 50000; safeT[1].act = SEQ_ACT_CLR_LINES; safeT[1].arg = 1;
    safeT[2].time = FRAME_CLK; safeT[2].act = SEQ_ACT_END; safeT[2].arg = 0;
}

static void setup(uint32_t hold, uint32_t wait)
{
    uint32_t w[4] = {0,0,0,0};
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 4096); mbox_init(&HB); seq_drv_init(&DRV, &S.hal);
    tables();
    CHECK(mon_init(&MON, &S.hal, &LG, &HB, &OWNER, safeT, 3, hold, wait));
    /* bring the sequencer into steady state with the main table: 1 ms frames */
    CHECK_EQ(seq_load_unguarded(&DRV, mainT, 3), SEQ_OK);
    hal_sim_clocks(&S, 1000);
    CHECK_EQ(seq_load_unguarded(&DRV, mainT, 3), SEQ_OK);
    hal_sim_clocks(&S, FRAME_CLK);
    MON.last_fc = hal_rd(&S.hal, SEQ_FRAME_CNT);
    hb_count = 0; main_alive = true; main_commits = 0;
    mbox_write(&HB, w, 4);
}

/* one frame: main core work at the frame start (if alive and owner), then the monitor poll in the middle of the frame, then the rest of the frame */
static void frame(void)
{
    uint32_t w[4];
    if (main_alive && hal_rd(&S.hal, SYS_MAIN_HALT) == 0) {
        if (mon_main_owns(&OWNER)) {
            if (seq_load(&DRV, mainT, 3) == SEQ_OK) main_commits++;
        }
        hb_count++; w[0] = hb_count; w[1] = 0; w[2] = 0; w[3] = 0; mbox_write(&HB, w, 4);
    }
    hal_sim_clocks(&S, FRAME_CLK / 2);
    mon_poll(&MON);
    hal_sim_clocks(&S, FRAME_CLK / 2);
}

static bool active_is(const seq_entry *t)
{
    uint32_t i, b = hal_rd(&S.hal, SEQ_STATUS) & 1u;
    for (i = 0; i < 3; i++) {
        uint64_t e = ((uint64_t)t[i].time << 24) | ((uint64_t)t[i].act << 16) | t[i].arg;
        if (S.bank[b][i] != e) return false;
    }
    return true;
}

static uint32_t count_type(uint16_t type)
{
    uint32_t n = 0, i; clog_rec r;
    for (i = 0; i < clog_count(&LG); i++) if (clog_get(&LG, i, &r) && r.type == type) n++;
    return n;
}

TEST(alive_never_takes_over)
{
    uint32_t i;
    setup(50, 20);
    for (i = 0; i < 100000; i++) frame();
    CHECK_EQ(MON.takeovers, 0);
    CHECK_EQ(OWNER, MON_OWNER_MAIN);
    CHECK_EQ(hal_rd(&S.hal, SYS_MAIN_HALT), 0);
    CHECK(active_is(mainT));
    CHECK(hal_rd(&S.hal, SEQ_MISSED) <= 1);
    CHECK_EQ(main_commits, 100000);
    CHECK_EQ(clog_count(&LG), 0);
}

TEST(stall_takeover_and_release)
{
    uint32_t i, f_stall, f_take = 0;
    setup(50, 20);
    for (i = 0; i < 100; i++) frame();
    main_alive = false;                                    /* the main core stops: no commit, no heartbeat */
    f_stall = hal_rd(&S.hal, SEQ_FRAME_CNT);
    for (i = 0; i < 10; i++) {
        frame();
        if (!f_take && MON.takeovers) f_take = hal_rd(&S.hal, SEQ_FRAME_CNT);
    }
    CHECK(f_take != 0);
    CHECK(f_take - f_stall <= 3);                          /* committed within three frames of the stall */
    CHECK_EQ(OWNER, MON_OWNER_MON);
    CHECK_EQ(hal_rd(&S.hal, SYS_MAIN_HALT), 1);
    CHECK(active_is(safeT));                               /* the safe table is running */
    CHECK_EQ(count_type(CLOG_MONITOR_SAFE), 1);
    CHECK(!mon_main_owns(&OWNER));
    /* hold time over: the main core is released and comes back */
    for (i = 0; i < 60 && hal_rd(&S.hal, SYS_MAIN_HALT) == 1; i++) frame();
    CHECK_EQ(hal_rd(&S.hal, SYS_MAIN_HALT), 0);
    main_alive = true;
    for (i = 0; i < 10; i++) frame();
    CHECK_EQ(OWNER, MON_OWNER_MAIN);
    CHECK_EQ(count_type(CLOG_MONITOR_RELEASE), 1);
    for (i = 0; i < 5; i++) frame();
    CHECK(active_is(mainT));                               /* the main table is back */
    CHECK_EQ(MON.takeovers, 1);                            /* and no second takeover */
}

TEST(main_does_not_return)
{
    uint32_t i;
    setup(10, 8);
    for (i = 0; i < 50; i++) frame();
    main_alive = false;
    for (i = 0; i < 200; i++) frame();                     /* hold 10, release, wait 8, halt again, hold ... */
    CHECK_EQ(OWNER, MON_OWNER_MON);
    CHECK_EQ(MON.takeovers, 1);                            /* the ownership was never given back, so no second takeover */
    CHECK(active_is(safeT));
    CHECK(MON.state == MON_SAFE_HOLD || MON.state == MON_WAIT_ALIVE);
}

TEST(alive_but_not_committing)
{
    /* the heartbeat runs but the sequencer table is not updated: `missed` reaches 2 */
    uint32_t i, w[4] = {0,0,0,0};
    setup(50, 20);
    for (i = 0; i < 20; i++) frame();
    for (i = 0; i < 6; i++) {
        hb_count++; w[0] = hb_count; mbox_write(&HB, w, 4);
        hal_sim_clocks(&S, FRAME_CLK / 2); mon_poll(&MON); hal_sim_clocks(&S, FRAME_CLK / 2);
    }
    CHECK_EQ(MON.takeovers, 1);
    CHECK_EQ(OWNER, MON_OWNER_MON);
}

TEST(damaged_safe_table_not_committed)
{
    uint32_t i;
    setup(50, 20);
    MON.safe[1].arg ^= 0x40;                               /* memory damage in the monitor's copy */
    for (i = 0; i < 20; i++) frame();
    main_alive = false;
    for (i = 0; i < 10; i++) frame();
    CHECK_EQ(MON.bad_table, 1);
    CHECK_EQ(count_type(CLOG_SAFE_TABLE_BAD), 1);
    CHECK(!active_is(safeT));                              /* nothing committed from the damaged table */
    { clog_rec r; uint32_t k, ok_flag = 99; for (k = 0; k < clog_count(&LG); k++) if (clog_get(&LG, k, &r) && r.type == CLOG_MONITOR_SAFE) ok_flag = r.a[2]; CHECK_EQ(ok_flag, 0); }
}

TEST(init_rejects_bad_table)
{
    mon_t m; seq_entry bad[2];
    tables();
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 4096); mbox_init(&HB);
    bad[0] = safeT[0]; bad[1] = safeT[0];                  /* no END */
    CHECK(!mon_init(&m, &S.hal, &LG, &HB, &OWNER, bad, 2, 10, 10));
}

int main(void)
{
    RUN(alive_never_takes_over); RUN(stall_takeover_and_release); RUN(main_does_not_return); RUN(alive_but_not_committing);
    RUN(damaged_safe_table_not_committed); RUN(init_rejects_bad_table);
    TC_DONE();
}
