// SRC: hostproto.c crc.c
/* T33-19: MAVLink 2 and MSP v1/v2 framing from a DMA ring */
#include "tcheck.h"
#include "hostproto.h"

/* bitwise reference CRCs, independent of crc.c */
static uint16_t rc16(uint16_t c, const uint8_t *p, size_t n)       /* X.25 / MCRF4XX */
{
    size_t i; int k;
    for (i = 0; i < n; i++) { c = (uint16_t)(c ^ p[i]); for (k = 0; k < 8; k++) c = (uint16_t)((c & 1) ? (c >> 1) ^ 0x8408 : c >> 1); }
    return c;
}
static uint8_t rc8(const uint8_t *p, size_t n)
{
    size_t i; int k; uint8_t c = 0;
    for (i = 0; i < n; i++) { c ^= p[i]; for (k = 0; k < 8; k++) c = (uint8_t)((c & 0x80) ? (c << 1) ^ 0xD5 : c << 1); }
    return c;
}

static int extra_of(uint32_t id)            /* known messages: ids 0..299 with a CRC extra derived from the id; others unknown */
{
    if (id < 300 || id == 0x10203u) return (int)((id * 37u + 11u) & 0xFFu);
    return -1;
}

static uint32_t mk_mav(uint8_t *o, uint8_t seq, uint32_t id, const uint8_t *pl, uint8_t len, uint8_t incompat)
{
    uint32_t n = 0, k; uint16_t c;
    o[n++] = 0xFD; o[n++] = len; o[n++] = incompat; o[n++] = 0; o[n++] = seq; o[n++] = 1; o[n++] = 200;
    o[n++] = (uint8_t)id; o[n++] = (uint8_t)(id >> 8); o[n++] = (uint8_t)(id >> 16);
    for (k = 0; k < len; k++) o[n++] = pl[k];
    c = rc16(0xFFFF, o + 1, n - 1);
    { uint8_t e = (uint8_t)extra_of(id); c = rc16(c, &e, 1); }
    o[n++] = (uint8_t)c; o[n++] = (uint8_t)(c >> 8);
    if (incompat & 1) for (k = 0; k < 13; k++) o[n++] = (uint8_t)(0xA0 + k);
    return n;
}
static uint32_t mk_msp1(uint8_t *o, uint8_t dir, uint8_t cmd, const uint8_t *pl, uint8_t len)
{
    uint32_t n = 0, k; uint8_t x;
    o[n++] = '$'; o[n++] = 'M'; o[n++] = dir; o[n++] = len; o[n++] = cmd;
    for (k = 0; k < len; k++) o[n++] = pl[k];
    x = rc8(NULL, 0); for (k = 3; k < n; k++) x ^= o[k];
    o[n++] = x;
    return n;
}
static uint32_t mk_msp2(uint8_t *o, uint8_t dir, uint8_t flag, uint16_t cmd, const uint8_t *pl, uint16_t len)
{
    uint32_t n = 0, k;
    o[n++] = '$'; o[n++] = 'X'; o[n++] = dir; o[n++] = flag; o[n++] = (uint8_t)cmd; o[n++] = (uint8_t)(cmd >> 8); o[n++] = (uint8_t)len; o[n++] = (uint8_t)(len >> 8);
    for (k = 0; k < len; k++) o[n++] = pl[k];
    o[n] = rc8(o + 3, n - 3); n++;
    return n;
}

typedef struct { uint8_t proto, dir; uint32_t id; uint16_t len; uint8_t pl[255]; uint8_t seq, flags; } want_t;

static spsc_t RING, OUTQ;
static uint8_t ringbuf[65536];
static hp_frame outbuf[16];
static hp_t H;

static void setup(void)
{
    spsc_init(&RING, ringbuf, 65536, 1);
    spsc_init(&OUTQ, outbuf, 16, sizeof(hp_frame));
    hp_init(&H, extra_of, &OUTQ);
}
static void feed(const uint8_t *b, uint32_t n) { uint32_t i; for (i = 0; i < n; i++) CHECK(spsc_push(&RING, &b[i])); }

