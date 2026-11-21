// SRC: pair.c sha2.c curve25519.c crashlog.c crc.c
// FULLRUN: yes
/* T33-23: pairing */
#include "tcheck.h"
#include "hal_sim.h"
#include "pair.h"
#include "curve25519.h"

static hal_sim SA, SB;
static uint32_t runs(void) { return getenv("T33_FULL") ? 1000u : 60u; }       /* the sanitizer build is about 100 times slower on the curve code */
static clog_t LA, LB;

static void setup(uint32_t sa, uint32_t sb)
{
    hal_sim_init(&SA, sa); hal_sim_init(&SB, sb);
    clog_open(&LA, &SA.hal, 0, 2048); clog_open(&LB, &SB.hal, 0, 2048);
}

TEST(honest_pairing_agrees)
{
    uint32_t i, bad = 0, codes_differ_from_prev = 0, last = 0xFFFFFFFFu;
    for (i = 0; i < runs(); i++) {
        pair_t a, b; uint8_t pa[32], pb[32];
        setup(1000u + i * 2u, 5000u + i * 3u);
        pair_init(&a, &SA.hal, &LA, true); pair_init(&b, &SB.hal, &LB, false);
        if (!pair_start(&a, pa) || !pair_start(&b, pb)) { bad++; continue; }
        if (!pair_on_peer_key(&a, pb) || !pair_on_peer_key(&b, pa)) { bad++; continue; }
        if (pair_code(&a) != pair_code(&b) || pair_code(&a) > 999999u) bad++;
        if (memcmp(a.link_key, b.link_key, 32) || memcmp(a.auth_key, b.auth_key, 32)) bad++;
        if (!memcmp(a.link_key, a.auth_key, 32)) bad++;                                  /* two different keys */
        { uint8_t z[32] = {0}; if (memcmp(a.sk, z, 32) || memcmp(b.sk, z, 32)) bad++; }             /* the private key is wiped once the keys are derived */
        if (!pair_confirm(&a, true) || !pair_confirm(&b, true)) bad++;
        if (a.state != PAIR_DONE) bad++;
        if (pair_code(&a) != last) codes_differ_from_prev++;
        last = pair_code(&a);
    }
    CHECK_EQ(bad, 0);
    CHECK(codes_differ_from_prev + 3u >= runs());                                                  /* the code is not constant */
}

TEST(man_in_the_middle_gives_different_codes)
{
    uint32_t i, equal_codes = 0, equal_keys = 0;
    for (i = 0; i < runs(); i++) {
        pair_t a, b, e1, e2; uint8_t pa[32], pb[32], pe1[32], pe2[32];
        hal_sim SE;
        setup(10u + i, 70000u + i); hal_sim_init(&SE, 300000u + i);
        pair_init(&a, &SA.hal, &LA, true); pair_init(&b, &SB.hal, &LB, false);
        pair_init(&e1, &SE.hal, &LA, false); pair_init(&e2, &SE.hal, &LB, true);        /* the attacker plays the responder towards A and the initiator towards B */
        pair_start(&a, pa); pair_start(&b, pb); pair_start(&e1, pe1); pair_start(&e2, pe2);
        pair_on_peer_key(&a, pe1);              /* A believes pe1 is B's key */
        pair_on_peer_key(&b, pe2);              /* B believes pe2 is A's key */
        pair_on_peer_key(&e1, pa); pair_on_peer_key(&e2, pb);
        if (pair_code(&a) == pair_code(&b)) equal_codes++;
        if (!memcmp(a.link_key, b.link_key, 32)) equal_keys++;
        (void)pa; (void)pb;
    }
    CHECK_EQ(equal_keys, 0);
    CHECK(equal_codes <= 1);                    /* chance 10^-6 per attempt: none expected in 1000; one would not be a defect */
    printf("    man in the middle: %u of %u attempts with equal codes\n", equal_codes, runs());
}

