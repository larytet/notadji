#include "hostproto.h"
#include "crc.h"

void hp_init(hp_t *h, hp_extra_fn extra, spsc_t *out_queue)
{
    memset(h, 0, sizeof *h);
    h->extra = extra; h->out = out_queue;
}

typedef enum { TRY_OK, TRY_WAIT, TRY_BAD } try_t;

static void drop(hp_t *h, uint32_t k)
{
    memmove(h->win, h->win + k, h->n - k);
    h->n -= k;
}

/* MAVLink 2: STX 0xFD, len, incompat, compat, seq, sysid, compid, msgid[3], payload, crc[2], optional signature[13] */
static try_t try_mav2(hp_t *h, hp_frame *f, uint32_t *used)
{
    const uint8_t *b = h->win;
    uint32_t len, total, sig = 0, msgid;
    uint16_t crc;
    int extra;
    if (h->n < 10u) return TRY_WAIT;
    len = b[1];
    if (b[2] & ~1u) { h->st.bad_header++; return TRY_BAD; }          /* unknown incompatibility flag: the frame must be discarded */
    if (b[2] & 1u) sig = 13u;
    total = 10u + len + 2u + sig;
    if (h->n < total) return TRY_WAIT;
    msgid = (uint32_t)b[7] | ((uint32_t)b[8] << 8) | ((uint32_t)b[9] << 16);
    extra = h->extra ? h->extra(msgid) : -1;
    if (extra < 0) { h->st.unknown_id++; return TRY_BAD; }           /* cannot be checked: dropped */
    crc = crc16_mcrf4xx(b + 1, 9u + len);
    crc = crc16_mcrf4xx_update(crc, &(uint8_t){ (uint8_t)extra }, 1);
    if (crc != fw_ld16(b + 10u + len)) { h->st.bad_crc++; return TRY_BAD; }
    f->proto = HP_MAVLINK2; f->dir = 0; f->flags = b[2]; f->signed_frame = sig != 0u;
    f->seq = b[4]; f->sysid = b[5]; f->compid = b[6]; f->id = msgid; f->len = (uint16_t)len;
    memcpy(f->payload, b + 10, len);
    *used = total;
    return TRY_OK;
}

/* MSP: '$' 'M' dir size cmd payload xor   |   '$' 'X' dir flag cmd[2] size[2] payload crc8 */
static try_t try_msp(hp_t *h, hp_frame *f, uint32_t *used)
{
    const uint8_t *b = h->win;
    uint32_t len, total;
    if (h->n < 3u) return TRY_WAIT;
    if (b[2] != '<' && b[2] != '>' && b[2] != '!') { h->st.bad_header++; return TRY_BAD; }
    if (b[1] == 'M') {
        uint8_t x = 0; uint32_t i;
        if (h->n < 5u) return TRY_WAIT;
        len = b[3];
        if (len == 255u) { h->st.bad_header++; return TRY_BAD; }      /* jumbo frames are not supported */
        total = 6u + len;
        if (h->n < total) return TRY_WAIT;
        for (i = 3; i < 5u + len; i++) x ^= b[i];
        if (x != b[5u + len]) { h->st.bad_crc++; return TRY_BAD; }
        f->proto = HP_MSP1; f->dir = b[2]; f->flags = 0; f->signed_frame = false; f->seq = f->sysid = f->compid = 0;
        f->id = b[4]; f->len = (uint16_t)len; memcpy(f->payload, b + 5, len);
        *used = total;
        return TRY_OK;
    }
    if (b[1] == 'X') {
        if (h->n < 8u) return TRY_WAIT;
        len = (uint32_t)b[6] | ((uint32_t)b[7] << 8);
        if (len > HP_MAX_PAYLOAD) { h->st.bad_header++; return TRY_BAD; }
        total = 9u + len;
        if (h->n < total) return TRY_WAIT;
        if (crc8_dvb_s2(b + 3, 5u + len) != b[8u + len]) { h->st.bad_crc++; return TRY_BAD; }
        f->proto = HP_MSP2; f->dir = b[2]; f->flags = b[3]; f->signed_frame = false; f->seq = f->sysid = f->compid = 0;
        f->id = (uint32_t)b[4] | ((uint32_t)b[5] << 8); f->len = (uint16_t)len; memcpy(f->payload, b + 8, len);
        *used = total;
        return TRY_OK;
    }
    h->st.bad_header++;
    return TRY_BAD;
}

uint32_t hp_poll(hp_t *h, spsc_t *in_ring, uint32_t max_bytes)
{
    uint32_t emitted = 0, steps = 0, pulled = 0;
    hp_frame f;
    for (;;) {
        /* top up the window within the byte budget */
        while (h->n < HP_WIN && pulled < max_bytes && spsc_pop(in_ring, &h->win[h->n])) { h->n++; pulled++; }
        if (h->n == 0 || steps >= HP_MAX_STEPS) break;
        steps++;
        {
            try_t r; uint32_t used = 0;
            if (h->win[0] == 0xFDu) r = try_mav2(h, &f, &used);
            else if (h->win[0] == '$') r = try_msp(h, &f, &used);
            else { h->st.garbage_bytes++; drop(h, 1); continue; }
            if (r == TRY_WAIT) {
                /* nothing more to learn without more bytes; if the window is full the candidate cannot be completed: drop its start byte */
                if (h->n >= HP_WIN) { h->st.bad_header++; drop(h, 1); continue; }
                if (pulled >= max_bytes || spsc_count(in_ring) == 0) break;
                continue;
            }
            if (r == TRY_BAD) { drop(h, 1); continue; }
            if (!spsc_push(h->out, &f)) { h->st.out_full++; break; }  /* back-pressure: the frame stays in the window */
            h->st.frames[f.proto]++;
            drop(h, used);
            emitted++;
        }
    }
    return emitted;
}

uint32_t hp_mav2_encode(uint8_t *o, uint8_t seq, uint8_t sysid, uint8_t compid, uint32_t msgid, const uint8_t *payload, uint8_t len, int crc_extra)
{
    uint16_t crc;
    o[0] = 0xFD; o[1] = len; o[2] = 0; o[3] = 0; o[4] = seq; o[5] = sysid; o[6] = compid;
    o[7] = (uint8_t)msgid; o[8] = (uint8_t)(msgid >> 8); o[9] = (uint8_t)(msgid >> 16);
    memcpy(o + 10, payload, len);
    crc = crc16_mcrf4xx(o + 1, 9u + len);
    crc = crc16_mcrf4xx_update(crc, &(uint8_t){ (uint8_t)crc_extra }, 1);
    fw_st16(o + 10u + len, crc);
    return 12u + len;
}

uint32_t hp_msp1_encode(uint8_t *o, uint8_t dir, uint8_t cmd, const uint8_t *payload, uint8_t len)
{
    uint8_t x = (uint8_t)(len ^ cmd); uint32_t i;
    o[0] = '$'; o[1] = 'M'; o[2] = dir; o[3] = len; o[4] = cmd;
    for (i = 0; i < len; i++) { o[5 + i] = payload[i]; x ^= payload[i]; }
    o[5u + len] = x;
    return 6u + len;
}

uint32_t hp_msp2_encode(uint8_t *o, uint8_t dir, uint8_t flag, uint16_t cmd, const uint8_t *payload, uint8_t len)
{
    o[0] = '$'; o[1] = 'X'; o[2] = dir; o[3] = flag; fw_st16(o + 4, cmd); fw_st16(o + 6, len);
    memcpy(o + 8, payload, len);
    o[8u + len] = crc8_dvb_s2(o + 3, 5u + len);
    return 9u + len;
}
