// SRC: sched.c sup.c crashlog.c crc.c seq_drv.c mac_fb.c protect.c thermal.c rf_prot.c hostproto.c ../23-link-adaptation/link_adapt.c
/* T33-26: the whole control firmware on a 300 MHz model core: the task set of spec/13 section 2 at the 1080p120 workload, load, deadlines,
 * and a fault run: stalled task, antenna fault, hot PA, stalled main core. Task costs are model cycles (see the table below), not measurements. */
#include "tcheck.h"
#include "hal_sim.h"
#include "sup.h"
#include "mac_fb.h"
#include "protect.h"
#include "hostproto.h"
#include <math.h>

/* model costs per run, cycles. Spec/13 estimates, except where this module measured a larger bound (feedback path: a64_cost.py) */
#define C_FRAME   3000u      /* sequencer table update */
#define C_FB      34001u     /* feedback parse and link adaptation: the pessimistic static bound of a64_cost.py (the spec estimate was 3,500) */
#define C_RATE    4000u
#define C_RF      1500u      /* VSWR and power loop */
#define C_THERM   3000u
#define C_HOST    15000u     /* 300 bytes per ms at 50 cycles */
#define C_LOG     1500u
#define C_SYNC    1000u
#define C_AGC     800u
#define C_CAL     20000u     /* background calibration (200,000 cycles at 5 Hz in spec/13) sliced into 20,000 cycles every 20 ms: a run-to-completion task of 0.67 ms
                              * would make the 1 ms tasks miss their deadlines (found by this test, design/33 section 8) */
#define C_DPD     4000u      /* DPD solve (40,000 cycles at 10 Hz) sliced into 4,000 cycles every 10 ms */
#define C_TICK    2600u      /* tick and interrupt overhead */

#define FRAME_CLK 200000u

static hal_sim S;
static clog_t LG, LS;                    /* LG: events (rare, kept long), LS: link statistics at 1 kHz (short history) */
static sched_t SC;
static sup_t SU;
static mbox_t HB;
static mon_t MON;
static _Atomic uint32_t OWNER;
static seq_drv_t DRV;
static mac_ctl_t MAC;
static prot_t P;
static hp_t HP;
static spsc_t RING, OUTQ;
static uint8_t ringbuf[4096];
static hp_frame outbuf[8];
static uint8_t RX[FB_MAX_LEN + 4];
static seq_entry mainT[3], safeT[3];
static uint32_t cost_scale_fb = 1;       /* fault injection: the feedback task takes this many times longer */
static bool host_quiet;
static int T_frame, T_fb, T_rate, T_rf, T_therm, T_host, T_log, T_sync, T_agc, T_cal, T_dpd, T_sup;
static int S_frame, S_fb, S_rf, S_host;
static uint32_t fb_seq, rate_shadow[MAC_SLICE_TGT_N];
static int16_t det_fwd = -1000;
static bool main_halted_seen;

static void set_detectors(double vswr)
{
    double g = (vswr - 1.0) / (vswr + 1.0);
    hal_wr(&S.hal, RF_DET_FWD, (uint32_t)(uint16_t)det_fwd);
    hal_wr(&S.hal, RF_DET_REV, (uint32_t)(uint16_t)(int16_t)lround(det_fwd + 2000.0 * log10(g)));
}
static void set_temps(uint32_t pa)
{
    static uint32_t j;
    int jit = (int)(++j & 1u), p = (int)pa * 4;
    hal_wr(&S.hal, SENS_TEMP(0), (uint32_t)(uint16_t)(int16_t)(p + jit));
    hal_wr(&S.hal, SENS_TEMP(1), (uint32_t)(uint16_t)(int16_t)(55 * 4 - jit));
    hal_wr(&S.hal, SENS_TEMP(2), (uint32_t)(uint16_t)(int16_t)(60 * 4 + jit));
    hal_wr(&S.hal, SENS_TEMP(3), (uint32_t)(uint16_t)(int16_t)(45 * 4 - jit));
}

