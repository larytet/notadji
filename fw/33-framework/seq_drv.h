/* seq_drv - driver for the frame-timeline sequencer (module 10): validate a table, write it into the inactive bank, commit (R33-06, HSI-002).
 * The driver keeps a checksum of what it wrote into each physical bank, so an unchanged table needs only the commit write. */
#ifndef SEQ_DRV_H
#define SEQ_DRV_H

#include "hal.h"

typedef struct { uint32_t time; uint8_t act; uint16_t arg; } seq_entry;

typedef enum {
    SEQ_OK = 0, SEQ_ERR_EMPTY, SEQ_ERR_TOO_DEEP, SEQ_ERR_UNSORTED, SEQ_ERR_NO_END, SEQ_ERR_END_NOT_LAST, SEQ_ERR_TIME_RANGE,
    SEQ_ERR_ACTION, SEQ_ERR_LATE, SEQ_ERR_RACE, SEQ_ERR_NOT_OWNER
} seq_status;

#define SEQ_WR_CLOCKS      40u      /* fabric clocks per entry written (4 register writes; conservative for an AXI-Lite port) */
#define SEQ_COMMIT_MARGIN  200u     /* fabric clocks kept free before the END clock (1 us at 200 MHz) */

typedef struct {
    hal_t   *h;
    uint32_t sum[2];                /* checksum of the table in each physical bank */
    bool     known[2];
    uint32_t n_written, n_skipped;  /* statistics: tables written in full / commit only */
    uint32_t epoch_seen;            /* ownership epoch at the last load (see seq_load_owned in sup.h) */
} seq_drv_t;

void       seq_drv_init(seq_drv_t *d, hal_t *h);
seq_status seq_validate(const seq_entry *t, uint32_t n);
/* load and commit. SEQ_ERR_LATE: not enough time before the frame end, nothing written or committed (try again next frame).
 * SEQ_ERR_RACE: the banks swapped while the table was being written (the guard failed); the driver forgets what the banks hold. */
seq_status seq_load(seq_drv_t *d, const seq_entry *t, uint32_t n);
/* the same without the timing guard (monitor takeover when the frame position does not matter, tests) */
seq_status seq_load_unguarded(seq_drv_t *d, const seq_entry *t, uint32_t n);

#endif