TEST(encoders_agree_with_reference)
{
    int k;
    for (k = 0; k < 2000; k++) {
        uint8_t pl[255], a[300], b[300]; uint8_t len = (uint8_t)(tc_rand() % 256); uint32_t i, na, nb, id = (uint32_t)(tc_rand() % 300);
        for (i = 0; i < len; i++) pl[i] = (uint8_t)tc_rand();
        na = mk_mav(a, 7, id, pl, len, 0); nb = hp_mav2_encode(b, 7, 1, 200, id, pl, len, extra_of(id));
        CHECK(na == nb && memcmp(a, b, na) == 0);
        len = (uint8_t)(tc_rand() % 255);
        na = mk_msp1(a, '<', 0x42, pl, len); nb = hp_msp1_encode(b, '<', 0x42, pl, len); CHECK(na == nb && memcmp(a, b, na) == 0);
        na = mk_msp2(a, '>', 3, 0x1234, pl, len); nb = hp_msp2_encode(b, '>', 3, 0x1234, pl, len); CHECK(na == nb && memcmp(a, b, na) == 0);
    }
}

static void check_frame(const hp_frame *f, const want_t *w, uint32_t *bad)
{
    if (f->proto != w->proto || f->id != w->id || f->len != w->len || memcmp(f->payload, w->pl, w->len) != 0) { (*bad)++; return; }
    if (w->proto != HP_MAVLINK2 && f->dir != w->dir) (*bad)++;
    if (w->proto == HP_MAVLINK2 && f->seq != w->seq) (*bad)++;
}

TEST(random_stream_with_garbage)
{
    enum { N = 100000 };
    static want_t *w;
    uint32_t i, got = 0, bad = 0, extra_frames = 0, total_bytes = 0;
    uint8_t buf[320];
    hp_frame f;
    w = (want_t *)malloc(sizeof(want_t) * 4096);
    setup();
    tc_rs = 20240607;
    {
        uint32_t pending = 0;
        for (i = 0; i < N; i++) {
            want_t *x = &w[pending % 4096]; uint32_t n, g, j, k;
            memset(x, 0, sizeof *x);
            x->proto = (uint8_t)(1 + tc_rand() % 3);
            for (j = 0; j < 255; j++) x->pl[j] = (uint8_t)tc_rand();
            /* garbage between frames: random bytes, biased to contain start bytes that begin false frames */
            g = (uint32_t)(tc_rand() % 24);
            for (j = 0; j < g; j++) { uint8_t c = (uint8_t)tc_rand(); if (tc_rand() % 5 == 0) c = (tc_rand() & 1) ? 0xFD : '$'; buf[j] = c; }
            feed(buf, g); total_bytes += g;
            if (x->proto == HP_MAVLINK2) {
                x->id = (uint32_t)(tc_rand() % 300); x->len = (uint16_t)(tc_rand() % 256); x->seq = (uint8_t)tc_rand();
                if (x->len > 0 && (tc_rand() & 1)) { x->len = (uint16_t)(1 + tc_rand() % 8); }
                n = mk_mav(buf, x->seq, x->id, x->pl, (uint8_t)x->len, 0);
            } else if (x->proto == HP_MSP1) {
                x->dir = (uint8_t)"<>!"[tc_rand() % 3]; x->id = (uint32_t)(tc_rand() % 256); x->len = (uint16_t)(tc_rand() % 255);
                n = mk_msp1(buf, x->dir, (uint8_t)x->id, x->pl, (uint8_t)x->len);
            } else {
                x->dir = (uint8_t)"<>!"[tc_rand() % 3]; x->id = (uint32_t)(tc_rand() % 65536); x->len = (uint16_t)(tc_rand() % 256);
                n = mk_msp2(buf, x->dir, (uint8_t)tc_rand(), (uint16_t)x->id, x->pl, x->len);
            }
            feed(buf, n); total_bytes += n; pending++;
            /* poll (bounded work per call); collect everything that came out */
            for (k = 0; k < 4; k++) hp_poll(&H, &RING, 600);
            while (spsc_pop(&OUTQ, &f)) {
                if (got >= pending) { extra_frames++; continue; }
                check_frame(&f, &w[got % 4096], &bad); got++;
            }
        }
        /* flush: padding so that a false candidate at the end resolves */
        { uint32_t k; memset(buf, 0, 300); feed(buf, 300);
        for (k = 0; k < 20; k++) hp_poll(&H, &RING, 600); }
        while (spsc_pop(&OUTQ, &f)) { if (got >= pending) { extra_frames++; continue; } check_frame(&f, &w[got % 4096], &bad); got++; }
        CHECK_EQ(got, pending);
    }
    CHECK_EQ(bad, 0);
    CHECK_EQ(extra_frames, 0);                         /* nothing invented out of garbage */
    printf("    %u frames, %u bytes, bad crc %llu, bad header %llu, garbage %llu\n", got, total_bytes, (unsigned long long)H.st.bad_crc,
           (unsigned long long)H.st.bad_header, (unsigned long long)H.st.garbage_bytes);
    free(w);
}

