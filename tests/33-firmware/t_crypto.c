// FULLRUN: yes
// SRC: sha2.c curve25519.c
/* T33-20, T33-21, T33-22: SHA-2, HMAC, HKDF, X25519, Ed25519 verification */
#include "tcheck.h"
#include "sha2.h"
#include "curve25519.h"

static int hexv(char c) { return c >= '0' && c <= '9' ? c - '0' : (c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1); }
static size_t unhex(const char *s, uint8_t *o)
{
    size_t n = 0;
    if (s[0] == '-' && s[1] == 0) return 0;
    while (s[0] && s[1]) { o[n++] = (uint8_t)(hexv(s[0]) * 16 + hexv(s[1])); s += 2; }
    return n;
}
static void H(const char *s, uint8_t *o) { unhex(s, o); }

TEST(known_answers)
{
    uint8_t d[64], e[64];
    sha256("abc", 3, d); H("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", e); CHECK(memcmp(d, e, 32) == 0);
    sha512("abc", 3, d); H("ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f", e);
    CHECK(memcmp(d, e, 64) == 0);
    sha256("", 0, d); H("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", e); CHECK(memcmp(d, e, 32) == 0);
    { uint8_t key[20], mac[32]; memset(key, 0x0b, 20); hmac_sha256(key, 20, "Hi There", 8, mac);
      H("b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7", e); CHECK(memcmp(mac, e, 32) == 0); }
    { uint8_t ikm[22], salt[13], info[10], okm[42], want[42]; int i;
      memset(ikm, 0x0b, 22); for (i = 0; i < 13; i++) salt[i] = (uint8_t)i; for (i = 0; i < 10; i++) info[i] = (uint8_t)(0xf0 + i);
      CHECK(hkdf_sha256(salt, 13, ikm, 22, info, 10, okm, 42));
      H("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865", want); CHECK(memcmp(okm, want, 42) == 0); }
    { uint8_t big[255 * 32 + 1]; CHECK(!hkdf_sha256(NULL, 0, "k", 1, "i", 1, big, sizeof big)); }
}

TEST(vectors_from_file)
{
    FILE *f = fopen(getenv("VEC") ? getenv("VEC") : "build/vectors.txt", "r");
    static char line[20000], t[16], a[6000], b[6000], c[6000], d[6000], e[20000];
    uint32_t n[8] = {0}, bad = 0;
    CHECK(f != NULL);
    if (!f) return;
    while (fgets(line, sizeof line, f)) {
        static uint8_t m[4000], x[4000], y[4000], z[9000], out[9000];
        size_t lm, lx, ly;
        int k = sscanf(line, "%15s %5999s %5999s %5999s %5999s %19999s", t, a, b, c, d, e);
        if (k < 3) continue;
        if (!strcmp(t, "S256")) {
            lm = unhex(a, m); sha256(m, lm, out); unhex(b, x); { if (memcmp(out, x, 32)) bad++; }
            n[0]++;
        } else if (!strcmp(t, "S512")) {
            lm = unhex(a, m); sha512(m, lm, out); unhex(b, x); { if (memcmp(out, x, 64)) bad++; }
            n[1]++;
        } else if (!strcmp(t, "HMAC")) {
            lx = unhex(a, x); lm = unhex(b, m); hmac_sha256(x, lx, m, lm, out); unhex(c, y); { if (memcmp(out, y, 32)) bad++; }
            n[2]++;
        } else if (!strcmp(t, "HKDF")) {
            size_t ls = unhex(a, x), li = unhex(b, m), lf = unhex(c, y), L = (size_t)atoi(d), lo;
            lo = unhex(e, z);
            { if (lo != L || !hkdf_sha256(x, ls, m, li, y, lf, out, L) || memcmp(out, z, L)) bad++; }
            n[3]++;
        } else if (!strcmp(t, "X25519")) {
            uint8_t kk[32], uu[32], want[32]; unhex(a, kk); unhex(b, uu); unhex(c, want);
            x25519(out, kk, uu); { if (memcmp(out, want, 32)) bad++; }
            n[4]++;
        } else if (!strcmp(t, "X25519B")) {
            uint8_t kk[32], want[32]; unhex(a, kk); unhex(b, want);
            x25519_base(out, kk); { if (memcmp(out, want, 32)) bad++; }
            n[5]++;
        } else if (!strcmp(t, "ED")) {
            uint8_t pk[32], sig[64]; lm = unhex(b, m); unhex(a, pk); unhex(c, sig);
            if (!ed25519_verify(sig, m, lm, pk)) bad++;
            n[6]++;
        }
        (void)ly;
    }
    fclose(f);
    CHECK_EQ(bad, 0);
    printf("    vectors: sha256 %u, sha512 %u, hmac %u, hkdf %u, x25519 %u + %u, ed25519 %u\n", n[0], n[1], n[2], n[3], n[4], n[5], n[6]);
    CHECK(n[0] > 100 && n[1] > 100 && n[2] > 300 && n[3] > 150 && n[4] > 400 && n[5] > 150 && n[6] >= 100);
}

