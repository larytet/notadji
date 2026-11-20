#include "chan_select.h"

#define SCORE_NONE 0x7FFFFFFF

static uint32_t elapsed(uint32_t now, uint32_t then) { return now - then; }

void cs_default_cfg(cs_cfg *c)
{
    uint8_t i;
    c->n_ch = 12;
    c->enabled_mask = 0xFFFu;
    for (i = 0; i < CS_MAX_FALLBACK; i++) c->fallback[i] = 0;
    c->n_fallback = 0;
    c->link_id = 0;
    c->stale_ms = 2000;
    c->memory_ms = 10000;
    c->det_ms = 10;
    c->min_stay_ms = 500;
    c->probation_ms = 200;
    c->blacklist_ms = 5000;
    c->jitter_ms = 0;
    c->margin = 16;               /* 3 dB */
    c->rise = 32;                 /* 6 dB */
    c->adj_pen = 16;
    c->unknown_pen = 24;
    c->qual_pen = 48;
    c->strong_lg = 400;
    c->loss_trig_ppm = 20000;
    c->severe_ppm = 500000;
    c->confirm = 2;
    c->switch_lead = 4;
}

static int usable(const cs_state *s, const cs_cfg *c, uint8_t ch, uint32_t t_ms)
{
    if (ch >= c->n_ch || ch >= CS_MAX_CH) return 0;
    if (!((c->enabled_mask >> ch) & 1u)) return 0;
    if (s->ch[ch].bl && elapsed(s->ch[ch].bl_until, t_ms) < 0x80000000u && s->ch[ch].bl_until != t_ms) return 0;
    return 1;
}

static int is_strong(const cs_state *s, const cs_cfg *c, uint8_t ch, uint32_t t_ms)
{
    return ch < c->n_ch && s->ch[ch].have && elapsed(t_ms, s->ch[ch].t_scan) < c->stale_ms && (s->ch[ch].lvl_q4 >> 4) >= c->strong_lg;
}

int32_t cs_score(const cs_state *s, const cs_cfg *c, uint8_t ch, uint32_t t_ms)
{
    int32_t sc;
    const cs_chan *k;
    if (!usable(s, c, ch, t_ms)) return SCORE_NONE;
    k = &s->ch[ch];
    if (!k->have) return SCORE_NONE;                                  /* never scanned: only the fallback list may take it */
    sc = k->lvl_q4 >> 4;
    if (elapsed(t_ms, k->t_scan) >= c->stale_ms) sc += c->unknown_pen;
    if (ch > 0 && is_strong(s, c, (uint8_t)(ch - 1), t_ms)) sc += c->adj_pen;
    if (is_strong(s, c, (uint8_t)(ch + 1), t_ms)) sc += c->adj_pen;
    if (k->q_valid && elapsed(t_ms, k->q_t) < c->memory_ms && k->q_loss >= c->loss_trig_ppm) sc += c->qual_pen;
    return sc;
}

uint32_t cs_strong_adjacent(const cs_state *s, const cs_cfg *c, uint32_t t_ms)
{
    uint32_t m = 0;
    if (s->cur > 0 && is_strong(s, c, (uint8_t)(s->cur - 1), t_ms)) m |= 1u << (s->cur - 1);
    if (s->cur + 1 < c->n_ch && is_strong(s, c, (uint8_t)(s->cur + 1), t_ms)) m |= 1u << (s->cur + 1);
    return m;
}

