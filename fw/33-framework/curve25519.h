/* curve25519 - X25519 (RFC 7748) and Ed25519 signature verification (RFC 8032) on the 16-limb field representation of TweetNaCl (R33-11).
 * X25519 has no secret-dependent branch or table index. Ed25519 verification handles public data only; it additionally rejects a non-canonical
 * S (S >= L), non-canonical point encodings and small-order public keys. */
#ifndef CURVE25519_H
#define CURVE25519_H

#include "fw_types.h"

void x25519(uint8_t out[32], const uint8_t scalar[32], const uint8_t point[32]);
void x25519_base(uint8_t out[32], const uint8_t scalar[32]);
/* true if the 64-byte signature is valid for msg under the 32-byte public key */
bool ed25519_verify(const uint8_t sig[64], const void *msg, size_t n, const uint8_t pk[32]);

#endif
