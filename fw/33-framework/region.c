#include "region.h"
#include "curve25519.h"

region_status region_verify(const uint8_t *b, uint32_t len, const uint8_t pk[32], uint32_t magic, uint16_t min_version, region_t *out)
{
    uint32_t i;
    region_t r;
    if (len != REGION_LEN) return REGION_BAD_LEN;
    if (!ed25519_verify(b + 36, b, 36, pk)) return REGION_BAD_SIG;       /* signature first: nothing of the content is trusted before it */
    r.magic = fw_ld32(b);
    if (r.magic != magic) return REGION_BAD_MAGIC;                       /* a validly signed table of the other kind is not accepted */
    r.version = fw_ld16(b + 4); r.region_id = fw_ld16(b + 6); r.band_mask = fw_ld16(b + 8);
    r.dfs = b[10]; r.dwell_ms = fw_ld16(b + 12); r.n_bands = b[14];
    for (i = 0; i < REGION_BANDS; i++) r.max_power_x4[i] = (int16_t)fw_ld16(b + 16 + 2 * i);
    r.counter = fw_ld32(b + 32);
    if (r.version < min_version) return REGION_OLD_VERSION;
    if (out) *out = r;
    return REGION_OK;
}

int16_t region_clamp_power(const region_t *r, uint8_t band, int16_t req)
{
    if (band >= REGION_BANDS || !(((uint32_t)r->band_mask >> band) & 1u)) return REGION_NOT_ALLOWED;
    return req > r->max_power_x4[band] ? r->max_power_x4[band] : req;
}

uint16_t region_clamp_dwell(const region_t *r, uint16_t req)
{
    return (r->dwell_ms != 0u && req > r->dwell_ms) ? r->dwell_ms : req;
}