TEST(incremental_every_split)
{
    uint8_t m[300], d1[64], d2[64]; size_t i, j;
    for (i = 0; i < sizeof m; i++) m[i] = (uint8_t)(i * 31 + 7);
    sha256(m, 300, d1); { sha512_t dummy; (void)dummy; }
    for (i = 0; i <= 300; i += 1) {
        sha256_t c; sha256_init(&c); sha256_update(&c, m, i); sha256_update(&c, m + i, 300 - i); sha256_final(&c, d2);
        if (memcmp(d1, d2, 32)) { CHECK(0); return; }
    }
    sha512(m, 300, d1);
    for (i = 0; i <= 300; i += 1) {
        sha512_t c; sha512_init(&c); sha512_update(&c, m, i); sha512_update(&c, m + i, 300 - i); sha512_final(&c, d2);
        if (memcmp(d1, d2, 64)) { CHECK(0); return; }
    }
    /* three-way splits at random places and byte-wise */
    for (j = 0; j < 500; j++) {
        size_t a = (size_t)(tc_rand() % 301), b = a + (size_t)(tc_rand() % (301 - a));
        sha256_t c; sha256_init(&c); sha256_update(&c, m, a); sha256_update(&c, m + a, b - a); sha256_update(&c, m + b, 300 - b); sha256_final(&c, d2);
        sha256(m, 300, d1);
        if (memcmp(d1, d2, 32)) { CHECK(0); return; }
    }
    { sha256_t c; sha256_init(&c); for (i = 0; i < 300; i++) sha256_update(&c, m + i, 1); sha256_final(&c, d2); sha256(m, 300, d1); CHECK(memcmp(d1, d2, 32) == 0); }
    CHECK(1);
}

TEST(x25519_rfc7748)
{
    uint8_t a[32], b[32], pa[32], pb[32], s1[32], s2[32], w[32], nine[32] = {9}, k[32], u[32], r[32];
    int i;
    H("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a", a);
    H("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb", b);
    x25519(pa, a, nine); x25519(pb, b, nine);
    H("8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a", w); CHECK(memcmp(pa, w, 32) == 0);
    H("de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f", w); CHECK(memcmp(pb, w, 32) == 0);
    x25519(s1, a, pb); x25519(s2, b, pa);
    H("4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742", w); CHECK(memcmp(s1, w, 32) == 0); CHECK(memcmp(s2, w, 32) == 0);
    memcpy(k, nine, 32); memcpy(u, nine, 32);
    for (i = 1; i <= 1000; i++) {
        x25519(r, k, u); memcpy(u, k, 32); memcpy(k, r, 32);
        if (i == 1) { H("422c8e7a6227d7bca1350b3e2bb7279f7897b87bb6854b783c60e80311ae3079", w); CHECK(memcmp(k, w, 32) == 0); }
    }
    H("684cf59ba83309552800ef566f2f4d3c1c3887c49360e3875f2eb94d99532c51", w); CHECK(memcmp(k, w, 32) == 0);
}

TEST(ed25519_rfc8032)
{
    uint8_t pk[32], sig[64], msg[1];
    H("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", pk);
    H("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b", sig);
    CHECK(ed25519_verify(sig, "", 0, pk));
    H("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", pk);
    H("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00", sig);
    msg[0] = 0x72;
    CHECK(ed25519_verify(sig, msg, 1, pk));
    msg[0] = 0x73; CHECK(!ed25519_verify(sig, msg, 1, pk));
}

/* Every bit of signature, key and message is flipped in the full run (T33_FULL set, plain -O2 build: 5 signatures, about 4,500 flips, a few seconds).
 * The sanitizer build samples 40 random bits of each part, because verification is about 100 times slower there. */