TEST(one_corrupted_byte_loses_only_its_frame)
{
    int rep;
    tc_rs = 99;
    for (rep = 0; rep < 300; rep++) {
        enum { NF = 30 };
        uint8_t stream[NF * 320], pl[255]; uint32_t off[NF + 1], n = 0, i, victim, pos, got = 0, ok_expected = NF - 1, ids[NF], k;
        hp_frame f; uint32_t seen[NF] = {0};
        setup();
        for (i = 0; i < NF; i++) {
            uint32_t len = (uint32_t)(tc_rand() % 100), id = i;                  /* ids identify the frames */
            for (k = 0; k < len; k++) pl[k] = (uint8_t)tc_rand();
            off[i] = n; ids[i] = id;
            switch (i % 3) {
            case 0: n += mk_mav(stream + n, (uint8_t)i, id, pl, (uint8_t)len, 0); break;
            case 1: n += mk_msp1(stream + n, '>', (uint8_t)id, pl, (uint8_t)len); break;
            default: n += mk_msp2(stream + n, '>', 0, (uint16_t)id, pl, (uint16_t)len); break;
            }
        }
        off[NF] = n;
        victim = (uint32_t)(tc_rand() % NF);
        pos = off[victim] + (uint32_t)(tc_rand() % (off[victim + 1] - off[victim]));
        stream[pos] ^= (uint8_t)(1u << (tc_rand() % 8));
        feed(stream, n);
        { uint8_t z[300] = {0}; feed(z, 300); }
        for (k = 0; k < 20; k++) { hp_poll(&H, &RING, 700); while (spsc_pop(&OUTQ, &f)) { if (f.id < NF) { seen[f.id]++; got++; } } }
        CHECK_EQ(got, ok_expected);
        CHECK_EQ(seen[ids[victim]], 0);
        for (i = 0; i < NF; i++) if (i != victim && seen[i] != 1) { CHECK(0); break; }
    }
}

TEST(bounded_work_per_call)
{
    uint8_t buf[300], pl[100]; uint32_t i, n, calls = 0, before, frames = 0;
    hp_frame f;
    setup();
    memset(pl, 5, sizeof pl);
    n = mk_msp1(buf, '<', 1, pl, 100);
    for (i = 0; i < 100; i++) feed(buf, n);                  /* 10,600 bytes at once */
    while (spsc_count(&RING) > 0 || H.n > 0) {
        before = spsc_count(&RING);
        frames += hp_poll(&H, &RING, 64);
        CHECK(before - spsc_count(&RING) <= 64);              /* at most 64 bytes taken from the ring per call */
        while (spsc_pop(&OUTQ, &f)) { }
        if (++calls > 10000) break;
        if (spsc_count(&RING) == 0 && H.n < 106) break;
    }
    CHECK_EQ(frames, 100);
}

TEST(mavlink_details)
{
    uint8_t buf[320], pl[255]; uint32_t n; hp_frame f;
    memset(pl, 0, sizeof pl); pl[0] = 9; pl[1] = 8;
    setup();
    /* trailing zeros trimmed by the sender: len is what was transmitted */
    n = mk_mav(buf, 1, 24, pl, 2, 0); feed(buf, n);
    CHECK_EQ(hp_poll(&H, &RING, 300), 1); CHECK(spsc_pop(&OUTQ, &f)); CHECK_EQ(f.len, 2); CHECK_EQ(f.payload[1], 8); CHECK(!f.signed_frame);
    /* signed frame: signature skipped */
    n = mk_mav(buf, 2, 25, pl, 2, 1); feed(buf, n);
    { uint8_t t[2] = {1, 2}; feed(t, 0); (void)t; }
    CHECK_EQ(hp_poll(&H, &RING, 300), 1); CHECK(spsc_pop(&OUTQ, &f)); CHECK(f.signed_frame); CHECK_EQ(f.id, 25);
    /* a signed frame followed by another frame: the 13 signature bytes are not mistaken for a start byte */
    { uint32_t n2; n = mk_mav(buf, 3, 26, pl, 2, 1); buf[n - 5] = 0xFD; buf[n - 4] = '$';  /* inside the signature */
      n2 = mk_mav(buf + n, 4, 27, pl, 2, 0); feed(buf, n + n2); }
    CHECK_EQ(hp_poll(&H, &RING, 600), 2); CHECK(spsc_pop(&OUTQ, &f)); CHECK_EQ(f.id, 26); CHECK(spsc_pop(&OUTQ, &f)); CHECK_EQ(f.id, 27);
    /* unknown incompatibility flag: the frame is discarded */
    n = mk_mav(buf, 5, 28, pl, 2, 2); feed(buf, n);
    { uint8_t z[40] = {0}; feed(z, 40); }
    CHECK_EQ(hp_poll(&H, &RING, 300), 0); CHECK(H.st.bad_header >= 1);
    /* unknown message id: cannot be checked, dropped and counted */
    n = mk_mav(buf, 6, 5000, pl, 2, 0); feed(buf, n);
    { uint8_t z[40] = {0}; feed(z, 40); }
    { uint64_t u0 = H.st.unknown_id; CHECK_EQ(hp_poll(&H, &RING, 300), 0); CHECK(H.st.unknown_id > u0); }
    /* 24-bit message id and the longest payload */
    memset(pl, 0x11, sizeof pl); n = mk_mav(buf, 7, 0x10203u, pl, 255, 0); feed(buf, n);
    CHECK_EQ(hp_poll(&H, &RING, 600), 1); CHECK(spsc_pop(&OUTQ, &f)); CHECK_EQ(f.id, 0x10203u); CHECK_EQ(f.len, 255);
}

