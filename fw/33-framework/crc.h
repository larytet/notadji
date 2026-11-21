/* crc - checksums used by the firmware: CRC-32 (IEEE, crash log), CRC-16/MCRF4XX (MAVLink, feedback message), CRC-8/DVB-S2 (MSP v2). */
#ifndef CRC_H
#define CRC_H

#include "fw_types.h"

uint32_t crc32_ieee(const void *data, size_t n);                          /* init 0xFFFFFFFF, reflected, xorout 0xFFFFFFFF; check "123456789" = 0xCBF43926 */
uint16_t crc16_mcrf4xx_update(uint16_t crc, const void *data, size_t n);  /* poly 0x1021 reflected, no final xor; start with 0xFFFF; check = 0x6F91 */
static inline uint16_t crc16_mcrf4xx(const void *d, size_t n) { return crc16_mcrf4xx_update(0xFFFFu, d, n); }
uint8_t  crc8_dvb_s2_update(uint8_t crc, const void *data, size_t n);     /* poly 0xD5, init 0; check = 0xBC */
static inline uint8_t crc8_dvb_s2(const void *d, size_t n) { return crc8_dvb_s2_update(0, d, n); }

#endif
