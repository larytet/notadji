// SRC: rf_prot.c
/* T33-16, T33-17: VSWR accuracy, protection state machine, antenna flags, calibration trigger, power loop */
#include "tcheck.h"
#include "rf_prot.h"
#include <math.h>

static rf_cfg C;
static const int16_t FWD = -1000;                     /* -10 dBm at the detector */

static int16_t rev_for(double s, int16_t fwd)         /* reflected detector reading for a VSWR s */
{
    double g = (s - 1.0) / (s + 1.0);
    return (int16_t)lround(fwd + 2000.0 * log10(g));
}

static double vs(uint16_t q8) { return q8 / 256.0; }

TEST(vswr_accuracy)
{
    double s, worst = 0, worst_lo = 0, worst_3 = 0;
    for (s = 1.05; s <= 10.0; s += 0.01) {
        int16_t rev = rev_for(s, FWD);
        double got = vs(rf_vswr(FWD, rev)), err = fabs(got - s);
        if (err > worst) worst = err;
        if (s >= 1.2 && s <= 2.0 && err > worst_lo) worst_lo = err;
        if (s >= 2.7 && s <= 3.3 && err > worst_3) worst_3 = err;
    }
    printf("    VSWR error: worst %.3f over 1.05..10, %.3f over 1.2..2, %.3f around 3:1\n", worst, worst_lo, worst_3);
    CHECK(worst_3 <= 0.3);
    CHECK(worst_lo <= 0.1);
    CHECK(worst <= 0.5);
    CHECK_EQ(rf_vswr(-1000, -1000), VSWR_MAX_Q8);    /* full reflection */
    CHECK_EQ(rf_vswr(-1000, -900), VSWR_MAX_Q8);     /* reflected above forward: measurement error, treated as the worst case */
    CHECK(rf_vswr(-1000, -5000) < VSWR_Q8(1.05));    /* very good match */
    /* independent of the absolute level */
    CHECK(llabs((long long)rf_vswr(-500, rev_for(3.0, -500)) - (long long)rf_vswr(-1500, rev_for(3.0, -1500))) <= 4);
}

static void run_samples(rf_t *r, int16_t fwd, int16_t rev, int n, uint32_t *now, uint32_t dt, rf_out *o)
{
    int i;
    for (i = 0; i < n; i++) { *now += dt; rf_update(r, fwd, rev, *now, o); }
}

TEST(foldback_and_trip)
{
    rf_t r; rf_out o; uint32_t now = 0;
    rf_default_cfg(&C); rf_init(&r, &C, 0);
    run_samples(&r, FWD, rev_for(1.5, FWD), 20, &now, 1000, &o);
    CHECK_EQ(o.state, RF_OK); CHECK(o.pa_enable); CHECK_EQ(o.backoff_x4, 0);
    /* one sample at 4:1 does not fold back, two in a row do */
    now += 1000; rf_update(&r, FWD, rev_for(4.0, FWD), now, &o); CHECK_EQ(o.state, RF_OK);
    now += 1000; rf_update(&r, FWD, rev_for(1.5, FWD), now, &o); CHECK_EQ(o.state, RF_OK);
    now += 1000; rf_update(&r, FWD, rev_for(4.0, FWD), now, &o); CHECK_EQ(o.state, RF_OK);
    now += 1000; rf_update(&r, FWD, rev_for(4.0, FWD), now, &o); CHECK_EQ(o.state, RF_FOLDBACK); CHECK(o.changed);
    CHECK_EQ(o.backoff_x4, 24); CHECK(o.pa_enable);                                   /* 6 dB */
    /* one sample above 6:1: trip in that very call, PA disabled */
    now += 1000; rf_update(&r, FWD, rev_for(7.0, FWD), now, &o);
    CHECK_EQ(o.state, RF_TRIP); CHECK(!o.pa_enable);
    /* a straight trip from the normal state too (open antenna) */
    rf_init(&r, &C, 0); now = 0;
    run_samples(&r, FWD, rev_for(1.5, FWD), 5, &now, 1000, &o);
    now += 1000; rf_update(&r, FWD, rev_for(12.0, FWD), now, &o);
    CHECK_EQ(o.state, RF_TRIP); CHECK(!o.pa_enable); CHECK(o.ant_flags & ANT_FLAG_GROSS);
    /* with trip_confirm = 2 two samples are needed */
    C.trip_confirm = 2; rf_init(&r, &C, 0); now = 0;
    now += 1000; rf_update(&r, FWD, rev_for(7.0, FWD), now, &o); CHECK(o.state != RF_TRIP);
    now += 1000; rf_update(&r, FWD, rev_for(7.0, FWD), now, &o); CHECK_EQ(o.state, RF_TRIP);
}

