// SRC: protect.c thermal.c rf_prot.c mac_fb.c crashlog.c crc.c ../23-link-adaptation/link_adapt.c
/* T33-15, T33-16 glue: sensors and detectors read through the HAL, limits merged for the MAC control, PA enable, log entries */
#include "tcheck.h"
#include "hal_sim.h"
#include "protect.h"
#include <math.h>

static hal_sim S;
static clog_t LG;
static mac_ctl_t MAC;
static prot_t P;
static uint8_t RX[FB_MAX_LEN + 4];

static void temps(int pa, int x, int soc, int brd, int jitter)
{
    hal_wr(&S.hal, SENS_TEMP(0), (uint32_t)(uint16_t)(int16_t)(pa * 4 + jitter));
    hal_wr(&S.hal, SENS_TEMP(1), (uint32_t)(uint16_t)(int16_t)(x * 4 - jitter));
    hal_wr(&S.hal, SENS_TEMP(2), (uint32_t)(uint16_t)(int16_t)(soc * 4 + jitter));
    hal_wr(&S.hal, SENS_TEMP(3), (uint32_t)(uint16_t)(int16_t)(brd * 4 - jitter));
}
static void det(int16_t fwd, double vswr)
{
    double g = (vswr - 1.0) / (vswr + 1.0);
    hal_wr(&S.hal, RF_DET_FWD, (uint32_t)(uint16_t)fwd);
    hal_wr(&S.hal, RF_DET_REV, (uint32_t)(uint16_t)(int16_t)lround(fwd + 2000.0 * log10(g)));
}
static uint32_t count_type(uint16_t type)
{
    uint32_t n = 0, i; clog_rec r;
    for (i = 0; i < clog_count(&LG); i++) if (clog_get(&LG, i, &r) && r.type == type) n++;
    return n;
}
static void setup(void)
{
    fb_msg m;
    uint32_t n, k;
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 8192);
    mac_ctl_init(&MAC, &S.hal, &LG, RX);
    prot_init(&P, &S.hal, &LG, &MAC, hal_now_us(&S.hal));
    temps(40, 40, 40, 40, 0); det(-1000, 1.5);
    /* bring the link adaptation up to a high MCS so that a limit has something to reduce */
    memset(&m, 0, sizeof m); m.n_slices = 8; m.ack[0] = 0xFF; m.snr_x10 = 300; m.mcs_rec = 255;
    for (k = 0; k < 60; k++) { m.seq = (uint8_t)(k + 1); n = fb_encode(&m, RX); hal_sim_advance_us(&S, 1000); hal_wr(&S.hal, MAC_FB_LEN, n); mac_ctl_poll(&MAC); }
    prot_merge(&P);
}

TEST(vswr_trip_and_recovery_through_hal)
{
    uint32_t b0, i;
    setup();
    b0 = hal_rd(&S.hal, MAC_SLICE_BUDGET);
    CHECK(b0 > 0); CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 1);
    for (i = 0; i < 20; i++) { hal_sim_advance_us(&S, 1000); temps(40, 40, 40, 40, (int)(i & 1)); prot_thermal_task(&P); prot_rf_task(&P); }
    CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 1); CHECK_EQ(P.rout.state, RF_OK);
    det(-1000, 3.6);
    hal_sim_advance_us(&S, 1000); prot_rf_task(&P);
    CHECK_EQ(P.rout.state, RF_OK);                                       /* one sample is not enough for the fold-back */
    hal_sim_advance_us(&S, 1000); prot_rf_task(&P);
    CHECK_EQ(P.rout.state, RF_FOLDBACK);
    CHECK_EQ(MAC.lim.pwr_backoff_x4, 24);
    CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 1);
    { int16_t p_now = (int16_t)hal_rd(&S.hal, MAC_PWR_X4); CHECK_EQ(p_now, MAC.out.pwr_x4 - 24); }
    det(-1000, 8.0);
    hal_sim_advance_us(&S, 1000); prot_rf_task(&P);                      /* a single sample above 6:1 */
    CHECK_EQ(P.rout.state, RF_TRIP);
    CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 0);                               /* cleared in the same call */
    CHECK_EQ(hal_rd(&S.hal, MAC_SLICE_BUDGET), 0);                       /* nothing is sent */
    CHECK_EQ(P.trips, 1);
    CHECK(count_type(CLOG_RF_STATE) >= 2);
    /* antenna reconnected: detector sees nothing while off, then the probe */
    det(-9000, 1.5);
    for (i = 0; i < 101; i++) { hal_sim_advance_us(&S, 1000); prot_rf_task(&P); }
    CHECK_EQ(P.rout.state, RF_PROBE); CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 1);
    det(-1000, 1.6);
    for (i = 0; i < 30; i++) { hal_sim_advance_us(&S, 1000); prot_rf_task(&P); }
    CHECK_EQ(P.rout.state, RF_OK);
    CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 1);
    CHECK_EQ(MAC.lim.pwr_backoff_x4, 0);
    CHECK_EQ(hal_rd(&S.hal, MAC_SLICE_BUDGET), b0);
}