/* ---- tasks: the real firmware function, then the model cost of the rest of the work ---- */
static void t_frame(void *a)
{
    (void)a;
    (void)seq_load_owned(&DRV, &OWNER, mainT, 3);
    hal_sim_burn(&S, C_FRAME);
    sup_checkin(&SU, S_frame);
}
static void t_fb(void *a)
{
    (void)a;
    (void)mac_ctl_poll(&MAC);
    mac_ctl_tick(&MAC);
    hal_sim_burn(&S, (uint64_t)C_FB * cost_scale_fb);
    sup_checkin(&SU, S_fb);
}
static void t_rate(void *a) { (void)a; (void)rate_targets(&S.hal, MAC.out.slice_budget, MAC.lim.bitrate_pct, 600, 8, rate_shadow); hal_sim_burn(&S, C_RATE); }
static void t_rf(void *a) { (void)a; prot_rf_task(&P); hal_sim_burn(&S, C_RF); sup_checkin(&SU, S_rf); }
static void t_therm(void *a) { (void)a; prot_thermal_task(&P); hal_sim_burn(&S, C_THERM); }
static void t_host(void *a)
{
    hp_frame f;
    (void)a;
    hp_poll(&HP, &RING, 400);
    while (spsc_pop(&OUTQ, &f)) { }
    hal_sim_burn(&S, host_quiet ? 2000u : C_HOST);
    sup_checkin(&SU, S_host);
}
static void t_log(void *a) { (void)a; clog_append(&LS, CLOG_LINK_STATS, 0, MAC.out.mcs, (uint32_t)MAC.n_ok, 0, 0); hal_sim_burn(&S, C_LOG); }
static void t_sync(void *a) { (void)a; hal_sim_burn(&S, C_SYNC); }
static void t_agc(void *a) { (void)a; hal_sim_burn(&S, C_AGC); }
static void t_cal(void *a) { (void)a; hal_sim_burn(&S, C_CAL); }
static void t_dpd(void *a) { (void)a; hal_sim_burn(&S, C_DPD); }
static void t_sup(void *a)
{
    (void)a;
    sup_tick(&SU);
    if (sup_safe_requested(&SU)) { mac_ctl_force_safe(&MAC); sup_safe_clear(&SU); }
}

static int add(const char *n, void (*fn)(void *), uint32_t period, uint32_t budget, uint8_t prio)
{
    sched_task_cfg c; c.name = n; c.fn = fn; c.arg = NULL; c.period_us = period; c.deadline_us = 0; c.budget_cycles = budget; c.prio = prio;
    return sched_add(&SC, &c);
}

static void build(void)
{
    uint32_t i;
    memset(rate_shadow, 0xFF, sizeof rate_shadow);
    hal_sim_init(&S, 7); clog_open(&LG, &S.hal, 0, 16384); clog_open(&LS, &S.hal, 16384, 49152);
    sched_init(&SC, &S.hal);
    mbox_init(&HB);
    sup_init(&SU, &S.hal, &SC, &LG, &HB);
    mac_ctl_init(&MAC, &S.hal, &LG, RX);
    prot_init(&P, &S.hal, &LG, &MAC, hal_now_us(&S.hal));
    spsc_init(&RING, ringbuf, 4096, 1); spsc_init(&OUTQ, outbuf, 8, sizeof(hp_frame));
    hp_init(&HP, NULL, &OUTQ);
    seq_drv_init(&DRV, &S.hal);
    mainT[0].time = 1000; mainT[0].act = SEQ_ACT_SET_LINES; mainT[0].arg = 3;
    mainT[1].time = 120000; mainT[1].act = SEQ_ACT_CLR_LINES; mainT[1].arg = 3;
    mainT[2].time = FRAME_CLK; mainT[2].act = SEQ_ACT_END; mainT[2].arg = 0;
    safeT[0].time = 1000; safeT[0].act = SEQ_ACT_SET_LINES; safeT[0].arg = 1;
    safeT[1].time = 50000; safeT[1].act = SEQ_ACT_CLR_LINES; safeT[1].arg = 1;
    safeT[2].time = FRAME_CLK; safeT[2].act = SEQ_ACT_END; safeT[2].arg = 0;
    mon_init(&MON, &S.hal, &LG, &HB, &OWNER, safeT, 3, 50, 20);
    T_frame = add("frame", t_frame, 1000, 20000, 0);   T_rf = add("rf", t_rf, 1000, 20000, 0);
    T_fb = add("fb", t_fb, 1000, 60000, 1);            T_rate = add("rate", t_rate, 1000, 20000, 2);
    T_therm = add("thermal", t_therm, 10000, 20000, 3); T_host = add("host", t_host, 1000, 40000, 4);
    T_sync = add("sync", t_sync, 1000, 10000, 4);      T_agc = add("agc", t_agc, 1000, 10000, 4);
    T_log = add("log", t_log, 1000, 10000, 5);
    T_cal = add("cal", t_cal, 20000, 40000, 6);       T_dpd = add("dpd", t_dpd, 10000, 10000, 6);
    T_sup = add("sup", t_sup, 1000, 20000, 7);
    S_frame = sup_register(&SU, T_frame); S_fb = sup_register(&SU, T_fb); S_rf = sup_register(&SU, T_rf); S_host = sup_register(&SU, T_host);
    (void)i;
    /* steady sequencer state with the main table */
    seq_load_unguarded(&DRV, mainT, 3); hal_sim_clocks(&S, 1000); seq_load_unguarded(&DRV, mainT, 3); hal_sim_clocks(&S, FRAME_CLK);
    MON.last_fc = hal_rd(&S.hal, SEQ_FRAME_CNT);
    set_detectors(1.5); set_temps(40);
    fb_seq = 0; cost_scale_fb = 1; host_quiet = false; main_halted_seen = false;
    sched_start(&SC);
}

