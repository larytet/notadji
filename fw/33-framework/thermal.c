#include "thermal.h"

void therm_default_cfg(therm_cfg *c)
{
    static const int16_t en[4] = { THERM_C(85), THERM_C(95), THERM_C(105), THERM_C(115) };
    static const int16_t lv[4] = { THERM_C(80), THERM_C(90), THERM_C(100), THERM_C(110) };
    static const int16_t bo[5] = { 0, 12, 12, 24, 0 };           /* 3 dB from level 1, 6 dB at level 3 */
    static const uint8_t br[5] = { 100, 100, 70, 40, 0 };
    static const uint8_t fd[5] = { 1, 1, 1, 2, 1 };
    uint8_t i;
    for (i = 0; i < 4; i++) { c->enter_x4[i] = en[i]; c->leave_x4[i] = lv[i]; }
    for (i = 0; i < 5; i++) { c->pwr_backoff_x4[i] = bo[i]; c->bitrate_pct[i] = br[i]; c->fps_div[i] = fd[i]; }
    c->min_dwell_ms = 1000;
    c->valid_min_x4 = THERM_C(-40); c->valid_max_x4 = THERM_C(150);
    c->stuck_ms = 2000; c->stuck_move_x4 = THERM_C(1);
    c->recal_dt_x4 = THERM_C(5); c->recal_period_ms = 60000;
}

void therm_init(therm_t *t, const therm_cfg *c, uint32_t now_ms)
{
    memset(t, 0, sizeof *t);
    t->cfg = *c;
    t->level_since_ms = now_ms; t->cal_ms = now_ms;
    t->recal_due = true;                                   /* no calibration yet at power-up */
}

static int16_t absd(int16_t a, int16_t b) { int32_t d = (int32_t)a - b; return (int16_t)(d < 0 ? -d : d); }

void therm_update(therm_t *t, const int16_t raw[THERM_N], bool hw_trip, uint32_t now_ms, therm_out *o)
{
    const therm_cfg *c = &t->cfg;
    uint8_t i, j, target, prev = t->level, nvalid = 0, inv = 0;
    int16_t hot = c->valid_min_x4, fallback = (int16_t)(c->enter_x4[3] - 1), pa_ref = 0;
    bool have_ref = false;

    /* change tracking for the stuck detector */
    for (i = 0; i < THERM_N; i++) {
        if (!t->have || raw[i] != t->last_raw[i]) {
            t->same_since_ms[i] = now_ms; t->stuck[i] = false;
            for (j = 0; j < THERM_N; j++) t->anchor[i][j] = raw[j];
        }
    }
    for (i = 0; i < THERM_N; i++) {
        if ((uint32_t)(now_ms - t->same_since_ms[i]) >= c->stuck_ms) {
            for (j = 0; j < THERM_N; j++) if (j != i && absd(raw[j], t->anchor[i][j]) > c->stuck_move_x4) { t->stuck[i] = true; break; }
        }
        t->last_raw[i] = raw[i];
    }
    t->have = true;

    for (i = 0; i < THERM_N; i++) {
        bool bad = raw[i] < c->valid_min_x4 || raw[i] > c->valid_max_x4 || t->stuck[i];
        if (bad) { inv |= (uint8_t)(1u << i); continue; }
        nvalid++;
        if (raw[i] > hot) hot = raw[i];
        if (i == 0) { pa_ref = raw[0]; have_ref = true; }
    }
    /* an invalid sensor reads as just below the shutdown threshold (treated as hot); all invalid: shut down */
    if (inv && fallback > hot) hot = fallback;
    if (nvalid == 0) hot = (int16_t)(c->enter_x4[3] + 1);

    /* level: up at once to the highest entered level, down one step at a time after the dwell and below the leave threshold */
    target = 0;
    for (i = 0; i < 4; i++) if (hot >= c->enter_x4[i]) target = (uint8_t)(i + 1u);
    if (hw_trip) target = 4;
    if (target > t->level) { t->level = target; t->level_since_ms = now_ms; }
    else if (t->level > 0 && !hw_trip && hot < c->leave_x4[t->level - 1u] && (uint32_t)(now_ms - t->level_since_ms) >= c->min_dwell_ms) {
        t->level--; t->level_since_ms = now_ms;
    }

    /* re-calibration trigger (CAL-003): the PA sensor if valid, else the hottest */
    {
        int16_t ref = have_ref ? pa_ref : hot;
        if (absd(ref, t->t_cal_x4) >= c->recal_dt_x4) t->recal_due = true;
        if ((uint32_t)(now_ms - t->cal_ms) >= c->recal_period_ms) t->recal_due = true;
    }

    o->level = t->level;
    o->pwr_backoff_x4 = c->pwr_backoff_x4[t->level];
    o->bitrate_pct = c->bitrate_pct[t->level];
    o->fps_div = c->fps_div[t->level];
    o->shutdown = t->level >= 4u;
    o->hw_trip = hw_trip;
    o->hottest_x4 = hot;
    o->invalid_mask = inv;
    o->recal_due = t->recal_due;
    o->changed = t->level != prev;
}

void therm_recal_done(therm_t *t, uint32_t now_ms)
{
    int16_t ref = t->last_raw[0];
    t->t_cal_x4 = (ref >= t->cfg.valid_min_x4 && ref <= t->cfg.valid_max_x4 && !t->stuck[0]) ? ref : t->t_cal_x4;
    t->cal_ms = now_ms; t->recal_due = false;
}
