/* mac_fb - uplink feedback message, MAC control task and rate retarget (R33-07, R33-08; MAC-004, MAC-005, VID-006).
 * Message (little-endian; defined in design/33 section 3.6): 0 type 0xFB | 1 seq | 2..3 snr_x10 (int16) | 4 mcs_rec (255: none) | 5 rssi_dbm (int8) |
 * 6 n_slices (1..64) | 7 flags | 8.. ack bitmap ceil(n/8) bytes (bit set: slice acknowledged) | CRC-16/MCRF4XX of everything before it, 2 bytes. */
#ifndef MAC_FB_H
#define MAC_FB_H

#include "hal.h"
#include "crashlog.h"
#include "link_adapt.h"

#define FB_TYPE        0xFBu
#define FB_MAX_SLICES  64u
#define FB_HDR         8u
#define FB_MAX_LEN     (FB_HDR + FB_MAX_SLICES / 8u + 2u)
#define FB_FLAG_MISS_BURST 0x01u

typedef struct {
    uint8_t  seq;
    int16_t  snr_x10;
    uint8_t  mcs_rec;
    int8_t   rssi_dbm;
    uint8_t  n_slices;
    uint8_t  flags;
    uint8_t  ack[FB_MAX_SLICES / 8u];
} fb_msg;

typedef enum { FB_OK = 0, FB_ERR_LEN, FB_ERR_TYPE, FB_ERR_N, FB_ERR_CRC, FB_ERR_SEQ } fb_status;

fb_status fb_parse(const uint8_t *buf, uint32_t len, fb_msg *m);
uint32_t  fb_encode(const fb_msg *m, uint8_t *buf);               /* ground-unit side and tests; returns the length */
uint32_t  fb_lost(const fb_msg *m);                               /* slices not acknowledged */

/* limits imposed by thermal and RF protection (module 33 S4); the MAC control applies them on top of the link-adaptation output */
typedef struct {
    int16_t  pwr_backoff_x4;     /* reduction of the transmit power, 0.25 dB units, >= 0 */
    uint8_t  bitrate_pct;        /* 100: no limit */
    uint8_t  fps_div;            /* 1: full frame rate */
    bool     tx_inhibit;
} mac_limits;

typedef struct {
    hal_t     *h;
    clog_t    *log;
    la_cfg     cfg;
    la_state   la;
    la_out     out;                /* last output of the link adaptation (before the limits) */
    mac_limits lim;
    const uint8_t *rx;             /* receive buffer the modem DMA fills (the length register says how much is valid) */
    uint8_t    last_seq;
    bool       have_seq;
    uint32_t   n_ok, n_len, n_type, n_n, n_crc, n_stale, n_applied;
    uint32_t   shadow_mcs, shadow_pwr, shadow_budget;
    bool       shadow_valid;
    uint32_t   safe_hold_until_us;  /* the safe schedule requested by supervision holds until this time, whatever the feedback says */
    bool       safe_hold;
    uint32_t   last_apply_cycles;   /* cycles from the feedback poll to the last register commit (measured on the HAL counter) */
} mac_ctl_t;

void mac_ctl_init(mac_ctl_t *c, hal_t *h, clog_t *log, const uint8_t *rx_buf);
/* poll the receive buffer: process one pending message; returns the status (FB_OK if one was applied; FB_ERR_LEN when nothing was pending) */
fb_status mac_ctl_poll(mac_ctl_t *c);
void mac_ctl_tick(mac_ctl_t *c);                                  /* feedback timeout handling of the link adaptation, once per frame */
#define MAC_SAFE_HOLD_US 100000u
void mac_ctl_force_safe(mac_ctl_t *c);                            /* supervision asks for the safe schedule: held for MAC_SAFE_HOLD_US, feedback is only tracked meanwhile */
void mac_ctl_apply(mac_ctl_t *c, bool force);                     /* write MCS, power and budget (with the limits) to the modem registers */

/* per-slice byte targets for the encoder: the frame budget scaled by the bitrate limit, minus the telemetry share, spread over the slices with the
 * remainder on the earliest slices; written to MAC_SLICE_TGT (only changed words). Returns the frame total. */
uint32_t rate_targets(hal_t *h, uint32_t slice_budget, uint8_t bitrate_pct, uint32_t tele_bytes, uint16_t n_slices, uint32_t *shadow);

#endif
