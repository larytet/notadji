#include "curve25519.h"
#include "curve25519_k.h"
#include "sha2.h"

typedef int64_t gf[16];

static const gf GF0 = {0}, GF1 = {1}, K121665 = {0xDB41, 1};
static const uint8_t ORDER_L[32] = {
    0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10 };

static void set25519(gf r, const gf a) { int i; for (i = 0; i < 16; i++) r[i] = a[i]; }

static void car25519(gf o)
{
    int i;
    int64_t c;
    for (i = 0; i < 16; i++) {
        o[i] += (int64_t)1 << 16;
        c = o[i] >> 16;
        o[(i + 1) * (i < 15)] += c - 1 + 37 * (c - 1) * (i == 15);
        o[i] -= c * ((int64_t)1 << 16);          /* multiplication: a left shift of a negative value is undefined in C */
    }
}

static void sel25519(gf p, gf q, int b)
{
    int64_t t, c = ~((int64_t)b - 1);
    int i;
    for (i = 0; i < 16; i++) { t = c & (p[i] ^ q[i]); p[i] ^= t; q[i] ^= t; }
}

static void pack25519(uint8_t *o, const gf n)
{
    int i, j, b;
    gf m, t;
    for (i = 0; i < 16; i++) t[i] = n[i];
    car25519(t); car25519(t); car25519(t);
    for (j = 0; j < 2; j++) {
        m[0] = t[0] - 0xffed;
        for (i = 1; i < 15; i++) { m[i] = t[i] - 0xffff - ((m[i - 1] >> 16) & 1); m[i - 1] &= 0xffff; }
        m[15] = t[15] - 0x7fff - ((m[14] >> 16) & 1);
        b = (int)((m[15] >> 16) & 1);
        m[14] &= 0xffff;
        sel25519(t, m, 1 - b);
    }
    for (i = 0; i < 16; i++) { o[2 * i] = (uint8_t)(t[i] & 0xff); o[2 * i + 1] = (uint8_t)(t[i] >> 8); }
}

static int neq25519(const gf a, const gf b)
{
    uint8_t c[32], d[32];
    pack25519(c, a); pack25519(d, b);
    return ct_memcmp(c, d, 32) != 0;
}

static uint8_t par25519(const gf a) { uint8_t d[32]; pack25519(d, a); return (uint8_t)(d[0] & 1u); }

static void unpack25519(gf o, const uint8_t *n)
{
    int i;
    for (i = 0; i < 16; i++) o[i] = n[2 * i] + ((int64_t)n[2 * i + 1] << 8);
    o[15] &= 0x7fff;
}

static void fadd(gf o, const gf a, const gf b) { int i; for (i = 0; i < 16; i++) o[i] = a[i] + b[i]; }
static void fsub(gf o, const gf a, const gf b) { int i; for (i = 0; i < 16; i++) o[i] = a[i] - b[i]; }

static void fmul(gf o, const gf a, const gf b)
{
    int64_t t[31];
    int i, j;
    for (i = 0; i < 31; i++) t[i] = 0;
    for (i = 0; i < 16; i++) for (j = 0; j < 16; j++) t[i + j] += a[i] * b[j];
    for (i = 0; i < 15; i++) t[i] += 38 * t[i + 16];
    for (i = 0; i < 16; i++) o[i] = t[i];
    car25519(o); car25519(o);
}

static void fsqr(gf o, const gf a) { fmul(o, a, a); }

static void inv25519(gf o, const gf in)
{
    gf c;
    int a;
    for (a = 0; a < 16; a++) c[a] = in[a];
    for (a = 253; a >= 0; a--) { fsqr(c, c); if (a != 2 && a != 4) fmul(c, c, in); }
    for (a = 0; a < 16; a++) o[a] = c[a];
}

static void pow2523(gf o, const gf in)
{
    gf c;
    int a;
    for (a = 0; a < 16; a++) c[a] = in[a];
    for (a = 250; a >= 0; a--) { fsqr(c, c); if (a != 1) fmul(c, c, in); }
    for (a = 0; a < 16; a++) o[a] = c[a];
}

