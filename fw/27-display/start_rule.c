#include "start_rule.h"

static uint32_t isqrt32(uint32_t v)
{
    uint32_t r = 0, bit = 1u << 30;
    while (bit > v) bit >>= 2;
    while (bit != 0u) {
        if (v >= r + bit) {
            v -= r + bit;
            r = (r >> 1) + bit;
        } else r >>= 1;
        bit >>= 2;
    }
    return r;
}

void sr_init(sr_state *s, uint8_t n_slices)
{
    uint8_t k;
    s->n_slices = n_slices > SR_MAX_SLICES ? SR_MAX_SLICES : n_slices;
    for (k = 0; k < SR_MAX_SLICES; k++) {
        s->mean_q4[k] = 0;
        s->var_q8[k] = 0;
        s->seen[k] = 0;
    }
}

void sr_report(sr_state *s, uint8_t k, int32_t t_us, int32_t line_us)
{
    int32_t x, d;
    uint32_t d2;
    if (k >= s->n_slices) return;
    x = (t_us - line_us) * 16;
    if (!s->seen[k]) {
        s->mean_q4[k] = x;
        s->var_q8[k] = 0;
        s->seen[k] = 1;
        return;
    }
    d = x - s->mean_q4[k];
    s->mean_q4[k] += d / 16;
    /* d in Q4 (us x 16): d^2 is Q8; keep it from overflowing for lateness differences below 2000 us */
    d2 = (uint32_t)((int64_t)d * d > 0x7FFFFFFF ? 0x7FFFFFFF : (int64_t)d * d);
    s->var_q8[k] = s->var_q8[k] + (uint32_t)(((int64_t)d2 - (int64_t)s->var_q8[k]) / 16);
}

int32_t sr_start(const sr_state *s, int32_t z_q8, int32_t margin_us)
{
    int32_t best = -0x7FFFFFFF;
    uint8_t k;
    for (k = 0; k < s->n_slices; k++) {
        int32_t sigma_q4, v;
        if (!s->seen[k]) continue;
        sigma_q4 = (int32_t)isqrt32(s->var_q8[k]);               /* sqrt of Q8 is Q4 */
        v = s->mean_q4[k] + (int32_t)(((int64_t)z_q8 * sigma_q4) >> 8);
        if (v > best) best = v;
    }
    if (best == -0x7FFFFFFF) return margin_us;
    return (best + 8) / 16 + margin_us;
}
