#include "dpd_fw.h"

typedef struct { float re, im; } cf;

static cf cmul(cf a, cf b) { cf r; r.re = a.re * b.re - a.im * b.im; r.im = a.re * b.im + a.im * b.re; return r; }
static cf cconj(cf a) { cf r; r.re = a.re; r.im = -a.im; return r; }
static cf csub(cf a, cf b) { cf r; r.re = a.re - b.re; r.im = a.im - b.im; return r; }

/* Newton iteration, enough for the diagonal pivots (positive, finite) */
static float fsqrt(float x)
{
    float y;
    int i;
    if (x <= 0.0f) return 0.0f;
    y = x > 1.0f ? x : 1.0f;
    for (i = 0; i < 40; i++) y = 0.5f * (y + x / y);
    return y;
}

static int16_t q12(float v, int *clipped)
{
    float s = v * 4096.0f;
    if (s > 32767.0f) { *clipped = 1; return 32767; }
    if (s < -32768.0f) { *clipped = 1; return -32768; }
    return (int16_t)(s >= 0.0f ? s + 0.5f : s - 0.5f);
}

dpd_status dpd_solve(const int64_t acc_re[DPD_NACC], const int64_t acc_im[DPD_NACC], uint32_t n, float ridge,
                     int16_t a_re[DPD_NT], int16_t a_im[DPD_NT])
{
    cf A[DPD_NT][DPD_NT], L[DPD_NT][DPD_NT], c[DPD_NT], z[DPD_NT], x[DPD_NT];
    float d[DPD_NT];
    float scale, tr = 0.0f;
    int p, q, k, e = 0, clipped = 0;
    if (n == 0u) return DPD_ERR_N;
    scale = 1.0f / ((float)n * 1073741824.0f);                /* 2^-30 / n: the products are Q30 */
    for (p = 0; p < DPD_NT; p++) {
        for (q = p; q < DPD_NT; q++) {
            A[p][q].re = (float)acc_re[e] * scale;
            A[p][q].im = (float)acc_im[e] * scale;
            A[q][p] = cconj(A[p][q]);
            e++;
        }
    }
    for (p = 0; p < DPD_NT; p++) {
        c[p].re = (float)acc_re[e] * scale;
        c[p].im = (float)acc_im[e] * scale;
        e++;
        tr += A[p][p].re;
    }
    (void)tr;
    /* Jacobi scaling: the high-order basis functions are tiny next to the linear one (a factor 1e3 in amplitude), which would make the
     * system ill-conditioned for single precision; scale every column to unit diagonal, and load the diagonal relatively */
    for (p = 0; p < DPD_NT; p++) {
        d[p] = fsqrt(A[p][p].re);
        if (!(d[p] > 1e-9f)) return DPD_ERR_SINGULAR;
    }
    for (p = 0; p < DPD_NT; p++) {
        for (q = 0; q < DPD_NT; q++) {
            A[p][q].re /= d[p] * d[q];
            A[p][q].im /= d[p] * d[q];
        }
        c[p].re /= d[p];
        c[p].im /= d[p];
        A[p][p].re += ridge;
    }
    /* Cholesky A = L L^H */
    for (p = 0; p < DPD_NT; p++) {
        for (q = 0; q <= p; q++) {
            cf s = A[p][q];
            for (k = 0; k < q; k++) s = csub(s, cmul(L[p][k], cconj(L[q][k])));
            if (p == q) {
                float dd = s.re;
                if (!(dd > 1e-12f)) return DPD_ERR_SINGULAR;
                L[p][p].re = fsqrt(dd);
                L[p][p].im = 0.0f;
            } else {
                float inv = 1.0f / L[q][q].re;
                L[p][q].re = s.re * inv;
                L[p][q].im = s.im * inv;
            }
        }
        for (q = p + 1; q < DPD_NT; q++) { L[p][q].re = 0.0f; L[p][q].im = 0.0f; }
    }
    /* L z = c, then L^H x = z */
    for (p = 0; p < DPD_NT; p++) {
        cf s = c[p];
        for (k = 0; k < p; k++) s = csub(s, cmul(L[p][k], z[k]));
        z[p].re = s.re / L[p][p].re;
        z[p].im = s.im / L[p][p].re;
    }
    for (p = DPD_NT - 1; p >= 0; p--) {
        cf s = z[p];
        for (k = p + 1; k < DPD_NT; k++) s = csub(s, cmul(cconj(L[k][p]), x[k]));
        x[p].re = s.re / L[p][p].re;
        x[p].im = s.im / L[p][p].re;
    }
    for (p = 0; p < DPD_NT; p++) {
        a_re[p] = q12(x[p].re / d[p], &clipped);
        a_im[p] = q12(x[p].im / d[p], &clipped);
    }
    return clipped ? DPD_ERR_RANGE : DPD_OK;
}

int32_t dpd_update(int16_t a_re[DPD_NT], int16_t a_im[DPD_NT], const int16_t n_re[DPD_NT], const int16_t n_im[DPD_NT], uint8_t shift)
{
    int32_t worst = 0;
    int p;
    for (p = 0; p < DPD_NT; p++) {
        int32_t dr = (int32_t)n_re[p] - a_re[p];
        int32_t di = (int32_t)n_im[p] - a_im[p];
        int32_t sr = dr >= 0 ? (dr >> shift) : -((-dr) >> shift);
        int32_t si = di >= 0 ? (di >> shift) : -((-di) >> shift);
        a_re[p] = (int16_t)(a_re[p] + sr);
        a_im[p] = (int16_t)(a_im[p] + si);
        if (dr < 0) dr = -dr;
        if (di < 0) di = -di;
        if (dr > worst) worst = dr;
        if (di > worst) worst = di;
    }
    return worst;
}

void dpd_align(const int16_t *u_iq, const int16_t *y_iq, uint32_t n, int32_t max_lag, int32_t *lag, int32_t *g_re_q15, int32_t *g_im_q15)
{
    float best = -1.0f, bre = 0.0f, bim = 0.0f, bp = 1.0f;
    int32_t l, bl = 0;
    uint32_t k;
    for (l = -max_lag; l <= max_lag; l++) {
        float sre = 0.0f, sim = 0.0f, pu = 0.0f;
        for (k = 0; k < n; k++) {
            int32_t m = (int32_t)k + l;
            float ur, ui, yr, yi;
            if (m < 0 || m >= (int32_t)n) continue;
            ur = (float)u_iq[2 * k];
            ui = (float)u_iq[2 * k + 1];
            yr = (float)y_iq[2 * m];
            yi = (float)y_iq[2 * m + 1];
            sre += yr * ur + yi * ui;                     /* y conj(u) */
            sim += yi * ur - yr * ui;
            pu += ur * ur + ui * ui;
        }
        if (pu > 0.0f) {
            float mag = (sre * sre + sim * sim) / pu;
            if (mag > best) {
                best = mag;
                bl = l;
                bre = sre;
                bim = sim;
                bp = pu;
            }
        }
    }
    *lag = bl;
    *g_re_q15 = (int32_t)(bre / bp * 32768.0f + (bre >= 0.0f ? 0.5f : -0.5f));
    *g_im_q15 = (int32_t)(bim / bp * 32768.0f + (bim >= 0.0f ? 0.5f : -0.5f));
}
