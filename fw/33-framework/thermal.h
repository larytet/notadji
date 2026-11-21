/* thermal - temperature supervision with throttling steps (R33-09; THM-001..003, THM-006, CAL-003).
 * Temperatures are raw 0.25 deg C, signed 16 bit. Four sensors: 0 PA/FEM, 1 transceiver, 2 SoC, 3 board. */
#ifndef THERMAL_H
#define THERMAL_H

#include "fw_types.h"

#define THERM_N 4u
#define THERM_LEVELS 5u            /* 0 normal, 1 TX power back-off, 2 bitrate 70%, 3 bitrate 40% and half frame rate, 4 shutdown */
#define THERM_C(x) ((int16_t)((x) * 4))

typedef struct {
    int16_t  enter_x4[THERM_LEVELS - 1u];   /* hottest sensor at or above: go to level 1..4 */
    int16_t  leave_x4[THERM_LEVELS - 1u];   /* below: leave that level (hysteresis) */
    uint32_t min_dwell_ms;                  /* minimum time in a level before stepping down */
    int16_t  pwr_backoff_x4[THERM_LEVELS];
    uint8_t  bitrate_pct[THERM_LEVELS];
    uint8_t  fps_div[THERM_LEVELS];
    int16_t  valid_min_x4, valid_max_x4;    /* readings outside are invalid sensors */
    uint32_t stuck_ms;                      /* unchanged this long while another sensor moved more than stuck_move_x4: stuck */
    int16_t  stuck_move_x4;
    int16_t  recal_dt_x4;                   /* CAL-003: re-calibrate after this change since the last calibration */
    uint32_t recal_period_ms;               /* ... or after this time */
} therm_cfg;

typedef struct {
    uint8_t  level;
    int16_t  pwr_backoff_x4;
    uint8_t  bitrate_pct, fps_div;
    bool     shutdown;
    bool     hw_trip;                       /* the independent hardware trip is latched (THM-006) */
    int16_t  hottest_x4;
    uint8_t  invalid_mask;                  /* bit i: sensor i invalid (range or stuck) */
    bool     recal_due;
    bool     changed;                       /* level differs from the previous update */
} therm_out;

typedef struct {
    therm_cfg cfg;
    uint8_t  level;
    uint32_t level_since_ms;
    int16_t  last_raw[THERM_N];
    uint32_t same_since_ms[THERM_N];
    int16_t  anchor[THERM_N][THERM_N];      /* all readings when sensor i last changed */
    bool     stuck[THERM_N];
    bool     have;
    int16_t  t_cal_x4;
    uint32_t cal_ms;
    bool     recal_due;
} therm_t;

void therm_default_cfg(therm_cfg *c);
void therm_init(therm_t *t, const therm_cfg *c, uint32_t now_ms);
void therm_update(therm_t *t, const int16_t raw[THERM_N], bool hw_trip, uint32_t now_ms, therm_out *o);
void therm_recal_done(therm_t *t, uint32_t now_ms);

#endif
