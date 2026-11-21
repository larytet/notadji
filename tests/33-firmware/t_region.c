// SRC: region.c curve25519.c sha2.c
/* T33-24: signed region and entitlement tables and the limiter */
#include "tcheck.h"
#include "region.h"

static int hexv(char c) { return c >= '0' && c <= '9' ? c - '0' : (c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1); }
static size_t unhex(const char *s, uint8_t *o) { size_t n = 0; while (s[0] && s[1] && s[0] != '\n') { o[n++] = (uint8_t)(hexv(s[0]) * 16 + hexv(s[1])); s += 2; } return n; }

static uint8_t PK[32], RGN[REGION_LEN], ENT[REGION_LEN], BAD[REGION_LEN];
static bool loaded;

static void load(void)
{
    FILE *f; static char line[1000], tag[16], hex[900];
    if (loaded) return;
    f = fopen(getenv("VEC") ? getenv("VEC") : "build/vectors.txt", "r");
    CHECK(f != NULL);
    if (!f) return;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%15s %899s", tag, hex) != 2) continue;
        if (!strcmp(tag, "RGNKEY")) unhex(hex, PK);
        else if (!strcmp(tag, "RGN")) unhex(hex, RGN);
        else if (!strcmp(tag, "ENT")) unhex(hex, ENT);
        else if (!strcmp(tag, "RGNBAD")) unhex(hex, BAD);
    }
    fclose(f);
    loaded = true;
}

TEST(valid_tables_and_fields)
{
    region_t r;
    load();
    CHECK_EQ(region_verify(RGN, REGION_LEN, PK, REGION_MAGIC, 5, &r), REGION_OK);
    CHECK_EQ(r.version, 5); CHECK_EQ(r.region_id, 7); CHECK_EQ(r.band_mask, 5); CHECK_EQ(r.dfs, 1); CHECK_EQ(r.dwell_ms, 400); CHECK_EQ(r.n_bands, 3);
    CHECK_EQ(r.max_power_x4[0], 80); CHECK_EQ(r.max_power_x4[2], 92); CHECK_EQ(r.counter, 11);
    CHECK_EQ(region_verify(ENT, REGION_LEN, PK, ENTITLE_MAGIC, 3, &r), REGION_OK);
    CHECK_EQ(r.band_mask, 6);                                    /* option bits */
}

TEST(every_bit_flip_rejected)
{
    uint32_t bad = 0, i, tested = 0;
    uint8_t t[REGION_LEN];
    load();
    for (i = 0; i < REGION_LEN * 8; i++) {
        memcpy(t, RGN, REGION_LEN); t[i / 8] ^= (uint8_t)(1u << (i % 8));
        tested++;
        if (region_verify(t, REGION_LEN, PK, REGION_MAGIC, 0, NULL) == REGION_OK) bad++;
    }
    CHECK_EQ(bad, 0);
    CHECK_EQ(tested, 800);
}

TEST(wrong_key_kind_version_length)
{
    region_t r; uint8_t pk2[32], longer[REGION_LEN + 1];
    load();
    CHECK_EQ(region_verify(BAD, REGION_LEN, PK, REGION_MAGIC, 0, &r), REGION_BAD_SIG);          /* signed by another key */
    memcpy(pk2, PK, 32); pk2[5] ^= 1; CHECK_EQ(region_verify(RGN, REGION_LEN, pk2, REGION_MAGIC, 0, &r), REGION_BAD_SIG);
    CHECK_EQ(region_verify(ENT, REGION_LEN, PK, REGION_MAGIC, 0, &r), REGION_BAD_MAGIC);        /* a valid entitlement table is not a region table */
    CHECK_EQ(region_verify(RGN, REGION_LEN, PK, ENTITLE_MAGIC, 0, &r), REGION_BAD_MAGIC);
    CHECK_EQ(region_verify(RGN, REGION_LEN, PK, REGION_MAGIC, 6, &r), REGION_OLD_VERSION);      /* older than the stored counter */
    CHECK_EQ(region_verify(RGN, REGION_LEN, PK, REGION_MAGIC, 5, &r), REGION_OK);
    CHECK_EQ(region_verify(RGN, REGION_LEN - 1, PK, REGION_MAGIC, 0, &r), REGION_BAD_LEN);
    memcpy(longer, RGN, REGION_LEN); longer[REGION_LEN] = 0;
    CHECK_EQ(region_verify(longer, REGION_LEN + 1, PK, REGION_MAGIC, 0, &r), REGION_BAD_LEN);
    CHECK_EQ(region_verify(RGN, 0, PK, REGION_MAGIC, 0, &r), REGION_BAD_LEN);
}

TEST(limiter)
{
    region_t r; uint32_t i, bad = 0;
    load();
    CHECK_EQ(region_verify(RGN, REGION_LEN, PK, REGION_MAGIC, 0, &r), REGION_OK);
    tc_rs = 123;
    for (i = 0; i < 100000; i++) {
        uint8_t band = (uint8_t)(tc_rand() % 12); int16_t req = (int16_t)((int)(tc_rand() % 400) - 100); int16_t g = region_clamp_power(&r, band, req);
        bool allowed = band < REGION_BANDS && (((uint32_t)r.band_mask >> band) & 1u);
        if (!allowed) { if (g != REGION_NOT_ALLOWED) bad++; continue; }
        if (g > r.max_power_x4[band]) bad++;                          /* never above the signed limit */
        if (g > req) bad++;                                           /* never raised */
        if (req <= r.max_power_x4[band] && g != req) bad++;           /* below the limit: unchanged */
        if (req > r.max_power_x4[band] && g != r.max_power_x4[band]) bad++;
    }
    CHECK_EQ(bad, 0);
    CHECK_EQ(region_clamp_dwell(&r, 1000), 400); CHECK_EQ(region_clamp_dwell(&r, 100), 100); CHECK_EQ(region_clamp_dwell(&r, 400), 400);
    r.dwell_ms = 0; CHECK_EQ(region_clamp_dwell(&r, 1000), 1000);   /* 0: no limit */
}

int main(void) { RUN(valid_tables_and_fields); RUN(every_bit_flip_rejected); RUN(wrong_key_kind_version_length); RUN(limiter); TC_DONE(); }