TEST(ed25519_every_bit_flip_rejected)
{
    FILE *f = fopen(getenv("VEC") ? getenv("VEC") : "build/vectors.txt", "r");
    static char line[20000], t[16], a[200], b[3000], c[200];
    uint32_t cases = 0, flips = 0, accepted = 0;
    bool full = getenv("T33_FULL") != NULL;
    CHECK(f != NULL);
    if (!f) return;
    while (cases < (full ? 6u : 2u) && fgets(line, sizeof line, f)) {
        uint8_t pk[32], sig[64], m[1100]; size_t lm; int i, k, n;
        if (sscanf(line, "%15s %199s %2999s %199s", t, a, b, c) < 4 || strcmp(t, "ED")) continue;
        lm = unhex(b, m); unhex(a, pk); unhex(c, sig);
        if (lm > 40) continue;                                    /* short messages: all message bits are flipped as well */
        CHECK(ed25519_verify(sig, m, lm, pk));
        n = full ? 512 : 40;
        for (k = 0; k < n; k++) { i = full ? k : (int)(tc_rand() % 512); sig[i / 8] ^= (uint8_t)(1u << (i % 8)); flips++; if (ed25519_verify(sig, m, lm, pk)) accepted++; sig[i / 8] ^= (uint8_t)(1u << (i % 8)); }
        n = full ? 256 : 40;
        for (k = 0; k < n; k++) { i = full ? k : (int)(tc_rand() % 256); pk[i / 8] ^= (uint8_t)(1u << (i % 8)); flips++; if (ed25519_verify(sig, m, lm, pk)) accepted++; pk[i / 8] ^= (uint8_t)(1u << (i % 8)); }
        n = full ? (int)(lm * 8) : (lm ? 40 : 0);
        for (k = 0; k < n; k++) { i = full ? k : (int)(tc_rand() % (lm * 8)); m[i / 8] ^= (uint8_t)(1u << (i % 8)); flips++; if (ed25519_verify(sig, m, lm, pk)) accepted++; m[i / 8] ^= (uint8_t)(1u << (i % 8)); }
        cases++;
    }
    fclose(f);
    CHECK_EQ(accepted, 0);
    CHECK(cases >= 2);
    if (full) CHECK(cases >= 6 && flips >= 4096);
    printf("    %u single-bit flips over %u signatures%s: %u accepted\n", flips, cases, full ? " (all bits)" : " (sampled)", accepted);
}

TEST(ed25519_strictness)
{
    uint8_t pk[32], sig[64], bad[64], msg[1] = {0x72};
    static const uint8_t Lc[32] = { 0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14,
                                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10 };
    unsigned i, carry = 0;
    H("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", pk);
    H("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00", sig);
    CHECK(ed25519_verify(sig, msg, 1, pk));
    /* S + L is the same number modulo the group order: a lax verifier accepts it, this one must not */
    memcpy(bad, sig, 64);
    for (i = 0; i < 32; i++) { unsigned v = bad[32 + i] + Lc[i] + carry; bad[32 + i] = (uint8_t)v; carry = v >> 8; }
    if (carry == 0) CHECK(!ed25519_verify(bad, msg, 1, pk)); else CHECK(1);      /* (S of this vector is small: no overflow) */
    /* the classic forgery against non-strict verifiers: identity public key, R = identity, S = 0, any message */
    { uint8_t idpk[32] = {1}, forged[64] = {1}; CHECK(!ed25519_verify(forged, "anything", 8, idpk)); }
    /* small-order encodings as public keys: y = 0 (order 4), y = -1 (order 2), the order-8 points */
    {
        const char *so[] = {
            "0000000000000000000000000000000000000000000000000000000000000000",
            "0000000000000000000000000000000000000000000000000000000000000080",
            "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
            "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
            "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a" };
        unsigned k;
        for (k = 0; k < 5; k++) {
            uint8_t spk[32], fsig[64]; H(so[k], spk); memset(fsig, 0, 64); fsig[0] = 1;
            CHECK(!ed25519_verify(fsig, "x", 1, spk));
            memcpy(fsig, sig, 64); CHECK(!ed25519_verify(fsig, "x", 1, spk));
        }
    }
    /* non-canonical encodings: y >= p in the public key or in R */
    { uint8_t npk[32]; memset(npk, 0xff, 32); npk[31] = 0x7f; npk[0] = 0xee; CHECK(!ed25519_verify(sig, msg, 1, npk));
      memcpy(bad, sig, 64); memset(bad, 0xff, 32); bad[31] = 0x7f; CHECK(!ed25519_verify(bad, msg, 1, pk)); }
    /* short or empty input */
    CHECK(!ed25519_verify(sig, NULL, 0, pk));
}

TEST(x25519_clamping_and_base)
{
    uint8_t k[32], k2[32], p1[32], p2[32], u[32];
    int i;
    for (i = 0; i < 100; i++) {
        int j;
        for (j = 0; j < 32; j++) { k[j] = (uint8_t)tc_rand(); u[j] = (uint8_t)tc_rand(); }
        memcpy(k2, k, 32); k2[0] = (uint8_t)(k2[0] ^ 7u); k2[31] = (uint8_t)(k2[31] ^ 0x80u);      /* bits cleared by the clamping */
        x25519(p1, k, u); x25519(p2, k2, u);
        if (memcmp(p1, p2, 32)) { CHECK(0); return; }
    }
    CHECK(1);
}

int main(void)
{
    RUN(known_answers); RUN(vectors_from_file); RUN(incremental_every_split); RUN(x25519_rfc7748); RUN(ed25519_rfc8032);
    RUN(ed25519_strictness); RUN(x25519_clamping_and_base); RUN(ed25519_every_bit_flip_rejected);
    TC_DONE();
}
