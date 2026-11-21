// SRC: sched.c
// LIBS: -pthread
/* T33-02, T33-03, T33-04: scheduler order and release, accounting, deferred events */
#include "tcheck.h"
#include "hal_sim.h"
#include "sched.h"
#include <pthread.h>

static hal_sim S;
static int trace[64], trace_n;
static uint32_t cost[4];

static void task_fn(void *a)
{
    int id = (int)(intptr_t)a;
    if (trace_n < 64) trace[trace_n++] = id;
    hal_sim_burn(&S, cost[id]);
}

static sched_task_cfg mk(const char *n, int id, uint32_t period, uint32_t budget, uint8_t prio)
{
    sched_task_cfg c = { n, task_fn, (void *)(intptr_t)id, period, 0, budget, prio };
    return c;
}

TEST(order_and_period)
{
    sched_t s; sched_task_cfg a, b, c; int ia, ib, ic, k;
    hal_sim_init(&S, 1); sched_init(&s, &S.hal);
    memset(cost, 0, sizeof cost);
    a = mk("A", 0, 1000, 0, 2); b = mk("B", 1, 1000, 0, 1); c = mk("C", 2, 2000, 0, 3);
    ia = sched_add(&s, &a); ib = sched_add(&s, &b); ic = sched_add(&s, &c);
    CHECK(ia == 0 && ib == 1 && ic == 2);
    sched_start(&s);
    sched_tick(&s);
    CHECK_EQ(trace_n, 3);
    CHECK(trace[0] == 1 && trace[1] == 0 && trace[2] == 2);       /* B (prio 1), A (2), C (3) */
    for (k = 1; k < 100000; k++) { hal_sim_advance_us(&S, 1000); sched_tick(&s); }
    CHECK_EQ(sched_get(&s, ia)->runs, 100000);
    CHECK_EQ(sched_get(&s, ib)->runs, 100000);
    CHECK_EQ(sched_get(&s, ic)->runs, 50000);
    CHECK_EQ(sched_get(&s, ia)->skipped, 0);
    CHECK_EQ(sched_get(&s, ia)->misses, 0);
    /* nothing can be added once started */
    CHECK(sched_add(&s, &a) < 0);
}

TEST(late_tick_no_double_release)
{
    sched_t s; sched_task_cfg a; int ia;
    hal_sim_init(&S, 1); sched_init(&s, &S.hal);
    memset(cost, 0, sizeof cost); trace_n = 0;
    a = mk("A", 0, 1000, 0, 1);
    ia = sched_add(&s, &a);
    sched_start(&s);
    sched_tick(&s);                                   /* t = 0 */
    hal_sim_advance_us(&S, 3000);                     /* three periods pass without a tick */
    sched_tick(&s);
    CHECK_EQ(sched_get(&s, ia)->runs, 2);             /* one run, not three */
    CHECK_EQ(sched_get(&s, ia)->skipped, 2);          /* releases at 2 ms and 3 ms were never served */
    CHECK_EQ(sched_get(&s, ia)->misses, 1);           /* it ran 3 ms after its release, deadline is 1 ms */
    sched_tick(&s);                                   /* same instant: not released again */
    CHECK_EQ(sched_get(&s, ia)->runs, 2);
    hal_sim_advance_us(&S, 1000);
    sched_tick(&s);
    CHECK_EQ(sched_get(&s, ia)->runs, 3);             /* back on the grid */
    CHECK_EQ(sched_get(&s, ia)->skipped, 2);
}

TEST(accounting_random)
{
    sched_t s; sched_task_cfg c[3]; int idx[3], j; uint32_t k;
    uint64_t sum[3] = {0,0,0}, run[3] = {0,0,0}, over[3] = {0,0,0}; uint32_t mx[3] = {0,0,0};
    uint64_t busy = 0, t0;
    uint32_t period[3] = {1000, 1000, 2000};
    uint32_t budget[3] = {20000, 30000, 50000};
    hal_sim_init(&S, 1); sched_init(&s, &S.hal);
    for (j = 0; j < 3; j++) { c[j] = mk("t", j, period[j], budget[j], (uint8_t)j); idx[j] = sched_add(&s, &c[j]); }
    sched_start(&s); t0 = hal_cycles(&S.hal);
    tc_rs = 12345;
    for (k = 0; k < 20000u; k++) {
        uint32_t cur[3];
        for (j = 0; j < 3; j++) cost[j] = (uint32_t)(tc_rand() % (budget[j] * 12u / 10u));
        memcpy(cur, cost, sizeof cur);
        sched_tick(&s);
        for (j = 0; j < 3; j++) {
            if (k % (period[j] / 1000u) == 0) {
                sum[j] += cur[j]; run[j]++; busy += cur[j];
                if (cur[j] > mx[j]) mx[j] = cur[j];
                if (cur[j] > budget[j]) over[j]++;
            }
        }
        /* next 1 ms boundary: advance idle time up to it (the tasks' own cost is already in the clock) */
        {
            uint64_t target = t0 + (uint64_t)(k + 1u) * 1000u * HAL_CORE_MHZ, now = hal_cycles(&S.hal);
            if (now < target) hal_sim_burn(&S, target - now);
        }
    }
    for (j = 0; j < 3; j++) {
        const sched_stats *st = sched_get(&s, idx[j]);
        CHECK_EQ(st->runs, run[j]);
        CHECK_EQ(st->sum_cycles, sum[j]);
        CHECK_EQ(st->max_cycles, mx[j]);
        CHECK_EQ(st->overruns, over[j]);
    }
    {
        uint64_t el = hal_cycles(&S.hal) - t0;
        long long expect = (long long)(busy * 1000u / el);
        long long got = sched_load_x1000(&s);
        CHECK(llabs(got - expect) <= 1);
    }
}

