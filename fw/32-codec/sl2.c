/* SL2 reference model. See design/32-codec-efficiency.md section 2 for the definition. */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "sl2.h"

sl2_stats sl2_st;
double sl2_tune[8] = {1.0, 21845.0, 10923.0, 1.0, 0, 0, 0, 0};   /* lambda scale, intra and inter rounding offsets (of 65536), motion lambda scale */

#define CLIP255(v) ((v) < 0 ? 0 : ((v) > 255 ? 255 : (v)))
#define CLIPQP(v) ((v) < 0 ? 0 : ((v) > 51 ? 51 : (v)))

/* ---------------------------------------------------------------- tables */
static const int8_t DCT_T[8][8] = {
    {64, 64, 64, 64, 64, 64, 64, 64}, {89, 75, 50, 18, -18, -50, -75, -89}, {83, 36, -36, -83, -83, -36, 36, 83},
    {75, -18, -89, -50, 50, 89, 18, -75}, {64, -64, -64, 64, 64, -64, -64, 64}, {50, -89, 18, 75, -75, -18, 89, -50},
    {36, -83, 83, -36, -36, 83, -83, 36}, {18, -50, 75, -89, 89, -75, 50, -18}};
static int8_t HAD[8][8];                 /* Walsh-Hadamard in sequency order */
static int scan_i[64], scan_j[64];
static int32_t RQ[52], DQ[52];           /* DCT quantiser */
static int32_t RH[52][64], SH_[52][64];  /* Hadamard quantiser (SL1 weighting) */
static double cost_tab[4096];
static int init_done;
static int lam_i[52];                    /* lambda x 16 */

static void tables_init(void) {
    if (init_done) return;
    int h[8][8] = {{1}};
    for (int n = 1; n < 8; n *= 2)
        for (int i = 0; i < n; i++)
            for (int j = 0; j < n; j++) {
                h[i][j + n] = h[i][j];
                h[i + n][j] = h[i][j];
                h[i + n][j + n] = -h[i][j];
            }
    int ch[8], idx[8];
    for (int r = 0; r < 8; r++) {
        ch[r] = 0;
        for (int c = 0; c < 7; c++) ch[r] += h[r][c] != h[r][c + 1];
        idx[r] = r;
    }
    for (int a = 0; a < 8; a++)
        for (int b = a + 1; b < 8; b++)
            if (ch[idx[b]] < ch[idx[a]]) { int t = idx[a]; idx[a] = idx[b]; idx[b] = t; }
    for (int r = 0; r < 8; r++)
        for (int c = 0; c < 8; c++) HAD[r][c] = (int8_t)h[idx[r]][c];
    /* diagonal scan as SL1 */
    int n = 0;
    for (int s = 0; s < 15; s++) {
        int lo = s < 8 ? 0 : s - 7, hi = s < 8 ? s : 7;
        if (s % 2) for (int i = lo; i <= hi; i++) { scan_i[n] = i; scan_j[n] = s - i; n++; }
        else for (int i = hi; i >= lo; i--) { scan_i[n] = i; scan_j[n] = s - i; n++; }
    }
    for (int qp = 0; qp < 52; qp++) {
        double step = 16.0 * 0.625 * pow(2.0, qp / 6.0);      /* the integer DCT has a gain of 16 against the orthonormal one */
        RQ[qp] = (int32_t)floor(65536.0 / step + 0.5);
        DQ[qp] = (int32_t)floor(16.0 * step + 0.5);
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int st = (int)floor(8 * 0.625 * pow(2.0, qp / 6.0) * (1 + 0.05 * (i + j)) + 0.5);
                SH_[qp][i * 8 + j] = st;
                RH[qp][i * 8 + j] = (int32_t)floor(65536.0 / st + 0.5);
            }
        lam_i[qp] = (int)floor(16.0 * 0.85 * pow(2.0, (qp - 12) / 3.0) + 0.5);
    }
    for (int i = 0; i < 4096; i++) cost_tab[i] = -log2((i + 0.5) / 4096.0);
    init_done = 1;
}

/* ---------------------------------------------------------------- transforms */
void sl2_fwd(int dct, const int32_t *x, int32_t *c) {
    tables_init();
    int32_t t[64];
    if (dct) {
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int64_t s = 0;
                for (int k = 0; k < 8; k++) s += (int64_t)DCT_T[i][k] * x[k * 8 + j];
                t[i * 8 + j] = (int32_t)((s + 2) >> 2);
            }
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int64_t s = 0;
                for (int k = 0; k < 8; k++) s += (int64_t)t[i * 8 + k] * DCT_T[j][k];
                c[i * 8 + j] = (int32_t)((s + 256) >> 9);
            }
    } else {
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int s = 0;
                for (int k = 0; k < 8; k++) s += HAD[i][k] * x[k * 8 + j];
                t[i * 8 + j] = s;
            }
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int s = 0;
                for (int k = 0; k < 8; k++) s += t[i * 8 + k] * HAD[j][k];
                c[i * 8 + j] = s;
            }
    }
}

void sl2_inv(int dct, const int32_t *c, int32_t *x) {
    tables_init();
    int32_t t[64];
    if (dct) {
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int64_t s = 0;
                for (int k = 0; k < 8; k++) s += (int64_t)DCT_T[k][i] * c[k * 8 + j];
                t[i * 8 + j] = (int32_t)((s + 64) >> 7);
            }
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int64_t s = 0;
                for (int k = 0; k < 8; k++) s += (int64_t)t[i * 8 + k] * DCT_T[k][j];
                x[i * 8 + j] = (int32_t)((s + 2048) >> 12);
            }
    } else {
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int s = 0;
                for (int k = 0; k < 8; k++) s += HAD[k][i] * c[k * 8 + j];
                t[i * 8 + j] = s;
            }
        for (int i = 0; i < 8; i++)
            for (int j = 0; j < 8; j++) {
                int s = 0;
                for (int k = 0; k < 8; k++) s += t[i * 8 + k] * HAD[k][j];
                x[i * 8 + j] = (s + 32) >> 6;
            }
    }
}

/* ---------------------------------------------------------------- arithmetic coder */
typedef struct { uint16_t a, b; } prob;

enum { K_ENC = 0, K_DEC = 1, K_COST = 2 };

