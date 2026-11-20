#include "link_adapt.h"

#define OFFSET_LIMIT_UDB 10000000     /* +/-10 dB */
#define FALL_FAST_X100   600          /* a fall of more than 6 dB is taken at once */

static uint32_t elapsed(uint32_t now, uint32_t then) { return now - then; }

void la_default_cfg(la_cfg *c)
{
    static const la_mcs t[10] = {
        {128, 20, 2},  {256, 50, 1},  {384, 70, 0},  {512, 105, 0}, {768, 125, 0},
        {1024, 170, 0}, {1152, 185, 0}, {1280, 205, 0}, {1536, 245, 0}, {1707, 270, 0},
    };
    uint8_t i;
    for (i = 0; i < LA_MAX_MCS; i++) {
        c->mcs[i].rate_x256 = 0;
        c->mcs[i].thr_x10 = 0;
        c->mcs[i].rung = 0;
    }
    for (i = 0; i < 10; i++) c->mcs[i] = t[i];
    c->n_mcs = 10;
    c->mcs_min = 0;
    c->mcs_max = 9;
    c->per_target_ppm = 1000;
    c->up_hys_x10 = 5;
    c->down_hys_x10 = 3;
    c->up_dwell_us = 1000;
    c->down_dwell_us = 0;
    c->olla_step_udb = 200000;        /* 0.2 dB */
    c->olla_neg_limit_udb = 4000000;  /* 4 dB */
    c->probe_window_us = 200000;
    c->probe_max_us = 8000000;
    c->pwr_min_x4 = 0;
    c->pwr_max_x4 = 120;              /* 30 dB range in 0.25 dB steps */
    c->pwr_margin_x10 = 60;
    c->pwr_headroom_x10 = 40;
    c->pwr_dwell_us = 10000;
    c->fb_timeout_us = 10000;
    c->outage_us = 20000;
    c->dl_sym_per_frame = 40;
    c->data_tones = 234;
    c->slices_per_frame = 8;
    c->video_share_x256 = 218;        /* 0.85 */
}

uint32_t la_slice_budget(const la_cfg *c, uint8_t mcs)
{
    uint32_t bits, video;
    if (mcs >= c->n_mcs || c->slices_per_frame == 0) return 0;
    bits  = ((uint32_t)c->dl_sym_per_frame * c->data_tones * c->mcs[mcs].rate_x256) >> 8;
    video = (bits * c->video_share_x256) >> 8;
    return video / c->slices_per_frame / 8u;
}

static uint8_t first_mcs_of_rung(const la_cfg *c, uint8_t rung)
{
    uint8_t i, best = c->n_mcs;
    for (i = 0; i < c->n_mcs; i++) {
        if (c->mcs[i].rung == rung && (best == c->n_mcs || c->mcs[i].thr_x10 < c->mcs[best].thr_x10)) best = i;
    }
    return best;
}

static int32_t snr_eff_x100(const la_state *s)
{
    return s->snr_f_x100 - s->offset_udb / 10000;
}

static void finish(la_state *s, const la_cfg *c, la_out *o)
{
    o->mcs = s->mcs;
    o->pwr_x4 = s->pwr_x4;
    o->slice_budget = la_slice_budget(c, s->mcs);
    o->rung = s->rung;
    o->outage = s->outage;
    o->safe = s->safe;
    o->changed = (uint8_t)(o->mcs != s->prev.mcs || o->pwr_x4 != s->prev.pwr_x4 || o->slice_budget != s->prev.slice_budget);
    s->prev = *o;
}