TEST(msp_details)
{
    uint8_t buf[330], pl[300]; uint32_t n; hp_frame f; uint32_t k;
    for (k = 0; k < 300; k++) pl[k] = (uint8_t)k;
    setup();
    n = mk_msp1(buf, '>', 0x66, pl, 0); feed(buf, n);                         /* empty payload */
    CHECK_EQ(hp_poll(&H, &RING, 300), 1); CHECK(spsc_pop(&OUTQ, &f)); CHECK_EQ(f.proto, HP_MSP1); CHECK_EQ(f.dir, '>'); CHECK_EQ(f.len, 0);
    n = mk_msp1(buf, '!', 0x01, pl, 254); feed(buf, n);                       /* error frame, longest v1 */
    CHECK_EQ(hp_poll(&H, &RING, 300), 1); CHECK(spsc_pop(&OUTQ, &f)); CHECK_EQ(f.dir, '!'); CHECK_EQ(f.len, 254);
    n = mk_msp1(buf, '<', 0x01, pl, 255); feed(buf, n);                       /* jumbo: not supported */
    { uint8_t z[300] = {0}; feed(z, 300); }
    CHECK_EQ(hp_poll(&H, &RING, 700), 0);
    n = mk_msp2(buf, '<', 0x81, 0xABCD, pl, 255); feed(buf, n);
    CHECK_EQ(hp_poll(&H, &RING, 700), 1); CHECK(spsc_pop(&OUTQ, &f)); CHECK_EQ(f.proto, HP_MSP2); CHECK_EQ(f.id, 0xABCD); CHECK_EQ(f.flags, 0x81); CHECK_EQ(f.len, 255);
    n = mk_msp2(buf, '<', 0, 1, pl, 256); feed(buf, n);                       /* longer than 255: refused */
    { uint8_t z[300] = {0}; feed(z, 300); }
    CHECK_EQ(hp_poll(&H, &RING, 700), 0);
    n = mk_msp2(buf, '<', 0, 1, pl, 4); buf[2] = '?'; feed(buf, n);              /* bad direction with a valid CRC (it does not cover the direction) */
    { uint8_t z[300] = {0}; feed(z, 300); }
    CHECK_EQ(hp_poll(&H, &RING, 700), 0);
}

TEST(output_queue_full_backpressure)
{
    uint8_t buf[100], pl[8] = {1,2,3,4,5,6,7,8}; uint32_t n, i, got = 0; hp_frame f;
    setup();
    n = mk_msp1(buf, '<', 9, pl, 8);
    for (i = 0; i < 40; i++) { buf[4] = (uint8_t)i; { uint32_t k; uint8_t x = (uint8_t)(8 ^ i); for (k = 0; k < 8; k++) x ^= pl[k]; buf[n - 1] = x; } feed(buf, n); }
    hp_poll(&H, &RING, 1000);
    CHECK_EQ(spsc_count(&OUTQ), 16);                          /* queue capacity */
    CHECK(H.st.out_full >= 1);
    for (i = 0; i < 10; i++) { while (spsc_pop(&OUTQ, &f)) { CHECK_EQ(f.id, got); got++; } hp_poll(&H, &RING, 1000); }
    while (spsc_pop(&OUTQ, &f)) { CHECK_EQ(f.id, got); got++; }
    CHECK_EQ(got, 40);                                        /* none lost */
}

int main(void)
{
    RUN(encoders_agree_with_reference); RUN(random_stream_with_garbage); RUN(one_corrupted_byte_loses_only_its_frame);
    RUN(bounded_work_per_call); RUN(mavlink_details); RUN(msp_details); RUN(output_queue_full_backpressure);
    TC_DONE();
}