typedef struct {
    int kind, bypass_all;
    uint32_t range, code;
    uint64_t low;
    uint8_t cache;
    uint64_t csize;
    int first;
    uint8_t *buf;
    int pos, cap, overflow;
    const uint8_t *in;
    int inlen, inpos;
    double cost;
    long long nbins;
    int cat;
} coder;

static void rc_out(coder *c, uint8_t b) {
    if (c->first) { c->first = 0; return; }
    if (c->pos < c->cap) c->buf[c->pos++] = b; else c->overflow = 1;
}

static void rc_shift(coder *c) {
    if ((uint32_t)c->low < 0xFF000000u || (c->low >> 32) != 0) {
        uint8_t carry = (uint8_t)(c->low >> 32), t = c->cache;
        do { rc_out(c, (uint8_t)(t + carry)); t = 0xFF; } while (--c->csize);
        c->cache = (uint8_t)((c->low >> 24) & 0xFF);
    }
    c->csize++;
    c->low = (c->low & 0x00FFFFFFu) << 8;
}

static void rc_init_enc(coder *c, uint8_t *buf, int cap, int bypass_all) {
    memset(c, 0, sizeof *c);
    c->kind = K_ENC; c->range = 0xFFFFFFFFu; c->csize = 1; c->first = 1; c->buf = buf; c->cap = cap; c->bypass_all = bypass_all;
}
static void rc_init_cost(coder *c, int bypass_all) {
    memset(c, 0, sizeof *c);
    c->kind = K_COST; c->bypass_all = bypass_all;
}
static void rc_init_dec(coder *c, const uint8_t *in, int len, int bypass_all) {
    memset(c, 0, sizeof *c);
    c->kind = K_DEC; c->range = 0xFFFFFFFFu; c->in = in; c->inlen = len; c->bypass_all = bypass_all;
    for (int i = 0; i < 4; i++) c->code = (c->code << 8) | (c->inpos < len ? in[c->inpos++] : 0);
}
static int rc_finish(coder *c) {
    for (int i = 0; i < 5; i++) rc_shift(c);
    while (c->pos > 0 && c->buf[c->pos - 1] == 0) c->pos--;     /* the decoder pads with zeros */
    return c->pos;
}

static int code_p(coder *c, uint32_t p0, int bit) {              /* p0 = P(bit 0) in 16 bits */
    uint32_t bound = (c->range >> 16) * p0;
    if (c->kind == K_ENC) {
        if (!bit) c->range = bound; else { c->low += bound; c->range -= bound; }
        while (c->range < (1u << 24)) { c->range <<= 8; rc_shift(c); }
        return bit;
    }
    if (c->kind == K_DEC) {
        if (c->code < bound) { c->range = bound; bit = 0; } else { c->code -= bound; c->range -= bound; bit = 1; }
        while (c->range < (1u << 24)) {
            c->range <<= 8;
            c->code = (c->code << 8) | (c->inpos < c->inlen ? c->in[c->inpos++] : 0);
        }
        return bit;
    }
    return bit;
}

static int bin(coder *c, prob *p, int bit) {
    c->nbins++;
    if (c->bypass_all) {                                          /* no context modelling: every bin costs one bit */
        if (c->kind == K_COST) { c->cost += 1.0; return bit; }
        if (c->kind == K_ENC) sl2_st.cat_bits[c->cat] += 1.0;
        return code_p(c, 32768, bit);
    }
    uint32_t p0 = ((uint32_t)p->a + p->b) >> 1;
    if (p0 < 32) p0 = 32;
    if (p0 > 65504) p0 = 65504;
    if (c->kind == K_COST) c->cost += cost_tab[(bit ? 65536 - p0 : p0) >> 4];
    else {
        bit = code_p(c, p0, bit);
        if (c->kind == K_ENC) sl2_st.cat_bits[c->cat] += cost_tab[(bit ? 65536 - p0 : p0) >> 4];
    }
    if (!bit) { p->a += (65536 - p->a) >> 4; p->b += (65536 - p->b) >> 7; }
    else { p->a -= p->a >> 4; p->b -= p->b >> 7; }
    return bit;
}

static int byp(coder *c, int bit) {
    c->nbins++;
    if (c->kind == K_COST) { c->cost += 1.0; return bit; }
    if (c->kind == K_ENC) sl2_st.cat_bits[c->cat] += 1.0;
    return code_p(c, 32768, bit);
}

#define V(c, x) ((c)->kind == K_DEC ? 0 : (x))

static int eg_byp(coder *c, int v, int k) {                      /* Exp-Golomb of v >= 0, bypass bins */
    int out = 0;
    for (;;) {
        int b = byp(c, V(c, v >= (1 << k)));
        if (!b || (c->kind == K_DEC && k > 24)) break;                /* guard against a corrupted stream */
        v -= 1 << k;
        out += 1 << k;
        k++;
    }
    int r = 0;
    for (int i = k - 1; i >= 0; i--) r |= byp(c, V(c, (v >> i) & 1)) << i;
    return out + r;
}

/* unary with up to maxu bins on contexts p[min(i, nctx-1)], escape Exp-Golomb-k of the rest */
static int unary_eg(coder *c, prob *p, int nctx, int val, int maxu, int k) {
    int u = 0;
    while (u < maxu) {
        int b = bin(c, &p[u < nctx ? u : nctx - 1], V(c, val > u));
        if (!b) return u;
        u++;
    }
    return maxu + eg_byp(c, V(c, val - maxu), k);
}

/* ---------------------------------------------------------------- contexts */
typedef struct {
    prob skip[3], intra[3], imode[3], mvz[2], mvs[2], mvm[2][8];
    prob dqz, dqs, dqm[6];
    prob cbf[6], sig[2][63], last[2][63], lv1[5], lvn[5];
} ctxs;

static void ctx_init(ctxs *x) {
    prob *p = (prob *)x;
    for (size_t i = 0; i < sizeof *x / sizeof *p; i++) { p[i].a = 32768; p[i].b = 32768; }
}

/* ---------------------------------------------------------------- slice state */
typedef struct {
    const sl2_cfg *cfg;
    int W, SH, y0, bw, bh, mbw, tools, intra_slice, qp, has_dqp;
    const uint8_t *src, *ref;
    uint8_t *cur;                    /* unfiltered reconstruction of the slice, SH x W */
    uint8_t *mode, *imode, *nnz, *coded, *bqp;
    int16_t *mvx, *mvy;
    const int8_t *dqp;               /* per macroblock of the picture */
    int keep;
    ctxs cx;
} sl;