void la_init(la_state *s, const la_cfg *c, uint32_t t_us)
{
    uint64_t up = (uint64_t)c->olla_step_udb * c->per_target_ppm;
    uint32_t den = 1000000u - c->per_target_ppm;
    s->snr_f_x100 = 0;
    s->offset_udb = 0;
    s->step_up_udb = den ? (uint32_t)(up / den) : 0;
    s->last_up_us = t_us - c->up_dwell_us;
    s->last_down_us = t_us - c->down_dwell_us;
    s->last_pwr_us = t_us - c->pwr_dwell_us;
    s->last_fb_us = t_us;
    s->below_since_us = t_us;
    s->probe_hold_us = c->up_dwell_us;
    s->mcs = c->mcs_min;
    s->rung = c->mcs[c->mcs_min].rung;
    s->below = 0;
    s->outage = 0;
    s->safe = 0;
    s->have_snr = 0;
    s->probing = 0;
    s->snr_at_up_x100 = 0;
    s->pwr_x4 = c->pwr_max_x4;
    s->prev.mcs = s->mcs;
    s->prev.pwr_x4 = s->pwr_x4;
    s->prev.slice_budget = la_slice_budget(c, s->mcs);
    s->prev.rung = s->rung;
    s->prev.outage = 0;
    s->prev.safe = 0;
    s->prev.changed = 0;
}

