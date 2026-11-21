#include "seq_drv.h"
#include "crc.h"

void seq_drv_init(seq_drv_t *d, hal_t *h) { memset(d, 0, sizeof *d); d->h = h; }

seq_status seq_validate(const seq_entry *t, uint32_t n)
{
    uint32_t i, last = 0;
    if (n == 0) return SEQ_ERR_EMPTY;
    if (n > SEQ_DEPTH) return SEQ_ERR_TOO_DEEP;
    for (i = 0; i < n; i++) {
        if (t[i].time > 0xFFFFFFu) return SEQ_ERR_TIME_RANGE;
        if (t[i].time < last) return SEQ_ERR_UNSORTED;
        last = t[i].time;
        if (!(t[i].act <= SEQ_ACT_SET_PLL || t[i].act == SEQ_ACT_END)) return SEQ_ERR_ACTION;
        if (t[i].act == SEQ_ACT_END) {
            if (i != n - 1u) return SEQ_ERR_END_NOT_LAST;
            if (t[i].time < SEQ_MIN_FRAME) return SEQ_ERR_TIME_RANGE;    /* the hardware would stretch it: refuse a table that does not say what it does */
        }
    }
    if (t[n - 1u].act != SEQ_ACT_END) return SEQ_ERR_NO_END;
    return SEQ_OK;
}

static uint64_t pack(const seq_entry *e) { return ((uint64_t)e->time << 24) | ((uint64_t)e->act << 16) | e->arg; }

static uint32_t table_sum(const seq_entry *t, uint32_t n)
{
    uint8_t b[SEQ_DEPTH * 8];
    uint32_t i;
    for (i = 0; i < n; i++) { uint64_t v = pack(&t[i]); fw_st32(b + 8u * i, (uint32_t)v); fw_st32(b + 8u * i + 4u, (uint32_t)(v >> 32)); }
    return crc32_ieee(b, 8u * n) ^ n;
}

static seq_status do_load(seq_drv_t *d, const seq_entry *t, uint32_t n, bool guard)
{
    hal_t *h = d->h;
    seq_status v = seq_validate(t, n);
    uint32_t st, inactive, sum, i;
    if (v != SEQ_OK) return v;
    sum = table_sum(t, n);
    st = hal_rd(h, SEQ_STATUS);
    inactive = ((st & 1u) ^ 1u);
    if (guard) {
        uint32_t len = hal_rd(h, SEQ_FRAME_LEN), tick = hal_rd(h, SEQ_TICK);
        uint32_t need = (d->known[inactive] && d->sum[inactive] == sum) ? 0u : n * SEQ_WR_CLOCKS;
        /* with len == 0 (no END in the running table) the frame never ends and there is no deadline */
        if (len != 0 && (tick >= len || len - tick < need + SEQ_COMMIT_MARGIN)) return SEQ_ERR_LATE;
    }
    if (!(d->known[inactive] && d->sum[inactive] == sum)) {
        d->known[inactive] = false;
        for (i = 0; i < n; i++) {
            uint64_t e = pack(&t[i]);
            hal_wr(h, SEQ_WR_ADDR, i);
            hal_wr(h, SEQ_WR_DATA_LO, (uint32_t)e);
            hal_wr(h, SEQ_WR_DATA_HI, (uint32_t)(e >> 32));
            hal_wr(h, SEQ_WR_STROBE, 1);
        }
        if ((hal_rd(h, SEQ_STATUS) & 1u) != (st & 1u)) {              /* the banks swapped under us: the writes went to the wrong bank */
            d->known[0] = d->known[1] = false;
            return SEQ_ERR_RACE;
        }
        d->sum[inactive] = sum; d->known[inactive] = true;
        d->n_written++;
    } else d->n_skipped++;
    hal_wr(h, SEQ_COMMIT, 1);
    return SEQ_OK;
}

seq_status seq_load(seq_drv_t *d, const seq_entry *t, uint32_t n) { return do_load(d, t, n, true); }
seq_status seq_load_unguarded(seq_drv_t *d, const seq_entry *t, uint32_t n) { return do_load(d, t, n, false); }
