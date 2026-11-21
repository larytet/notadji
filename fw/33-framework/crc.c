#include "crc.h"

/* 16-entry nibble tables: small (constant data 64 bytes), two lookups per byte */
static const uint32_t T32[16] = {
    0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu, 0x76DC4190u, 0x6B6B51F4u, 0x4DB26158u, 0x5005713Cu,
    0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu, 0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu };

uint32_t crc32_ieee(const void *data, size_t n)
{
    const uint8_t *p = (const uint8_t *)data;
    uint32_t c = 0xFFFFFFFFu;
    while (n--) {
        c ^= *p++;
        c = (c >> 4) ^ T32[c & 15u];
        c = (c >> 4) ^ T32[c & 15u];
    }
    return ~c;
}

uint16_t crc16_mcrf4xx_update(uint16_t crc, const void *data, size_t n)
{
    const uint8_t *p = (const uint8_t *)data;
    while (n--) {
        uint8_t i;
        crc = (uint16_t)(crc ^ *p++);
        for (i = 0; i < 8; i++) crc = (uint16_t)((crc & 1u) ? ((crc >> 1) ^ 0x8408u) : (crc >> 1));
    }
    return crc;
}

uint8_t crc8_dvb_s2_update(uint8_t crc, const void *data, size_t n)
{
    const uint8_t *p = (const uint8_t *)data;
    while (n--) {
        uint8_t i;
        crc ^= *p++;
        for (i = 0; i < 8; i++) crc = (uint8_t)((crc & 0x80u) ? (((uint32_t)crc << 1) ^ 0xD5u) : ((uint32_t)crc << 1));
    }
    return crc;
}
