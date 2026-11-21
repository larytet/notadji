// SRC: thermal.c
/* T33-15: thermal steps, hysteresis, dwell, invalid and stuck sensors, hardware trip, recalibration triggers */
#include "tcheck.h"
#include "thermal.h"

static therm_cfg C;
static int jit;
/* readings jitter by one LSB (0.25 deg C) from call to call, as real converters do: a perfectly constant reading is what the stuck detector looks for */
static void fill(int16_t raw[4], int16_t pa, int16_t x, int16_t soc, int16_t brd)
{
    int16_t j = (int16_t)((++jit) & 1);
    raw[0] = (int16_t)(pa + j); raw[1] = (int16_t)(x - j); raw[2] = (int16_t)(soc + j); raw[3] = (int16_t)(brd - j);
}

/* independent reference of the level logic (no sensor validity) written as a plain state machine */
typedef struct { int lvl; uint32_t since; } ref_t;
static int ref_step(ref_t *r, int hot_x4, uint32_t now)
{
    int target = 0, i;
    for (i = 0; i < 4; i++) if (hot_x4 >= C.enter_x4[i]) target = i + 1;
    if (target > r->lvl) { r->lvl = target; r->since = now; }
    else if (r->lvl > 0 && hot_x4 < C.leave_x4[r->lvl - 1] && now - r->since >= C.min_dwell_ms) { r->lvl--; r->since = now; }
    return r->lvl;
}

TEST(levels_vs_reference)
{
    therm_t t; ref_t ref = {0, 0}; int16_t raw[4]; therm_out o; uint32_t i, now = 0, bad = 0, steps = 0; int walk = 60 * 4;
    therm_default_cfg(&C); therm_init(&t, &C, 0);
    tc_rs = 4242;
    for (i = 0; i < 200000; i++) {
        int j;
        now += 10;                                          /* 100 Hz */
        walk += (int)(tc_rand() % 9) - 4 + (walk < 400 ? 1 : 0) - (walk > 460 ? 1 : 0) ; /* random walk between about 80 and 120 deg C (x4 units) */
        if (walk < 200) walk = 200;
        if (walk > 520) walk = 520;
        for (j = 0; j < 4; j++) raw[j] = (int16_t)(walk - 8 * j - (int)(tc_rand() % 3));   /* sensor 0 hottest or close; all keep changing */
        therm_update(&t, raw, false, now, &o);
        {
            int hot = raw[0]; for (j = 1; j < 4; j++) if (raw[j] > hot) hot = raw[j];
            if (ref_step(&ref, hot, now) != o.level) bad++;
            if (o.changed) steps++;
        }
    }
    CHECK_EQ(bad, 0);
    CHECK(steps > 20);
}

TEST(entry_skips_levels_exit_is_stepwise)
{
    therm_t t; int16_t raw[4]; therm_out o; uint32_t now = 0;
    therm_default_cfg(&C); therm_init(&t, &C, 0);
    fill(raw, THERM_C(60), THERM_C(60), THERM_C(60), THERM_C(60)); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 0);
    now += 10; fill(raw, THERM_C(106), THERM_C(60), THERM_C(61), THERM_C(60)); therm_update(&t, raw, false, now, &o);
    CHECK_EQ(o.level, 3); CHECK(o.changed);
    CHECK_EQ(o.bitrate_pct, 40); CHECK_EQ(o.fps_div, 2); CHECK_EQ(o.pwr_backoff_x4, 24); CHECK(!o.shutdown);
    /* cool down at once: not before the dwell, then one level per dwell */
    now += 500; fill(raw, THERM_C(60), THERM_C(62), THERM_C(61), THERM_C(60)); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 3);
    now += 600; fill(raw, THERM_C(60), THERM_C(62), THERM_C(61), THERM_C(61)); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 2);
    now += 10;  fill(raw, THERM_C(60), THERM_C(63), THERM_C(61), THERM_C(61)); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 2);
    now += 1000; fill(raw, THERM_C(60), THERM_C(63), THERM_C(62), THERM_C(61)); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 1);
    now += 1000; fill(raw, THERM_C(60), THERM_C(63), THERM_C(62), THERM_C(62)); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 0);
    CHECK_EQ(o.bitrate_pct, 100); CHECK_EQ(o.pwr_backoff_x4, 0);
}

TEST(hysteresis_no_chatter)
{
    therm_t t; int16_t raw[4]; therm_out o; uint32_t now = 0, i, changes = 0;
    therm_default_cfg(&C); therm_init(&t, &C, 0);
    for (i = 0; i < 2000; i++) {                            /* sensor wobbles by 1 deg C around the level-1 entry threshold */
        int16_t pa = (int16_t)(THERM_C(85) + ((i & 1u) ? 4 : -4) + (int16_t)(i & 2u));
        now += 10; fill(raw, pa, (int16_t)(pa - 8 + (int16_t)(i & 1u)), (int16_t)(pa - 12), (int16_t)(pa - 16 - (int16_t)(i & 3u)));
        therm_update(&t, raw, false, now, &o);
        if (o.changed) changes++;
    }
    CHECK(changes <= 2);                                    /* in once (and maybe out once at the end), not at every wobble */
}