static void feed_feedback(bool ok)
{
    fb_msg m; uint32_t n;
    memset(&m, 0, sizeof m); m.n_slices = 8; m.ack[0] = 0xFF; m.snr_x10 = 300; m.mcs_rec = 255; m.seq = (uint8_t)(++fb_seq);
    n = fb_encode(&m, RX);
    if (!ok) { hal_wr(&S.hal, MAC_FB_LEN, 0); return; }
    hal_wr(&S.hal, MAC_FB_LEN, n);
}

static void feed_host(void)
{
    uint8_t buf[320], pl[100]; uint32_t n, i, total = 0;
    if (host_quiet) return;
    memset(pl, 3, sizeof pl);
    while (total < 300u) {                                 /* 300 bytes per ms: MSP v1 frames */
        n = hp_msp1_encode(buf, '>', 2, pl, 50);
        for (i = 0; i < n; i++) spsc_push(&RING, &buf[i]);
        total += n;
    }
}

/* one frame of 1 ms: inputs arrive, the tick comes, the core works, idle until the next frame; the monitor polls in the middle */
static void one_frame(bool main_runs)
{
    uint64_t t_next = sched_next_due(&SC);
    uint64_t now = hal_cycles(&S.hal);
    if (!main_runs) hal_sim_advance_us(&S, 1000);                          /* the scheduler is not running: time passes anyway */
    else if (t_next > now) hal_sim_burn(&S, t_next - now);
    if (main_runs) {
        feed_feedback(true); feed_host();
        hal_sim_burn(&S, C_TICK);
        sched_tick(&SC);
    }
    mon_poll(&MON);
}

static uint32_t count_type(uint16_t type)
{
    uint32_t n = 0, i; clog_rec r;
    for (i = 0; i < clog_count(&LG); i++) if (clog_get(&LG, i, &r) && r.type == type) n++;
    return n;
}
static int first_index(uint16_t type)
{
    uint32_t i; clog_rec r;
    for (i = 0; i < clog_count(&LG); i++) if (clog_get(&LG, i, &r) && r.type == type) return (int)i;
    return -1;
}

TEST(normal_load_and_deadlines)
{
    uint32_t i; int k;
    build();
    sched_window_reset(&SC);
    for (i = 0; i < 10000; i++) one_frame(true);             /* 10 s */
    printf("    load %.1f%% of a 300 MHz core over 10 s\n", sched_load_x1000(&SC) / 10.0);
    CHECK(sched_load_x1000(&SC) <= 500);                     /* HSI-005: at most 50% */
    for (k = 0; k < (int)SC.n; k++) {
        const sched_stats *st = sched_get(&SC, k);
        CHECK_EQ(st->misses, 0); CHECK_EQ(st->overruns, 0); CHECK_EQ(st->skipped, 0);
    }
    CHECK(!sup_safe_requested(&SU));
    CHECK_EQ(SU.starved_periods, 0);
    CHECK_EQ(MON.takeovers, 0);
    CHECK(hal_rd(&S.hal, SEQ_MISSED) <= 1);
    CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 1);
    CHECK(hal_rd(&S.hal, MAC_MCS) > 2);                      /* the link adapted up with the good feedback */
    CHECK_EQ(HP.st.bad_crc, 0);
    CHECK(HP.st.frames[HP_MSP1] > 9000);                     /* the host traffic went through (frames of 56 bytes, 300 bytes per ms) */
    CHECK_EQ(count_type(CLOG_TASK_OVERRUN) + count_type(CLOG_DEADLINE) + count_type(CLOG_RF_STATE) + count_type(CLOG_SAFE_REQUEST), 0);
    printf("    worst cycles: fb %u (budget 60000), host %u, frame %u, rf %u\n", sched_get(&SC, T_fb)->max_cycles, sched_get(&SC, T_host)->max_cycles,
           sched_get(&SC, T_frame)->max_cycles, sched_get(&SC, T_rf)->max_cycles);
}