void cs_init(cs_state *s, const cs_cfg *c, uint8_t start_ch, uint32_t t_ms)
{
    uint8_t i;
    for (i = 0; i < CS_MAX_CH; i++) {
        s->ch[i].lvl_q4 = 0;
        s->ch[i].t_scan = 0;
        s->ch[i].bl_until = 0;
        s->ch[i].q_t = 0;
        s->ch[i].q_loss = 0;
        s->ch[i].have = 0;
        s->ch[i].bl = 0;
        s->ch[i].q_valid = 0;
    }
    (void)c;
    s->cur = start_ch;
    s->prev = start_ch;
    s->have_prev = 0;
    s->last_switch_ms = t_ms - 0x10000000u;      /* long ago: the first switch is not held back */
    s->degr_since_ms = t_ms;
    s->severe_since_ms = t_ms;
    s->trig_ms = t_ms;
    s->degr = 0;
    s->severe = 0;
    s->trig_set = 0;
    s->confirm_cnt = 0;
    s->confirm_ch = 0;
    s->base_q4 = 0;
    s->base_set = 0;
    s->loss_ppm = 0;
    s->snr_ok = 0;
    s->jitter_wait = 0;
    s->n_switch = 0;
}

void cs_scan(cs_state *s, const cs_cfg *c, uint8_t ch, uint16_t lg, uint32_t t_ms)
{
    cs_chan *k;
    int32_t v = (int32_t)lg * 16;
    if (ch >= c->n_ch || ch >= CS_MAX_CH) return;
    k = &s->ch[ch];
    if (!k->have || elapsed(t_ms, k->t_scan) >= c->stale_ms) k->lvl_q4 = v;
    else k->lvl_q4 += (v - k->lvl_q4) / 4;
    k->have = 1;
    k->t_scan = t_ms;
    if (ch == s->cur) {
        /* slow baseline: falls at once, rises by 1/64 of the gap per scan */
        if (!s->base_set || k->lvl_q4 < s->base_q4) s->base_q4 = k->lvl_q4;
        else s->base_q4 += (k->lvl_q4 - s->base_q4) / 64;
        s->base_set = 1;
    }
}

void cs_quality(cs_state *s, const cs_cfg *c, uint32_t loss_ppm, uint32_t t_ms)
{
    int32_t d = (int32_t)loss_ppm - (int32_t)s->loss_ppm;
    s->loss_ppm = (uint32_t)((int32_t)s->loss_ppm + d / 2);        /* fast filter: the decision rule adds the dwell */
    s->ch[s->cur].q_loss = s->loss_ppm;
    s->ch[s->cur].q_t = t_ms;
    s->ch[s->cur].q_valid = 1;
    (void)c;
}

static void do_switch(cs_state *s, uint8_t target, uint32_t t_ms, uint16_t frame_no, uint8_t lead, uint8_t reason, cs_decision *d)
{
    d->switch_now = 1;
    d->target = target;
    d->effective_frame = (uint16_t)(frame_no + lead);
    d->reason = reason;
    s->prev = s->cur;
    s->have_prev = 1;
    s->cur = target;
    s->last_switch_ms = t_ms;
    s->degr = 0;
    s->severe = 0;
    s->trig_set = 0;
    s->confirm_cnt = 0;
    s->base_set = 0;
    s->loss_ppm = 0;
    s->n_switch++;
}

/* best candidate other than the current channel; returns 255 if none */
static uint8_t best_candidate(const cs_state *s, const cs_cfg *c, uint32_t t_ms, int32_t *score)
{
    uint8_t i, best = 255;
    int32_t bs = SCORE_NONE;
    for (i = 0; i < c->n_ch && i < CS_MAX_CH; i++) {
        int32_t sc;
        if (i == s->cur) continue;
        sc = cs_score(s, c, i, t_ms);
        if (sc < bs) {
            bs = sc;
            best = i;
        }
    }
    *score = bs;
    return best;
}

static uint8_t fallback_pick(const cs_state *s, const cs_cfg *c, uint32_t t_ms)
{
    uint8_t i;
    for (i = 0; i < c->n_fallback && i < CS_MAX_FALLBACK; i++) {
        if (c->fallback[i] != s->cur && usable(s, c, c->fallback[i], t_ms)) return c->fallback[i];
    }
    return 255;
}