/* ---------------- X25519 ---------------- */

void x25519(uint8_t out[32], const uint8_t n[32], const uint8_t p[32])
{
    uint8_t z[32];
    gf x, a, b, c, d, e, f, xr, zr;
    int i, r;
    for (i = 0; i < 31; i++) z[i] = n[i];
    z[31] = (uint8_t)((n[31] & 127u) | 64u);
    z[0] = (uint8_t)(z[0] & 248u);
    unpack25519(x, p);
    for (i = 0; i < 16; i++) { b[i] = x[i]; d[i] = a[i] = c[i] = 0; }
    a[0] = d[0] = 1;
    for (i = 254; i >= 0; --i) {
        r = (z[i >> 3] >> (i & 7)) & 1;
        sel25519(a, b, r); sel25519(c, d, r);
        fadd(e, a, c); fsub(a, a, c); fadd(c, b, d); fsub(b, b, d);
        fsqr(d, e); fsqr(f, a); fmul(a, c, a); fmul(c, b, e);
        fadd(e, a, c); fsub(a, a, c); fsqr(b, a); fsub(c, d, f);
        fmul(a, c, K121665); fadd(a, a, d); fmul(c, c, a); fmul(a, d, f); fmul(d, b, x); fsqr(b, e);
        sel25519(a, b, r); sel25519(c, d, r);
    }
    for (i = 0; i < 16; i++) { xr[i] = a[i]; zr[i] = c[i]; }
    inv25519(zr, zr);
    fmul(xr, xr, zr);
    pack25519(out, xr);
    fw_wipe(z, sizeof z);
}

void x25519_base(uint8_t out[32], const uint8_t n[32])
{
    uint8_t nine[32] = {9};
    x25519(out, n, nine);
}

/* ---------------- Ed25519 verification ---------------- */

static void eadd(gf p[4], gf q[4])
{
    gf a, b, c, d, t, e, f, g, h;
    fsub(a, p[1], p[0]); fsub(t, q[1], q[0]); fmul(a, a, t);
    fadd(b, p[0], p[1]); fadd(t, q[0], q[1]); fmul(b, b, t);
    fmul(c, p[3], q[3]); fmul(c, c, K_D2);
    fmul(d, p[2], q[2]); fadd(d, d, d);
    fsub(e, b, a); fsub(f, d, c); fadd(g, d, c); fadd(h, b, a);
    fmul(p[0], e, f); fmul(p[1], h, g); fmul(p[2], g, f); fmul(p[3], e, h);
}

static void cswap(gf p[4], gf q[4], uint8_t b) { int i; for (i = 0; i < 4; i++) sel25519(p[i], q[i], b); }

static void epack(uint8_t *r, gf p[4])
{
    gf tx, ty, zi;
    inv25519(zi, p[2]); fmul(tx, p[0], zi); fmul(ty, p[1], zi);
    pack25519(r, ty);
    r[31] ^= (uint8_t)(par25519(tx) << 7);
}

static void escalarmult(gf p[4], gf q[4], const uint8_t *s)
{
    int i;
    set25519(p[0], GF0); set25519(p[1], GF1); set25519(p[2], GF1); set25519(p[3], GF0);
    for (i = 255; i >= 0; --i) {
        uint8_t b = (uint8_t)((s[i / 8] >> (i & 7)) & 1);
        cswap(p, q, b);
        eadd(q, p);
        eadd(p, p);
        cswap(p, q, b);
    }
}

static void escalarbase(gf p[4], const uint8_t *s)
{
    gf q[4];
    set25519(q[0], K_X); set25519(q[1], K_Y); set25519(q[2], GF1); fmul(q[3], K_X, K_Y);
    escalarmult(p, q, s);
}

