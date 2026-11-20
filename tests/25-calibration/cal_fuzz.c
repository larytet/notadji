/* Random sums and random non-volatile images under UBSan and ASan. */
#include <stdio.h>
#include <string.h>
#include "cal_mgr.h"

static uint32_t lcg(uint32_t *s) { *s = *s * 1664525u + 1013904223u; return *s >> 8; }
static uint64_t r64(uint32_t *s) { return ((uint64_t)lcg(s) << 40) ^ ((uint64_t)lcg(s) << 20) ^ lcg(s); }

int main(void)
{
    static cal_table tab;
    static uint8_t nv[CAL_ENTRIES][CAL_NV_BYTES];
    cal_mgr m;
    cal_sums s;
    cal_lim lim = {1024u, 100u, 8192, 4000};
    cal_coeff c;
    uint32_t r = 7, ok = 0, rej = 0;
    long k;
    int j;
    for (k = 0; k < 300000; k++) {
        s.sum_i = (int64_t)(r64(&r) % 0x180000000ull) - 0xC0000000ll;
        s.sum_q = (int64_t)(r64(&r) % 0x180000000ull) - 0xC0000000ll;
        s.sum_ii = r64(&r) % 0x800000000000ull;
        s.sum_qq = r64(&r) % 0x800000000000ull;
        s.sum_iq = (int64_t)(r64(&r) % 0x800000000000ull) - 0x400000000000ll;
        s.n = lcg(&r) % 140000u;
        if (cal_stats_to_coeff(&s, &lim, &c) == CAL_OK) ok++; else rej++;
    }
    for (k = 0; k < 2000; k++) {
        cal_entry e;
        uint8_t st;
        memset(&e, 0, sizeof e);
        for (j = 0; j < CAL_ENTRIES; j++) {
            e.version = (lcg(&r) % 8 == 0) ? 2u : CAL_VERSION;
            e.band = (uint8_t)(j / (CAL_GROUPS * CAL_TBINS));
            e.group = (uint8_t)((j / CAL_TBINS) % CAL_GROUPS);
            e.tbin = (uint8_t)(j % CAL_TBINS);
            e.valid = 1;
            e.rx.eps_r = (int16_t)lcg(&r);
            cal_entry_pack(&e, nv[j]);
            if (lcg(&r) % 16 == 0) nv[j][lcg(&r) % CAL_NV_BYTES] ^= (uint8_t)(1u << (lcg(&r) % 8));
        }
        cal_table_load(&tab, (const uint8_t (*)[CAL_NV_BYTES])nv, CAL_ENTRIES);
        cal_init(&m, &tab);
        cal_on_hop(&m, (uint8_t)(lcg(&r) % 3), (uint8_t)(lcg(&r) % 9), (int16_t)(lcg(&r) % 2000) - 600, 1000u + (uint32_t)k);
        if (cal_lookup(&tab, (uint8_t)(lcg(&r) % 3), (uint8_t)(lcg(&r) % 9), (int16_t)(lcg(&r) % 2000) - 600, &st) >= CAL_ENTRIES || st > CAL_TBINS) {
            printf("lookup out of range\n");
            return 1;
        }
        (void)cal_tick(&m, (uint32_t)k * 7u, (int16_t)(lcg(&r) % 1500), (uint8_t)(lcg(&r) % 8));
    }
    printf("%u accepted, %u rejected windows, 2000 random table images", ok, rej);
    puts("");
    return 0;
}
