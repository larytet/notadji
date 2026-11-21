#include "sha2.h"
#include "sha2_k.h"

#define ROR32(x, n) (((x) >> (n)) | ((x) << (32 - (n))))
#define ROR64(x, n) (((x) >> (n)) | ((x) << (64 - (n))))

static void sha256_block(sha256_t *c, const uint8_t *p)
{
    uint32_t w[64], a, b, cc, d, e, f, g, h, t1, t2;
    uint32_t i;
    for (i = 0; i < 16; i++) w[i] = ((uint32_t)p[4 * i] << 24) | ((uint32_t)p[4 * i + 1] << 16) | ((uint32_t)p[4 * i + 2] << 8) | p[4 * i + 3];
    for (i = 16; i < 64; i++) {
        uint32_t s0 = ROR32(w[i - 15], 7) ^ ROR32(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = ROR32(w[i - 2], 17) ^ ROR32(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    a = c->h[0]; b = c->h[1]; cc = c->h[2]; d = c->h[3]; e = c->h[4]; f = c->h[5]; g = c->h[6]; h = c->h[7];
    for (i = 0; i < 64; i++) {
        t1 = h + (ROR32(e, 6) ^ ROR32(e, 11) ^ ROR32(e, 25)) + ((e & f) ^ (~e & g)) + sha256_k[i] + w[i];
        t2 = (ROR32(a, 2) ^ ROR32(a, 13) ^ ROR32(a, 22)) + ((a & b) ^ (a & cc) ^ (b & cc));
        h = g; g = f; f = e; e = d + t1; d = cc; cc = b; b = a; a = t1 + t2;
    }
    c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d; c->h[4] += e; c->h[5] += f; c->h[6] += g; c->h[7] += h;
}

void sha256_init(sha256_t *c)
{
    uint32_t i;
    for (i = 0; i < 8; i++) c->h[i] = sha256_h0[i];
    c->len = 0; c->n = 0;
}

void sha256_update(sha256_t *c, const void *d, size_t n)
{
    const uint8_t *p = (const uint8_t *)d;
    c->len += n;
    while (n) {
        size_t k = 64u - c->n;
        if (k > n) k = n;
        memcpy(c->buf + c->n, p, k);
        c->n += (uint32_t)k; p += k; n -= k;
        if (c->n == 64u) { sha256_block(c, c->buf); c->n = 0; }
    }
}

void sha256_final(sha256_t *c, uint8_t out[32])
{
    uint64_t bits = c->len * 8u;
    uint8_t pad = 0x80u, z = 0, lenb[8];
    uint32_t i;
    sha256_update(c, &pad, 1);
    while (c->n != 56u) sha256_update(c, &z, 1);
    for (i = 0; i < 8; i++) lenb[i] = (uint8_t)(bits >> (56 - 8 * i));
    sha256_update(c, lenb, 8);
    for (i = 0; i < 8; i++) { out[4 * i] = (uint8_t)(c->h[i] >> 24); out[4 * i + 1] = (uint8_t)(c->h[i] >> 16); out[4 * i + 2] = (uint8_t)(c->h[i] >> 8); out[4 * i + 3] = (uint8_t)c->h[i]; }
    fw_wipe(c, sizeof *c);
}

void sha256(const void *d, size_t n, uint8_t out[32]) { sha256_t c; sha256_init(&c); sha256_update(&c, d, n); sha256_final(&c, out); }

static void sha512_block(sha512_t *c, const uint8_t *p)
{
    uint64_t w[80], a, b, cc, d, e, f, g, h, t1, t2;
    uint32_t i, k;
    for (i = 0; i < 16; i++) { w[i] = 0; for (k = 0; k < 8; k++) w[i] = (w[i] << 8) | p[8 * i + k]; }
    for (i = 16; i < 80; i++) {
        uint64_t s0 = ROR64(w[i - 15], 1) ^ ROR64(w[i - 15], 8) ^ (w[i - 15] >> 7);
        uint64_t s1 = ROR64(w[i - 2], 19) ^ ROR64(w[i - 2], 61) ^ (w[i - 2] >> 6);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    a = c->h[0]; b = c->h[1]; cc = c->h[2]; d = c->h[3]; e = c->h[4]; f = c->h[5]; g = c->h[6]; h = c->h[7];
    for (i = 0; i < 80; i++) {
        t1 = h + (ROR64(e, 14) ^ ROR64(e, 18) ^ ROR64(e, 41)) + ((e & f) ^ (~e & g)) + sha512_k[i] + w[i];
        t2 = (ROR64(a, 28) ^ ROR64(a, 34) ^ ROR64(a, 39)) + ((a & b) ^ (a & cc) ^ (b & cc));
        h = g; g = f; f = e; e = d + t1; d = cc; cc = b; b = a; a = t1 + t2;
    }
    c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d; c->h[4] += e; c->h[5] += f; c->h[6] += g; c->h[7] += h;
}

void sha512_init(sha512_t *c)
{
    uint32_t i;
    for (i = 0; i < 8; i++) c->h[i] = sha512_h0[i];
    c->len = 0; c->n = 0;
}

void sha512_update(sha512_t *c, const void *d, size_t n)
{
    const uint8_t *p = (const uint8_t *)d;
    c->len += n;
    while (n) {
        size_t k = 128u - c->n;
        if (k > n) k = n;
        memcpy(c->buf + c->n, p, k);
        c->n += (uint32_t)k; p += k; n -= k;
        if (c->n == 128u) { sha512_block(c, c->buf); c->n = 0; }
    }
}

void sha512_final(sha512_t *c, uint8_t out[64])
{
    uint64_t bits = c->len * 8u;                       /* messages are far below 2^61 bytes: the upper 64 length bits are zero */
    uint8_t pad = 0x80u, z = 0, lenb[16];
    uint32_t i, k;
    sha512_update(c, &pad, 1);
    while (c->n != 112u) sha512_update(c, &z, 1);
    memset(lenb, 0, 8);
    for (i = 0; i < 8; i++) lenb[8 + i] = (uint8_t)(bits >> (56 - 8 * i));
    sha512_update(c, lenb, 16);
    for (i = 0; i < 8; i++) for (k = 0; k < 8; k++) out[8 * i + k] = (uint8_t)(c->h[i] >> (56 - 8 * k));
    fw_wipe(c, sizeof *c);
}

void sha512(const void *d, size_t n, uint8_t out[64]) { sha512_t c; sha512_init(&c); sha512_update(&c, d, n); sha512_final(&c, out); }

void hmac_sha256(const void *key, size_t klen, const void *msg, size_t mlen, uint8_t out[32])
{
    uint8_t k[64], pad[64], inner[32];
    sha256_t c;
    uint32_t i;
    memset(k, 0, sizeof k);
    if (klen > 64u) sha256(key, klen, k); else memcpy(k, key, klen);
    for (i = 0; i < 64; i++) pad[i] = (uint8_t)(k[i] ^ 0x36u);
    sha256_init(&c); sha256_update(&c, pad, 64); sha256_update(&c, msg, mlen); sha256_final(&c, inner);
    for (i = 0; i < 64; i++) pad[i] = (uint8_t)(k[i] ^ 0x5Cu);
    sha256_init(&c); sha256_update(&c, pad, 64); sha256_update(&c, inner, 32); sha256_final(&c, out);
    fw_wipe(k, sizeof k); fw_wipe(pad, sizeof pad); fw_wipe(inner, sizeof inner);
}

bool hkdf_sha256(const void *salt, size_t slen, const void *ikm, size_t ilen, const void *info, size_t infolen, uint8_t *okm, size_t olen)
{
    uint8_t prk[32], t[32], zero[32], buf[32 + 128 + 1];
    size_t done = 0, tl = 0;
    uint8_t ctr = 1;
    if (olen > 255u * 32u || infolen > 128u) return false;
    if (salt == NULL || slen == 0) { memset(zero, 0, sizeof zero); hmac_sha256(zero, 32, ikm, ilen, prk); }
    else hmac_sha256(salt, slen, ikm, ilen, prk);
    while (done < olen) {
        size_t k, m = 0;
        memcpy(buf, t, tl); m = tl;
        memcpy(buf + m, info, infolen); m += infolen;
        buf[m++] = ctr++;
        hmac_sha256(prk, 32, buf, m, t); tl = 32;
        k = olen - done < 32u ? olen - done : 32u;
        memcpy(okm + done, t, k); done += k;
    }
    fw_wipe(prk, sizeof prk); fw_wipe(t, sizeof t); fw_wipe(buf, sizeof buf);
    return true;
}

int ct_memcmp(const void *a, const void *b, size_t n)
{
    const uint8_t *x = (const uint8_t *)a, *y = (const uint8_t *)b;
    uint8_t d = 0;
    size_t i;
    for (i = 0; i < n; i++) d |= (uint8_t)(x[i] ^ y[i]);
    return d;
}

void fw_wipe(void *p, size_t n)
{
    volatile uint8_t *v = (volatile uint8_t *)p;
    while (n--) *v++ = 0;
}
