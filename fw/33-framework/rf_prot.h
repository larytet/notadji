/* rf_prot - VSWR measurement, antenna protection and the transmit power loop (R33-09; ANT-001..004, CAL-006, CAL-008).
 * Detector readings are in 0.01 dB relative to 0 dBm (signed 16 bit), forward and reflected. VSWR is Q8 (256 = 1:1). */
#ifndef RF_PROT_H
#define RF_PROT_H

#include "fw_types.h"

#define VSWR_Q8(x) ((uint16_t)((x) * 256))
#define VSWR_MAX_Q8 0xFFFFu

typedef enum { RF_OK = 0, RF_FOLDBACK = 1, RF_TRIP = 2, RF_PROBE = 3 } rf_state;
enum { ANT_FLAG_GROSS = 1, ANT_FLAG_DETUNED = 2, ANT_FLAG_NO_SIGNAL = 4 };

typedef struct {
    uint16_t fold_q8, trip_q8;               /* 3:1 and 6:1 */
    uint16_t fold_rec_q8, trip_rec_q8;       /* recovery thresholds 2.5:1 and 4:1 */
    uint16_t gross_q8;                       /* 10:1: open or short */
    uint8_t  fold_confirm, trip_confirm;     /* consecutive samples above the threshold (trip: 1, so one 1 ms sample is enough) */
    uint32_t fold_rec_us, trip_hold_us, probe_us, probe_timeout_us;
    uint8_t  probe_samples;                  /* good probe samples needed to leave PROBE */
    int16_t  fold_backoff_x4;                /* 6 dB = 24 */
    int16_t  fwd_floor_x100;                 /* forward detector below this: no verdict */
    uint16_t detune_delta_q8;                /* worse than the calibration reference by this: detuned (1.0) */
    uint16_t recal_delta_q8;                 /* CAL-008: 0.5 */
    uint8_t  recal_confirm;
} rf_cfg;

typedef struct {
    uint8_t  state;
    bool     pa_enable;
    int16_t  backoff_x4;
    uint16_t vswr_q8;
    bool     valid;                          /* this sample had enough forward power for a verdict */
    uint8_t  ant_flags;
    bool     recal_due;
    bool     changed;
} rf_out;

typedef struct {
    rf_cfg   cfg;
    rf_state state;
    uint8_t  over_fold, over_trip, good_probe, recal_cnt;
    uint32_t below_since_us, state_since_us;
    bool     below_active;
    uint16_t vswr_q8, vswr_cal_q8;
    bool     cal_valid, recal_due;
} rf_t;

void     rf_default_cfg(rf_cfg *c);
void     rf_init(rf_t *r, const rf_cfg *c, uint32_t now_us);
uint16_t rf_vswr(int16_t fwd_x100, int16_t rev_x100);                       /* VSWR_MAX_Q8 for rev >= fwd */
void     rf_update(rf_t *r, int16_t fwd_x100, int16_t rev_x100, uint32_t now_us, rf_out *o);
void     rf_cal_done(rf_t *r);                                                /* store the current VSWR as the reference, clear the trigger */

/* power control loop (CAL-006): integrator on the detector error, gain code in 0.25 dB steps */
typedef struct {
    int32_t code, code_min, code_max;
    int16_t target_x4;
    uint8_t kshift;                          /* gain 1 / 2^kshift of the error */
} pwr_loop;

void    pwr_loop_init(pwr_loop *l, int32_t code, int32_t cmin, int32_t cmax, int16_t target_x4, uint8_t kshift);
int32_t pwr_loop_step(pwr_loop *l, int16_t measured_x4);                     /* returns the new gain code */

#endif
