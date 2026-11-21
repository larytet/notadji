#include "sup.h"
#include "crc.h"

void sup_init(sup_t *u, hal_t *h, sched_t *s, clog_t *log, mbox_t *hb)
{
    memset(u, 0, sizeof *u);
    u->h = h; u->s = s; u->log = log; u->hb = hb;
}

int sup_register(sup_t *u, int sched_idx)
{
    if (u->n >= SUP_MAX || sched_idx < 0) return -1;
    u->task[u->n] = sched_idx;
    return u->n++;
}

void sup_checkin(sup_t *u, int id)
{
    if (id >= 0 && id < u->n) u->checked[id] = true;
}

bool sup_safe_requested(const sup_t *u) { return u->safe_req; }
void sup_safe_clear(sup_t *u) { u->safe_req = false; }

void sup_tick(sup_t *u)
{
    uint8_t i;
    bool all = true;
    uint32_t words[4];
    for (i = 0; i < u->n; i++) {
        const sched_stats *st = sched_get(u->s, u->task[i]);
        if (st == NULL) continue;
        /* log an overrun streak once when it reaches the limit, again every further multiple of the limit */
        if (st->consec_overrun >= SUP_OVERRUN_LIMIT && st->consec_overrun % SUP_OVERRUN_LIMIT == 0 &&
            st->consec_overrun != u->last_overrun_logged[i]) {
            clog_append(u->log, CLOG_TASK_OVERRUN, 0, i, st->consec_overrun, st->max_cycles, (uint32_t)st->overruns);
            u->last_overrun_logged[i] = st->consec_overrun;
            if (!u->safe_req) clog_append(u->log, CLOG_SAFE_REQUEST, 0, i, 1, 0, 0);
            u->safe_req = true;
        }
        if (st->consec_overrun == 0) u->last_overrun_logged[i] = 0;
        if (st->miss_flag) {
            clog_append(u->log, CLOG_DEADLINE, 0, i, (uint32_t)st->misses, st->last_cycles, 0);
            if (!u->safe_req) clog_append(u->log, CLOG_SAFE_REQUEST, 0, i, 2, 0, 0);
            u->safe_req = true;
            sched_clear_miss(u->s, u->task[i]);
        }
        if (!u->checked[i]) all = false;
    }
    if (all) {
        u->h->wdog_kick(u->h);
        u->kicks++;
        u->starved_logged = false;
    } else {
        u->starved_periods++;
        if (!u->starved_logged) {
            for (i = 0; i < u->n && u->checked[i]; i++) { }
            clog_append(u->log, CLOG_WDOG_STARVED, 0, i, u->starved_periods, 0, 0);
            u->starved_logged = true;
        }
    }
    for (i = 0; i < u->n; i++) u->checked[i] = false;
    u->heartbeat++;
    words[0] = u->heartbeat; words[1] = u->safe_req ? 1u : 0u; words[2] = u->kicks; words[3] = u->main_state;
    mbox_write(u->hb, words, 4);
}

/* ---------------- monitor ---------------- */

static uint32_t safe_sum(const mon_t *m)
{
    uint8_t b[SEQ_DEPTH * 8];
    uint32_t i;
    for (i = 0; i < m->safe_n; i++) {
        fw_st32(b + 8u * i, m->safe[i].time);
        fw_st32(b + 8u * i + 4u, ((uint32_t)m->safe[i].act << 16) | m->safe[i].arg);
    }
    return crc32_ieee(b, 8u * m->safe_n);
}

bool mon_init(mon_t *m, hal_t *h, clog_t *log, const mbox_t *hb, _Atomic uint32_t *owner,
              const seq_entry *safe, uint32_t n, uint32_t hold_frames, uint32_t wait_frames)
{
    if (seq_validate(safe, n) != SEQ_OK) return false;
    memset(m, 0, sizeof *m);
    m->h = h; m->log = log; m->hb = hb; m->owner = owner;
    seq_drv_init(&m->drv, h);
    memcpy(m->safe, safe, n * sizeof safe[0]);
    m->safe_n = n; m->safe_crc = safe_sum(m);
    m->hold_limit = hold_frames; m->wait_limit = wait_frames;
    m->last_fc = hal_rd(h, SEQ_FRAME_CNT);
    m->state = MON_WATCH;
    atomic_store(owner, MON_OWNER_MAIN);
    return true;
}

static bool commit_safe(mon_t *m)
{
    if (safe_sum(m) != m->safe_crc) {                       /* the table in this core's memory was damaged: never commit it */
        m->bad_table++;
        clog_append(m->log, CLOG_SAFE_TABLE_BAD, 0, m->safe_crc, safe_sum(m), 0, 0);
        return false;
    }
    /* the main core is halted: the frame position does not matter for the writes, but the table must still land in the inactive bank */
    return seq_load_unguarded(&m->drv, m->safe, m->safe_n) == SEQ_OK;
}

void mon_poll(mon_t *m)
{
    uint32_t fc = hal_rd(m->h, SEQ_FRAME_CNT);
    uint32_t df = fc - m->last_fc, w[4] = {0, 0, 0, 0}, seq;
    bool hb_moved;
    if (df == 0) return;
    m->last_fc = fc;
    seq = mbox_read(m->hb, w, 4);
    hb_moved = (seq != 0 && w[0] != m->last_hb);
    if (seq != 0) m->last_hb = w[0];

    switch (m->state) {
    case MON_WATCH: {
        uint32_t missed = hal_rd(m->h, SEQ_MISSED);
        if (m->grace) { m->grace = m->grace > df ? m->grace - df : 0; missed = 0; }
        if (hb_moved) m->stale_frames = 0; else m->stale_frames += df;
        if (m->stale_frames >= MON_STALL_FRAMES || missed >= MON_STALL_FRAMES) {
            uint32_t expected = MON_OWNER_MAIN;
            hal_wr(m->h, SYS_MAIN_HALT, 1);                  /* stop the main core first: no concurrent writer */
            if (atomic_compare_exchange_strong(m->owner, &expected, MON_OWNER_MON)) {
                bool ok = commit_safe(m);
                m->takeovers++;
                clog_append(m->log, CLOG_MONITOR_SAFE, 0, m->stale_frames, missed, ok ? 1u : 0u, fc);
                m->state = MON_SAFE_HOLD; m->hold_frames = 0;
            }
        }
        break; }
    case MON_SAFE_HOLD:
        m->hold_frames += df;
        if (m->hold_frames >= m->hold_limit) {
            hal_wr(m->h, SYS_MAIN_HALT, 0);                  /* release: the main core restarts */
            m->state = MON_WAIT_ALIVE; m->wait_frames = 0; m->alive_frames = 0;
        }
        break;
    case MON_WAIT_ALIVE:
        m->wait_frames += df;
        if (hb_moved) m->alive_frames += df;
        if (m->alive_frames >= MON_STALL_FRAMES ) {   /* the heartbeat is back; the main core commits tables once it owns the sequencer again */
            atomic_store_explicit(m->owner, MON_OWNER_MAIN, memory_order_release);
            clog_append(m->log, CLOG_MONITOR_RELEASE, 0, m->wait_frames, 0, 0, fc);
            m->state = MON_WATCH; m->stale_frames = 0; m->grace = MON_STALL_FRAMES + 1u;   /* `missed` still shows the hold time until the first commit */
        } else if (m->wait_frames >= m->wait_limit) {        /* did not come back: halt again and keep the safe table */
            hal_wr(m->h, SYS_MAIN_HALT, 1);
            m->state = MON_SAFE_HOLD; m->hold_frames = 0;
        }
        break;
    }
}
