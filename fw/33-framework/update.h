/* update - A/B image slots, signed images, trial boot, rollback and anti-rollback (R33-12; SW-004, SEC-003).
 * Flash layout (sector = hal flash_sector): sector 0 and 1: boot record copies; then slot 0 and slot 1 of equal size.
 * Boot record (one per copy sector, 64 bytes, CRC-32): magic, generation, active slot, state (confirmed or trial), trial boot count, bad-slot mask,
 * rollback counter, update session (target slot, total length). The copy with the highest valid generation wins; a new record always goes to the
 * other sector, so a power loss during the write leaves the previous record intact.
 * Image: 128-byte header {magic, version, length, flags, SHA-256 of the payload, reserved; Ed25519 signature over bytes 0..63} followed by the payload. */
#ifndef UPDATE_H
#define UPDATE_H

#include "hal.h"
#include "crashlog.h"

#define IMG_MAGIC     0x31474D49u     /* "IMG1" */
#define IMG_HDR       128u
#define UPD_MAX_TRIAL 3u
#define UPD_CHUNK_MAX 256u

typedef enum { UPD_OK = 0, UPD_ERR_STATE, UPD_ERR_OFFSET, UPD_ERR_SIZE, UPD_ERR_FLASH, UPD_ERR_HDR, UPD_ERR_SIG, UPD_ERR_HASH, UPD_ERR_VERSION } upd_status;
enum { BOOT_CONFIRMED = 1, BOOT_TRIAL = 2 };

typedef struct {
    uint32_t generation;
    uint8_t  active, state, trial_boots, bad_mask;
    uint32_t rollback;                    /* images older than this are refused */
    uint8_t  upd_target;                  /* slot of an update in progress, 0xFF none */
    uint32_t upd_total;
} boot_rec;

typedef struct {
    hal_t   *h;
    clog_t  *log;
    const uint8_t *pk;                    /* image signing public key (immutable boot code in the product) */
    uint32_t sector, slot_bytes;
    boot_rec rec;
    bool     rec_valid;
    int      rec_sector;                  /* which copy holds the current record, -1 none */
    bool     updating;
    uint8_t  target;
    uint32_t total, next_off;
} upd_t;

void upd_init(upd_t *u, hal_t *h, clog_t *log, const uint8_t pk[32]);
/* factory provisioning: record pointing at slot 0 (the image must already be in the slot) */
bool upd_factory_record(upd_t *u);
/* boot: choose the slot to start, counting trial boots and rolling back; verifies signature and hash of the chosen image. -1: no valid image */
int  upd_boot_select(upd_t *u);
/* the link has run well for long enough: make a trial image permanent and raise the rollback counter */
bool upd_confirm(upd_t *u);
/* start (or resume) an update of the inactive slot with an image of `total` bytes (header + payload) */
upd_status upd_begin(upd_t *u, uint32_t total, bool resume);
uint32_t   upd_next_offset(const upd_t *u);
upd_status upd_chunk(upd_t *u, uint32_t off, const uint8_t *data, uint32_t n);
upd_status upd_finish(upd_t *u);                      /* verify header, signature, version and hash, then switch to trial */
upd_status upd_verify_slot(upd_t *u, uint8_t slot, uint32_t *version_out);

#endif