void cs_tick(cs_state *s, const cs_cfg *c, uint32_t t_ms, uint16_t frame_no, cs_decision *d)
{
    int32_t cur_q4 = s->ch[s->cur].lvl_q4;
    int degr_now, severe_now, rise_now = 0;
    int32_t best_sc, cur_sc;
    uint8_t best;
    d->switch_now = 0;
    d->target = s->cur;
    d->effective_frame = frame_no;
    d->reason = 0;

    /* clear expired blacklist entries */
    {
        uint8_t i;
        for (i = 0; i < CS_MAX_CH; i++) {
            if (s->ch[i].bl && elapsed(t_ms, s->ch[i].bl_until) < 0x80000000u) s->ch[i].bl = 0;
        }
    }

    if (s->ch[s->cur].have && s->base_set && elapsed(t_ms, s->ch[s->cur].t_scan) < c->stale_ms)
        rise_now = (cur_q4 - s->base_q4) >= c->rise * 16;
    severe_now = s->loss_ppm >= c->severe_ppm;
    degr_now = severe_now || s->loss_ppm >= c->loss_trig_ppm || rise_now;

    if (degr_now && !s->degr) { s->degr = 1; s->degr_since_ms = t_ms; s->jitter_wait = c->jitter_ms ? (uint32_t)((c->link_id * 7919u) % (c->jitter_ms + 1u)) : 0; }
    if (!degr_now) { s->degr = 0; s->confirm_cnt = 0; }
    if (severe_now && !s->severe) { s->severe = 1; s->severe_since_ms = t_ms; }
    if (!severe_now) s->severe = 0;
    if (!s->degr) return;

    /* the degradation has to hold for det_ms (plus the link's jitter, not for severe loss) */
    if (severe_now) {
        if (elapsed(t_ms, s->severe_since_ms) < c->det_ms) return;
    } else {
        if (elapsed(t_ms, s->degr_since_ms) < c->det_ms + s->jitter_wait) return;
    }

    /* probation: the channel we just moved to is bad: blacklist it */
    if (severe_now && elapsed(t_ms, s->last_switch_ms) < c->probation_ms && s->have_prev) {
        uint8_t bad = s->cur;
        s->ch[bad].bl = 1;
        s->ch[bad].bl_until = t_ms + c->blacklist_ms;
        best = best_candidate(s, c, t_ms, &best_sc);
        if (best == 255) best = fallback_pick(s, c, t_ms);
        if (best == 255 && usable(s, c, s->prev, t_ms) && s->prev != bad) best = s->prev;       /* last resort: where we came from */
        if (best != 255) {
            do_switch(s, best, t_ms, frame_no, c->switch_lead, 4, d);
        }
        return;
    }

    /* minimum stay (not for severe loss) */
    if (!severe_now && elapsed(t_ms, s->last_switch_ms) < c->min_stay_ms) return;

    best = best_candidate(s, c, t_ms, &best_sc);
    cur_sc = s->ch[s->cur].have ? (s->ch[s->cur].lvl_q4 >> 4) : (best == 255 ? 0 : best_sc + c->margin);   /* unknown own level: assume it is not better */
    {
        int32_t lp = (int32_t)(s->loss_ppm / 1000u);
        int32_t pen = 0;
        while (lp > 0 && pen < 128) { pen += 8; lp >>= 1; }        /* about 8 lg units per doubling of the loss in 1/1000 */
        cur_sc += pen;
    }
    if (best == 255) {
        uint8_t fb = fallback_pick(s, c, t_ms);
        if (fb != 255 && (severe_now || elapsed(t_ms, s->degr_since_ms) >= c->det_ms)) do_switch(s, fb, t_ms, frame_no, c->switch_lead, 5, d);
        return;
    }
    if (!severe_now) {
        if (best_sc + c->margin > cur_sc) { s->confirm_cnt = 0; return; }
        if (s->confirm_cnt == 0 || s->confirm_ch != best) { s->confirm_ch = best; s->confirm_cnt = 1; }
        else s->confirm_cnt++;
        if (s->confirm_cnt < c->confirm) return;
    }
    do_switch(s, best, t_ms, frame_no, c->switch_lead, severe_now ? 3 : (s->loss_ppm >= c->loss_trig_ppm ? 1 : 2), d);
}
