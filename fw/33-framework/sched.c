#include "sched.h"

#define STACK_PAINT 0xA5u

void sched_init(sched_t *s, hal_t *hal)
{
    memset(s, 0, sizeof *s);
    s->hal = hal;
    atomic_init(&s->events, 0);
}

int sched_add(sched_t *s, const sched_task_cfg *c)
{
    sched_task *t;
    if (s->started || s->n >= SCHED_MAX_TASKS || c->fn == NULL || c->period_us == 0) return -1;
    t = &s->tasks[s->n];
    memset(t, 0, sizeof *t);
    t->cfg = *c;
    if (t->cfg.deadline_us == 0) t->cfg.deadline_us = t->cfg.period_us;
    return s->n++;
}

int sched_on_event(sched_t *s, uint8_t ev, void (*fn)(void *), void *arg)
{
    if (ev >= SCHED_MAX_EVENTS || fn == NULL) return -1;
    s->ev_fn[ev] = fn; s->ev_arg[ev] = arg;
    return 0;
}

void sched_start(sched_t *s)
{
    uint8_t i, j;
    uint64_t now = hal_cycles(s->hal);
    for (i = 0; i < s->n; i++) { s->order[i] = i; s->tasks[i].next_rel = now; }
    /* stable insertion sort by priority */
    for (i = 1; i < s->n; i++) {
        uint8_t v = s->order[i];
        for (j = i; j > 0 && s->tasks[s->order[j - 1]].cfg.prio > s->tasks[v].cfg.prio; j--) s->order[j] = s->order[j - 1];
        s->order[j] = v;
    }
    s->started = true;
    s->t0 = now; s->busy = 0;
}

void sched_post(sched_t *s, uint8_t ev)
{
    if (ev < SCHED_MAX_EVENTS) atomic_fetch_or_explicit(&s->events, 1u << ev, memory_order_release);
}

void sched_tick(sched_t *s)
{
    uint64_t now = hal_cycles(s->hal);
    uint32_t ev;
    bool rel[SCHED_MAX_TASKS];
    uint8_t i;
    if (!s->started) return;

    /* deferred interrupt handlers */
    ev = atomic_exchange_explicit(&s->events, 0, memory_order_acquire);
    for (i = 0; i < SCHED_MAX_EVENTS && ev; i++) {
        if (ev & (1u << i)) {
            uint64_t a = hal_cycles(s->hal);
            ev &= ~(1u << i);
            if (s->ev_fn[i]) { s->ev_fn[i](s->ev_arg[i]); s->ev_runs[i]++; }
            s->busy += hal_cycles(s->hal) - a;
        }
    }

    /* the set of tasks released is decided at the start of the tick */
    for (i = 0; i < s->n; i++) rel[i] = now >= s->tasks[i].next_rel;

    for (i = 0; i < s->n; i++) {
        uint8_t k = s->order[i];
        sched_task *t = &s->tasks[k];
        uint64_t start, end, period_c, dl_c, release;
        uint32_t cyc;
        if (!rel[k]) continue;
        period_c = (uint64_t)t->cfg.period_us * HAL_CORE_MHZ;
        dl_c = (uint64_t)t->cfg.deadline_us * HAL_CORE_MHZ;
        release = t->next_rel;
        start = hal_cycles(s->hal);
        t->cfg.fn(t->cfg.arg);
        end = hal_cycles(s->hal);
        cyc = (uint32_t)(end - start);
        s->busy += end - start;

        t->st.runs++;
        t->st.sum_cycles += cyc;
        t->st.last_cycles = cyc;
        if (cyc > t->st.max_cycles) t->st.max_cycles = cyc;
        if (t->cfg.budget_cycles && cyc > t->cfg.budget_cycles) { t->st.overruns++; t->st.consec_overrun++; }
        else t->st.consec_overrun = 0;
        if (end > release + dl_c) { t->st.misses++; t->st.miss_flag = true; }

        /* next release: the next grid point after the release just served; periods already past are skipped, not queued */
        t->next_rel = release + period_c;
        if (now >= t->next_rel) {
            uint64_t late = (now - t->next_rel) / period_c + 1u;
            t->st.skipped += late;
            t->next_rel += late * period_c;
        }
    }
}

uint64_t sched_next_due(const sched_t *s)
{
    uint8_t i;
    uint64_t m = UINT64_MAX;
    for (i = 0; i < s->n; i++) if (s->tasks[i].next_rel < m) m = s->tasks[i].next_rel;
    return m;
}

uint32_t sched_load_x1000(const sched_t *s)
{
    uint64_t el = hal_cycles(s->hal) - s->t0;
    if (el == 0) return 0;
    return (uint32_t)((s->busy * 1000u) / el);
}

void sched_window_reset(sched_t *s) { s->t0 = hal_cycles(s->hal); s->busy = 0; }

const sched_stats *sched_get(const sched_t *s, int idx)
{
    return (idx >= 0 && idx < s->n) ? &s->tasks[idx].st : NULL;
}

void fw_stack_paint(void *base, size_t n) { memset(base, STACK_PAINT, n); }

size_t fw_stack_used(const void *base, size_t n)
{
    const uint8_t *p = (const uint8_t *)base;
    size_t i = 0;
    while (i < n && p[i] == STACK_PAINT) i++;      /* untouched part is at the low end */
    return n - i;
}

void sched_clear_miss(sched_t *s, int idx)
{
    if (idx >= 0 && idx < s->n) s->tasks[idx].st.miss_flag = false;
}