TEST(thermal_through_hal_and_merge)
{
    uint32_t i;
    setup();
    for (i = 0; i < 5; i++) { hal_sim_advance_us(&S, 10000); temps(100, 70, 80, 60, (int)(i & 1)); prot_thermal_task(&P); }
    CHECK_EQ(P.tout.level, 2);                                           /* 100 deg C at the PA: level 2 */
    CHECK_EQ(MAC.lim.bitrate_pct, 70); CHECK_EQ(MAC.lim.pwr_backoff_x4, 12);
    /* RF fold-back adds to the thermal back-off */
    det(-1000, 3.6);
    for (i = 0; i < 3; i++) { hal_sim_advance_us(&S, 1000); prot_rf_task(&P); }
    CHECK_EQ(MAC.lim.pwr_backoff_x4, 12 + 24);
    CHECK_EQ(MAC.lim.bitrate_pct, 70);
    /* shutdown level */
    for (i = 0; i < 5; i++) { hal_sim_advance_us(&S, 10000); temps(120, 70, 80, 60, (int)(i & 1)); prot_thermal_task(&P); }
    CHECK_EQ(P.tout.level, 4); CHECK(MAC.lim.tx_inhibit);
    CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 0);
    CHECK_EQ(hal_rd(&S.hal, MAC_SLICE_BUDGET), 0);
    CHECK(count_type(CLOG_THERMAL_STEP) >= 2);
}

TEST(sensor_failure_logged_and_hot)
{
    uint32_t i;
    setup();
    hal_sim_advance_us(&S, 10000); temps(40, 40, 40, 40, 0); prot_thermal_task(&P);
    CHECK_EQ(P.tout.level, 0);
    hal_wr(&S.hal, SENS_TEMP(1), 0x8000u);
    for (i = 0; i < 3; i++) { hal_sim_advance_us(&S, 10000); prot_thermal_task(&P); }
    CHECK_EQ(P.tout.invalid_mask, 2); CHECK_EQ(P.tout.level, 3);
    CHECK_EQ(count_type(CLOG_SENSOR_FAIL), 1);                           /* logged when it appears, not at every sample */
}

TEST(hardware_trip_register)
{
    setup();
    hal_wr(&S.hal, SENS_HW_TRIP, 1u);
    hal_sim_advance_us(&S, 10000); temps(40, 40, 40, 40, 0); prot_thermal_task(&P);
    CHECK_EQ(P.tout.level, 4); CHECK(P.tout.hw_trip); CHECK_EQ(hal_rd(&S.hal, RF_PA_EN), 0);
}

TEST(merge_cap)
{
    setup();
    P.tout.pwr_backoff_x4 = 100; P.rout.backoff_x4 = 100; P.rout.pa_enable = true;
    prot_merge(&P);
    CHECK_EQ(MAC.lim.pwr_backoff_x4, 120);
}

int main(void) { RUN(vswr_trip_and_recovery_through_hal); RUN(thermal_through_hal_and_merge); RUN(sensor_failure_logged_and_hot); RUN(hardware_trip_register); RUN(merge_cap); TC_DONE(); }