TEST(fault_run)
{
    uint32_t i, f0, stall_frame = 0, take_frame = 0;
    int idx_over, idx_safe, idx_rf, idx_th, idx_mon, idx_rel;
    uint32_t mcs_before;
    build();
    for (i = 0; i < 1000; i++) one_frame(true);               /* 1 s settling */
    mcs_before = hal_rd(&S.hal, MAC_MCS);
    CHECK(mcs_before > 2);

    /* F1: the feedback task takes ten times its budget for five frames */
    cost_scale_fb = 10;
    for (i = 0; i < 5; i++) one_frame(true);
    cost_scale_fb = 1;
    CHECK(count_type(CLOG_TASK_OVERRUN) >= 1);
    CHECK(count_type(CLOG_SAFE_REQUEST) >= 1);
    for (i = 0; i < 20; i++) one_frame(true);
    CHECK(hal_rd(&S.hal, MAC_MCS) < mcs_before);              /* the safe schedule was applied */
    for (i = 0; i < 1500; i++) one_frame(true);               /* feedback is good again: the link climbs back */
    CHECK(hal_rd(&S.hal, MAC_MCS) >= mcs_before - 1);

    /* F2: an open antenna for one period */
    set_detectors(12.0);
    one_frame(true);
    CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 0);                    /* tripped within the very frame that saw it */
    CHECK_EQ(P.rout.state, RF_TRIP);
    set_detectors(1.5);
    for (i = 0; i < 400; i++) one_frame(true);                /* hold, probe, recover */
    CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 1);
    CHECK(P.rout.state == RF_OK || P.rout.state == RF_FOLDBACK);

    /* F3: a hot PA */
    set_temps(100);
    for (i = 0; i < 30; i++) { set_temps(100); one_frame(true); }
    CHECK_EQ(P.tout.level, 2); CHECK_EQ(MAC.lim.bitrate_pct, 70);
    set_temps(40);
    for (i = 0; i < 3500; i++) { set_temps(40); one_frame(true); }
    CHECK_EQ(P.tout.level, 0);

    /* F4: the main core stops (the scheduler is not called any more); the monitor and the sequencer keep running */
    f0 = hal_rd(&S.hal, SEQ_FRAME_CNT); stall_frame = f0;
    for (i = 0; i < 12; i++) {
        one_frame(false);
        if (!take_frame && MON.takeovers) take_frame = hal_rd(&S.hal, SEQ_FRAME_CNT);
    }
    CHECK(take_frame != 0 && take_frame - stall_frame <= 3);
    CHECK_EQ(hal_rd(&S.hal, SYS_MAIN_HALT), 1);
    CHECK_EQ(OWNER & 1u, MON_OWNER_MON);
    {   uint32_t b = hal_rd(&S.hal, SEQ_STATUS) & 1u; CHECK_EQ(S.bank[b][0], ((uint64_t)safeT[0].time << 24) | ((uint64_t)safeT[0].act << 16) | safeT[0].arg); }
    /* the hold time passes with the main core stopped, then it is released and restarts */
    for (i = 0; i < 80 && hal_rd(&S.hal, SYS_MAIN_HALT) == 1; i++) one_frame(false);
    CHECK_EQ(hal_rd(&S.hal, SYS_MAIN_HALT), 0);
    sched_start(&SC);                                          /* the main core boots again */
    for (i = 0; i < 30; i++) one_frame(true);
    CHECK_EQ(OWNER & 1u, MON_OWNER_MAIN);
    CHECK_EQ(MON.takeovers, 1);
    { uint32_t b = hal_rd(&S.hal, SEQ_STATUS) & 1u; CHECK_EQ(S.bank[b][1], ((uint64_t)mainT[1].time << 24) | ((uint64_t)mainT[1].act << 16) | mainT[1].arg); }   /* main table back */

    /* the log tells the story in order */
    idx_over = first_index(CLOG_TASK_OVERRUN); idx_safe = first_index(CLOG_SAFE_REQUEST); idx_rf = first_index(CLOG_RF_STATE);
    idx_th = first_index(CLOG_THERMAL_STEP); idx_mon = first_index(CLOG_MONITOR_SAFE); idx_rel = first_index(CLOG_MONITOR_RELEASE);
    CHECK(idx_safe >= 0 && idx_over > idx_safe && idx_rf > idx_over && idx_th > idx_rf && idx_mon > idx_th && idx_rel > idx_mon);      /* the first deadline miss raises the request before three overruns are counted */
    printf("    log order: overrun %d, safe request %d, rf %d, thermal %d, monitor %d, release %d (of %u event entries; %u link-statistics entries kept)\n",
           idx_over, idx_safe, idx_rf, idx_th, idx_mon, idx_rel, clog_count(&LG), clog_count(&LS));
    (void)main_halted_seen;
}

int main(void) { RUN(normal_load_and_deadlines); RUN(fault_run); TC_DONE(); }
