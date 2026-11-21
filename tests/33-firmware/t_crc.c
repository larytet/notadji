// SRC: crc.c
/* T33-18 (part): published check values and agreement with bitwise references */
#include "tcheck.h"
#include "crc.h"

static uint32_t ref32(const uint8_t *p, size_t n)
{
    uint32_t c = 0xFFFFFFFFu; size_t i; int k;
    for (i = 0; i < n; i++) { c ^= p[i]; for (k = 0; k < 8; k++) c = (c & 1u) ? (c >> 1) ^ 0xEDB88320u : c >> 1; }
    return ~c;
}
static uint16_t ref16(const uint8_t *p, size_t n)    /* CRC-16/MCRF4XX written MSB-first with a reflected input and output */
{
    uint16_t c = 0xFFFF; size_t i; int k;
    for (i = 0; i < n; i++) {
        uint8_t b = p[i], r = 0; int j;
        for (j = 0; j < 8; j++) if (b & (1 << j)) r |= (uint8_t)(0x80 >> j);
        c = (uint16_t)(c ^ (r << 8));
        for (k = 0; k < 8; k++) c = (uint16_t)((c & 0x8000) ? (c << 1) ^ 0x1021 : c << 1);
    }
    { uint16_t o = 0; int j; for (j = 0; j < 16; j++) if (c & (1 << j)) o |= (uint16_t)(0x8000 >> j); return o; }
}
static uint8_t ref8(const uint8_t *p, size_t n)
{
    uint8_t c = 0; size_t i; int k;
    for (i = 0; i < n; i++) { c ^= p[i]; for (k = 0; k < 8; k++) c = (uint8_t)((c & 0x80) ? (c << 1) ^ 0xD5 : c << 1); }
    return c;
}

TEST(check_values)
{
    const char *s = "123456789";
    CHECK_EQ(crc32_ieee(s, 9), 0xCBF43926u);
    CHECK_EQ(crc16_mcrf4xx(s, 9), 0x6F91u);
    CHECK_EQ(crc8_dvb_s2(s, 9), 0xBCu);
    CHECK_EQ(crc32_ieee("", 0), 0u);
    CHECK_EQ(crc16_mcrf4xx("", 0), 0xFFFFu);
}

TEST(random_vs_reference)
{
    int i;
    for (i = 0; i < 20000; i++) {
        uint8_t b[300]; size_t n = tc_rand() % 300, k;
        for (k = 0; k < n; k++) b[k] = (uint8_t)tc_rand();
        if (crc32_ieee(b, n) != ref32(b, n)) { CHECK(0); break; }
        if (crc16_mcrf4xx(b, n) != ref16(b, n)) { CHECK(0); break; }
        if (crc8_dvb_s2(b, n) != ref8(b, n)) { CHECK(0); break; }
    }
    CHECK(1);
}

TEST(incremental)
{
    uint8_t b[100]; size_t k, cut;
    for (k = 0; k < 100; k++) b[k] = (uint8_t)(k * 7);
    for (cut = 0; cut <= 100; cut++) {
        uint16_t c = crc16_mcrf4xx_update(0xFFFF, b, cut); c = crc16_mcrf4xx_update(c, b + cut, 100 - cut);
        uint8_t d = crc8_dvb_s2_update(crc8_dvb_s2(b, cut), b + cut, 100 - cut);
        CHECK_EQ(c, crc16_mcrf4xx(b, 100)); CHECK_EQ(d, crc8_dvb_s2(b, 100));
    }
}

int main(void) { RUN(check_values); RUN(random_vs_reference); RUN(incremental); TC_DONE(); }
