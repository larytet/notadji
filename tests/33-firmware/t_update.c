// SRC: update.c crashlog.c crc.c sha2.c curve25519.c
// FULLRUN: yes
/* T33-25: A/B update with power cuts, trial boots, rollback, anti-rollback, rejection of bad images */
#include "tcheck.h"
#include "hal_sim.h"
#include "update.h"

static int hexv(char c) { return c >= '0' && c <= '9' ? c - '0' : (c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1); }
static size_t unhex(const char *s, uint8_t *o) { size_t n = 0; while (s[0] && s[1] && s[0] != '\n') { o[n++] = (uint8_t)(hexv(s[0]) * 16 + hexv(s[1])); s += 2; } return n; }

typedef struct { uint8_t *d; size_t n; } blob;
static blob V1, V2, V2B, V3, BADHASH, BADSIG, HUGE_, BADMAGIC;
static uint8_t PK[32];
static bool loaded;

static void load(void)
{
    FILE *f; static char line[30000], tag[24], hex[30000];
    if (loaded) return;
    f = fopen(getenv("VEC") ? getenv("VEC") : "build/vectors.txt", "r");
    CHECK(f != NULL);
    if (!f) return;
    while (fgets(line, sizeof line, f)) {
        blob *b = NULL;
        if (sscanf(line, "%23s %29999s", tag, hex) != 2) continue;
        if (!strcmp(tag, "IMGKEY")) { unhex(hex, PK); continue; }
        if (!strcmp(tag, "IMGV1")) b = &V1; else if (!strcmp(tag, "IMGV2")) b = &V2; else if (!strcmp(tag, "IMGV3")) b = &V3; else if (!strcmp(tag, "IMGV2B")) b = &V2B;
        else if (!strcmp(tag, "IMGBADHASH")) b = &BADHASH; else if (!strcmp(tag, "IMGBADSIG")) b = &BADSIG;
        else if (!strcmp(tag, "IMGHUGE")) b = &HUGE_; else if (!strcmp(tag, "IMGMAGIC")) b = &BADMAGIC;
        if (b) { b->d = (uint8_t *)malloc(strlen(hex) / 2 + 1); b->n = unhex(hex, b->d); }
    }
    fclose(f);
    loaded = true;
}

static hal_sim S;
static clog_t LG;
static upd_t U;

static void provision_v1(void)         /* factory: image in slot 0 and the boot record */
{
    uint32_t off = (2u) * SIM_SECTOR, i;
    hal_sim_init(&S, 1); clog_open(&LG, &S.hal, 0, 4096);
    for (i = 0; i < V1.n; i += SIM_SECTOR) S.hal.fl_erase(&S.hal, off + i);
    S.hal.fl_program(&S.hal, off, V1.d, (uint32_t)V1.n);
    upd_init(&U, &S.hal, &LG, PK);
    CHECK(upd_factory_record(&U));
}

static upd_status send(upd_t *u, const blob *img, bool resume)
{
    upd_status st = upd_begin(u, (uint32_t)img->n, resume);
    uint32_t off;
    if (st != UPD_OK) return st;
    for (off = upd_next_offset(u); off < img->n; ) {
        uint32_t k = (uint32_t)(img->n - off) < UPD_CHUNK_MAX ? (uint32_t)(img->n - off) : UPD_CHUNK_MAX;
        st = upd_chunk(u, off, img->d + off, k);
        if (st != UPD_OK) return st;
        off += k;
    }
    return upd_finish(u);
}

static uint32_t slot_version(int slot)
{
    uint32_t v = 0;
    if (slot < 0) return 0;
    return upd_verify_slot(&U, (uint8_t)slot, &v) == UPD_OK ? v : 0u;
}

TEST(clean_update_trial_and_rollback)
{
    int sel, i;
    load(); provision_v1();
    CHECK_EQ(upd_boot_select(&U), 0);
    CHECK_EQ(send(&U, &V2, false), UPD_OK);
    CHECK_EQ(U.rec.state, BOOT_TRIAL); CHECK_EQ(U.rec.active, 1);
    for (i = 1; i <= 3; i++) { sel = upd_boot_select(&U); CHECK_EQ(sel, 1); CHECK_EQ(U.rec.trial_boots, i); }
    sel = upd_boot_select(&U);                                    /* the fourth start without a confirmation: back to the old image */
    CHECK_EQ(sel, 0); CHECK_EQ(U.rec.state, BOOT_CONFIRMED); CHECK(U.rec.bad_mask & 2u);
    CHECK_EQ(slot_version(sel), 1);
    CHECK_EQ(upd_boot_select(&U), 0);                             /* and it stays there */
    /* a new update may use the slot again */
    CHECK_EQ(send(&U, &V3, false), UPD_OK);
    CHECK_EQ(U.rec.active, 1); CHECK(!(U.rec.bad_mask & 2u));
    CHECK_EQ(slot_version(upd_boot_select(&U)), 3);
}

