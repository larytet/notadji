/* link_adapt - link-adaptation controller for the air unit real-time core (design/23-link-adaptation.md).
 * Portable C99: no heap, no floating point, no library calls. */
#ifndef LINK_ADAPT_H
#define LINK_ADAPT_H

#include <stdint.h>

#define LA_MAX_MCS 16
#define LA_NO_REC  255u

typedef struct {
    uint16_t rate_x256;       /* bits per data tone (modulation bits times code rate) in 1/256 units */
    int16_t  thr_x10;         /* SNR needed for the slice-error target, 0.1 dB */
    uint8_t  rung;            /* quality ladder rung of SYS-004: 0 best */
} la_mcs;

typedef struct {
    la_mcs   mcs[LA_MAX_MCS];
    uint8_t  n_mcs;
    uint8_t  mcs_min, mcs_max;
    uint32_t per_target_ppm;          /* slice-loss target, default 1000 (PHY-011) */
    int16_t  up_hys_x10;              /* extra SNR needed for a step up, 0.1 dB */
    int16_t  down_hys_x10;            /* extra SNR margin kept before a step down, 0.1 dB */
    uint32_t up_dwell_us;             /* minimum time between steps up */
    uint32_t down_dwell_us;           /* minimum time between steps down */
    uint32_t olla_step_udb;           /* outer loop: offset added for a lost slice, in 1e-6 dB */
    uint32_t olla_neg_limit_udb;      /* the offset may not go below minus this (limits probing of a higher MCS), 1e-6 dB */
    uint32_t probe_window_us;         /* a step down this soon after a step up counts as a failed probe */
    uint32_t probe_max_us;            /* longest wait before probing the next MCS again */
    int16_t  pwr_min_x4, pwr_max_x4;  /* transmit power limits, 0.25 dB units */
    int16_t  pwr_margin_x10;          /* raise power while the next MCS is within this many 0.1 dB */
    int16_t  pwr_headroom_x10;        /* lower power when this far above the threshold at the top MCS */
    uint32_t pwr_dwell_us;            /* minimum time between power steps */
    uint32_t fb_timeout_us;           /* no feedback for this long: safe schedule */
    uint32_t outage_us;               /* below the lowest threshold for this long: outage */
    uint16_t dl_sym_per_frame;        /* data symbols in the downlink part of a frame */
    uint16_t data_tones;              /* data tones per symbol */
    uint16_t slices_per_frame;
    uint16_t video_share_x256;        /* share of the payload for video after telemetry and overhead */
} la_cfg;

typedef struct {
    uint32_t t_us;
    int16_t  snr_x10;                 /* receiver SNR estimate, 0.1 dB */
    uint8_t  n_slices;                /* slices accounted in this message */
    uint8_t  n_lost;                  /* of which lost (after the retransmission rule) */
    uint8_t  mcs_rec;                 /* recommendation of the ground unit, LA_NO_REC: none */
} la_fb;

typedef struct {
    uint8_t  mcs;
    int16_t  pwr_x4;
    uint32_t slice_budget;            /* payload bytes per slice */
    uint8_t  rung;
    uint8_t  outage;
    uint8_t  safe;
    uint8_t  changed;                 /* mcs, power or budget differs from the previous output */
} la_out;

typedef struct {
    int32_t  snr_f_x100;              /* filtered SNR, 0.01 dB */
    int32_t  offset_udb;              /* outer-loop offset, 1e-6 dB */
    uint32_t step_up_udb;             /* offset removed per acknowledged slice */
    uint32_t last_up_us, last_down_us, last_pwr_us, last_fb_us;
    uint32_t below_since_us;
    uint32_t probe_hold_us;
    int32_t  snr_at_up_x100;
    uint8_t  mcs, rung, below, outage, safe, have_snr, probing;
    int16_t  pwr_x4;
    la_out   prev;
} la_state;

void     la_init(la_state *s, const la_cfg *c, uint32_t t_us);
void     la_on_feedback(la_state *s, const la_cfg *c, const la_fb *fb, la_out *o);
void     la_tick(la_state *s, const la_cfg *c, uint32_t t_us, la_out *o);
uint32_t la_slice_budget(const la_cfg *c, uint8_t mcs);
void     la_default_cfg(la_cfg *c);

#endif
