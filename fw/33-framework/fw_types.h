/* fw_types - common types and rules of the firmware framework (design/33-firmware-framework.md section 1).
 * LP64 clean: fixed-width types only, no long, no pointer-to-integer casts. No heap. */
#ifndef FW_TYPES_H
#define FW_TYPES_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#ifdef FW_NO_LIBC_HEADERS
/* freestanding target build: the platform provides these four (the only libc symbols the framework uses) */
void *memcpy(void *d, const void *s, size_t n);
void *memmove(void *d, const void *s, size_t n);
void *memset(void *d, int c, size_t n);
int memcmp(const void *a, const void *b, size_t n);
#else
#include <string.h>
#endif

#define FW_ARRAY_LEN(a) (sizeof(a) / sizeof((a)[0]))
#define FW_STATIC_ASSERT(c, m) _Static_assert(c, m)

FW_STATIC_ASSERT(sizeof(uint64_t) == 8, "64-bit counters");
FW_STATIC_ASSERT(sizeof(void *) == 8, "the framework targets 64-bit cores (AArch64, LP64)");

/* little-endian byte access for wire and retained-memory formats (no struct overlay) */
static inline uint16_t fw_ld16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static inline uint32_t fw_ld32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static inline void fw_st16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static inline void fw_st32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

/* wrap-safe difference of two 32-bit microsecond stamps, as signed */
static inline int32_t fw_tdiff32(uint32_t a, uint32_t b) { return (int32_t)(a - b); }

#endif
