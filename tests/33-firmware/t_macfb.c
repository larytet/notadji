// SRC: mac_fb.c crashlog.c crc.c ../23-link-adaptation/link_adapt.c
/* T33-12, T33-13, T33-14: feedback parser, feedback to register commit, rate retarget */
#include "tcheck.h"
#include "hal_sim.h"
#include "mac_fb.h"
#include "crc.h"

static hal_sim S;
static clog_t LG;
static uint8_t RX[FB_MAX_LEN + 4];

static void rand_msg(fb_msg *m)
{
    uint32_t i, nb;
    memset(m, 0, sizeof *m);
    m->seq = (uint8_t)tc_rand(); m->snr_x10 = (int16_t)((int)(tc_rand() % 400) - 50); m->mcs_rec = (tc_rand() % 4) ? (uint8_t)(tc_rand() % 10) : 255u;
    m->rssi_dbm = (int8_t)(-90 + (int)(tc_rand() % 60)); m->n_slices = (uint8_t)(1 + tc_rand() % FB_MAX_SLICES); m->flags = (uint8_t)(tc_rand() & 1u);
    nb = ((uint32_t)m->n_slices + 7u) / 8u;
    for (i = 0; i < nb; i++) m->ack[i] = (uint8_t)tc_rand();
    if (m->n_slices & 7u) m->ack[nb - 1u] = (uint8_t)(m->ack[nb - 1u] & ((1u << (m->n_slices & 7u)) - 1u));
}

TEST(parse_roundtrip)
{
    int k;
    for (k = 0; k < 20000; k++) {
        fb_msg a, b; uint8_t buf[FB_MAX_LEN]; uint32_t n;
        rand_msg(&a);
        n = fb_encode(&a, buf);
        CHECK_EQ(n, FB_HDR + (a.n_slices + 7u) / 8u + 2u);
        CHECK_EQ(fb_parse(buf, n, &b), FB_OK);
        CHECK(b.seq == a.seq && b.snr_x10 == a.snr_x10 && b.mcs_rec == a.mcs_rec && b.rssi_dbm == a.rssi_dbm && b.n_slices == a.n_slices && b.flags == a.flags);
        CHECK(memcmp(a.ack, b.ack, sizeof a.ack) == 0);
        { uint32_t i, zeros = 0; for (i = 0; i < a.n_slices; i++) if (!((a.ack[i / 8] >> (i % 8)) & 1)) zeros++;        /* independent count */
          CHECK_EQ(fb_lost(&b), zeros); }
    }
}

TEST(every_bit_flip_rejected)
{
    int k; uint32_t bad = 0, tested = 0;
    for (k = 0; k < 200; k++) {
        fb_msg a, b; uint8_t buf[FB_MAX_LEN]; uint32_t n, byte, bit;
        rand_msg(&a);
        n = fb_encode(&a, buf);
        for (byte = 0; byte < n; byte++) for (bit = 0; bit < 8; bit++) {
            uint8_t t[FB_MAX_LEN]; memcpy(t, buf, n); t[byte] ^= (uint8_t)(1u << bit);
            tested++;
            if (fb_parse(t, n, &b) == FB_OK) bad++;
        }
    }
    CHECK_EQ(bad, 0);
    CHECK(tested > 20000);
}

