#include "cal_mgr.h"

static uint32_t elapsed(uint32_t now, uint32_t then) { return now - then; }

uint32_t cal_crc32(const uint8_t *p, uint32_t n)
{
    uint32_t crc = 0xFFFFFFFFu, i;
    uint8_t b;
    for (i = 0; i < n; i++) {
        crc ^= p[i];
        for (b = 0; b < 8; b++) crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1u)));
    }
    return ~crc;
}

static uint64_t uabs64(int64_t v) { return v < 0 ? (uint64_t)0 - (uint64_t)v : (uint64_t)v; }

/* round-to-nearest signed division of a by a positive b */
static int64_t sdiv(int64_t a, uint64_t b)
{
    uint64_t q = (uabs64(a) + b / 2u) / b;
    return a < 0 ? -(int64_t)q : (int64_t)q;
}

static int16_t sat16(int64_t v) { return (int16_t)(v > 32767 ? 32767 : (v < -32768 ? -32768 : v)); }

cal_status cal_stats_to_coeff(const cal_sums *s, const cal_lim *lim, cal_coeff *out)
{
    uint64_t ai, aq, di, dq, sii, sqq, p;
    int64_t mean_i, mean_q, siq, a;
    uint64_t pm;
    int64_t er, ei;
    if (s->n < lim->min_n || s->n == 0) return CAL_REJ_N;
    ai = uabs64(s->sum_i);
    aq = uabs64(s->sum_q);
    if (ai >= 0x100000000ull || aq >= 0x100000000ull) return CAL_REJ_SAT;        /* more than 2^17 full-scale samples: out of range */
    mean_i = sdiv(s->sum_i, s->n);
    mean_q = sdiv(s->sum_q, s->n);
    if (mean_i > lim->dc_max || mean_i < -lim->dc_max || mean_q > lim->dc_max || mean_q < -lim->dc_max) return CAL_REJ_DC;
    /* centred second moments: S - S_x S_y / N */
    di = (ai * ai) / s->n;
    dq = (aq * aq) / s->n;
    sii = s->sum_ii > di ? s->sum_ii - di : 0u;
    sqq = s->sum_qq > dq ? s->sum_qq - dq : 0u;
    /* S_i S_q / N without overflow: (ai * aq) can reach 2^64, so divide one factor first with remainder handling */
    {
        uint64_t q1 = ai / s->n, r1 = ai % s->n;
        uint64_t prod = q1 * aq + (r1 * aq) / s->n;
        int neg = ((s->sum_i < 0) != (s->sum_q < 0));
        siq = neg ? -(int64_t)prod : (int64_t)prod;
        siq = s->sum_iq - siq;
    }
    p = sii + sqq;
    pm = p / s->n;
    if (pm < lim->min_power_x) return CAL_REJ_POWER;
    a = (int64_t)sii - (int64_t)sqq;
    er = sdiv(a * 16384, p);                      /* e_r = (S_ii - S_qq) / (2 P) in Q15 */
    ei = sdiv(siq * 32768, p);                    /* e_i = S_iq / P in Q15 */
    if (er > lim->eps_max || er < -lim->eps_max || ei > lim->eps_max || ei < -lim->eps_max) return CAL_REJ_EPS;
    out->dc_i = sat16(mean_i);
    out->dc_q = sat16(mean_q);
    out->eps_r = sat16(er);
    out->eps_i = sat16(ei);
    return CAL_OK;
}

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { put16(p, (uint16_t)v); put16(p + 2, (uint16_t)(v >> 16)); }
static uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t get32(const uint8_t *p) { return (uint32_t)get16(p) | ((uint32_t)get16(p + 2) << 16); }

void cal_entry_pack(const cal_entry *e, uint8_t out[CAL_NV_BYTES])
{
    put16(out + 0, e->version);
    out[2] = e->band;
    out[3] = e->group;
    out[4] = e->tbin;
    out[5] = e->valid;
    put16(out + 6, (uint16_t)e->rx.dc_i);
    put16(out + 8, (uint16_t)e->rx.dc_q);
    put16(out + 10, (uint16_t)e->rx.eps_r);
    put16(out + 12, (uint16_t)e->rx.eps_i);
    put16(out + 14, (uint16_t)e->tx.dc_i);
    put16(out + 16, (uint16_t)e->tx.dc_q);
    put16(out + 18, (uint16_t)e->tx.eps_r);
    put16(out + 20, (uint16_t)e->tx.eps_i);
    put16(out + 22, (uint16_t)e->tx_gain_x16);
    put16(out + 24, (uint16_t)e->rx_gain_x16);
    put16(out + 26, 0);
    put32(out + 28, cal_crc32(out, 28));
}

