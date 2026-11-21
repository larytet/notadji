#include "crashlog.h"
#include "crc.h"

#define CLOG_MAGIC 0x43474F4Cu   /* "LOGC" */
#define CLOG_VERSION 1u

static void rec_encode(const clog_rec *r, uint8_t b[CLOG_REC_SIZE])
{
    uint32_t i;
    fw_st32(b + 0, r->seq); fw_st32(b + 4, r->t_us); fw_st16(b + 8, r->type); fw_st16(b + 10, r->flags);
    for (i = 0; i < 4; i++) fw_st32(b + 12 + 4 * i, r->a[i]);
    fw_st32(b + 28, crc32_ieee(b, 28));
}

static bool rec_decode(const uint8_t b[CLOG_REC_SIZE], clog_rec *r)
{
    uint32_t i;
    if (fw_ld32(b + 28) != crc32_ieee(b, 28)) return false;
    r->seq = fw_ld32(b); r->t_us = fw_ld32(b + 4); r->type = fw_ld16(b + 8); r->flags = fw_ld16(b + 10);
    for (i = 0; i < 4; i++) r->a[i] = fw_ld32(b + 12 + 4 * i);
    return r->seq != 0;
}

static uint32_t rec_off(const clog_t *c, uint32_t seq) { return c->base + CLOG_HDR_SIZE + ((seq - 1u) % c->cap) * CLOG_REC_SIZE; }

static void hdr_write(clog_t *c)
{
    uint8_t b[CLOG_HDR_SIZE];
    memset(b, 0, sizeof b);
    fw_st32(b, CLOG_MAGIC); fw_st32(b + 4, c->cap); fw_st16(b + 8, CLOG_REC_SIZE); fw_st16(b + 10, CLOG_VERSION);
    fw_st32(b + 12, crc32_ieee(b, 12));
    c->h->ret_write(c->h, c->base, b, sizeof b);
}

void clog_clear(clog_t *c)
{
    uint8_t z[CLOG_REC_SIZE];
    uint32_t i;
    memset(z, 0, sizeof z);
    hdr_write(c);
    for (i = 0; i < c->cap; i++) c->h->ret_write(c->h, c->base + CLOG_HDR_SIZE + i * CLOG_REC_SIZE, z, CLOG_REC_SIZE);
    c->next_seq = 1; c->oldest = 1; c->recovered = 0;
}

bool clog_open(clog_t *c, hal_t *h, uint32_t base, uint32_t size)
{
    uint8_t b[CLOG_HDR_SIZE];
    uint32_t cap, i, hi = 0, lo;
    bool ok;
    if (size < CLOG_HDR_SIZE + CLOG_REC_SIZE || (uint64_t)base + size > h->ret_size) return false;
    memset(c, 0, sizeof *c);
    c->h = h; c->base = base;
    cap = (size - CLOG_HDR_SIZE) / CLOG_REC_SIZE;
    c->cap = cap;
    h->ret_read(h, base, b, sizeof b);
    ok = fw_ld32(b) == CLOG_MAGIC && fw_ld32(b + 4) == cap && fw_ld16(b + 8) == CLOG_REC_SIZE && fw_ld16(b + 10) == CLOG_VERSION &&
         fw_ld32(b + 12) == crc32_ieee(b, 12);
    if (!ok) { c->reinit = true; clog_clear(c); return true; }

    /* scan: a slot is valid if its CRC is good and the sequence number belongs to the slot */
    for (i = 0; i < cap; i++) {
        uint8_t rb[CLOG_REC_SIZE]; clog_rec r;
        h->ret_read(h, base + CLOG_HDR_SIZE + i * CLOG_REC_SIZE, rb, sizeof rb);
        if (rec_decode(rb, &r) && (r.seq - 1u) % cap == i) { if (r.seq > hi) hi = r.seq; }
        else { bool empty = true; uint32_t k; for (k = 0; k < CLOG_REC_SIZE; k++) if (rb[k]) { empty = false; break; } if (!empty) c->dropped_torn++; }
    }
    if (hi == 0) { c->next_seq = 1; c->oldest = 1; c->recovered = 0; return true; }
    /* the log is the contiguous run ending at hi: walk back while the slots hold exactly seq-1, seq-2 ... */
    lo = hi;
    while (lo > 1 && hi - lo + 1u < cap) {
        uint8_t rb[CLOG_REC_SIZE]; clog_rec r;
        h->ret_read(h, rec_off(c, lo - 1u), rb, sizeof rb);
        if (rec_decode(rb, &r) && r.seq == lo - 1u) lo--; else break;
    }
    c->next_seq = hi + 1u; c->oldest = lo; c->recovered = hi - lo + 1u;
    return true;
}

void clog_append(clog_t *c, uint16_t type, uint16_t flags, uint32_t a0, uint32_t a1, uint32_t a2, uint32_t a3)
{
    clog_rec r; uint8_t b[CLOG_REC_SIZE];
    if (c->next_seq == 0xFFFFFFFFu) clog_clear(c);       /* 2^32 records (49 days at 1 kHz): start over rather than let the numbering wrap */
    r.seq = c->next_seq; r.t_us = hal_now_us(c->h); r.type = type; r.flags = flags;
    r.a[0] = a0; r.a[1] = a1; r.a[2] = a2; r.a[3] = a3;
    rec_encode(&r, b);
    c->h->ret_write(c->h, rec_off(c, r.seq), b, sizeof b);
    c->next_seq++;
    if (c->next_seq - c->oldest > c->cap) c->oldest = c->next_seq - c->cap;
}

uint32_t clog_count(const clog_t *c) { return c->next_seq - c->oldest; }

bool clog_get(const clog_t *c, uint32_t k, clog_rec *r)
{
    uint8_t b[CLOG_REC_SIZE];
    if (k >= clog_count(c)) return false;
    c->h->ret_read(c->h, rec_off(c, c->oldest + k), b, sizeof b);
    return rec_decode(b, r);
}