TEST(confirm_makes_permanent_and_raises_counter)
{
    load(); provision_v1();
    CHECK_EQ(send(&U, &V2, false), UPD_OK);
    CHECK_EQ(upd_boot_select(&U), 1);
    CHECK(upd_confirm(&U));
    CHECK_EQ(U.rec.state, BOOT_CONFIRMED); CHECK_EQ(U.rec.rollback, 2);
    { int i; for (i = 0; i < 10; i++) CHECK_EQ(upd_boot_select(&U), 1); }
    CHECK_EQ(U.rec.trial_boots, 0);
    CHECK(!upd_confirm(&U));                                      /* nothing to confirm */
    /* the old image (version 1) can no longer be installed, a newer one can */
    CHECK_EQ(send(&U, &V2, false), UPD_OK);                       /* the same version is allowed again (the counter is a minimum) */
    CHECK_EQ(upd_boot_select(&U), 0);                             /* slot 0 now holds it as a trial */
    CHECK(upd_confirm(&U));
    CHECK_EQ(send(&U, &V1, false), UPD_ERR_VERSION);
    CHECK_EQ(upd_boot_select(&U), 0);                             /* a refused update changes nothing */
    CHECK_EQ(send(&U, &V3, false), UPD_OK);
}

TEST(bad_images_are_refused)
{
    load(); provision_v1();
    CHECK_EQ(send(&U, &BADHASH, false), UPD_ERR_HASH);
    CHECK_EQ(send(&U, &BADSIG, false), UPD_ERR_SIG);
    CHECK_EQ(send(&U, &HUGE_, false), UPD_ERR_SIZE);
    CHECK_EQ(send(&U, &BADMAGIC, false), UPD_ERR_HDR);
    CHECK_EQ(U.rec.active, 0); CHECK_EQ(U.rec.state, BOOT_CONFIRMED);
    CHECK_EQ(upd_boot_select(&U), 0);
    CHECK_EQ(slot_version(0), 1);
    /* announced size different from the image */
    CHECK_EQ(upd_begin(&U, (uint32_t)V2.n + 100u, false), UPD_OK);
    { uint32_t off; for (off = 0; off < V2.n; off += UPD_CHUNK_MAX) upd_chunk(&U, off, V2.d + off, (V2.n - off) < UPD_CHUNK_MAX ? (uint32_t)(V2.n - off) : UPD_CHUNK_MAX); }
    CHECK_EQ(upd_finish(&U), UPD_ERR_SIZE);                       /* not all announced bytes arrived */
    CHECK_EQ(upd_begin(&U, (uint32_t)V2.n - 100u, false), UPD_OK);
    { uint32_t off; for (off = 0; off < V2.n - 100u; off += UPD_CHUNK_MAX) upd_chunk(&U, off, V2.d + off, ((V2.n - 100u) - off) < UPD_CHUNK_MAX ? (uint32_t)((V2.n - 100u) - off) : UPD_CHUNK_MAX); }
    CHECK_EQ(upd_finish(&U), UPD_ERR_SIZE);                       /* header length and announced size differ */
    CHECK_EQ(upd_boot_select(&U), 0);
}

TEST(chunk_discipline)
{
    uint8_t buf[300] = {0};
    load(); provision_v1();
    CHECK_EQ(upd_chunk(&U, 0, buf, 10), UPD_ERR_STATE);           /* no update started */
    CHECK_EQ(upd_finish(&U), UPD_ERR_STATE);
    CHECK_EQ(upd_begin(&U, 50, false), UPD_ERR_SIZE);             /* smaller than the header */
    CHECK_EQ(upd_begin(&U, 1u << 30, false), UPD_ERR_SIZE);       /* larger than the slot */
    CHECK_EQ(upd_begin(&U, 1000, false), UPD_OK);
    CHECK_EQ(upd_chunk(&U, 10, buf, 10), UPD_ERR_OFFSET);         /* out of order */
    CHECK_EQ(upd_chunk(&U, 0, buf, 257), UPD_ERR_SIZE);
    CHECK_EQ(upd_chunk(&U, 0, buf, 0), UPD_ERR_SIZE);
    CHECK_EQ(upd_chunk(&U, 0, buf, 200), UPD_OK);
    CHECK_EQ(upd_chunk(&U, 200, buf, 100), UPD_OK);
    CHECK_EQ(upd_chunk(&U, 100, buf, 100), UPD_ERR_OFFSET);       /* repeated */
    CHECK_EQ(upd_chunk(&U, 300, buf, 256), UPD_OK);
    CHECK_EQ(upd_chunk(&U, 556, buf, 256), UPD_OK);
    CHECK_EQ(upd_chunk(&U, 812, buf, 256), UPD_ERR_SIZE);         /* beyond the announced end */
    CHECK_EQ(upd_finish(&U), UPD_ERR_SIZE);
}