TEST(malformed)
{
    fb_msg a, b; uint8_t buf[FB_MAX_LEN + 8]; uint32_t n;
    memset(&a, 0, sizeof a); a.n_slices = 8; a.ack[0] = 0xFF;
    n = fb_encode(&a, buf);
    CHECK_EQ(fb_parse(buf, n - 1, &b), FB_ERR_LEN);
    CHECK_EQ(fb_parse(buf, n + 1, &b), FB_ERR_LEN);
    CHECK_EQ(fb_parse(buf, 0, &b), FB_ERR_LEN);
    CHECK_EQ(fb_parse(buf, FB_MAX_LEN + 1, &b), FB_ERR_LEN);
    a.n_slices = 0; n = fb_encode(&a, buf);    /* valid CRC, n_slices 0 */
    CHECK_EQ(fb_parse(buf, n, &b), FB_ERR_N);
    memset(&a, 0, sizeof a); a.n_slices = 8; n = fb_encode(&a, buf);
    buf[6] = 65; fw_st16(buf + n - 2, crc16_mcrf4xx(buf, n - 2));
    CHECK_EQ(fb_parse(buf, n, &b), FB_ERR_N);
    buf[6] = 8; buf[0] = 0xFA; fw_st16(buf + n - 2, crc16_mcrf4xx(buf, n - 2));
    CHECK_EQ(fb_parse(buf, n, &b), FB_ERR_TYPE);
}

static void push(mac_ctl_t *c, const fb_msg *m, bool corrupt)
{
    uint32_t n = fb_encode(m, RX);
    if (corrupt) RX[tc_rand() % n] ^= (uint8_t)(1u << (tc_rand() % 8));
    hal_wr(&S.hal, MAC_FB_LEN, n);
    (void)c;
}

TEST(sequence_window_and_counters)
{
    mac_ctl_t c; fb_msg m; uint8_t seqs[] = {5, 5, 4, 6, 7, 6, 255, 0, 1};
    int exp_ok[] = {1, 0, 0, 1, 1, 0, 0 /* 255 is 248 ahead: reads as -8 */, 0, 0};
    unsigned i;
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 4096);
    mac_ctl_init(&c, &S.hal, &LG, RX);
    memset(&m, 0, sizeof m); m.n_slices = 8; m.ack[0] = 0xFF; m.snr_x10 = 300; m.mcs_rec = 255;
    for (i = 0; i < sizeof seqs; i++) {
        m.seq = seqs[i]; push(&c, &m, false);
        hal_sim_advance_us(&S, 1000);
        CHECK_EQ(mac_ctl_poll(&c) == FB_OK, exp_ok[i]);
    }
    CHECK_EQ(c.n_ok, 3); CHECK_EQ(c.n_stale, 6);
    /* window: from 7 the next accepted may be 8 .. 134; 135 and beyond read as older */
    m.seq = 135; push(&c, &m, false); CHECK_EQ(mac_ctl_poll(&c), FB_ERR_SEQ);
    m.seq = 134; push(&c, &m, false); CHECK_EQ(mac_ctl_poll(&c), FB_OK);
    m.seq = 7; push(&c, &m, false); CHECK_EQ(mac_ctl_poll(&c), FB_ERR_SEQ);
    c.last_seq = 250; m.seq = 3; push(&c, &m, false); CHECK_EQ(mac_ctl_poll(&c), FB_OK);          /* 250 -> 3 across the wrap */
    /* nothing pending */
    CHECK_EQ(hal_rd(&S.hal, MAC_FB_LEN), 0); CHECK_EQ(mac_ctl_poll(&c), FB_ERR_LEN);
}

TEST(corrupt_counted_and_logged)
{
    mac_ctl_t c; fb_msg m; int k; uint32_t bad = 0;
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 8192);
    mac_ctl_init(&c, &S.hal, &LG, RX);
    tc_rs = 5;
    for (k = 0; k < 500; k++) {
        rand_msg(&m); m.seq = (uint8_t)k;
        push(&c, &m, true);
        if (mac_ctl_poll(&c) == FB_OK) bad++;
    }
    CHECK_EQ(bad, 0);
    CHECK_EQ(c.n_crc + c.n_len + c.n_type + c.n_n, 500);
    CHECK(clog_count(&LG) >= 500 - 8 || clog_count(&LG) == 8192u / 32u - 1u || clog_count(&LG) > 100);
    CHECK_EQ(c.n_ok, 0);
}

