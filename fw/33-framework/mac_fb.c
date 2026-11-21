#include "mac_fb.h"
#include "crc.h"

uint32_t fb_lost(const fb_msg *m)
{
    uint32_t i, lost = 0;
    for (i = 0; i < m->n_slices; i++) if (!(((uint32_t)m->ack[i >> 3] >> (i & 7u)) & 1u)) lost++;
    return lost;
}

fb_status fb_parse(const uint8_t *b, uint32_t len, fb_msg *m)
{
    uint32_t nb, total, i;
    if (len < FB_HDR + 2u || len > FB_MAX_LEN) return FB_ERR_LEN;       /* at least the header and the CRC: byte 6 can be read */
    if (b[0] != FB_TYPE) return FB_ERR_TYPE;
    if (b[6] < 1u || b[6] > FB_MAX_SLICES) return FB_ERR_N;
    nb = ((uint32_t)b[6] + 7u) / 8u;
    total = FB_HDR + nb + 2u;
    if (len != total) return FB_ERR_LEN;
    if (fw_ld16(b + total - 2u) != crc16_mcrf4xx(b, total - 2u)) return FB_ERR_CRC;
    m->seq = b[1];
    m->snr_x10 = (int16_t)fw_ld16(b + 2);
    m->mcs_rec = b[4];
    m->rssi_dbm = (int8_t)b[5];
    m->n_slices = b[6];
    m->flags = b[7];
    for (i = 0; i < sizeof m->ack; i++) m->ack[i] = 0;
    for (i = 0; i < nb; i++) m->ack[i] = b[FB_HDR + i];
    /* bits above n_slices are ignored (cleared) so that two equal states compare equal */
    if (m->n_slices & 7u) m->ack[nb - 1u] = (uint8_t)(m->ack[nb - 1u] & ((1u << (m->n_slices & 7u)) - 1u));
    return FB_OK;
}

uint32_t fb_encode(const fb_msg *m, uint8_t *b)
{
    uint32_t nb = ((uint32_t)m->n_slices + 7u) / 8u, i, total = FB_HDR + nb + 2u;
    b[0] = FB_TYPE; b[1] = m->seq; fw_st16(b + 2, (uint16_t)m->snr_x10); b[4] = m->mcs_rec; b[5] = (uint8_t)m->rssi_dbm;
    b[6] = m->n_slices; b[7] = m->flags;
    for (i = 0; i < nb; i++) b[FB_HDR + i] = m->ack[i];
    fw_st16(b + total - 2u, crc16_mcrf4xx(b, total - 2u));
    return total;
}

void mac_ctl_init(mac_ctl_t *c, hal_t *h, clog_t *log, const uint8_t *rx_buf)
{
    memset(c, 0, sizeof *c);
    c->h = h; c->log = log; c->rx = rx_buf;
    la_default_cfg(&c->cfg);
    la_init(&c->la, &c->cfg, hal_now_us(h));
    c->lim.bitrate_pct = 100; c->lim.fps_div = 1;
    memset(&c->out, 0, sizeof c->out);
    c->out.mcs = c->la.mcs;
}

void mac_ctl_apply(mac_ctl_t *c, bool force)
{
    int32_t p = c->out.pwr_x4 - c->lim.pwr_backoff_x4;
    uint32_t pw, mcs = c->out.mcs, budget = c->out.slice_budget;
    if (p < -32768) p = -32768;
    pw = (uint32_t)(uint16_t)(int16_t)p;
    if (c->lim.tx_inhibit) budget = 0;
    if (!force && c->shadow_valid && c->shadow_mcs == mcs && c->shadow_pwr == pw && c->shadow_budget == budget) return;
    hal_wr(c->h, MAC_MCS, mcs);
    hal_wr(c->h, MAC_PWR_X4, pw);
    hal_wr(c->h, MAC_SLICE_BUDGET, budget);
    hal_wr(c->h, MAC_APPLY, 1);
    c->shadow_mcs = mcs; c->shadow_pwr = pw; c->shadow_budget = budget; c->shadow_valid = true;
    c->n_applied++;
}