typedef struct {
    int kind;                        /* 0 skip, 1 inter, 2 intra */
    int imode, mvx, mvy, cbf;
    int lev[64];                     /* levels in scan order */
    uint8_t rec[64];
    double J;
} cand;

static int mb_dqp(const sl *s, int bx, int by) {
    if (!s->has_dqp || !s->dqp) return 0;
    int mbx = bx >> 1, mby = (s->y0 >> 4) + (by >> 1);
    return s->dqp[mby * s->mbw + mbx];
}

static int avail_left(const sl *s, int bx, int by) { (void)s; (void)by; return bx > 0; }
static int avail_top(const sl *s, int bx, int by) { (void)bx; (void)s; return by > 0; }

/* ---------------------------------------------------------------- motion vector prediction */
static void mv_pred(const sl *s, int bx, int by, int *px, int *py) {
    int ax = 0, ay = 0, bxv = 0, byv = 0, cx = 0, cy = 0, na = 0, nb = 0, nc = 0;
    int W8 = s->bw;
    if (bx > 0 && s->coded[by * W8 + bx - 1] && s->mode[by * W8 + bx - 1] != 2) { na = 1; ax = s->mvx[by * W8 + bx - 1]; ay = s->mvy[by * W8 + bx - 1]; }
    if (by > 0 && s->coded[(by - 1) * W8 + bx] && s->mode[(by - 1) * W8 + bx] != 2) { nb = 1; bxv = s->mvx[(by - 1) * W8 + bx]; byv = s->mvy[(by - 1) * W8 + bx]; }
    int cxx = bx + 1, cyy = by - 1;
    int cok = (by > 0 && cxx < W8 && s->coded[cyy * W8 + cxx]);
    if (!cok) { cxx = bx - 1; cok = (by > 0 && bx > 0 && s->coded[cyy * W8 + cxx]); }
    if (cok && s->mode[cyy * W8 + cxx] != 2) { nc = 1; cx = s->mvx[cyy * W8 + cxx]; cy = s->mvy[cyy * W8 + cxx]; }
    if (na + nb + nc == 1) {
        *px = na ? ax : (nb ? bxv : cx);
        *py = na ? ay : (nb ? byv : cy);
        return;
    }
#define MED(a, b, c) ((a) > (b) ? ((b) > (c) ? (b) : ((a) > (c) ? (c) : (a))) : ((a) > (c) ? (a) : ((b) > (c) ? (c) : (b))))
    *px = MED(ax, bxv, cx);
    *py = MED(ay, byv, cy);
#undef MED
}

/* ---------------------------------------------------------------- inter prediction */
typedef struct { const uint8_t *ref; int W, y0, y1; } refpl;

static inline int P(const refpl *r, int x, int y) {
    x = x < 0 ? 0 : (x >= r->W ? r->W - 1 : x);
    y = y < r->y0 ? r->y0 : (y >= r->y1 ? r->y1 - 1 : y);
    return r->ref[y * r->W + x];
}
static inline int hh(const refpl *r, int x, int y) {
    return P(r, x - 2, y) - 5 * P(r, x - 1, y) + 20 * P(r, x, y) + 20 * P(r, x + 1, y) - 5 * P(r, x + 2, y) + P(r, x + 3, y);
}
static inline int hv(const refpl *r, int x, int y) {
    return P(r, x, y - 2) - 5 * P(r, x, y - 1) + 20 * P(r, x, y) + 20 * P(r, x, y + 1) - 5 * P(r, x, y + 2) + P(r, x, y + 3);
}
static inline int bq(int v) { return CLIP255((v + 16) >> 5); }
static inline int cq(const refpl *r, int x, int y) {
    int j1 = hh(r, x, y - 2) - 5 * hh(r, x, y - 1) + 20 * hh(r, x, y) + 20 * hh(r, x, y + 1) - 5 * hh(r, x, y + 2) + hh(r, x, y + 3);
    return CLIP255((j1 + 512) >> 10);
}

static int qpel_sample(const refpl *r, int x, int y, int fx, int fy) {
    switch (fy * 4 + fx) {
    case 0: return P(r, x, y);
    case 1: return (P(r, x, y) + bq(hh(r, x, y)) + 1) >> 1;
    case 2: return bq(hh(r, x, y));
    case 3: return (P(r, x + 1, y) + bq(hh(r, x, y)) + 1) >> 1;
    case 4: return (P(r, x, y) + bq(hv(r, x, y)) + 1) >> 1;
    case 5: return (bq(hh(r, x, y)) + bq(hv(r, x, y)) + 1) >> 1;
    case 6: return (bq(hh(r, x, y)) + cq(r, x, y) + 1) >> 1;
    case 7: return (bq(hh(r, x, y)) + bq(hv(r, x + 1, y)) + 1) >> 1;
    case 8: return bq(hv(r, x, y));
    case 9: return (bq(hv(r, x, y)) + cq(r, x, y) + 1) >> 1;
    case 10: return cq(r, x, y);
    case 11: return (cq(r, x, y) + bq(hv(r, x + 1, y)) + 1) >> 1;
    case 12: return (P(r, x, y + 1) + bq(hv(r, x, y)) + 1) >> 1;
    case 13: return (bq(hv(r, x, y)) + bq(hh(r, x, y + 1)) + 1) >> 1;
    case 14: return (cq(r, x, y) + bq(hh(r, x, y + 1)) + 1) >> 1;
    default: return (bq(hv(r, x + 1, y)) + bq(hh(r, x, y + 1)) + 1) >> 1;
    }
}

static void mc_block(const sl *s, int bx, int by, int mvx, int mvy, uint8_t *out) {
    refpl r = {s->ref, s->W, s->y0, s->y0 + s->SH};
    int x0 = bx * 8 + (mvx >> 2), y0 = s->y0 + by * 8 + (mvy >> 2), fx = mvx & 3, fy = mvy & 3;
    for (int j = 0; j < 8; j++)
        for (int i = 0; i < 8; i++) out[j * 8 + i] = (uint8_t)qpel_sample(&r, x0 + i, y0 + j, fx, fy);
}

