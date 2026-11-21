#include "rf_prot.h"
#include "vswr_table.h"

void rf_default_cfg(rf_cfg *c)
{
    c->fold_q8 = VSWR_Q8(3); c->trip_q8 = VSWR_Q8(6);
    c->fold_rec_q8 = VSWR_Q8(2.5); c->trip_rec_q8 = VSWR_Q8(4);
    c->gross_q8 = VSWR_Q8(10);
    c->fold_confirm = 2; c->trip_confirm = 1;
    c->fold_rec_us = 10000; c->trip_hold_us = 100000; c->probe_us = 5000; c->probe_timeout_us = 20000;
    c->probe_samples = 5;
    c->fold_backoff_x4 = 24;
    c->fwd_floor_x100 = -2000;               /* -20 dBm at the detector */
    c->detune_delta_q8 = VSWR_Q8(1); c->recal_delta_q8 = VSWR_Q8(0.5); c->recal_confirm = 10;
}

void rf_init(rf_t *r, const rf_cfg *c, uint32_t now_us)
{
    memset(r, 0, sizeof *r);
    r->cfg = *c; r->state = RF_OK; r->state_since_us = now_us; r->vswr_q8 = VSWR_Q8(1);
}

/* gamma = 10^((rev - fwd) / 2000) from the table with linear interpolation; VSWR = (1 + gamma) / (1 - gamma) */
uint16_t rf_vswr(int16_t fwd_x100, int16_t rev_x100)
{
    int32_t d = (int32_t)rev_x100 - fwd_x100;           /* 0.01 dB */
    uint32_t g, pos, i, frac;
    if (d >= 0) return VSWR_MAX_Q8;
    if (d <= -4000) d = -4000;
    pos = (uint32_t)(d + 4000);                         /* 0 .. 3999 in 0.01 dB; table step 25 */
    i = pos / 25u; frac = pos % 25u;
    g = vswr_gamma_q15[i] + (((uint32_t)vswr_gamma_q15[i + 1u] - vswr_gamma_q15[i]) * frac + 12u) / 25u;
    if (g >= 32768u - 8u) return VSWR_MAX_Q8;           /* above about 255:1 */
    {
        uint64_t v = ((uint64_t)(32768u + g) << 8) / (32768u - g);
        return v > VSWR_MAX_Q8 ? (uint16_t)VSWR_MAX_Q8 : (uint16_t)v;
    }
}

static void set_state(rf_t *r, rf_state s, uint32_t now_us)
{
    r->state = s; r->state_since_us = now_us; r->below_active = false; r->good_probe = 0;
}

void rf_update(rf_t *r, int16_t fwd_x100, int16_t rev_x100, uint32_t now_us, rf_out *o)
{
    const rf_cfg *c = &r->cfg;
    rf_state prev = r->state;
    bool valid = fwd_x100 >= c->fwd_floor_x100;
    uint16_t v = valid ? rf_vswr(fwd_x100, rev_x100) : r->vswr_q8;
    uint8_t flags = 0;
    if (valid) r->vswr_q8 = v;
    if (!valid) flags |= ANT_FLAG_NO_SIGNAL;

    if (valid) {
        /* trip: fast path, from any state that is transmitting */
        if (v >= c->trip_q8) { if (r->over_trip < 255u) r->over_trip++; } else r->over_trip = 0;
        if (v >= c->fold_q8) { if (r->over_fold < 255u) r->over_fold++; } else r->over_fold = 0;
    }
    switch (r->state) {
    case RF_OK:
        if (valid && r->over_trip >= c->trip_confirm) set_state(r, RF_TRIP, now_us);
        else if (valid && r->over_fold >= c->fold_confirm) set_state(r, RF_FOLDBACK, now_us);
        break;
    case RF_FOLDBACK:
        if (valid && r->over_trip >= c->trip_confirm) { set_state(r, RF_TRIP, now_us); break; }
        if (valid) {
            if (v < c->fold_rec_q8) {
                if (!r->below_active) { r->below_active = true; r->below_since_us = now_us; }
                if ((uint32_t)(now_us - r->below_since_us) >= c->fold_rec_us) set_state(r, RF_OK, now_us);
            } else r->below_active = false;
        }
        break;
    case RF_TRIP:                                       /* PA off; after the hold time try a probe burst at reduced power */
        if ((uint32_t)(now_us - r->state_since_us) >= c->trip_hold_us) set_state(r, RF_PROBE, now_us);
        break;
    case RF_PROBE:
        if (valid && v >= c->trip_rec_q8) { set_state(r, RF_TRIP, now_us); break; }
        if (valid && v < c->trip_rec_q8) {
            if (++r->good_probe >= c->probe_samples) { set_state(r, RF_FOLDBACK, now_us); break; }
        }
        if ((uint32_t)(now_us - r->state_since_us) >= c->probe_timeout_us) set_state(r, RF_TRIP, now_us);   /* no forward power seen */
        break;
    }

    /* antenna flags and the calibration trigger (CAL-008) */
    if (valid && v >= c->gross_q8) flags |= ANT_FLAG_GROSS;
    else if (valid && v >= c->fold_q8 && r->cal_valid && (uint32_t)v >= (uint32_t)r->vswr_cal_q8 + c->detune_delta_q8) flags |= ANT_FLAG_DETUNED;
    if (valid && r->cal_valid) {
        uint16_t d = v > r->vswr_cal_q8 ? (uint16_t)(v - r->vswr_cal_q8) : (uint16_t)(r->vswr_cal_q8 - v);
        if (d >= c->recal_delta_q8) { if (r->recal_cnt < 255u) r->recal_cnt++; } else r->recal_cnt = 0;
        if (r->recal_cnt >= c->recal_confirm) r->recal_due = true;
    } else if (valid && !r->cal_valid && r->state == RF_OK) r->recal_due = true;     /* no reference yet */

    o->state = (uint8_t)r->state;
    o->pa_enable = r->state != RF_TRIP;
    o->backoff_x4 = (r->state == RF_FOLDBACK || r->state == RF_PROBE || r->state == RF_TRIP) ? c->fold_backoff_x4 : 0;
    o->vswr_q8 = r->vswr_q8;
    o->valid = valid;
    o->ant_flags = flags;
    o->recal_due = r->recal_due;
    o->changed = r->state != prev;
}

void rf_cal_done(rf_t *r) { r->vswr_cal_q8 = r->vswr_q8; r->cal_valid = true; r->recal_due = false; r->recal_cnt = 0; }

void pwr_loop_init(pwr_loop *l, int32_t code, int32_t cmin, int32_t cmax, int16_t target_x4, uint8_t kshift)
{
    l->code = code; l->code_min = cmin; l->code_max = cmax; l->target_x4 = target_x4; l->kshift = kshift;
}

int32_t pwr_loop_step(pwr_loop *l, int16_t measured_x4)
{
    int32_t err = (int32_t)l->target_x4 - measured_x4, step, den = (int32_t)1 << l->kshift;
    /* round away from zero so that an error of one step still moves the code (no dead band) */
    step = err >= 0 ? (err + den - 1) / den : -((-err + den - 1) / den);
    l->code += step;
    if (l->code > l->code_max) l->code = l->code_max;      /* saturation clamps the integrator itself: no wind-up */
    if (l->code < l->code_min) l->code = l->code_min;
    return l->code;
}