static bool boot_ok(int sel, uint32_t *ver)
{
    uint32_t v = 0;
    if (sel < 0 || sel > 1) return false;
    if (upd_verify_slot(&U, (uint8_t)sel, &v) != UPD_OK) return false;
    if (ver) *ver = v;
    return true;
}

TEST(power_cut_at_every_flash_operation_of_an_update)
{
    uint32_t n_ops, k, bad = 0, resumed_ok = 0, new_image_at_cut = 0;
    load();
    provision_v1();
    { uint32_t before = S.fl_ops; CHECK_EQ(send(&U, &V2, false), UPD_OK); n_ops = S.fl_ops - before; }
    printf("    a full update is %u flash operations\n", n_ops);
    for (k = 0; k < n_ops + 2u; k++) {
        uint32_t ver = 0; int sel;
        provision_v1();
        S.fl_budget = (int64_t)k;
        (void)send(&U, &V2, false);                                  /* cut somewhere inside */
        hal_sim_power_cycle(&S);
        upd_init(&U, &S.hal, &LG, PK);                               /* a fresh start: everything comes from flash */
        sel = upd_boot_select(&U);
        if (!boot_ok(sel, &ver) || (ver != 1 && ver != 2)) { bad++; continue; }
        if (ver == 2) { new_image_at_cut++; if (U.rec.state != BOOT_TRIAL) bad++; }
        /* resume the update: it completes, whatever the point of the cut */
        if (ver == 1) {
            upd_status st = send(&U, &V2, true);
            if (st != UPD_OK) { bad++; continue; }
            resumed_ok++;
        }
        sel = upd_boot_select(&U);
        if (!boot_ok(sel, &ver) || ver != 2) { bad++; continue; }
        if (!upd_confirm(&U) || U.rec.rollback != 2) bad++;
    }
    CHECK_EQ(bad, 0);
    CHECK(resumed_ok > n_ops / 2);
    printf("    %u cut points: %u resumed to completion, %u had already switched to the new image\n", n_ops + 2u, resumed_ok, new_image_at_cut);
}

TEST(power_cut_during_boot_record_writes)
{
    /* the trial counter, the rollback and the confirmation all write records: cut every one of those writes in turn */
    uint32_t k, bad = 0, steps_total = 0;
    load();
    for (k = 0; k < 40; k++) {
        int i, sel; uint32_t ver;
        provision_v1();
        (void)send(&U, &V2, false);
        S.fl_budget = (int64_t)k; S.fl_ops = 0;
        for (i = 0; i < 4 && !S.fl_cut; i++) (void)upd_boot_select(&U);                  /* trial boots 1, 2, 3 and the rollback */
        steps_total += S.fl_ops;
        hal_sim_power_cycle(&S);
        upd_init(&U, &S.hal, &LG, PK);
        sel = upd_boot_select(&U);
        if (!boot_ok(sel, &ver)) { bad++; continue; }
        if (ver != 1 && ver != 2) bad++;
        /* from here the system must still work: confirm if on the new image, or update again if rolled back */
        if (ver == 2 && U.rec.state == BOOT_TRIAL) { if (!upd_confirm(&U)) bad++; }
        else if (ver == 1) { if (send(&U, &V3, false) != UPD_OK) bad++; }
    }
    CHECK_EQ(bad, 0);
    CHECK(steps_total > 0);
}