/* ---------------------------------------------------------------- intra prediction */
static int intra_ok(const sl *s, int bx, int by, int mode) {
    int l = avail_left(s, bx, by), t = avail_top(s, bx, by);
    if (mode == 0) return 1;
    if (mode == 1) return t;
    if (mode == 2) return l;
    return l && t;
}

static void intra_pred(const sl *s, int bx, int by, int mode, uint8_t *out) {
    const uint8_t *cur = s->cur;
    int W = s->W, x0 = bx * 8, y0 = by * 8;
    int l = avail_left(s, bx, by), t = avail_top(s, bx, by);
    int T[9], L[9];                  /* index 0 is the top-left sample, 1..8 the samples */
    if (t) for (int i = 0; i < 8; i++) T[i + 1] = cur[(y0 - 1) * W + x0 + i];
    if (l) for (int i = 0; i < 8; i++) L[i + 1] = cur[(y0 + i) * W + x0 - 1];
    if (l && t) { T[0] = L[0] = cur[(y0 - 1) * W + x0 - 1]; }
    if (mode == 0) {
        int sum = 0, n = 0, dc = 128;
        if (t) { for (int i = 1; i <= 8; i++) sum += T[i]; n += 8; }
        if (l) { for (int i = 1; i <= 8; i++) sum += L[i]; n += 8; }
        if (n) dc = (sum + n / 2) / n;
        memset(out, dc, 64);
    } else if (mode == 1) {
        for (int j = 0; j < 8; j++) for (int i = 0; i < 8; i++) out[j * 8 + i] = (uint8_t)T[i + 1];
    } else if (mode == 2) {
        for (int j = 0; j < 8; j++) for (int i = 0; i < 8; i++) out[j * 8 + i] = (uint8_t)L[j + 1];
    } else {
        int Hs = 0, Vs = 0;
        for (int x = 0; x < 4; x++) {
            Hs += (x + 1) * (T[5 + x] - (2 - x >= 0 ? T[3 - x] : T[0]));
            Vs += (x + 1) * (L[5 + x] - (2 - x >= 0 ? L[3 - x] : L[0]));
        }
        int a = 16 * (L[8] + T[8]), b = (17 * Hs + 16) >> 5, c = (17 * Vs + 16) >> 5;
        for (int j = 0; j < 8; j++)
            for (int i = 0; i < 8; i++) out[j * 8 + i] = (uint8_t)CLIP255((a + b * (i - 3) + c * (j - 3) + 16) >> 5);
    }
}

/* ---------------------------------------------------------------- syntax (symmetric for encoder, decoder and cost) */
static int nb_count(const uint8_t *arr, const sl *s, int bx, int by, int v) {
    int n = 0;
    if (bx > 0 && s->coded[by * s->bw + bx - 1] && arr[by * s->bw + bx - 1] == v) n++;
    if (by > 0 && s->coded[(by - 1) * s->bw + bx] && arr[(by - 1) * s->bw + bx] == v) n++;
    return n;
}

static void syn_dqp(coder *c, ctxs *x, int *dq) {
    c->cat = 6;
    int nz = bin(c, &x->dqz, V(c, *dq != 0));
    if (!nz) { *dq = 0; return; }
    int neg = bin(c, &x->dqs, V(c, *dq < 0));
    int m = 1 + unary_eg(c, x->dqm, 6, V(c, abs(*dq) - 1), 6, 1);
    *dq = neg ? -m : m;
}

static void syn_mvd(coder *c, ctxs *x, int comp, int *d) {
    c->cat = 2;
    int nz = bin(c, &x->mvz[comp], V(c, *d != 0));
    if (!nz) { *d = 0; return; }
    int neg = bin(c, &x->mvs[comp], V(c, *d < 0));
    int m = 1 + unary_eg(c, x->mvm[comp], 8, V(c, abs(*d) - 1), 8, 0);
    *d = neg ? -m : m;
}

static void syn_resid(coder *c, ctxs *x, int intra, int cbf_ctx, int *cbf, int *lev) {
    c->cat = 3;
    int has = bin(c, &x->cbf[intra * 3 + cbf_ctx], V(c, *cbf));
    *cbf = has;
    if (!has) { if (c->kind == K_DEC) memset(lev, 0, 64 * sizeof(int)); return; }
    int last = 0;
    if (c->kind != K_DEC) { for (int i = 0; i < 64; i++) if (lev[i]) last = i; }
    c->cat = 4;
    int sigpos[64], ns = 0;
    int dec = c->kind == K_DEC;
    if (dec) memset(lev, 0, 64 * sizeof(int));
    int i;
    for (i = 0; i < 63; i++) {
        int sg = bin(c, &x->sig[intra][i], V(c, lev[i] != 0));
        if (sg) {
            sigpos[ns++] = i;
            int ls = bin(c, &x->last[intra][i], V(c, i == last));
            if (ls) break;
        }
    }
    if (i == 63) sigpos[ns++] = 63;                              /* position 63 is significant by inference */
    int eq1 = 0, gt1 = 0;
    c->cat = 5;
    for (int k = ns - 1; k >= 0; k--) {
        int p = sigpos[k];
        int a = dec ? 0 : abs(lev[p]);
        int ctxA = gt1 ? 0 : (1 + eq1 < 4 ? 1 + eq1 : 4);
        int b0 = bin(c, &x->lv1[ctxA], V(c, a > 1));
        if (!b0) a = 1;
        else a = 2 + unary_eg(c, &x->lvn[gt1 < 4 ? gt1 : 4], 1, V(c, a - 2), 13, 0);
        if (a == 1) eq1++; else gt1++;
        int neg = byp(c, V(c, dec ? 0 : lev[p] < 0));
        if (dec) lev[p] = neg ? -a : a;
    }
}