TEST(feedback_to_registers)
{
    mac_ctl_t c; la_cfg cfg; la_state ref; la_out ro; int k; uint32_t mism = 0, applied_msgs = 0; uint8_t seq = 0;
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 4096);
    mac_ctl_init(&c, &S.hal, &LG, RX);
    la_default_cfg(&cfg);
    la_init(&ref, &cfg, hal_now_us(&S.hal));
    memset(&ro, 0, sizeof ro);
    tc_rs = 2024;
    for (k = 0; k < 3000; k++) {
        fb_msg m; la_fb fb; bool corrupt = (tc_rand() % 20) == 0;
        rand_msg(&m); m.seq = ++seq;
        m.snr_x10 = (int16_t)(100 + (int)(tc_rand() % 200));
        hal_sim_advance_us(&S, 1000);
        push(&c, &m, corrupt);
        if (mac_ctl_poll(&c) == FB_OK) {
            fb.t_us = hal_now_us(&S.hal); fb.snr_x10 = m.snr_x10; fb.n_slices = m.n_slices; fb.n_lost = (uint8_t)fb_lost(&m); fb.mcs_rec = m.mcs_rec;
            la_on_feedback(&ref, &cfg, &fb, &ro);
            applied_msgs++;
        } else if (!corrupt) mism++;
        if (hal_rd(&S.hal, MAC_MCS) != ro.mcs && c.shadow_valid) mism++;
        if (c.shadow_valid && (int16_t)hal_rd(&S.hal, MAC_PWR_X4) != ro.pwr_x4) mism++;
        if (c.shadow_valid && hal_rd(&S.hal, MAC_SLICE_BUDGET) != ro.slice_budget) mism++;
    }
    CHECK_EQ(mism, 0);
    CHECK(applied_msgs > 2700);
    CHECK(c.n_applied > 10 && c.n_applied <= applied_msgs);        /* registers written only when something changed */
}

TEST(limits_applied)
{
    mac_ctl_t c; fb_msg m;
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 4096);
    mac_ctl_init(&c, &S.hal, &LG, RX);
    memset(&m, 0, sizeof m); m.n_slices = 8; m.ack[0] = 0xFF; m.snr_x10 = 250; m.mcs_rec = 255; m.seq = 1;
    hal_sim_advance_us(&S, 1000); push(&c, &m, false); CHECK_EQ(mac_ctl_poll(&c), FB_OK);
    { int16_t p0 = (int16_t)hal_rd(&S.hal, MAC_PWR_X4); uint32_t b0 = hal_rd(&S.hal, MAC_SLICE_BUDGET); CHECK(b0 > 0);
      c.lim.pwr_backoff_x4 = 12;                                    /* 3 dB */
      hal_wr(&S.hal, MAC_APPLY, 0);
      mac_ctl_apply(&c, false);
      CHECK_EQ(hal_rd(&S.hal, MAC_APPLY), 1);                       /* the shadow registers are released together */
      CHECK_EQ((int16_t)hal_rd(&S.hal, MAC_PWR_X4), p0 - 12);
      c.lim.tx_inhibit = true; mac_ctl_apply(&c, false);
      CHECK_EQ(hal_rd(&S.hal, MAC_SLICE_BUDGET), 0);
      c.lim.tx_inhibit = false; mac_ctl_apply(&c, false);
      CHECK_EQ(hal_rd(&S.hal, MAC_SLICE_BUDGET), b0); }
}

TEST(safe_schedule_on_request)
{
    mac_ctl_t c; fb_msg m;
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 4096);
    mac_ctl_init(&c, &S.hal, &LG, RX);
    memset(&m, 0, sizeof m); m.n_slices = 8; m.ack[0] = 0xFF; m.snr_x10 = 300; m.mcs_rec = 255; m.seq = 1;
    { int i; for (i = 0; i < 60; i++) { m.seq = (uint8_t)(i + 1); hal_sim_advance_us(&S, 1000); push(&c, &m, false); CHECK_EQ(mac_ctl_poll(&c), FB_OK); } }
    CHECK(hal_rd(&S.hal, MAC_MCS) > 2);
    mac_ctl_force_safe(&c);
    CHECK(c.out.safe);
    CHECK(hal_rd(&S.hal, MAC_MCS) <= 1);                           /* the lowest rungs */
}

