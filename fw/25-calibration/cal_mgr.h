/* cal_mgr - calibration estimator, tables and triggers (design/25-calibration.md section 3).
 * Portable C99: no heap, no floating point, no library calls. */
#ifndef CAL_MGR_H
#define CAL_MGR_H

#include <stdint.h>

#define CAL_BANDS 2
#define CAL_GROUPS 8
#define CAL_TBINS 21
#define CAL_ENTRIES (CAL_BANDS * CAL_GROUPS * CAL_TBINS)
#define CAL_NV_BYTES 32
#define CAL_VERSION 1u

typedef struct {
    int64_t  sum_i, sum_q;
    uint64_t sum_ii, sum_qq;
    int64_t  sum_iq;
    uint32_t n;
} cal_sums;

typedef struct {
    int16_t dc_i, dc_q;                    /* LSBs */
    int16_t eps_r, eps_i;                  /* Q15 */
} cal_coeff;

typedef struct {
    uint32_t min_n;                        /* fewest samples to accept */
    uint32_t min_power_x;                  /* mean power (per sample, centred) below this: reject */
    int16_t  eps_max;                      /* Q15, larger: not a circular signal */
    int16_t  dc_max;                       /* LSBs */
} cal_lim;

typedef enum { CAL_OK = 0, CAL_REJ_N = 1, CAL_REJ_POWER = 2, CAL_REJ_EPS = 3, CAL_REJ_DC = 4, CAL_REJ_SAT = 5 } cal_status;

typedef struct {
    uint16_t version;
    uint8_t  band, group, tbin;
    uint8_t  valid;
    cal_coeff rx, tx;
    int16_t  tx_gain_x16, rx_gain_x16;
    uint32_t crc;
} cal_entry;

typedef struct {
    cal_entry e[CAL_ENTRIES];
    uint16_t  n_bad;                       /* entries that failed the CRC or the version check at load */
} cal_table;

typedef enum { CAL_JOB_NONE = 0, CAL_JOB_RX_DC = 1, CAL_JOB_TX_LO = 2, CAL_JOB_TX_IQ = 3, CAL_JOB_RX_IQ = 4 } cal_job;
enum { CAL_W_IDLE = 1, CAL_W_GUARD_TX = 2, CAL_W_RX_BURST = 4 };

typedef struct {
    const cal_table *tab;
    cal_entry work;                        /* the entry in force */
    uint8_t  have_entry;
    uint8_t  fresh[5];                     /* first update of this job after a hop or a start: take the full residual */
    uint32_t t_last[5];
    int16_t  temp_last[5];
    uint8_t  done_once[5];
    uint32_t last_job_ms;
    uint32_t min_gap_ms, period_ms, age_limit_ms;
    int16_t  temp_step_x10;
    uint32_t n_rej, n_ok;
    uint8_t  default_used;
} cal_mgr;

uint32_t cal_crc32(const uint8_t *p, uint32_t n);
cal_status cal_stats_to_coeff(const cal_sums *s, const cal_lim *lim, cal_coeff *out);
void cal_entry_pack(const cal_entry *e, uint8_t out[CAL_NV_BYTES]);
void cal_table_load(cal_table *t, const uint8_t nv[][CAL_NV_BYTES], uint16_t n);
int  cal_lookup(const cal_table *t, uint8_t band, uint8_t group, int16_t temp_x10, uint8_t *steps);   /* entry index or -1 */
void cal_regs(const cal_entry *e, int16_t out[8]);
void cal_init(cal_mgr *m, const cal_table *t);
void cal_on_hop(cal_mgr *m, uint8_t band, uint8_t group, int16_t temp_x10, uint32_t now_ms);
cal_job cal_tick(cal_mgr *m, uint32_t now_ms, int16_t temp_x10, uint8_t windows);
cal_status cal_result(cal_mgr *m, cal_job job, const cal_sums *s, const cal_lim *lim, uint32_t now_ms, int16_t temp_x10);

#endif