/* block syntax in one place: skip/intra flags, mode or vector difference, residual. pmv: predicted vector. */
static void syn_block(coder *c, sl *s, ctxs *x, int bx, int by, cand *b, int pmx, int pmy) {
    int dec = c->kind == K_DEC;
    int n_skip = nb_count(s->mode, s, bx, by, 0), n_intra = nb_count(s->mode, s, bx, by, 2);
    c->cat = 0;
    if (!s->intra_slice) {
        int sk = bin(c, &x->skip[n_skip], V(c, b->kind == 0));
        if (sk) { if (dec) b->kind = 0; b->cbf = 0; if (dec) memset(b->lev, 0, sizeof b->lev); return; }
        int in = bin(c, &x->intra[n_intra], V(c, b->kind == 2));
        if (dec) b->kind = in ? 2 : 1;
    } else if (dec) b->kind = 2;
    if (b->kind == 2) {
        if (s->tools & SL2_T_INTRA) {
            c->cat = 1;
            int b0 = bin(c, &x->imode[0], V(c, b->imode >> 1));
            int b1 = bin(c, &x->imode[1 + b0], V(c, b->imode & 1));
            if (dec) b->imode = b0 * 2 + b1;
        } else if (dec) b->imode = 0;
    } else {
        int dx = b->mvx - pmx, dy = b->mvy - pmy;
        syn_mvd(c, x, 0, &dx);
        syn_mvd(c, x, 1, &dy);
        if (dec) { b->mvx = pmx + dx; b->mvy = pmy + dy; }
    }
    int cctx = nb_count(s->nnz, s, bx, by, 1);
    syn_resid(c, x, b->kind == 2, cctx, &b->cbf, b->lev);
}

/* ---------------------------------------------------------------- reconstruction of a block from a candidate */
static void block_pred(const sl *s, int bx, int by, const cand *b, uint8_t *pred) {
    if (b->kind == 2) intra_pred(s, bx, by, b->imode, pred);
    else mc_block(s, bx, by, b->mvx, b->mvy, pred);
}

static void recon_from_levels(const sl *s, int qp, const uint8_t *pred, const int *lev, uint8_t *rec) {
    int dct = s->tools & SL2_T_DCT;
    int32_t c[64] = {0}, r[64];
    for (int k = 0; k < 64; k++) {
        if (!lev[k]) continue;
        int pos = scan_i[k] * 8 + scan_j[k];
        c[pos] = dct ? (lev[k] * DQ[qp] + 8) >> 4 : lev[k] * SH_[qp][pos];
    }
    sl2_inv(dct, c, r);
    for (int k = 0; k < 64; k++) rec[k] = (uint8_t)CLIP255(pred[k] + r[k]);
}

static int quantise(const sl *s, int qp, int intra, const uint8_t *pred, const uint8_t *src8, int *lev) {
    int dct = s->tools & SL2_T_DCT;
    int32_t x[64], c[64];
    for (int k = 0; k < 64; k++) x[k] = (int)src8[k] - pred[k];
    sl2_fwd(dct, x, c);
    int nz = 0;
    for (int k = 0; k < 64; k++) {
        int pos = scan_i[k] * 8 + scan_j[k];
        int64_t a = c[pos] < 0 ? -(int64_t)c[pos] : c[pos];
        int64_t f = dct ? (int64_t)(intra ? sl2_tune[1] : sl2_tune[2]) : (intra ? 29491 : 21845);
        int64_t lv = (a * (dct ? RQ[qp] : RH[qp][pos]) + f) >> 16;
        if (lv > 2000) lv = 2000;
        if (k >= s->keep) lv = 0;
        lev[k] = (int)(c[pos] < 0 ? -lv : lv);
        nz |= lev[k] != 0;
    }
    return nz;
}

static void fetch_src(const sl *s, int bx, int by, uint8_t *out) {
    for (int j = 0; j < 8; j++) memcpy(out + j * 8, s->src + (s->y0 + by * 8 + j) * s->W + bx * 8, 8);
}

static long ssd8(const uint8_t *a, const uint8_t *b) {
    long s = 0;
    for (int k = 0; k < 64; k++) { int d = (int)a[k] - b[k]; s += d * d; }
    return s;
}
static long sad8(const uint8_t *a, const uint8_t *b) {
    long s = 0;
    for (int k = 0; k < 64; k++) s += abs((int)a[k] - b[k]);
    return s;
}

/* full RD cost of a candidate: reconstruction, distortion, rate from a trial coder on a copy of the contexts */
static void eval_cand(sl *s, int bx, int by, int qp, const uint8_t *src8, cand *b, int pmx, int pmy, int zero_res) {
    uint8_t pred[64];
    sl2_st.probes++;
    if (b->kind == 0) { b->mvx = pmx; b->mvy = pmy; }
    block_pred(s, bx, by, b, pred);
    if (b->kind == 0 || zero_res) { memset(b->lev, 0, sizeof b->lev); b->cbf = 0; }
    else b->cbf = quantise(s, qp, b->kind == 2, pred, src8, b->lev);
    if (b->cbf) recon_from_levels(s, qp, pred, b->lev, b->rec); else memcpy(b->rec, pred, 64);
    ctxs tmp = s->cx;
    coder c;
    rc_init_cost(&c, !(s->tools & SL2_T_CTX));
    syn_block(&c, s, &tmp, bx, by, b, pmx, pmy);
    b->J = (double)ssd8(src8, b->rec) + lam_i[qp] / 16.0 * sl2_tune[0] * c.cost;
}

/* ---------------------------------------------------------------- motion search */
static int mvbits(int d) { int a = abs(d), n = 1; while (a) { n += 2; a >>= 1; } return n; }

static long sad_mv(const sl *s, int bx, int by, const uint8_t *src8, int mvx, int mvy, int pmx, int pmy, int lam_s) {
    uint8_t pr[64];
    sl2_st.sad_evals++;
    mc_block(s, bx, by, mvx, mvy, pr);
    return sad8(src8, pr) * 16 + (long)lam_s * (mvbits(mvx - pmx) + mvbits(mvy - pmy));
}

