/* sched - static run-to-completion scheduler with per-task accounting (R33-02, R33-03).
 * Tasks are released on a fixed grid (release = nominal time, so late service shows as a deadline miss, not as drift) and run in priority order
 * (lower number first) when sched_tick() is called from the frame timer. Deferred interrupt events run at the top of a tick. No heap. */
#ifndef SCHED_H
#define SCHED_H

#include "hal.h"
#include <stdatomic.h>

#define SCHED_MAX_TASKS  16u
#define SCHED_MAX_EVENTS 32u

typedef struct {
    const char *name;
    void (*fn)(void *arg);
    void *arg;
    uint32_t period_us;          /* release period */
    uint32_t deadline_us;        /* relative to the nominal release; 0: same as the period */
    uint32_t budget_cycles;      /* maximum cycles of one run; more counts as an overrun */
    uint8_t  prio;               /* 0 is the highest */
} sched_task_cfg;

typedef struct {
    uint64_t runs, overruns, misses, skipped;   /* skipped: periods that passed without a run (late tick) */
    uint64_t sum_cycles;
    uint32_t max_cycles, last_cycles;
    uint32_t consec_overrun;                    /* overruns in a row, cleared by a run within budget */
    bool     miss_flag;                         /* a deadline miss since the flag was last cleared */
} sched_stats;

typedef struct {
    sched_task_cfg cfg;
    sched_stats    st;
    uint64_t       next_rel;                    /* cycles */
} sched_task;

typedef struct {
    hal_t *hal;
    sched_task tasks[SCHED_MAX_TASKS];
    uint8_t    order[SCHED_MAX_TASKS];          /* task indices sorted by priority (stable) */
    uint8_t    n;
    bool       started;
    _Atomic uint32_t events;
    void     (*ev_fn[SCHED_MAX_EVENTS])(void *);
    void      *ev_arg[SCHED_MAX_EVENTS];
    uint64_t   ev_runs[SCHED_MAX_EVENTS];
    uint64_t   t0, busy;                        /* accounting window start and busy cycles inside it */
} sched_t;

void sched_init(sched_t *s, hal_t *hal);
int  sched_add(sched_t *s, const sched_task_cfg *c);                 /* index, or -1 (full, started, bad config) */
int  sched_on_event(sched_t *s, uint8_t ev, void (*fn)(void *), void *arg);   /* 0 or -1 */
void sched_start(sched_t *s);                                        /* the first release of every task is now */
void sched_post(sched_t *s, uint8_t ev);                             /* safe from interrupt context and from another core */
void sched_tick(sched_t *s);                                         /* release, run, account */
uint64_t sched_next_due(const sched_t *s);                           /* cycle count of the earliest next release */
uint32_t sched_load_x1000(const sched_t *s);                         /* busy / elapsed over the window, 1000 = 100% */
void sched_window_reset(sched_t *s);
const sched_stats *sched_get(const sched_t *s, int idx);
void sched_clear_miss(sched_t *s, int idx);

/* stack high-water: paint a region, later ask how much of it was touched (growing downwards from the end) */
void   fw_stack_paint(void *base, size_t n);
size_t fw_stack_used(const void *base, size_t n);

#endif