/* decode a point and negate it; -1 if it is not on the curve */
static int unpackneg(gf r[4], const uint8_t p[32])
{
    gf t, chk, num, den, den2, den4, den6;
    set25519(r[2], GF1);
    unpack25519(r[1], p);
    fsqr(num, r[1]); fmul(den, num, K_D); fsub(num, num, r[2]); fadd(den, r[2], den);
    fsqr(den2, den); fsqr(den4, den2); fmul(den6, den4, den2); fmul(t, den6, num); fmul(t, t, den);
    pow2523(t, t); fmul(t, t, num); fmul(t, t, den); fmul(t, t, den); fmul(r[0], t, den);
    fsqr(chk, r[0]); fmul(chk, chk, den);
    if (neq25519(chk, num)) fmul(r[0], r[0], K_I);
    fsqr(chk, r[0]); fmul(chk, chk, den);
    if (neq25519(chk, num)) return -1;
    if (par25519(r[0]) == (p[31] >> 7)) fsub(r[0], GF0, r[0]);
    fmul(r[3], r[0], r[1]);
    return 0;
}

static void modL(uint8_t *r, int64_t x[64])
{
    int64_t carry;
    int i, j;
    for (i = 63; i >= 32; --i) {
        carry = 0;
        for (j = i - 32; j < i - 12; ++j) {
            x[j] += carry - 16 * x[i] * ORDER_L[j - (i - 32)];
            carry = (x[j] + 128) >> 8;
            x[j] -= carry * 256;
        }
        x[j] += carry;
        x[i] = 0;
    }
    carry = 0;
    for (j = 0; j < 32; j++) {
        x[j] += carry - (x[31] >> 4) * ORDER_L[j];
        carry = x[j] >> 8;
        x[j] &= 255;
    }
    for (j = 0; j < 32; j++) x[j] -= carry * ORDER_L[j];
    for (i = 0; i < 32; i++) { x[i + 1] += x[i] >> 8; r[i] = (uint8_t)(x[i] & 255); }
}

static void reduce64(uint8_t r[64])
{
    int64_t x[64];
    int i;
    for (i = 0; i < 64; i++) x[i] = r[i];
    for (i = 0; i < 64; i++) r[i] = 0;
    modL(r, x);
}

/* a >= b for 32-byte little-endian numbers (public data) */
static bool ge_le(const uint8_t *a, const uint8_t *b)
{
    int i;
    for (i = 31; i >= 0; i--) { if (a[i] > b[i]) return true; if (a[i] < b[i]) return false; }
    return true;
}

static bool canonical_y(const uint8_t e[32])           /* the y coordinate (without the sign bit) is below 2^255 - 19 */
{
    static const uint8_t P[32] = { 0xed, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
                                   0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x7f };
    uint8_t y[32];
    memcpy(y, e, 32); y[31] = (uint8_t)(y[31] & 0x7Fu);
    return !ge_le(y, P);
}

/* the public key has small order when 8 A is the identity (x = 0 and y = z) */
static bool small_order(gf negA[4])
{
    gf q[4], zx;
    int i;
    for (i = 0; i < 4; i++) set25519(q[i], negA[i]);
    eadd(q, q); eadd(q, q); eadd(q, q);
    fsub(zx, q[1], q[2]);
    return !neq25519(q[0], GF0) && !neq25519(zx, GF0);
}

bool ed25519_verify(const uint8_t sig[64], const void *msg, size_t n, const uint8_t pk[32])
{
    uint8_t t[32], h[64];
    gf p[4], q[4];
    sha512_t c;
    if (ge_le(sig + 32, ORDER_L)) return false;                       /* S must be below the group order */
    if (!canonical_y(sig) || !canonical_y(pk)) return false;
    if (unpackneg(q, pk)) return false;
    if (small_order(q)) return false;
    sha512_init(&c); sha512_update(&c, sig, 32); sha512_update(&c, pk, 32); sha512_update(&c, msg, n); sha512_final(&c, h);
    reduce64(h);
    escalarmult(p, q, h);
    escalarbase(q, sig + 32);
    eadd(p, q);
    epack(t, p);
    return ct_memcmp(sig, t, 32) == 0;
}
