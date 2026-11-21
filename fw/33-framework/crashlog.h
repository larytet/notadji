/* crashlog - crash-surviving event log in retained RAM (R33-05, SW-005).
 * Header 16 bytes {magic, capacity, record size, version, CRC-16... see crashlog.c} then `capacity` records of 32 bytes:
 *   0 seq:u32 (1, 2, 3 ...; 0 = empty)  4 t_us:u32  8 type:u16  10 flags:u16  12..27 a0..a3:u32  28 crc32 over bytes 0..27.
 * Record n is stored in slot (n - 1) % capacity. A record is written in one call with its CRC last; after a reset the valid records
 * (CRC good, slot consistent) are found by scanning, and the newest contiguous run is the log. */
#ifndef CRASHLOG_H
#define CRASHLOG_H

#include "hal.h"

#define CLOG_REC_SIZE 32u
#define CLOG_HDR_SIZE 16u

/* event types (the arguments are explained at the place that logs them) */
enum {
    CLOG_BOOT = 1, CLOG_TASK_OVERRUN = 2, CLOG_DEADLINE = 3, CLOG_SAFE_REQUEST = 4, CLOG_MONITOR_SAFE = 5, CLOG_MONITOR_RELEASE = 6,
    CLOG_WDOG_STARVED = 7, CLOG_THERMAL_STEP = 8, CLOG_RF_STATE = 9, CLOG_SENSOR_FAIL = 10, CLOG_FB_DROP = 11, CLOG_LINK_STATS = 12,
    CLOG_CAL_EVENT = 13, CLOG_UPDATE = 14, CLOG_PAIR = 15, CLOG_SAFE_TABLE_BAD = 16, CLOG_USER = 100
};

typedef struct {
    uint32_t seq, t_us;
    uint16_t type, flags;
    uint32_t a[4];
} clog_rec;

typedef struct {
    hal_t   *h;
    uint32_t base, cap;       /* offset in retained RAM, number of records */
    uint32_t next_seq;        /* sequence number of the next record */
    uint32_t oldest;          /* sequence number of the oldest valid record (after open) */
    uint32_t recovered;       /* records found at open */
    uint32_t dropped_torn;    /* slots that held something invalid at open (torn or corrupt) */
    bool     reinit;          /* the header was invalid at open: the log was cleared */
} clog_t;

/* open (recover) a log in `size` bytes of retained RAM starting at `base`; returns false if the region is too small */
bool     clog_open(clog_t *c, hal_t *h, uint32_t base, uint32_t size);
void     clog_append(clog_t *c, uint16_t type, uint16_t flags, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3);
/* read the k-th oldest valid record (k = 0 .. count-1); false if k is out of range */
uint32_t clog_count(const clog_t *c);
bool     clog_get(const clog_t *c, uint32_t k, clog_rec *r);
void     clog_clear(clog_t *c);

#endif