void cal_table_load(cal_table *t, const uint8_t nv[][CAL_NV_BYTES], uint16_t n)
{
    uint16_t i;
    t->n_bad = 0;
    for (i = 0; i < CAL_ENTRIES; i++) t->e[i].valid = 0;
    for (i = 0; i < n && i < CAL_ENTRIES; i++) {
        const uint8_t *p = nv[i];
        cal_entry *e = &t->e[i];
        e->valid = 0;
        if (cal_crc32(p, 28) != get32(p + 28) || get16(p) != CAL_VERSION || p[5] != 1u ||
            p[2] >= CAL_BANDS || p[3] >= CAL_GROUPS || p[4] >= CAL_TBINS ||
            i != (uint16_t)((p[2] * CAL_GROUPS + p[3]) * CAL_TBINS + p[4])) {
            t->n_bad++;
            continue;
        }
        e->version = get16(p);
        e->band = p[2];
        e->group = p[3];
        e->tbin = p[4];
        e->rx.dc_i = (int16_t)get16(p + 6);
        e->rx.dc_q = (int16_t)get16(p + 8);
        e->rx.eps_r = (int16_t)get16(p + 10);
        e->rx.eps_i = (int16_t)get16(p + 12);
        e->tx.dc_i = (int16_t)get16(p + 14);
        e->tx.dc_q = (int16_t)get16(p + 16);
        e->tx.eps_r = (int16_t)get16(p + 18);
        e->tx.eps_i = (int16_t)get16(p + 20);
        e->tx_gain_x16 = (int16_t)get16(p + 22);
        e->rx_gain_x16 = (int16_t)get16(p + 24);
        e->crc = get32(p + 28);
        e->valid = 1;
    }
}

int cal_lookup(const cal_table *t, uint8_t band, uint8_t group, int16_t temp_x10, uint8_t *steps)
{
    int tb, k, idx;
    uint8_t n = 0;
    if (band >= CAL_BANDS || group >= CAL_GROUPS) {
        *steps = 0;
        return -1;
    }
    tb = (temp_x10 < -200) ? 0 : (temp_x10 + 200) / 50;          /* 5 degC bins from -20 degC */
    if (tb >= CAL_TBINS) tb = CAL_TBINS - 1;
    for (k = 0; k < 2 * CAL_TBINS; k++) {
        int b;                                                          /* order: 0, +1, -1, +2, -2 ... */
        if (k == 0) b = tb;
        else if (k & 1) b = tb + (k + 1) / 2;
        else b = tb - k / 2;
        if (b < 0 || b >= CAL_TBINS) continue;
        n++;
        idx = (band * CAL_GROUPS + group) * CAL_TBINS + b;
        if (t->e[idx].valid) {
            *steps = n;
            return idx;
        }
    }
    *steps = n;
    return -1;
}

void cal_regs(const cal_entry *e, int16_t out[8])
{
    out[0] = e->rx.dc_i;
    out[1] = e->rx.dc_q;
    out[2] = e->rx.eps_r;
    out[3] = e->rx.eps_i;
    out[4] = e->tx.dc_i;
    out[5] = e->tx.dc_q;
    out[6] = e->tx.eps_r;
    out[7] = e->tx.eps_i;
}

static void neutral(cal_entry *e)
{
    e->version = CAL_VERSION;
    e->band = e->group = e->tbin = 0;
    e->valid = 0;
    e->rx.dc_i = e->rx.dc_q = e->rx.eps_r = e->rx.eps_i = 0;
    e->tx.dc_i = e->tx.dc_q = e->tx.eps_r = e->tx.eps_i = 0;
    e->tx_gain_x16 = 16;
    e->rx_gain_x16 = 16;
    e->crc = 0;
}

void cal_init(cal_mgr *m, const cal_table *t)
{
    uint8_t j;
    m->tab = t;
    neutral(&m->work);
    m->have_entry = 0;
    for (j = 0; j < 5; j++) {
        m->fresh[j] = 1;
        m->t_last[j] = 0;
        m->temp_last[j] = 0;
        m->done_once[j] = 0;
    }
    m->last_job_ms = 0;
    m->min_gap_ms = 5;
    m->period_ms = 60000;
    m->age_limit_ms = 600000;
    m->temp_step_x10 = 50;
    m->n_rej = m->n_ok = 0;
    m->default_used = 1;
}