TEST(invalid_sensors)
{
    therm_t t; int16_t raw[4]; therm_out o; uint32_t now = 0;
    therm_default_cfg(&C); therm_init(&t, &C, 0);
    fill(raw, THERM_C(50), THERM_C(50), THERM_C(50), THERM_C(50)); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 0); CHECK_EQ(o.invalid_mask, 0);
    now += 10; raw[1] = (int16_t)0x8000; therm_update(&t, raw, false, now, &o);       /* no response */
    CHECK_EQ(o.invalid_mask, 2); CHECK_EQ(o.level, 3);                               /* treated as hot */
    now += 10; raw[1] = THERM_C(200); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.invalid_mask, 2);     /* out of range high */
    now += 10; raw[1] = THERM_C(-60); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.invalid_mask, 2);
    now += 10; raw[1] = THERM_C(51); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.invalid_mask, 0);
    now += 10; raw[0] = raw[1] = raw[2] = raw[3] = (int16_t)0x8000; therm_update(&t, raw, false, now, &o);
    CHECK_EQ(o.invalid_mask, 15); CHECK_EQ(o.level, 4); CHECK(o.shutdown);
}

TEST(stuck_sensor)
{
    therm_t t; int16_t raw[4]; therm_out o; uint32_t now = 0, i;
    therm_default_cfg(&C); therm_init(&t, &C, 0);
    /* all stable for 10 s: nothing is stuck, only constant */
    for (i = 0; i < 1000; i++) { now += 10; raw[0] = raw[1] = raw[2] = raw[3] = THERM_C(50); therm_update(&t, raw, false, now, &o); }
    CHECK_EQ(o.invalid_mask, 0); CHECK_EQ(o.level, 0);
    /* sensor 2 freezes (exactly constant) while the PA sensor warms by 10 deg C over 3 s and the others keep jittering */
    for (i = 0; i < 300; i++) {
        now += 10;
        raw[0] = (int16_t)(THERM_C(50) + (int16_t)(i * 40 / 300));
        raw[1] = (int16_t)(THERM_C(50) + (int16_t)(i & 1u));
        raw[2] = THERM_C(50);
        raw[3] = (int16_t)(THERM_C(50) + (int16_t)(i / 20) + (int16_t)(i & 1u));
        therm_update(&t, raw, false, now, &o);
    }
    CHECK(o.invalid_mask & 4u);                                                    /* sensor 2 flagged stuck */
    CHECK_EQ(o.level, 3);
    now += 10; raw[2] = (int16_t)(THERM_C(50) + 1); therm_update(&t, raw, false, now, &o);
    CHECK_EQ(o.invalid_mask & 4u, 0);                                              /* it moved: valid again */
}

TEST(hardware_trip)
{
    therm_t t; int16_t raw[4]; therm_out o; uint32_t now = 0;
    therm_default_cfg(&C); therm_init(&t, &C, 0);
    fill(raw, THERM_C(40), THERM_C(40), THERM_C(40), THERM_C(40));
    therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 0);
    now += 10; fill(raw, THERM_C(41), THERM_C(40), THERM_C(40), THERM_C(40)); therm_update(&t, raw, true, now, &o);
    CHECK_EQ(o.level, 4); CHECK(o.hw_trip); CHECK(o.shutdown);
    now += 5000; fill(raw, THERM_C(42), THERM_C(40), THERM_C(40), THERM_C(40)); therm_update(&t, raw, true, now, &o); CHECK_EQ(o.level, 4);     /* stays while latched */
    now += 1100; fill(raw, THERM_C(43), THERM_C(40), THERM_C(40), THERM_C(40)); therm_update(&t, raw, false, now, &o); CHECK_EQ(o.level, 3);     /* then steps down */
}

TEST(recalibration_at_power_up_even_at_zero_degrees)
{
    therm_t t; int16_t raw[4] = {0, 1, 0, 1}; therm_out o;
    therm_default_cfg(&C); therm_init(&t, &C, 0);
    therm_update(&t, raw, false, 10, &o);
    CHECK(o.recal_due);                                   /* the reading equals the initial reference, only the power-up flag asks for it */
}

TEST(recalibration_triggers)
{
    therm_t t; int16_t raw[4]; therm_out o; uint32_t now = 0;
    therm_default_cfg(&C); therm_init(&t, &C, 0);
    fill(raw, THERM_C(40), THERM_C(41), THERM_C(42), THERM_C(30)); therm_update(&t, raw, false, now, &o);
    CHECK(o.recal_due);                                     /* power-up: no calibration yet */
    therm_recal_done(&t, now);
    now += 10; fill(raw, THERM_C(40) + 1, THERM_C(41), THERM_C(42), THERM_C(30)); therm_update(&t, raw, false, now, &o); CHECK(!o.recal_due);
    now += 10; fill(raw, THERM_C(44), THERM_C(41), THERM_C(42), THERM_C(31)); therm_update(&t, raw, false, now, &o); CHECK(!o.recal_due);      /* +4 deg C */
    now += 10; fill(raw, THERM_C(45) + 1, THERM_C(41), THERM_C(42), THERM_C(32)); therm_update(&t, raw, false, now, &o); CHECK(o.recal_due);    /* +5.25 deg C */
    therm_recal_done(&t, now); CHECK(!t.recal_due);
    fill(raw, THERM_C(45) + 1, THERM_C(41), THERM_C(42), THERM_C(32));
    { uint32_t i; for (i = 0; i < 7000; i++) { now += 10; raw[3] = (int16_t)(raw[3] ^ 1); raw[1] = (int16_t)(raw[1] ^ 1); therm_update(&t, raw, false, now, &o); if (o.recal_due && now - t.cal_ms < 59990) { CHECK(0); break; } } }
    CHECK(o.recal_due);                                     /* 60 s without a re-calibration */
}

int main(void)
{
    RUN(levels_vs_reference); RUN(entry_skips_levels_exit_is_stepwise); RUN(hysteresis_no_chatter); RUN(invalid_sensors);
    RUN(stuck_sensor); RUN(hardware_trip); RUN(recalibration_at_power_up_even_at_zero_degrees); RUN(recalibration_triggers);
    TC_DONE();
}