static void burn_to_due(sched_t *s)
{
    uint64_t d = sched_next_due(s), n = hal_cycles(&S.hal);
    if (d > n) hal_sim_burn(&S, d - n);
}

TEST(overrun_consecutive_and_miss_flag)
{
    sched_t s; sched_task_cfg a; int ia;
    hal_sim_init(&S, 1); sched_init(&s, &S.hal);
    a = mk("A", 0, 1000, 1000, 0);
    ia = sched_add(&s, &a);
    sched_start(&s);
    cost[0] = 5000; sched_tick(&s);
    CHECK_EQ(sched_get(&s, ia)->consec_overrun, 1);
    burn_to_due(&s); cost[0] = 5000; sched_tick(&s);
    CHECK_EQ(sched_get(&s, ia)->consec_overrun, 2);
    burn_to_due(&s); cost[0] = 100; sched_tick(&s);
    CHECK_EQ(sched_get(&s, ia)->consec_overrun, 0);
    CHECK_EQ(sched_get(&s, ia)->overruns, 2);
    CHECK_EQ(sched_get(&s, ia)->misses, 0);
}

TEST(stack_paint)
{
    uint8_t stack[256]; size_t i;
    fw_stack_paint(stack, sizeof stack);
    CHECK_EQ(fw_stack_used(stack, sizeof stack), 0);
    for (i = 200; i < 256; i++) stack[i] = 0;
    CHECK_EQ(fw_stack_used(stack, sizeof stack), 56);
}

static int ev_runs[4];
static void ev_fn(void *a) { ev_runs[(int)(intptr_t)a]++; }
static sched_t *EVS;
static _Atomic int ev_stop;
static void *poster(void *arg)
{
    int i, n = (int)(intptr_t)arg;
    for (i = 0; i < n; i++) {
        int before = ev_runs[1];
        sched_post(EVS, 1);
        while (__atomic_load_n(&ev_runs[1], __ATOMIC_ACQUIRE) == before) { }     /* handshake: wait until the handler has run */
    }
    atomic_store(&ev_stop, 1);
    return NULL;
}

TEST(events)
{
    sched_t s; pthread_t th; int n = 100000;
    hal_sim_init(&S, 1); sched_init(&s, &S.hal);
    CHECK_EQ(sched_on_event(&s, 0, ev_fn, (void *)(intptr_t)0), 0);
    CHECK_EQ(sched_on_event(&s, 1, ev_fn, (void *)(intptr_t)1), 0);
    CHECK(sched_on_event(&s, 32, ev_fn, NULL) < 0);
    sched_start(&s);
    EVS = &s; atomic_store(&ev_stop, 0);
    memset(ev_runs, 0, sizeof ev_runs);
    pthread_create(&th, NULL, poster, (void *)(intptr_t)n);
    while (!atomic_load(&ev_stop)) sched_tick(&s);
    pthread_join(th, NULL);
    sched_tick(&s);
    CHECK_EQ(ev_runs[1], n);                          /* every post ran exactly once */
    CHECK_EQ(ev_runs[0], 0);                          /* nothing spurious */
    /* two events posted before one tick: both run once (events coalesce per tick, never run twice) */
    sched_post(&s, 0); sched_post(&s, 0); sched_post(&s, 1);
    sched_tick(&s);
    CHECK_EQ(ev_runs[0], 1); CHECK_EQ(ev_runs[1], n + 1);
}

int main(void)
{
    RUN(order_and_period); RUN(late_tick_no_double_release); RUN(accounting_random);
    RUN(overrun_consecutive_and_miss_flag); RUN(stack_paint); RUN(events);
    TC_DONE();
}
