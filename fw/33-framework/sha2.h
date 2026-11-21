/* sha2 - SHA-256, SHA-512, HMAC-SHA256 and HKDF-SHA256 (R33-11). No heap, no secrets-dependent branches in the hash round functions. */
#ifndef SHA2_H
#define SHA2_H

#include "fw_types.h"

typedef struct { uint32_t h[8]; uint8_t buf[64]; uint64_t len; uint32_t n; } sha256_t;
typedef struct { uint64_t h[8]; uint8_t buf[128]; uint64_t len; uint32_t n; } sha512_t;

void sha256_init(sha256_t *c);
void sha256_update(sha256_t *c, const void *d, size_t n);
void sha256_final(sha256_t *c, uint8_t out[32]);
void sha256(const void *d, size_t n, uint8_t out[32]);

void sha512_init(sha512_t *c);
void sha512_update(sha512_t *c, const void *d, size_t n);
void sha512_final(sha512_t *c, uint8_t out[64]);
void sha512(const void *d, size_t n, uint8_t out[64]);

void hmac_sha256(const void *key, size_t klen, const void *msg, size_t mlen, uint8_t out[32]);
/* RFC 5869; returns false if olen > 255 * 32 */
bool hkdf_sha256(const void *salt, size_t slen, const void *ikm, size_t ilen, const void *info, size_t infolen, uint8_t *okm, size_t olen);

/* constant-time comparison: 0 if equal */
int ct_memcmp(const void *a, const void *b, size_t n);
void fw_wipe(void *p, size_t n);

#endif
