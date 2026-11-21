#include "update.h"
#include "crc.h"
#include "sha2.h"
#include "curve25519.h"

#define BOOT_MAGIC 0x544F4F42u    /* "BOOT" */
#define REC_LEN 64u

static uint32_t slot_off(const upd_t *u, uint8_t slot) { return (2u + (uint32_t)slot * (u->slot_bytes / u->sector)) * u->sector; }

static void rec_encode(const boot_rec *r, uint8_t b[REC_LEN])
{
    memset(b, 0xFF, REC_LEN);
    fw_st32(b, BOOT_MAGIC); fw_st32(b + 4, r->generation);
    b[8] = r->active; b[9] = r->state; b[10] = r->trial_boots; b[11] = r->bad_mask;
    fw_st32(b + 12, r->rollback); b[16] = r->upd_target; fw_st32(b + 20, r->upd_total);
    memset(b + 24, 0, 36);
    fw_st32(b + 60, crc32_ieee(b, 60));
}

static bool rec_decode(const uint8_t b[REC_LEN], boot_rec *r)
{
    if (fw_ld32(b) != BOOT_MAGIC || fw_ld32(b + 60) != crc32_ieee(b, 60)) return false;
    r->generation = fw_ld32(b + 4); r->active = b[8]; r->state = b[9]; r->trial_boots = b[10]; r->bad_mask = b[11];
    r->rollback = fw_ld32(b + 12); r->upd_target = b[16]; r->upd_total = fw_ld32(b + 20);
    return r->active < 2u && (r->state == BOOT_CONFIRMED || r->state == BOOT_TRIAL);
}

static void load_record(upd_t *u)
{
    uint32_t s;
    u->rec_valid = false; u->rec_sector = -1;
    for (s = 0; s < 2; s++) {
        uint8_t b[REC_LEN]; boot_rec r;
        if (u->h->fl_read(u->h, s * u->sector, b, REC_LEN) != 0) continue;
        if (rec_decode(b, &r) && (!u->rec_valid || r.generation > u->rec.generation)) { u->rec = r; u->rec_valid = true; u->rec_sector = (int)s; }
    }
}

/* write a new record into the sector that does not hold the current one */
static bool store_record(upd_t *u, boot_rec *r)
{
    uint8_t b[REC_LEN];
    uint32_t s = (u->rec_sector == 0) ? 1u : 0u;
    r->generation = u->rec_valid ? u->rec.generation + 1u : 1u;
    rec_encode(r, b);
    if (u->h->fl_erase(u->h, s * u->sector) != 0) return false;
    if (u->h->fl_program(u->h, s * u->sector, b, REC_LEN) != 0) return false;
    u->rec = *r; u->rec_valid = true; u->rec_sector = (int)s;
    return true;
}

void upd_init(upd_t *u, hal_t *h, clog_t *log, const uint8_t pk[32])
{
    memset(u, 0, sizeof *u);
    u->h = h; u->log = log; u->pk = pk; u->sector = h->flash_sector;
    u->slot_bytes = ((h->flash_size / h->flash_sector - 2u) / 2u) * h->flash_sector;
    load_record(u);
}

bool upd_factory_record(upd_t *u)
{
    boot_rec r;
    memset(&r, 0, sizeof r);
    r.active = 0; r.state = BOOT_CONFIRMED; r.upd_target = 0xFF;
    u->rec_valid = false; u->rec_sector = -1;
    return store_record(u, &r);
}

upd_status upd_verify_slot(upd_t *u, uint8_t slot, uint32_t *version_out)
{
    uint8_t hdr[IMG_HDR], buf[UPD_CHUNK_MAX], dig[32];
    uint32_t off = slot_off(u, slot), len, ver, done;
    sha256_t c;
    if (u->h->fl_read(u->h, off, hdr, IMG_HDR) != 0) return UPD_ERR_FLASH;
    if (fw_ld32(hdr) != IMG_MAGIC) return UPD_ERR_HDR;
    len = fw_ld32(hdr + 8); ver = fw_ld32(hdr + 4);
    if (len > u->slot_bytes - IMG_HDR) return UPD_ERR_SIZE;
    if (!ed25519_verify(hdr + 64, hdr, 64, u->pk)) return UPD_ERR_SIG;
    sha256_init(&c);
    for (done = 0; done < len; ) {
        uint32_t k = len - done < UPD_CHUNK_MAX ? len - done : UPD_CHUNK_MAX;
        if (u->h->fl_read(u->h, off + IMG_HDR + done, buf, k) != 0) return UPD_ERR_FLASH;
        sha256_update(&c, buf, k); done += k;
    }
    sha256_final(&c, dig);
    if (ct_memcmp(dig, hdr + 16, 32) != 0) return UPD_ERR_HASH;
    if (version_out) *version_out = ver;
    return UPD_OK;
}