TEST(foldback_recovery_hysteresis)
{
    rf_t r; rf_out o; uint32_t now = 0;
    rf_default_cfg(&C); rf_init(&r, &C, 0);
    run_samples(&r, FWD, rev_for(3.5, FWD), 3, &now, 1000, &o); CHECK_EQ(o.state, RF_FOLDBACK);
    run_samples(&r, FWD, rev_for(2.8, FWD), 50, &now, 1000, &o); CHECK_EQ(o.state, RF_FOLDBACK);     /* between 2.5 and 3: stays */
    run_samples(&r, FWD, rev_for(2.0, FWD), 9, &now, 1000, &o); CHECK_EQ(o.state, RF_FOLDBACK);      /* below 2.5 for 9 ms: not yet */
    run_samples(&r, FWD, rev_for(2.9, FWD), 1, &now, 1000, &o); CHECK_EQ(o.state, RF_FOLDBACK);      /* a bad sample restarts the timer */
    run_samples(&r, FWD, rev_for(2.0, FWD), 9, &now, 1000, &o); CHECK_EQ(o.state, RF_FOLDBACK);
    run_samples(&r, FWD, rev_for(2.0, FWD), 2, &now, 1000, &o); CHECK_EQ(o.state, RF_OK); CHECK_EQ(o.backoff_x4, 0);
}

TEST(trip_probe_and_recovery)
{
    rf_t r; rf_out o; uint32_t now = 0; int n;
    rf_default_cfg(&C); rf_init(&r, &C, 0);
    now += 1000; rf_update(&r, FWD, rev_for(8.0, FWD), now, &o); CHECK_EQ(o.state, RF_TRIP);
    /* PA off: the detector sees nothing; the hold time is 100 ms */
    run_samples(&r, -9000, -9000, 98, &now, 1000, &o); CHECK_EQ(o.state, RF_TRIP); CHECK(!o.pa_enable);
    CHECK(o.ant_flags & ANT_FLAG_NO_SIGNAL);
    run_samples(&r, -9000, -9000, 3, &now, 1000, &o); CHECK_EQ(o.state, RF_PROBE); CHECK(o.pa_enable); CHECK_EQ(o.backoff_x4, 24);
    /* antenna reconnected: five good samples leave the probe, then the normal fold-back recovery */
    run_samples(&r, FWD, rev_for(1.6, FWD), 4, &now, 1000, &o); CHECK_EQ(o.state, RF_PROBE);
    run_samples(&r, FWD, rev_for(1.6, FWD), 1, &now, 1000, &o); CHECK_EQ(o.state, RF_FOLDBACK);
    n = 0; while (o.state != RF_OK && n++ < 100) run_samples(&r, FWD, rev_for(1.6, FWD), 1, &now, 1000, &o);
    CHECK_EQ(o.state, RF_OK); CHECK(n <= 12);
    /* antenna still bad: the probe ends in a new trip */
    rf_init(&r, &C, 0); now = 0;
    now += 1000; rf_update(&r, FWD, rev_for(8.0, FWD), now, &o);
    run_samples(&r, -9000, -9000, 101, &now, 1000, &o); CHECK_EQ(o.state, RF_PROBE);
    run_samples(&r, FWD, rev_for(5.0, FWD), 1, &now, 1000, &o); CHECK_EQ(o.state, RF_TRIP);
    /* probe with no forward power at all (the sequencer did not enable the PA): timeout back to trip */
    run_samples(&r, -9000, -9000, 101, &now, 1000, &o); CHECK_EQ(o.state, RF_PROBE);
    run_samples(&r, -9000, -9000, 21, &now, 1000, &o); CHECK_EQ(o.state, RF_TRIP);
}

TEST(no_verdict_without_forward_power)
{
    rf_t r; rf_out o; uint32_t now = 0;
    rf_default_cfg(&C); rf_init(&r, &C, 0);
    run_samples(&r, FWD, rev_for(1.5, FWD), 5, &now, 1000, &o);
    run_samples(&r, -2500, -2500, 50, &now, 1000, &o);       /* below the floor: reflected equals forward is meaningless */
    CHECK_EQ(o.state, RF_OK); CHECK(!o.valid); CHECK(o.ant_flags & ANT_FLAG_NO_SIGNAL);
}