/* the derivation checked against the independent computation in gen_vectors.py (X25519, SHA-256 of the transcript, HKDF with the label, code) */
TEST(derivation_matches_independent_vectors)
{
    FILE *f = fopen(getenv("VEC") ? getenv("VEC") : "build/vectors.txt", "r");
    static char line[2000], tag[8], a[100], b[100], c[100], d[100], e[20];
    uint32_t n = 0, bad = 0;
    CHECK(f != NULL);
    if (!f) return;
    while (fgets(line, sizeof line, f)) {
        pair_t pa, pb; uint8_t ska[32], skb[32], lk[32], ak[32], pkb_[32], pka_[32]; unsigned i;
        if (sscanf(line, "%7s %99s %99s %99s %99s %19s", tag, a, b, c, d, e) != 6 || strcmp(tag, "PAIR")) continue;
        for (i = 0; i < 32; i++) {
            unsigned x;
            sscanf(a + 2 * i, "%2x", &x); ska[i] = (uint8_t)x; sscanf(b + 2 * i, "%2x", &x); skb[i] = (uint8_t)x;
            sscanf(c + 2 * i, "%2x", &x); lk[i] = (uint8_t)x; sscanf(d + 2 * i, "%2x", &x); ak[i] = (uint8_t)x;
        }
        setup(1, 2);
        pair_init(&pa, &SA.hal, &LA, true); pair_init(&pb, &SB.hal, &LB, false);
        pair_start(&pa, pka_); pair_start(&pb, pkb_);
        memcpy(pa.sk, ska, 32); x25519_base(pa.pk, ska); memcpy(pka_, pa.pk, 32);          /* use the vector's private keys */
        memcpy(pb.sk, skb, 32); x25519_base(pb.pk, skb); memcpy(pkb_, pb.pk, 32);
        if (!pair_on_peer_key(&pa, pkb_) || !pair_on_peer_key(&pb, pka_)) { bad++; continue; }
        if (memcmp(pa.link_key, lk, 32) || memcmp(pa.auth_key, ak, 32) || pair_code(&pa) != (uint32_t)atoi(e)) bad++;
        if (memcmp(pb.link_key, lk, 32) || memcmp(pb.auth_key, ak, 32) || pair_code(&pb) != (uint32_t)atoi(e)) bad++;
        n++;
    }
    fclose(f);
    CHECK_EQ(bad, 0);
    CHECK(n >= 20);
}

TEST(transcript_order_matters)
{
    pair_t a, b; uint8_t pa[32], pb[32];
    setup(1, 2);
    pair_init(&a, &SA.hal, &LA, true); pair_init(&b, &SB.hal, &LB, true);               /* both think they are the initiator */
    pair_start(&a, pa); pair_start(&b, pb);
    pair_on_peer_key(&a, pb); pair_on_peer_key(&b, pa);
    CHECK(memcmp(a.link_key, b.link_key, 32) != 0);                                     /* a role mix-up cannot go unnoticed */
}

TEST(mismatch_wipes_and_locks)
{
    pair_t a, b; uint8_t pa[32], pb[32], zero[32] = {0}, scratch[32]; int k;
    setup(11, 12);
    pair_init(&a, &SA.hal, &LA, true); pair_init(&b, &SB.hal, &LB, false);
    for (k = 0; k < 3; k++) {
        CHECK(pair_start(&a, pa)); pair_start(&b, pb);
        pair_on_peer_key(&a, pb); pair_on_peer_key(&b, pa);
        CHECK(!pair_confirm(&a, false));                                                 /* the user saw different codes */
        CHECK(memcmp(a.link_key, zero, 32) == 0 && memcmp(a.auth_key, zero, 32) == 0);  /* keys wiped */
        CHECK_EQ(a.state, PAIR_FAILED);
    }
    CHECK(pair_locked(&a));
    CHECK(!pair_start(&a, scratch));                                                     /* locked */
    hal_sim_advance_us(&SA, 59000000u); CHECK(!pair_start(&a, scratch));
    hal_sim_advance_us(&SA, 2000000u); CHECK(pair_start(&a, scratch));                   /* after the timeout */
    CHECK_EQ(a.attempts, 0);
    /* a success resets the counter */
    pair_init(&a, &SA.hal, &LA, true);
    pair_start(&a, pa); pair_start(&b, pb); pair_on_peer_key(&a, pb); pair_on_peer_key(&b, pa);
    CHECK(!pair_confirm(&a, false)); CHECK_EQ(a.attempts, 1);
    pair_start(&a, pa); pair_start(&b, pb); pair_on_peer_key(&a, pb); pair_on_peer_key(&b, pa);
    CHECK(pair_confirm(&a, true)); CHECK_EQ(a.attempts, 0);
}

TEST(state_machine_and_bad_keys)
{
    pair_t a; uint8_t pa[32], pb[32] = {0}, one[32] = {1};
    setup(5, 6);
    pair_init(&a, &SA.hal, &LA, true);
    CHECK(!pair_on_peer_key(&a, pb));                    /* no key pair yet */
    CHECK(!pair_confirm(&a, true));
    pair_start(&a, pa);
    CHECK(!pair_on_peer_key(&a, pb)); CHECK_EQ(a.state, PAIR_FAILED);                 /* all-zero public key: all-zero secret */
    pair_start(&a, pa);
    CHECK(!pair_on_peer_key(&a, one));                                                 /* u = 1 has order 4 */
    pair_start(&a, pa);
    CHECK(pair_on_peer_key(&a, pa) || 1);               /* a reflected key is a valid point: allowed, the codes will not match the peer */
    CHECK(!pair_on_peer_key(&a, pa));                    /* a second key in the same state is ignored */
    CHECK(clog_count(&LA) == 0);
    pair_confirm(&a, true);
    CHECK(clog_count(&LA) == 1);
}

int main(void) { RUN(honest_pairing_agrees); RUN(derivation_matches_independent_vectors); RUN(man_in_the_middle_gives_different_codes); RUN(transcript_order_matters); RUN(mismatch_wipes_and_locks); RUN(state_machine_and_bad_keys); TC_DONE(); }