static void motion_search(const sl *s, int bx, int by, int qp, const uint8_t *src8, int pmx, int pmy, int *bmx, int *bmy) {
    int lam_s = (int)(sqrt(lam_i[qp] / 16.0) * 16 * sl2_tune[3] + 0.5);
    int subpel = s->tools & SL2_T_SUBPEL;
    long best = -1;
    int mx = 0, my = 0;
    /* integer full search around zero and around the integer part of the predictor */
    int starts[2][2] = {{0, 0}, {(pmx + 2) >> 2, (pmy + 2) >> 2}};
    for (int st = 0; st < 2; st++) {
        for (int dy = -8; dy <= 8; dy++)
            for (int dx = -8; dx <= 8; dx++) {
                int ix = starts[st][0] + dx, iy = starts[st][1] + dy;
                if (st == 1 && abs(dx) < 1 && abs(dy) < 1 && starts[1][0] == 0 && starts[1][1] == 0) continue;
                if (st == 1 && (abs(dx) > 3 || abs(dy) > 3)) continue;
                long v = sad_mv(s, bx, by, src8, ix * 4, iy * 4, pmx, pmy, lam_s);
                if (best < 0 || v < best) { best = v; mx = ix * 4; my = iy * 4; }
            }
    }
    if (subpel) {
        for (int step = 2; step >= 1; step--) {
            int cx = mx, cy = my;
            for (int dy = -1; dy <= 1; dy++)
                for (int dx = -1; dx <= 1; dx++) {
                    if (!dx && !dy) continue;
                    int tx = cx + dx * step, ty = cy + dy * step;
                    long v = sad_mv(s, bx, by, src8, tx, ty, pmx, pmy, lam_s);
                    if (v < best) { best = v; mx = tx; my = ty; }
                }
        }
    }
    *bmx = mx;
    *bmy = my;
}

/* ---------------------------------------------------------------- deblocking */
static const uint8_t ALPHA[52] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 4, 5, 6, 7, 8, 9, 10, 12, 13, 15, 17, 20, 22, 25, 28,
                                  32, 36, 40, 45, 50, 56, 63, 71, 80, 90, 101, 113, 127, 144, 162, 182, 203, 226, 255, 255};
static const uint8_t BETA[52] = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 6, 6, 7, 7, 8, 8,
                                 9, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15, 16, 16, 17, 17, 18, 18};
static const uint8_t TC0[52][3] = {
    {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0},
    {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 0}, {0, 0, 1}, {0, 0, 1}, {0, 0, 1}, {0, 0, 1}, {0, 1, 1}, {0, 1, 1}, {1, 1, 1},
    {1, 1, 1}, {1, 1, 1}, {1, 1, 1}, {1, 1, 2}, {1, 1, 2}, {1, 1, 2}, {1, 1, 2}, {1, 2, 3}, {1, 2, 3}, {2, 2, 3}, {2, 2, 4}, {2, 3, 4},
    {2, 3, 4}, {3, 3, 5}, {3, 4, 6}, {3, 4, 6}, {4, 5, 7}, {4, 5, 8}, {4, 6, 9}, {5, 7, 10}, {6, 8, 11}, {6, 8, 13}, {7, 10, 14},
    {8, 11, 16}, {9, 12, 18}, {10, 13, 20}, {11, 15, 23}, {13, 17, 25}};

static void filter_line(uint8_t *p, int step, int bS, int qpav) {   /* p points at q0; samples p[-step] = p0 ... */
    int idx = CLIPQP(qpav);
    int alpha = ALPHA[idx], beta = BETA[idx];
    int p0 = p[-step], p1 = p[-2 * step], p2 = p[-3 * step], p3 = p[-4 * step];
    int q0 = p[0], q1 = p[step], q2 = p[2 * step], q3 = p[3 * step];
    if (!(abs(p0 - q0) < alpha && abs(p1 - p0) < beta && abs(q1 - q0) < beta)) return;
    int ap = abs(p2 - p0), aq = abs(q2 - q0);
    if (bS < 4) {
        int tc0 = TC0[idx][bS - 1], tc = tc0 + (ap < beta) + (aq < beta);
        int d = (((q0 - p0) * 4) + (p1 - q1) + 4) >> 3;
        d = d < -tc ? -tc : (d > tc ? tc : d);
        p[-step] = (uint8_t)CLIP255(p0 + d);
        p[0] = (uint8_t)CLIP255(q0 - d);
        if (ap < beta) {
            int e = (p2 + ((p0 + q0 + 1) >> 1) - (p1 * 2)) >> 1;
            e = e < -tc0 ? -tc0 : (e > tc0 ? tc0 : e);
            p[-2 * step] = (uint8_t)(p1 + e);
        }
        if (aq < beta) {
            int e = (q2 + ((p0 + q0 + 1) >> 1) - (q1 * 2)) >> 1;
            e = e < -tc0 ? -tc0 : (e > tc0 ? tc0 : e);
            p[step] = (uint8_t)(q1 + e);
        }
    } else {
        int small = abs(p0 - q0) < ((alpha >> 2) + 2);
        if (ap < beta && small) {
            p[-step] = (uint8_t)((p2 + 2 * p1 + 2 * p0 + 2 * q0 + q1 + 4) >> 3);
            p[-2 * step] = (uint8_t)((p2 + p1 + p0 + q0 + 2) >> 2);
            p[-3 * step] = (uint8_t)((2 * p3 + 3 * p2 + p1 + p0 + q0 + 4) >> 3);
        } else p[-step] = (uint8_t)((2 * p1 + p0 + q1 + 2) >> 2);
        if (aq < beta && small) {
            p[0] = (uint8_t)((p1 + 2 * p0 + 2 * q0 + 2 * q1 + q2 + 4) >> 3);
            p[step] = (uint8_t)((p0 + q0 + q1 + q2 + 2) >> 2);
            p[2 * step] = (uint8_t)((2 * q3 + 3 * q2 + q1 + q0 + p0 + 4) >> 3);
        } else p[0] = (uint8_t)((2 * q1 + q0 + p1 + 2) >> 2);
    }
}

static int edge_bs(const sl *s, int ax, int ay, int bx, int by, int mb_edge) {
    int a = ay * s->bw + ax, b = by * s->bw + bx;
    if (s->mode[a] == 2 || s->mode[b] == 2) return mb_edge ? 4 : 3;
    if (s->nnz[a] || s->nnz[b]) return 2;
    if (abs(s->mvx[a] - s->mvx[b]) >= 4 || abs(s->mvy[a] - s->mvy[b]) >= 4) return 1;
    return 0;
}

static void deblock(sl *s) {
    int W = s->W;
    for (int by = 0; by < s->bh; by++)                           /* vertical edges */
        for (int bx = 1; bx < s->bw; bx++) {
            int bS = edge_bs(s, bx - 1, by, bx, by, (bx & 1) == 0);
            if (!bS) continue;
            int qpav = (s->bqp[by * s->bw + bx - 1] + s->bqp[by * s->bw + bx] + 1) >> 1;
            for (int j = 0; j < 8; j++) filter_line(s->cur + (by * 8 + j) * W + bx * 8, 1, bS, qpav);
        }
    for (int by = 1; by < s->bh; by++)                           /* horizontal edges */
        for (int bx = 0; bx < s->bw; bx++) {
            int bS = edge_bs(s, bx, by - 1, bx, by, (by & 1) == 0);
            if (!bS) continue;
            int qpav = (s->bqp[(by - 1) * s->bw + bx] + s->bqp[by * s->bw + bx] + 1) >> 1;
            for (int i = 0; i < 8; i++) filter_line(s->cur + by * 8 * W + bx * 8 + i, W, bS, qpav);
        }
}