int upd_boot_select(upd_t *u)
{
    boot_rec r;
    int tries;
    load_record(u);
    if (!u->rec_valid) return -1;
    for (tries = 0; tries < 2; tries++) {
        uint32_t ver = 0;
        r = u->rec;
        if (r.state == BOOT_TRIAL && r.trial_boots >= UPD_MAX_TRIAL) {          /* the trial image never got confirmed: give it up */
            r.bad_mask = (uint8_t)(r.bad_mask | (1u << r.active)); r.active ^= 1u; r.state = BOOT_CONFIRMED; r.trial_boots = 0;
            if (!store_record(u, &r)) return -1;
            clog_append(u->log, CLOG_UPDATE, 0, 3, r.active, 0, 0);
            continue;
        }
        if (upd_verify_slot(u, r.active, &ver) != UPD_OK) {                      /* damaged or forged: never booted */
            r.bad_mask = (uint8_t)(r.bad_mask | (1u << r.active)); r.active ^= 1u; r.state = BOOT_CONFIRMED; r.trial_boots = 0;
            if (r.bad_mask == 3u) return -1;
            if (!store_record(u, &r)) return -1;
            clog_append(u->log, CLOG_UPDATE, 0, 4, r.active, 0, 0);
            continue;
        }
        if (r.state == BOOT_TRIAL) {
            r.trial_boots++;                                                     /* counted before the jump */
            if (!store_record(u, &r)) return -1;
        }
        return r.active;
    }
    return -1;
}

bool upd_confirm(upd_t *u)
{
    boot_rec r = u->rec;
    uint32_t ver = 0;
    if (!u->rec_valid || r.state != BOOT_TRIAL) return false;
    if (upd_verify_slot(u, r.active, &ver) != UPD_OK) return false;
    r.state = BOOT_CONFIRMED; r.trial_boots = 0;
    if (ver > r.rollback) r.rollback = ver;
    if (!store_record(u, &r)) return false;
    clog_append(u->log, CLOG_UPDATE, 0, 2, r.active, ver, 0);
    return true;
}

static bool sector_blank(upd_t *u, uint32_t off)
{
    uint8_t b[64]; uint32_t i, k;
    for (i = 0; i < u->sector; i += 64u) {
        if (u->h->fl_read(u->h, off + i, b, 64) != 0) return false;
        for (k = 0; k < 64; k++) if (b[k] != 0xFF) return false;
    }
    return true;
}

upd_status upd_begin(upd_t *u, uint32_t total, bool resume)
{
    boot_rec r;
    uint8_t target;
    if (!u->rec_valid) return UPD_ERR_STATE;
    if (total < IMG_HDR || total > u->slot_bytes) return UPD_ERR_SIZE;
    target = (uint8_t)(u->rec.active ^ 1u);
    u->updating = true; u->target = target; u->total = total; u->next_off = 0;
    if (resume && u->rec.upd_target == target && u->rec.upd_total == total) {
        /* continue at the start of the last sector that has anything in it (a chunk may have been cut in the middle of it) */
        uint32_t s, nsec = u->slot_bytes / u->sector, first_blank = nsec;
        for (s = 0; s < nsec; s++) if (sector_blank(u, slot_off(u, target) + s * u->sector)) { first_blank = s; break; }
        u->next_off = first_blank == 0 ? 0u : (first_blank - 1u) * u->sector;
        if (u->next_off > total) u->next_off = 0;
        return UPD_OK;
    }
    r = u->rec; r.upd_target = target; r.upd_total = total;
    if (!store_record(u, &r)) { u->updating = false; return UPD_ERR_FLASH; }
    return UPD_OK;
}

uint32_t upd_next_offset(const upd_t *u) { return u->next_off; }

upd_status upd_chunk(upd_t *u, uint32_t off, const uint8_t *data, uint32_t n)
{
    uint32_t base;
    if (!u->updating) return UPD_ERR_STATE;
    if (off != u->next_off) return UPD_ERR_OFFSET;
    if (n == 0 || n > UPD_CHUNK_MAX || off + n > u->total) return UPD_ERR_SIZE;
    base = slot_off(u, u->target);
    while (n) {
        uint32_t in_sec = u->sector - (off % u->sector), k = n < in_sec ? n : in_sec;
        if (off % u->sector == 0 && u->h->fl_erase(u->h, base + off) != 0) return UPD_ERR_FLASH;     /* erase a sector when the write reaches it */
        if (u->h->fl_program(u->h, base + off, data, k) != 0) return UPD_ERR_FLASH;
        off += k; data += k; n -= k;
        u->next_off = off;
    }
    return UPD_OK;
}

upd_status upd_finish(upd_t *u)
{
    uint8_t hdr[IMG_HDR];
    uint32_t ver = 0, len;
    upd_status st;
    boot_rec r;
    if (!u->updating) return UPD_ERR_STATE;
    if (u->next_off != u->total) return UPD_ERR_SIZE;
    if (u->h->fl_read(u->h, slot_off(u, u->target), hdr, IMG_HDR) != 0) return UPD_ERR_FLASH;
    if (fw_ld32(hdr) != IMG_MAGIC) return UPD_ERR_HDR;
    len = fw_ld32(hdr + 8);
    if (len + IMG_HDR != u->total) return UPD_ERR_SIZE;                          /* the announced size must match the image */
    st = upd_verify_slot(u, u->target, &ver);
    if (st != UPD_OK) return st;
    if (ver < u->rec.rollback) return UPD_ERR_VERSION;                            /* anti-rollback */
    r = u->rec;
    r.active = u->target; r.state = BOOT_TRIAL; r.trial_boots = 0;
    r.bad_mask = (uint8_t)(r.bad_mask & ~(1u << u->target));
    r.upd_target = 0xFF; r.upd_total = 0;
    if (!store_record(u, &r)) return UPD_ERR_FLASH;
    u->updating = false;
    clog_append(u->log, CLOG_UPDATE, 0, 1, r.active, ver, 0);
    return UPD_OK;
}
