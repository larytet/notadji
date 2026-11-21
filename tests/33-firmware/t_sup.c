// SRC: sched.c sup.c crashlog.c crc.c seq_drv.c
/* T33-09: supervision (overruns, deadline misses, check-ins, watchdog kicks, heartbeat) */
#include "tcheck.h"
#include "hal_sim.h"
#include "sup.h"

static hal_sim S;
static sched_t SC;
static clog_t LG;
static mbox_t HB;
static sup_t SU;
static uint32_t cost[3];
static int sid[3], tid[3];
static bool do_checkin[3];

static void task(void *a)
{
    int id = (int)(intptr_t)a;
    hal_sim_burn(&S, cost[id]);
    if (do_checkin[id]) sup_checkin(&SU, sid[id]);
}

static void setup(void)
{
    int k;
    sched_task_cfg c;
    hal_sim_init(&S, 1); sched_init(&SC, &S.hal);
    clog_open(&LG, &S.hal, 0, 4096); mbox_init(&HB);
    sup_init(&SU, &S.hal, &SC, &LG, &HB);
    for (k = 0; k < 3; k++) {
        c.name = "t"; c.fn = task; c.arg = (void *)(intptr_t)k; c.period_us = 1000; c.deadline_us = 0; c.budget_cycles = 10000; c.prio = (uint8_t)k;
        tid[k] = sched_add(&SC, &c); sid[k] = sup_register(&SU, tid[k]);
        cost[k] = 1000; do_checkin[k] = true;
    }
    sched_start(&SC);
}

static void period(void)    /* one 1 ms frame: tick, supervision, idle to the next boundary */
{
    uint64_t d;
    sched_tick(&SC);
    sup_tick(&SU);
    d = sched_next_due(&SC);
    if (d > hal_cycles(&S.hal)) hal_sim_burn(&S, d - hal_cycles(&S.hal));
}

static uint32_t count_type(uint16_t type)
{
    uint32_t n = 0, i; clog_rec r;
    for (i = 0; i < clog_count(&LG); i++) if (clog_get(&LG, i, &r) && r.type == type) n++;
    return n;
}

TEST(normal_run)
{
    uint32_t i, hb[4];
    setup();
    for (i = 0; i < 1000000; i++) period();
    CHECK(!sup_safe_requested(&SU));
    CHECK_EQ(SU.kicks, 1000000);
    CHECK_EQ(S.wdog_kicks, 1000000);
    CHECK_EQ(clog_count(&LG), 0);
    CHECK(mbox_read(&HB, hb, 4) != 0);
    CHECK_EQ(hb[0], 1000000);
}

TEST(overrun_streak)
{
    uint32_t i;
    setup();
    cost[1] = 50000;                                    /* 5 x the budget */
    period(); period();
    CHECK(!sup_safe_requested(&SU));                    /* two in a row: not yet */
    period();
    CHECK(sup_safe_requested(&SU));
    CHECK_EQ(count_type(CLOG_TASK_OVERRUN), 1);
    CHECK_EQ(count_type(CLOG_SAFE_REQUEST), 1);
    for (i = 0; i < 6; i++) period();                   /* streak of 9: logged again at 6 and 9, not at every period */
    CHECK_EQ(count_type(CLOG_TASK_OVERRUN), 3);
    CHECK_EQ(count_type(CLOG_SAFE_REQUEST), 1);         /* the request is logged when it is raised */
    /* an overrun that does not repeat three times in a row: no request */
    sup_safe_clear(&SU); CHECK(!sup_safe_requested(&SU));
    setup();
    for (i = 0; i < 100; i++) { cost[2] = (i % 3 == 2) ? 20000u : 1000u; period(); }
    CHECK(!sup_safe_requested(&SU));
    CHECK_EQ(sched_get(&SC, tid[2])->overruns, 33);
}

TEST(deadline_miss)
{
    setup();
    period(); period();
    cost[0] = 400000;                                   /* a task that takes 1.3 ms: the next ones start late and miss */
    sched_tick(&SC); sup_tick(&SU);                     /* (the periods just advance; no idle in between) */
    CHECK(sup_safe_requested(&SU));
    CHECK(count_type(CLOG_DEADLINE) >= 1);
    CHECK(count_type(CLOG_SAFE_REQUEST) == 1);
    {   uint32_t n = count_type(CLOG_DEADLINE);
        sup_tick(&SU);                                  /* the miss flag was cleared: not reported twice */
        CHECK_EQ(count_type(CLOG_DEADLINE), n); }
}

TEST(watchdog_checkins)
{
    uint32_t i, k0;
    setup();
    for (i = 0; i < 10; i++) period();
    CHECK_EQ(S.wdog_kicks, 10);
    do_checkin[2] = false;                              /* one supervised task stops checking in */
    k0 = S.wdog_kicks;
    for (i = 0; i < 5; i++) period();
    CHECK_EQ(S.wdog_kicks, k0);                         /* no kick: the hardware watchdog will fire */
    CHECK_EQ(count_type(CLOG_WDOG_STARVED), 1);         /* logged once, not at each period */
    CHECK_EQ(SU.starved_periods, 5);
    do_checkin[2] = true;
    for (i = 0; i < 3; i++) period();
    CHECK_EQ(S.wdog_kicks, k0 + 3);
    do_checkin[0] = false; period(); do_checkin[0] = true; period();
    CHECK_EQ(count_type(CLOG_WDOG_STARVED), 2);         /* a new starvation episode is logged again */
}

TEST(registration_limits)
{
    sup_t u; int i;
    hal_sim_init(&S, 1); sched_init(&SC, &S.hal); clog_open(&LG, &S.hal, 0, 4096); mbox_init(&HB);
    sup_init(&u, &S.hal, &SC, &LG, &HB);
    for (i = 0; i < (int)SUP_MAX; i++) CHECK(sup_register(&u, 0) == i);
    CHECK(sup_register(&u, 0) < 0);
    CHECK(sup_register(&u, -1) < 0);
    sup_checkin(&u, 99); sup_checkin(&u, -1);          /* ignored */
}

int main(void) { RUN(normal_run); RUN(overrun_streak); RUN(deadline_miss); RUN(watchdog_checkins); RUN(registration_limits); TC_DONE(); }