/* ---------------------------------------------------------------- slice setup */
static int sl_open(sl *s, const sl2_cfg *cfg, const uint8_t *src, const uint8_t *ref, int slice, int intra_slice, int qp, const int8_t *dqp) {
    tables_init();
    memset(s, 0, sizeof *s);
    s->cfg = cfg; s->W = cfg->W; s->SH = cfg->SH; s->tools = cfg->tools; s->y0 = slice * cfg->SH;
    s->bw = cfg->W / 8; s->bh = cfg->SH / 8; s->mbw = cfg->W / 16;
    s->src = src; s->ref = ref; s->intra_slice = intra_slice || !ref; s->qp = qp; s->dqp = dqp; s->has_dqp = dqp != NULL;
    s->keep = 64;
    int nb = s->bw * s->bh;
    s->cur = (uint8_t *)calloc((size_t)s->W * s->SH, 1);
    s->mode = (uint8_t *)calloc(nb, 1); s->imode = (uint8_t *)calloc(nb, 1); s->nnz = (uint8_t *)calloc(nb, 1);
    s->coded = (uint8_t *)calloc(nb, 1); s->bqp = (uint8_t *)calloc(nb, 1);
    s->mvx = (int16_t *)calloc(nb, sizeof(int16_t)); s->mvy = (int16_t *)calloc(nb, sizeof(int16_t));
    ctx_init(&s->cx);
    return s->cur && s->mode && s->mvx ? 0 : -1;
}

static void sl_close(sl *s) {
    free(s->cur); free(s->mode); free(s->imode); free(s->nnz); free(s->coded); free(s->bqp); free(s->mvx); free(s->mvy);
}

static void store_block(sl *s, int bx, int by, const cand *b, int qp) {
    int i = by * s->bw + bx;
    s->mode[i] = (uint8_t)b->kind; s->imode[i] = (uint8_t)b->imode; s->nnz[i] = (uint8_t)b->cbf; s->coded[i] = 1; s->bqp[i] = (uint8_t)qp;
    s->mvx[i] = (int16_t)(b->kind == 2 ? 0 : b->mvx); s->mvy[i] = (int16_t)(b->kind == 2 ? 0 : b->mvy);
    for (int j = 0; j < 8; j++) memcpy(s->cur + (by * 8 + j) * s->W + bx * 8, b->rec + j * 8, 8);
}

/* ---------------------------------------------------------------- encoder */
int sl2_encode_slice(const sl2_cfg *cfg, const uint8_t *src, const uint8_t *ref, uint8_t *recon, int slice, int intra_slice,
                     int qp, const int8_t *dqp, int keep, uint8_t *out, int cap) {
    sl s;
    if (sl_open(&s, cfg, src, ref, slice, intra_slice, qp, dqp)) return -1;
    s.keep = keep;
    sl2_st.encodes++;
    coder c;
    uint8_t *buf = (uint8_t *)malloc((size_t)cap + 16);
    rc_init_enc(&c, buf, cap, !(cfg->tools & SL2_T_CTX));
    int rdo = cfg->tools & SL2_T_RDO;
    for (int mby = 0; mby < s.bh / 2; mby++)
        for (int mbx = 0; mbx < s.bw / 2; mbx++) {
            int dq = mb_dqp(&s, mbx * 2, mby * 2);
            if (s.has_dqp) syn_dqp(&c, &s.cx, &dq);
            for (int k = 0; k < 4; k++) {
                int bx = mbx * 2 + (k & 1), by = mby * 2 + (k >> 1);
                int bq_ = CLIPQP(s.qp + dq);
                uint8_t src8[64];
                fetch_src(&s, bx, by, src8);
                int pmx = 0, pmy = 0;
                cand best, t;
                memset(&best, 0, sizeof best);
                int have = 0;
                if (!s.intra_slice) mv_pred(&s, bx, by, &pmx, &pmy);
                if (!s.intra_slice) {
                    int mx, my;
                    motion_search(&s, bx, by, bq_, src8, pmx, pmy, &mx, &my);
                    if (rdo) {
                        memset(&t, 0, sizeof t); t.kind = 0;
                        eval_cand(&s, bx, by, bq_, src8, &t, pmx, pmy, 1);
                        best = t; have = 1;
                        for (int z = 0; z < 2; z++) {
                            memset(&t, 0, sizeof t); t.kind = 1; t.mvx = mx; t.mvy = my;
                            eval_cand(&s, bx, by, bq_, src8, &t, pmx, pmy, z);
                            if (!have || t.J < best.J) { best = t; have = 1; }
                        }
                    } else {                                      /* SAD rules */
                        uint8_t pr[64];
                        mc_block(&s, bx, by, pmx, pmy, pr);
                        long sk = sad8(src8, pr);
                        if (sk < 40 + 4 * bq_) { memset(&t, 0, sizeof t); t.kind = 0; eval_cand(&s, bx, by, bq_, src8, &t, pmx, pmy, 1); best = t; have = 1; }
                        else { memset(&t, 0, sizeof t); t.kind = 1; t.mvx = mx; t.mvy = my; eval_cand(&s, bx, by, bq_, src8, &t, pmx, pmy, 0); best = t; have = 1; }
                    }
                }
                /* intra candidates */
                int nmodes = (cfg->tools & SL2_T_INTRA) ? 4 : 1;
                if (rdo || s.intra_slice) {
                    for (int m = 0; m < nmodes; m++) {
                        if (!intra_ok(&s, bx, by, m)) continue;
                        for (int z = 0; z < 2; z++) {
                            memset(&t, 0, sizeof t); t.kind = 2; t.imode = m;
                            eval_cand(&s, bx, by, bq_, src8, &t, pmx, pmy, z);
                            if (!have || t.J < best.J) { best = t; have = 1; }
                        }
                    }
                } else {                                          /* intra only when inter is poor */
                    uint8_t pr[64];
                    mc_block(&s, bx, by, best.mvx, best.mvy, pr);
                    long sin = sad8(src8, pr);
                    int bm = -1;
                    long bs = 1L << 30;
                    for (int m = 0; m < nmodes; m++) {
                        if (!intra_ok(&s, bx, by, m)) continue;
                        intra_pred(&s, bx, by, m, pr);
                        long v = sad8(src8, pr);
                        if (v < bs) { bs = v; bm = m; }
                    }
                    if (bm >= 0 && bs + 64 + bq_ * 4 < sin) {
                        memset(&t, 0, sizeof t); t.kind = 2; t.imode = bm;
                        eval_cand(&s, bx, by, bq_, src8, &t, pmx, pmy, 0);
                        best = t;
                    }
                }
                /* code the chosen candidate for real */
                syn_block(&c, &s, &s.cx, bx, by, &best, pmx, pmy);
                store_block(&s, bx, by, &best, bq_);
                sl2_st.kind_cnt[best.kind]++;
                if (best.kind == 1 && (best.mvx != pmx || best.mvy != pmy)) sl2_st.kind_cnt[3]++;
                if (best.kind == 1 && best.cbf) sl2_st.kind_cnt[4]++;
                if (best.kind == 2 && best.cbf) sl2_st.kind_cnt[5]++;
            }
        }
    int n = rc_finish(&c);
    int ok = !c.overflow;
    sl2_st.bins += c.nbins;
    if (ok) {
        if (cfg->tools & SL2_T_DEBLOCK) deblock(&s);
        for (int y = 0; y < s.SH; y++) memcpy(recon + (s.y0 + y) * s.W, s.cur + y * s.W, s.W);
    }
    /* header: byte 0 = type (1 bit), qp (6 bits), has_dqp (1 bit) */
    int total = -1;
    if (ok && n + 1 <= cap) {
        out[0] = (uint8_t)(((s.intra_slice ? 1 : 0) << 7) | (qp << 1) | (s.has_dqp ? 1 : 0));
        memcpy(out + 1, buf, n);
        total = n + 1;
    }
    free(buf);
    sl_close(&s);
    return total;
}

