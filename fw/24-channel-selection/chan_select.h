/* chan_select - channel ranking and switching decisions (design/24-spectrum-scan.md section 2).
 * Portable C99: no heap, no floating point, no library calls. Levels are in "lg" units of the scan engine
 * (16 x log2 of the energy sum, 0.188 dB per unit). */
#ifndef CHAN_SELECT_H
#define CHAN_SELECT_H

#include <stdint.h>

#define CS_MAX_CH 32
#define CS_MAX_FALLBACK 8

typedef struct {
    uint8_t  n_ch;
    uint32_t enabled_mask;                 /* channels the link may use */
    uint8_t  fallback[CS_MAX_FALLBACK];
    uint8_t  n_fallback;
    uint16_t link_id;                      /* seeds the decision jitter */
    uint32_t stale_ms;                     /* a scan older than this is "unknown" */
    uint32_t memory_ms;                    /* remembered quality of a used channel */
    uint32_t det_ms;                       /* degradation must hold this long */
    uint32_t min_stay_ms;
    uint32_t probation_ms;
    uint32_t blacklist_ms;
    uint32_t jitter_ms;
    int32_t  margin;                       /* lg units a candidate must beat the current channel by */
    int32_t  rise;                         /* lg units of interference rise on the current channel that count as degradation */
    int32_t  adj_pen;                      /* penalty if an adjacent channel is strong */
    int32_t  unknown_pen;                  /* penalty for a stale or missing scan */
    int32_t  qual_pen;                     /* penalty for a remembered bad channel */
    int32_t  strong_lg;                    /* level above which a channel is "strong" (ADA-010) */
    uint32_t loss_trig_ppm;
    uint32_t severe_ppm;
    uint8_t  confirm;
    uint8_t  switch_lead;                  /* frames between the decision and the switch */
} cs_cfg;

typedef struct {
    int32_t  lvl_q4;                       /* smoothed level, lg x 16 */
    uint32_t t_scan, bl_until, q_t;
    uint32_t q_loss;
    uint8_t  have, bl, q_valid;
} cs_chan;

typedef struct {
    uint8_t  switch_now;
    uint8_t  target;
    uint16_t effective_frame;
    uint8_t  reason;                       /* 1 loss, 2 interference, 3 severe loss, 4 probation, 5 fallback */
} cs_decision;

typedef struct {
    cs_chan  ch[CS_MAX_CH];
    uint8_t  cur, prev, have_prev;
    uint32_t last_switch_ms, degr_since_ms, severe_since_ms, trig_ms;
    uint8_t  degr, severe, trig_set, confirm_cnt, confirm_ch;
    int32_t  base_q4;                      /* slow baseline of the current channel's level */
    uint8_t  base_set;
    uint32_t loss_ppm, snr_ok;
    uint32_t jitter_wait;
    uint32_t n_switch;
} cs_state;

void cs_default_cfg(cs_cfg *c);
void cs_init(cs_state *s, const cs_cfg *c, uint8_t start_ch, uint32_t t_ms);
void cs_scan(cs_state *s, const cs_cfg *c, uint8_t ch, uint16_t lg, uint32_t t_ms);
void cs_quality(cs_state *s, const cs_cfg *c, uint32_t loss_ppm, uint32_t t_ms);
void cs_tick(cs_state *s, const cs_cfg *c, uint32_t t_ms, uint16_t frame_no, cs_decision *d);
int32_t cs_score(const cs_state *s, const cs_cfg *c, uint8_t ch, uint32_t t_ms);   /* INT32_MAX: not usable */
uint32_t cs_strong_adjacent(const cs_state *s, const cs_cfg *c, uint32_t t_ms);    /* mask of strong neighbours of the current channel */

#endif
