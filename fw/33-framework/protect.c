#include "protect.h"

void prot_init(prot_t *p, hal_t *h, clog_t *log, mac_ctl_t *mac, uint32_t now_us)
{
    therm_cfg tc; rf_cfg rc;
    memset(p, 0, sizeof *p);
    p->h = h; p->log = log; p->mac = mac;
    therm_default_cfg(&tc); rf_default_cfg(&rc);
    therm_init(&p->th, &tc, now_us / 1000u);
    rf_init(&p->rf, &rc, now_us);
    p->tout.bitrate_pct = 100; p->tout.fps_div = 1;
    p->rout.pa_enable = true; p->pa_requested = true;
}

void prot_merge(prot_t *p)
{
    int32_t bo = (int32_t)p->tout.pwr_backoff_x4 + p->rout.backoff_x4;
    mac_limits l;
    l.pwr_backoff_x4 = (int16_t)(bo > 120 ? 120 : bo);                 /* at most 30 dB of back-off */
    l.bitrate_pct = p->tout.bitrate_pct;
    l.fps_div = p->tout.fps_div;
    l.tx_inhibit = p->tout.shutdown || !p->rout.pa_enable;
    p->mac->lim = l;
    p->pa_requested = !l.tx_inhibit;
    hal_wr(p->h, RF_PA_EN, p->pa_requested ? 1u : 0u);
    mac_ctl_apply(p->mac, false);
}

void prot_rf_task(prot_t *p)
{
    int16_t fwd = (int16_t)hal_rd(p->h, RF_DET_FWD), rev = (int16_t)hal_rd(p->h, RF_DET_REV);
    uint8_t before = p->rout.state;
    rf_update(&p->rf, fwd, rev, hal_now_us(p->h), &p->rout);
    if (p->rout.changed) {
        clog_append(p->log, CLOG_RF_STATE, 0, before, p->rout.state, p->rout.vswr_q8, p->rout.ant_flags);
        if (p->rout.state == RF_TRIP) p->trips++;
    }
    /* the trip clears the PA enable in the same call; the rest of the merge is only needed when something changed */
    if (p->rout.changed || !p->rout.pa_enable) prot_merge(p);
}

void prot_thermal_task(prot_t *p)
{
    int16_t raw[THERM_N]; uint8_t i, prev_inv = p->tout.invalid_mask;
    for (i = 0; i < THERM_N; i++) raw[i] = (int16_t)hal_rd(p->h, SENS_TEMP(i));
    therm_update(&p->th, raw, (hal_rd(p->h, SENS_HW_TRIP) & 1u) != 0u, hal_now_us(p->h) / 1000u, &p->tout);
    if (p->tout.changed) clog_append(p->log, CLOG_THERMAL_STEP, 0, p->tout.level, (uint32_t)(int32_t)p->tout.hottest_x4, p->tout.invalid_mask, p->tout.hw_trip ? 1u : 0u);
    if (p->tout.invalid_mask != prev_inv) clog_append(p->log, CLOG_SENSOR_FAIL, 0, p->tout.invalid_mask, prev_inv, 0, 0);
    prot_merge(p);
}