TEST(antenna_flags_and_calibration_trigger)
{
    rf_t r; rf_out o; uint32_t now = 0; int i;
    rf_default_cfg(&C); rf_init(&r, &C, 0);
    run_samples(&r, FWD, rev_for(1.5, FWD), 5, &now, 1000, &o);
    CHECK(o.recal_due);                                       /* no reference yet */
    rf_cal_done(&r); CHECK(!r.recal_due);
    run_samples(&r, FWD, rev_for(1.6, FWD), 100, &now, 1000, &o); CHECK(!o.recal_due);                   /* +0.1: no trigger */
    run_samples(&r, FWD, rev_for(2.2, FWD), 9, &now, 1000, &o); CHECK(!o.recal_due);                     /* +0.7 but for 9 samples only */
    run_samples(&r, FWD, rev_for(1.5, FWD), 1, &now, 1000, &o); CHECK(!o.recal_due);                     /* back: counter restarts */
    for (i = 0; i < 9; i++) run_samples(&r, FWD, rev_for(2.2, FWD), 1, &now, 1000, &o);
    CHECK(!o.recal_due);
    run_samples(&r, FWD, rev_for(2.2, FWD), 1, &now, 1000, &o); CHECK(o.recal_due);                      /* the 10th */
    rf_cal_done(&r);
    /* hand covering the antenna: detuned (a good reference, now 3.5) */
    rf_init(&r, &C, 0); now = 0;
    run_samples(&r, FWD, rev_for(1.4, FWD), 5, &now, 1000, &o); rf_cal_done(&r);
    run_samples(&r, FWD, rev_for(3.5, FWD), 3, &now, 1000, &o);
    CHECK(o.ant_flags & ANT_FLAG_DETUNED); CHECK(!(o.ant_flags & ANT_FLAG_GROSS));
    run_samples(&r, FWD, rev_for(10.5, FWD), 1, &now, 1000, &o);
    CHECK(o.ant_flags & ANT_FLAG_GROSS);
    /* a reference of 2.5 and now 3.2 is worse by less than 1.0: not flagged as detuned */
    rf_init(&r, &C, 0); now = 0;
    run_samples(&r, FWD, rev_for(2.5, FWD), 5, &now, 1000, &o); rf_cal_done(&r);
    run_samples(&r, FWD, rev_for(3.2, FWD), 3, &now, 1000, &o);
    CHECK(!(o.ant_flags & ANT_FLAG_DETUNED));
}

/* plant of the power loop: detector reads (base + code) in 0.25 dB steps, optionally one step late */
static int16_t base_pwr;
TEST(power_loop_settling)
{
    int delay, k, step_db; uint32_t worst_settle = 0;
    for (delay = 0; delay <= 1; delay++) for (step_db = -3; step_db <= 3; step_db += 6) {
        pwr_loop l; int32_t code; int16_t meas_prev, meas; int n, settled = -1, maxdev;
        base_pwr = (int16_t)(40 - 4 * step_db);             /* the plant starts 3 dB off target */
        pwr_loop_init(&l, 0, -200, 200, 40, 2);
        code = l.code; meas_prev = meas = (int16_t)(base_pwr + code);
        for (n = 1; n <= 10000; n++) {
            int16_t m = delay ? meas_prev : meas;
            meas_prev = meas;
            code = pwr_loop_step(&l, m);
            meas = (int16_t)(base_pwr + code);
            if (settled < 0 && abs(meas - 40) <= 1) settled = n;
            if (settled >= 0 && n > settled + 10 && abs(meas - 40) > 1) { CHECK(0); break; }      /* stays within one step */
        }
        maxdev = 0; (void)maxdev;
        CHECK(settled >= 1 && settled <= 10);                /* 10 steps of 10 us = 100 us */
        if ((uint32_t)settled > worst_settle) worst_settle = (uint32_t)settled;
        (void)k;
    }
    printf("    power loop settles in at most %u steps (10 us each)\n", worst_settle);
}

TEST(power_loop_no_windup)
{
    pwr_loop l; int n; int32_t code;
    pwr_loop_init(&l, 0, -50, 50, 400, 2);                   /* target 100 dB above the plant: saturates */
    for (n = 0; n < 5000; n++) code = pwr_loop_step(&l, (int16_t)(l.code));
    CHECK_EQ(code, 50);
    /* target becomes reachable: the code leaves the limit at once (no accumulated error) */
    l.target_x4 = 0;
    code = pwr_loop_step(&l, 50);
    CHECK(code < 50);
    for (n = 0; n < 10; n++) code = pwr_loop_step(&l, (int16_t)code);
    CHECK(abs(code) <= 1);
}

int main(void)
{
    RUN(vswr_accuracy); RUN(foldback_and_trip); RUN(foldback_recovery_hysteresis); RUN(trip_probe_and_recovery);
    RUN(no_verdict_without_forward_power); RUN(antenna_flags_and_calibration_trigger); RUN(power_loop_settling); RUN(power_loop_no_windup);
    TC_DONE();
}