void la_on_feedback(la_state *s, const la_cfg *c, const la_fb *fb, la_out *o)
{
    int32_t meas = (int32_t)fb->snr_x10 * 10;
    int32_t eff, thr_cur, ub, i;
    uint8_t ub_mcs;
    int32_t ok = (int32_t)fb->n_slices - (int32_t)fb->n_lost;
    int32_t lost = (int32_t)fb->n_lost;
    int explained = 0;

    if (ok < 0) ok = 0;
    /* first message after the start or after the safe schedule: take the measurement as it is */
    if (!s->have_snr || s->safe) {
        s->snr_f_x100 = meas;
        s->have_snr = 1;
        s->safe = 0;
    } else if (meas < s->snr_f_x100 - FALL_FAST_X100) {
        s->snr_f_x100 = meas;
        if (s->offset_udb < 0) s->offset_udb = 0;      /* an abrupt fall: the optimism learned so far is void */
        explained = 1;
    } else if (fb->n_lost != 0 && meas < s->snr_f_x100 - 50) {
        s->snr_f_x100 = meas;                          /* losses and a lower measurement agree: a real fade */
        explained = 1;
    } else if (meas < s->snr_f_x100) {
        s->snr_f_x100 -= (s->snr_f_x100 - meas + 7) >> 3;
    } else {
        s->snr_f_x100 += (meas - s->snr_f_x100 + 15) >> 4;
    }
    s->last_fb_us = fb->t_us;

    /* outer loop: losses that the SNR fall explains are not evidence of a biased estimate */
    if (!explained) s->offset_udb += lost * (int32_t)c->olla_step_udb;
    s->offset_udb -= ok * (int32_t)s->step_up_udb;
    if (s->offset_udb > OFFSET_LIMIT_UDB) s->offset_udb = OFFSET_LIMIT_UDB;
    if (s->offset_udb < -(int32_t)c->olla_neg_limit_udb) s->offset_udb = -(int32_t)c->olla_neg_limit_udb;
    eff = snr_eff_x100(s);

    /* upper bound on the MCS: configuration and the recommendation */
    ub_mcs = c->mcs_max;
    if (fb->mcs_rec != LA_NO_REC && fb->mcs_rec < ub_mcs) ub_mcs = fb->mcs_rec;
    if (ub_mcs < c->mcs_min) ub_mcs = c->mcs_min;

    /* MCS: down at once, up one step at a time */
    thr_cur = (int32_t)c->mcs[s->mcs].thr_x10 * 10;
    if (s->mcs > ub_mcs) {
        s->mcs = ub_mcs;
        s->last_down_us = fb->t_us;
    } else if (thr_cur > eff + (int32_t)c->down_hys_x10 * 10 && s->mcs > c->mcs_min &&
               elapsed(fb->t_us, s->last_down_us) >= c->down_dwell_us) {
        for (i = (int32_t)s->mcs - 1; i > (int32_t)c->mcs_min; i--) {
            if ((int32_t)c->mcs[i].thr_x10 * 10 <= eff + (int32_t)c->down_hys_x10 * 10) break;
        }
        if (s->probing && elapsed(fb->t_us, s->last_up_us) < c->probe_window_us && s->snr_f_x100 >= s->snr_at_up_x100 - 100) {
            uint32_t h = (s->probe_hold_us > c->probe_window_us) ? s->probe_hold_us : c->probe_window_us;
            s->probe_hold_us = (h > c->probe_max_us / 4u) ? c->probe_max_us : h * 4u;       /* a failed probe: wait much longer */
        }
        s->probing = 0;
        s->mcs = (uint8_t)i;
        s->last_down_us = fb->t_us;
    } else if (s->mcs < ub_mcs) {
        int32_t need = (int32_t)c->mcs[s->mcs + 1].thr_x10 * 10 + (int32_t)c->up_hys_x10 * 10;
        int32_t base = s->snr_f_x100 - (s->offset_udb > 0 ? s->offset_udb / 10000 : 0);   /* without the learned optimism */
        if (need <= base && elapsed(fb->t_us, s->last_up_us) >= c->up_dwell_us) {
            s->mcs++;                                                     /* justified by the measurement itself */
            s->last_up_us = fb->t_us;
            s->probing = 0;
        } else if (need <= eff && elapsed(fb->t_us, s->last_up_us) >= c->probe_window_us &&
                   elapsed(fb->t_us, s->last_down_us) >= s->probe_hold_us) {
            s->mcs++;                                                     /* a probe: only the outer loop's optimism allows it */
            s->last_up_us = fb->t_us;
            s->probing = 1;
            s->snr_at_up_x100 = s->snr_f_x100;
        }
    }

    if (s->probing && elapsed(fb->t_us, s->last_up_us) >= c->probe_window_us) {
        s->probing = 0;                                  /* the probe held: shorten the wait for the next one */
        if (s->probe_hold_us / 2u >= c->up_dwell_us) s->probe_hold_us /= 2u;
    }

    /* power loop */
    ub = ub_mcs;
    if (elapsed(fb->t_us, s->last_pwr_us) >= c->pwr_dwell_us) {
        thr_cur = (int32_t)c->mcs[s->mcs].thr_x10 * 10;
        if (s->pwr_x4 < c->pwr_max_x4 &&
            ((s->mcs < ub && (int32_t)c->mcs[s->mcs + 1].thr_x10 * 10 - eff <= (int32_t)c->pwr_margin_x10 * 10) ||
             eff < thr_cur + (int32_t)c->up_hys_x10 * 10)) {
            s->pwr_x4 = (int16_t)(s->pwr_x4 + 4 > c->pwr_max_x4 ? c->pwr_max_x4 : s->pwr_x4 + 4);
            s->snr_f_x100 += 100;
            s->last_pwr_us = fb->t_us;
        } else if (s->pwr_x4 > c->pwr_min_x4 && s->mcs == ub && eff >= thr_cur + (int32_t)c->pwr_headroom_x10 * 10) {
            s->pwr_x4 = (int16_t)(s->pwr_x4 - 4 < c->pwr_min_x4 ? c->pwr_min_x4 : s->pwr_x4 - 4);
            s->snr_f_x100 -= 100;
            s->last_pwr_us = fb->t_us;
        }
    }

    /* rung with 2 dB hysteresis on the way up in quality */
    {
        uint8_t cand = c->mcs[s->mcs].rung;
        if (cand >= s->rung) {
            s->rung = cand;
        } else {
            uint8_t f = first_mcs_of_rung(c, cand);
            if (f < c->n_mcs && snr_eff_x100(s) >= (int32_t)c->mcs[f].thr_x10 * 10 + 200) s->rung = cand;
        }
    }

    /* outage */
    eff = snr_eff_x100(s);
    if (eff < (int32_t)c->mcs[0].thr_x10 * 10 - 100) {
        if (!s->below) {
            s->below = 1;
            s->below_since_us = fb->t_us;
        }
        if (elapsed(fb->t_us, s->below_since_us) >= c->outage_us) s->outage = 1;
    } else {
        s->below = 0;
        s->outage = 0;
    }
    finish(s, c, o);
}

void la_tick(la_state *s, const la_cfg *c, uint32_t t_us, la_out *o)
{
    if (elapsed(t_us, s->last_fb_us) >= c->fb_timeout_us) {
        s->safe = 1;
        s->mcs = c->mcs_min;
        s->rung = c->mcs[c->mcs_min].rung;
        s->pwr_x4 = c->pwr_max_x4;
    }
    finish(s, c, o);
}