TEST(damage_in_flash_is_detected_at_boot)
{
    uint32_t off;
    load(); provision_v1();
    CHECK_EQ(send(&U, &V2, false), UPD_OK); CHECK_EQ(upd_boot_select(&U), 1); CHECK(upd_confirm(&U));
    /* a flipped bit in the active image: hash fails, the other slot (version 1) is started */
    off = (2u + 31u) * SIM_SECTOR + IMG_HDR + 700u; S.flash[off] ^= 0x08u;
    CHECK_EQ(upd_boot_select(&U), 0); CHECK(U.rec.bad_mask & 2u); CHECK_EQ(U.rec.active, 0);
    /* both damaged: no image */
    S.flash[2u * SIM_SECTOR + IMG_HDR + 900u] ^= 0x01u;
    CHECK_EQ(upd_boot_select(&U), -1);
    /* a header whose signature does not verify */
    provision_v1(); CHECK_EQ(send(&U, &V2, false), UPD_OK);
    S.flash[(2u + 31u) * SIM_SECTOR + 70u] ^= 0x02u;
    CHECK_EQ(upd_boot_select(&U), 0);
}

TEST(corrupt_boot_record_falls_back_to_the_previous_one)
{
    load(); provision_v1();
    CHECK_EQ(send(&U, &V2, false), UPD_OK);                       /* newest record: slot 1, trial; the one before it: update session */
    {   uint8_t *newest = S.flash + (U.rec_sector == 0 ? 0u : SIM_SECTOR);
        newest[9] ^= 3u;                                          /* state TRIAL (2) -> CONFIRMED (1): a bit flip in flash */
    }
    CHECK_EQ(upd_boot_select(&U), 0);                             /* the CRC rejects the damaged record, the older one (slot 0) is used */
    CHECK_EQ(U.rec.active, 0);
}

TEST(oversized_image_in_a_slot)
{
    uint32_t v = 0;
    load(); provision_v1();
    { uint32_t off = (2u + 31u) * SIM_SECTOR;
      S.hal.fl_erase(&S.hal, off);
      S.hal.fl_program(&S.hal, off, HUGE_.d, (uint32_t)HUGE_.n); }
    CHECK_EQ(upd_verify_slot(&U, 1, &v), UPD_ERR_SIZE);           /* signed header, length beyond the slot */
}

TEST(finished_session_is_forgotten)
{
    int i;
    load(); provision_v1();
    CHECK_EQ(send(&U, &V2, false), UPD_OK);                       /* slot 1 holds a complete V2 */
    for (i = 0; i < 4; i++) (void)upd_boot_select(&U);            /* three trial boots and the fall back: slot 0 is active again */
    CHECK_EQ(U.rec.active, 0);
    /* a different image of the same size, with a resume request: the old session must not be honoured (its target and size would match) */
    CHECK_EQ(V2B.n, V2.n);
    CHECK_EQ(send(&U, &V2B, true), UPD_OK);
    CHECK_EQ(slot_version(upd_boot_select(&U)), 4);
}

TEST(resume_rules)
{
    uint32_t off;
    load(); provision_v1();
    CHECK_EQ(upd_begin(&U, (uint32_t)V2.n, false), UPD_OK);
    for (off = 0; off < 5000; off += UPD_CHUNK_MAX) CHECK_EQ(upd_chunk(&U, off, V2.d + off, UPD_CHUNK_MAX), UPD_OK);
    upd_init(&U, &S.hal, &LG, PK);                                  /* reset in the middle of the transfer */
    CHECK_EQ(upd_begin(&U, (uint32_t)V2.n, true), UPD_OK);
    CHECK(upd_next_offset(&U) > 0 && upd_next_offset(&U) % SIM_SECTOR == 0 && upd_next_offset(&U) <= 5000u);
    CHECK_EQ(upd_begin(&U, (uint32_t)V2.n - 4, true), UPD_OK);       /* another size: a new session, from the start */
    CHECK_EQ(upd_next_offset(&U), 0);
    CHECK_EQ(upd_begin(&U, (uint32_t)V2.n, false), UPD_OK);          /* resume not asked for: from the start */
    CHECK_EQ(upd_next_offset(&U), 0);
}

int main(void)
{
    RUN(clean_update_trial_and_rollback); RUN(confirm_makes_permanent_and_raises_counter); RUN(bad_images_are_refused); RUN(chunk_discipline);
    RUN(resume_rules); RUN(damage_in_flash_is_detected_at_boot); RUN(corrupt_boot_record_falls_back_to_the_previous_one);
    RUN(oversized_image_in_a_slot); RUN(finished_session_is_forgotten);
    RUN(power_cut_during_boot_record_writes); RUN(power_cut_at_every_flash_operation_of_an_update);
    TC_DONE();
}
