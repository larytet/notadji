/* hostproto - parser for the flight-controller protocols: MAVLink 2, MSP v1 and MSP v2 (R33-10; SW-008, IF-001, MAC-007).
 * Bytes come from a DMA ring (spsc, one byte per item). They are collected in a window; the parser tries to decode a frame at the head of the window:
 * a good frame is emitted, an incomplete one waits, a bad one costs one byte (the next start byte inside it is found by the rescan, so a corrupted frame
 * loses only itself). Work per call is bounded by `max_bytes` and by HP_MAX_STEPS. */
#ifndef HOSTPROTO_H
#define HOSTPROTO_H

#include "spsc.h"

#define HP_WIN        640u
#define HP_MAX_PAYLOAD 255u
#define HP_MAX_STEPS  1400u          /* decode attempts per call: the window can hold up to HP_WIN bytes and each attempt consumes one or emits a frame */

typedef enum { HP_MAVLINK2 = 1, HP_MSP1 = 2, HP_MSP2 = 3 } hp_proto;

typedef struct {
    uint8_t  proto;
    uint8_t  dir;                    /* MSP: '<' request, '>' response, '!' error; MAVLink: 0 */
    uint8_t  seq, sysid, compid;     /* MAVLink */
    uint8_t  flags;                  /* MAVLink: incompat flags; MSP v2: flag byte */
    bool     signed_frame;           /* MAVLink signature present (skipped, not verified) */
    uint32_t id;                     /* MAVLink message id (24 bit), MSP command */
    uint16_t len;                    /* payload bytes as transmitted (MAVLink 2 trims trailing zeros) */
    uint8_t  payload[HP_MAX_PAYLOAD];
} hp_frame;

typedef struct {
    uint64_t frames[4];              /* by protocol */
    uint64_t bad_crc, bad_header, unknown_id, garbage_bytes, out_full;
} hp_stats;

/* CRC extra byte of a MAVLink message id, or a negative value for an unknown message */
typedef int (*hp_extra_fn)(uint32_t msgid);

typedef struct {
    uint8_t  win[HP_WIN];
    uint32_t n;                      /* bytes in the window */
    hp_extra_fn extra;
    spsc_t  *out;                    /* queue of hp_frame */
    hp_stats st;
} hp_t;

void hp_init(hp_t *h, hp_extra_fn extra, spsc_t *out_queue);
/* pull at most max_bytes from the byte ring, decode; returns the number of frames emitted by this call */
uint32_t hp_poll(hp_t *h, spsc_t *in_ring, uint32_t max_bytes);

/* encoders (the telemetry bridge sends frames back to the flight controller; tests use them) */
uint32_t hp_mav2_encode(uint8_t *out, uint8_t seq, uint8_t sysid, uint8_t compid, uint32_t msgid, const uint8_t *payload, uint8_t len, int crc_extra);
uint32_t hp_msp1_encode(uint8_t *out, uint8_t dir, uint8_t cmd, const uint8_t *payload, uint8_t len);
uint32_t hp_msp2_encode(uint8_t *out, uint8_t dir, uint8_t flag, uint16_t cmd, const uint8_t *payload, uint8_t len);

#endif
