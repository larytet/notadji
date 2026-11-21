/* region - signed region and entitlement tables and the power limiter (R33-11; SEC-003, SEC-005, SEC-006).
 * Serialised table, 100 bytes, little-endian, signed with Ed25519 over bytes 0..35:
 *   0 magic (4)  4 version u16  6 region_id u16  8 band_mask u16  10 dfs u8  11 0  12 dwell_ms u16  14 n_bands u8  15 0
 *   16 max_power_x4[8] int16 (0.25 dBm units)  32 counter u32 (not used by the limiter: carried for the monotonic rollback counter)  36 signature (64).
 * An entitlement table has the same layout with another magic: band_mask carries the option bits. */
#ifndef REGION_H
#define REGION_H

#include "fw_types.h"

#define REGION_MAGIC  0x314E4752u    /* "RGN1" */
#define ENTITLE_MAGIC 0x31544E45u    /* "ENT1" */
#define REGION_LEN    100u
#define REGION_BANDS  8u

typedef enum { REGION_OK = 0, REGION_BAD_LEN, REGION_BAD_MAGIC, REGION_BAD_SIG, REGION_OLD_VERSION } region_status;

typedef struct {
    uint32_t magic;
    uint16_t version, region_id, band_mask;
    uint8_t  dfs, n_bands;
    uint16_t dwell_ms;
    int16_t  max_power_x4[REGION_BANDS];
    uint32_t counter;
} region_t;

/* verify the signature with the public key, check the magic and that version >= min_version, fill `out` */
region_status region_verify(const uint8_t *buf, uint32_t len, const uint8_t pk[32], uint32_t magic, uint16_t min_version, region_t *out);

#define REGION_NOT_ALLOWED ((int16_t)-32768)
/* the largest transmit power allowed on `band` for a request, or REGION_NOT_ALLOWED when the band is not enabled */
int16_t region_clamp_power(const region_t *r, uint8_t band, int16_t req_x4);
uint16_t region_clamp_dwell(const region_t *r, uint16_t req_ms);               /* dwell_ms 0 means no limit */

#endif