int sl2_encode_slice_budget(const sl2_cfg *cfg, const uint8_t *src, const uint8_t *ref, uint8_t *recon, int slice, int intra_slice,
                            int budget, const int8_t *dqp, uint8_t *out, int cap, int *qp_out, int *nenc_out) {
    int nenc = 0, sz;
    int lo = 0, hi = 51;
    int bigcap = cap > 65536 ? cap : 65536;
    uint8_t *tmp = (uint8_t *)malloc((size_t)bigcap);
    int keep = 64;
    sz = sl2_encode_slice(cfg, src, ref, recon, slice, intra_slice, 51, dqp, 64, tmp, bigcap);
    nenc++;
    int qp = 51;
    if (sz > budget) {                                           /* truncate coefficients at QP 51 */
        int klo = 0, khi = 64;                                   /* smallest keep that does not fit is khi; find the largest that fits */
        int ks = sl2_encode_slice(cfg, src, ref, recon, slice, intra_slice, 51, dqp, 0, tmp, bigcap);
        nenc++;
        if (ks > budget) { keep = 0; sz = ks; }                  /* even without any coefficient the slice is over: report the size */
        else {
            while (khi - klo > 1) {
                int mid = (klo + khi) / 2;
                int m = sl2_encode_slice(cfg, src, ref, recon, slice, intra_slice, 51, dqp, mid, tmp, bigcap);
                nenc++;
                if (m <= budget) klo = mid; else khi = mid;
            }
            keep = klo;
        }
    } else {
        while (lo < hi) {
            int mid = (lo + hi) / 2;
            int m = sl2_encode_slice(cfg, src, ref, recon, slice, intra_slice, mid, dqp, 64, tmp, bigcap);
            nenc++;
            if (m <= budget) hi = mid; else lo = mid + 1;
        }
        qp = lo;
    }
    sz = sl2_encode_slice(cfg, src, ref, recon, slice, intra_slice, qp, dqp, keep, out, cap);
    nenc++;
    free(tmp);
    if (qp_out) *qp_out = qp;
    if (nenc_out) *nenc_out = nenc;
    return sz;
}

/* ---------------------------------------------------------------- decoder */
int sl2_decode_slice(const sl2_cfg *cfg, const uint8_t *ref, uint8_t *recon, int slice, const uint8_t *in, int len) {
    if (len < 1) return -1;
    int intra_slice = in[0] >> 7, qp = (in[0] >> 1) & 63, has_dqp = in[0] & 1;
    if (qp > 51) return -1;
    sl s;
    if (sl_open(&s, cfg, NULL, ref, slice, intra_slice, qp, NULL)) return -1;
    s.has_dqp = has_dqp;
    if (!ref) s.intra_slice = 1;
    coder c;
    rc_init_dec(&c, in + 1, len - 1, !(cfg->tools & SL2_T_CTX));
    for (int mby = 0; mby < s.bh / 2; mby++)
        for (int mbx = 0; mbx < s.bw / 2; mbx++) {
            int dq = 0;
            if (has_dqp) syn_dqp(&c, &s.cx, &dq);
            for (int k = 0; k < 4; k++) {
                int bx = mbx * 2 + (k & 1), by = mby * 2 + (k >> 1);
                int bq_ = CLIPQP(s.qp + dq);
                int pmx = 0, pmy = 0;
                if (!s.intra_slice) mv_pred(&s, bx, by, &pmx, &pmy);
                cand b;
                memset(&b, 0, sizeof b);
                syn_block(&c, &s, &s.cx, bx, by, &b, pmx, pmy);
                if (b.kind == 0) { b.mvx = pmx; b.mvy = pmy; }
                uint8_t pred[64];
                block_pred(&s, bx, by, &b, pred);
                if (b.cbf) recon_from_levels(&s, bq_, pred, b.lev, b.rec); else memcpy(b.rec, pred, 64);
                store_block(&s, bx, by, &b, bq_);
            }
        }
    if (cfg->tools & SL2_T_DEBLOCK) deblock(&s);
    for (int y = 0; y < s.SH; y++) memcpy(recon + (s.y0 + y) * s.W, s.cur + y * s.W, s.W);
    sl_close(&s);
    return 0;
}