fb_status mac_ctl_poll(mac_ctl_t *c)
{
    uint32_t len = hal_rd(c->h, MAC_FB_LEN);
    uint64_t t0;
    fb_msg m; fb_status st; la_fb fb;
    int8_t d;
    if (len == 0) return FB_ERR_LEN;
    t0 = hal_cycles(c->h);
    st = fb_parse(c->rx, len, &m);
    hal_wr(c->h, MAC_FB_LEN, 0);                      /* the buffer may be reused */
    switch (st) {
    case FB_ERR_LEN:  c->n_len++; break;
    case FB_ERR_TYPE: c->n_type++; break;
    case FB_ERR_N:    c->n_n++; break;
    case FB_ERR_CRC:  c->n_crc++; break;
    default: break;
    }
    if (st != FB_OK) { clog_append(c->log, CLOG_FB_DROP, 0, (uint32_t)st, len, 0, 0); return st; }
    d = (int8_t)(uint8_t)(m.seq - c->last_seq);
    if (c->have_seq && d <= 0) { c->n_stale++; return FB_ERR_SEQ; }       /* duplicate or older than the last accepted one */
    c->last_seq = m.seq; c->have_seq = true;

    if (c->safe_hold && fw_tdiff32(hal_now_us(c->h), c->safe_hold_until_us) < 0) { c->n_ok++; return FB_OK; }   /* held in the safe schedule: tracked, not applied */
    c->safe_hold = false;
    fb.t_us = hal_now_us(c->h);
    fb.snr_x10 = m.snr_x10;
    fb.n_slices = m.n_slices;
    fb.n_lost = (uint8_t)fb_lost(&m);
    fb.mcs_rec = m.mcs_rec;
    la_on_feedback(&c->la, &c->cfg, &fb, &c->out);
    mac_ctl_apply(c, false);
    c->n_ok++;
    c->last_apply_cycles = (uint32_t)(hal_cycles(c->h) - t0);
    return FB_OK;
}

void mac_ctl_tick(mac_ctl_t *c)
{
    if (c->safe_hold && fw_tdiff32(hal_now_us(c->h), c->safe_hold_until_us) < 0) return;      /* the safe output stays */
    c->safe_hold = false;
    la_tick(&c->la, &c->cfg, hal_now_us(c->h), &c->out);
    mac_ctl_apply(c, false);
}

void mac_ctl_force_safe(mac_ctl_t *c)
{
    uint32_t now = hal_now_us(c->h);
    c->la.last_fb_us = now - c->cfg.fb_timeout_us - 1u;       /* look like a feedback timeout: the link adaptation falls to its safe schedule */
    la_tick(&c->la, &c->cfg, now, &c->out);
    c->safe_hold = true; c->safe_hold_until_us = now + MAC_SAFE_HOLD_US;
    mac_ctl_apply(c, false);
}

uint32_t rate_targets(hal_t *h, uint32_t slice_budget, uint8_t bitrate_pct, uint32_t tele_bytes, uint16_t n_slices, uint32_t *shadow)
{
    uint32_t total, base, rem, i;
    if (n_slices == 0 || n_slices > MAC_SLICE_TGT_N) return 0;
    total = (uint32_t)(((uint64_t)slice_budget * n_slices * (bitrate_pct > 100u ? 100u : bitrate_pct)) / 100u);
    total = total > tele_bytes ? total - tele_bytes : 0u;
    base = total / n_slices; rem = total % n_slices;
    for (i = 0; i < n_slices; i++) {
        uint32_t t = base + (i < rem ? 1u : 0u);
        if (shadow[i] != t) { hal_wr(h, MAC_SLICE_TGT + 4u * i, t); shadow[i] = t; }
    }
    return total;
}