void cal_on_hop(cal_mgr *m, uint8_t band, uint8_t group, int16_t temp_x10, uint32_t now_ms)
{
    uint8_t st, j;
    int idx = cal_lookup(m->tab, band, group, temp_x10, &st);
    if (idx >= 0) {
        m->work = m->tab->e[idx];
        m->have_entry = 1;
        m->default_used = 0;
        for (j = 1; j < 5; j++) {
            m->done_once[j] = 1;                                    /* the restored values count as a calibration of this temperature */
            m->temp_last[j] = (int16_t)(((int16_t)m->work.tbin * 5 - 20) * 10 + 25);
            m->t_last[j] = now_ms;
        }
    } else {
        neutral(&m->work);
        m->work.band = band;
        m->work.group = group;
        m->have_entry = 0;
        m->default_used = 1;
        for (j = 1; j < 5; j++) m->done_once[j] = 0;
    }
    for (j = 0; j < 5; j++) m->fresh[j] = 1;
}

static int due(const cal_mgr *m, uint8_t job, uint32_t now_ms, int16_t temp_x10)
{
    int d;
    if (!m->done_once[job]) return 1;
    d = temp_x10 - m->temp_last[job];
    if (d < 0) d = -d;
    if (d > m->temp_step_x10) return 1;
    return elapsed(now_ms, m->t_last[job]) >= m->period_ms;
}

cal_job cal_tick(cal_mgr *m, uint32_t now_ms, int16_t temp_x10, uint8_t windows)
{
    cal_job j = CAL_JOB_NONE;
    if (m->last_job_ms != 0 && elapsed(now_ms, m->last_job_ms) < m->min_gap_ms) return CAL_JOB_NONE;
    if ((windows & CAL_W_IDLE) && due(m, CAL_JOB_RX_DC, now_ms, temp_x10)) j = CAL_JOB_RX_DC;
    else if ((windows & CAL_W_GUARD_TX) && m->done_once[CAL_JOB_RX_DC] && due(m, CAL_JOB_TX_LO, now_ms, temp_x10)) j = CAL_JOB_TX_LO;
    else if ((windows & CAL_W_GUARD_TX) && m->done_once[CAL_JOB_RX_DC] && due(m, CAL_JOB_TX_IQ, now_ms, temp_x10)) j = CAL_JOB_TX_IQ;
    else if ((windows & (CAL_W_RX_BURST | CAL_W_IDLE)) && due(m, CAL_JOB_RX_IQ, now_ms, temp_x10)) j = CAL_JOB_RX_IQ;
    if (j != CAL_JOB_NONE) m->last_job_ms = now_ms ? now_ms : 1u;
    return j;
}

/* old + (delta >> k), rounding towards zero, saturated */
static int16_t step_add(int16_t old, int32_t delta, uint8_t k)
{
    int32_t s = delta >= 0 ? (delta >> k) : -((-delta) >> k);
    return sat16((int64_t)old + s);
}

/* The statistics of every job are taken on the signal as it is after the corrections in force, so the estimate is the residual and
 * the update is additive; the first update after a hop or a start takes the full residual, later ones a quarter of it. */
cal_status cal_result(cal_mgr *m, cal_job job, const cal_sums *s, const cal_lim *lim, uint32_t now_ms, int16_t temp_x10)
{
    cal_coeff c;
    cal_status st = cal_stats_to_coeff(s, lim, &c);
    uint8_t k;
    if (st != CAL_OK) {
        m->n_rej++;
        return st;
    }
    if (job > CAL_JOB_RX_IQ) return CAL_REJ_N;
    k = m->fresh[job] ? 0u : 2u;
    switch (job) {
    case CAL_JOB_RX_DC:
        m->work.rx.dc_i = step_add(m->work.rx.dc_i, c.dc_i, k);
        m->work.rx.dc_q = step_add(m->work.rx.dc_q, c.dc_q, k);
        break;
    case CAL_JOB_RX_IQ:
        m->work.rx.eps_r = step_add(m->work.rx.eps_r, c.eps_r, k);
        m->work.rx.eps_i = step_add(m->work.rx.eps_i, c.eps_i, k);
        break;
    case CAL_JOB_TX_LO:
        m->work.tx.dc_i = step_add(m->work.tx.dc_i, -(int32_t)c.dc_i, k);      /* the transmit path adds the negated leakage */
        m->work.tx.dc_q = step_add(m->work.tx.dc_q, -(int32_t)c.dc_q, k);
        break;
    case CAL_JOB_TX_IQ:
        m->work.tx.eps_r = step_add(m->work.tx.eps_r, c.eps_r, k);
        m->work.tx.eps_i = step_add(m->work.tx.eps_i, c.eps_i, k);
        break;
    default:
        return CAL_REJ_N;
    }
    m->t_last[job] = now_ms;
    m->temp_last[job] = temp_x10;
    m->done_once[job] = 1;
    m->n_ok++;
    m->fresh[job] = 0;
    m->have_entry = 1;
    return CAL_OK;
}