TEST(feedback_timeout_in_tick)
{
    mac_ctl_t c; fb_msg m; uint32_t i;
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 4096);
    mac_ctl_init(&c, &S.hal, &LG, RX);
    memset(&m, 0, sizeof m); m.n_slices = 8; m.ack[0] = 0xFF; m.snr_x10 = 300; m.mcs_rec = 255; m.seq = 1;
    hal_sim_advance_us(&S, 1000); push(&c, &m, false); CHECK_EQ(mac_ctl_poll(&c), FB_OK);
    for (i = 0; i < 100; i++) { hal_sim_advance_us(&S, 1000); mac_ctl_tick(&c); }      /* no feedback for 100 ms */
    CHECK(c.out.safe);
}

TEST(rate_targets_invariants)
{
    int k; uint32_t shadow[MAC_SLICE_TGT_N]; uint32_t bad = 0;
    hal_sim_init(&S, 1);
    memset(shadow, 0xFF, sizeof shadow);
    tc_rs = 31337;
    for (k = 0; k < 100000; k++) {
        uint32_t budget = (uint32_t)(tc_rand() % 20000), tele = (uint32_t)(tc_rand() % 30000), i, sum = 0, total;
        uint16_t n = (uint16_t)(1 + tc_rand() % MAC_SLICE_TGT_N); uint8_t pct = (uint8_t)(tc_rand() % 130);
        uint64_t want = (uint64_t)budget * n * (pct > 100 ? 100 : pct) / 100;
        total = rate_targets(&S.hal, budget, pct, tele, n, shadow);
        for (i = 0; i < n; i++) {
            uint32_t t = hal_rd(&S.hal, MAC_SLICE_TGT + 4 * i);
            sum += t;
            if (t > budget) bad++;                          /* never above the slice budget */
            if (i > 0 && t > hal_rd(&S.hal, MAC_SLICE_TGT + 4 * (i - 1))) bad++;      /* earlier slices get the remainder */
        }
        if (sum != total) bad++;
        if (total != (want > tele ? want - tele : 0)) bad++;
    }
    CHECK_EQ(bad, 0);
    CHECK_EQ(rate_targets(&S.hal, 100, 100, 0, 0, shadow), 0);
    CHECK_EQ(rate_targets(&S.hal, 100, 100, 0, 65, shadow), 0);
}

TEST(rate_targets_thermal_step_and_writes)
{
    uint32_t shadow[MAC_SLICE_TGT_N], total0, total1, w0, i;
    hal_sim_init(&S, 1);
    memset(shadow, 0xFF, sizeof shadow);
    total0 = rate_targets(&S.hal, 5000, 100, 600, 8, shadow);
    CHECK_EQ(total0, 40000 - 600);
    w0 = S.log_n;
    rate_targets(&S.hal, 5000, 100, 600, 8, shadow);          /* unchanged: no register writes */
    CHECK_EQ(S.log_n, w0);
    total1 = rate_targets(&S.hal, 5000, 70, 600, 8, shadow);   /* thermal step 2: 70% within the same call */
    CHECK_EQ(total1, 28000 - 600);
    for (i = 0; i < 8; i++) CHECK(hal_rd(&S.hal, MAC_SLICE_TGT + 4 * i) <= 3500);
}

int main(void)
{
    RUN(parse_roundtrip); RUN(every_bit_flip_rejected); RUN(malformed); RUN(sequence_window_and_counters); RUN(corrupt_counted_and_logged);
    RUN(feedback_to_registers); RUN(limits_applied); RUN(safe_schedule_on_request); RUN(feedback_timeout_in_tick);
    RUN(rate_targets_invariants); RUN(rate_targets_thermal_step_and_writes);
    TC_DONE();
}
