/* dpd_fw - least-squares solution of the DPD coefficients from the dpd_corr accumulators (design/26-papr-dpd.md section 2).
 * Portable C99, single-precision floating point (an FPU is assumed), no heap, no library calls other than none. */
#ifndef DPD_FW_H
#define DPD_FW_H

#include <stdint.h>

#define DPD_NT 9                         /* coefficients: 3 orders x 3 memory taps */
#define DPD_NACC 54                      /* 45 matrix entries (upper triangle) + 9 vector entries */

typedef enum { DPD_OK = 0, DPD_ERR_N = 1, DPD_ERR_SINGULAR = 2, DPD_ERR_RANGE = 3 } dpd_status;

/* acc_re / acc_im: the 54 accumulators in dpd_corr order (R[p][q] for p <= q, row by row, then c[0..8]); n: samples accumulated;
 * ridge: relative diagonal loading (for example 1e-4); a_re / a_im: the coefficients in Q4.12 (3 j + m order). */
dpd_status dpd_solve(const int64_t acc_re[DPD_NACC], const int64_t acc_im[DPD_NACC], uint32_t n, float ridge,
                     int16_t a_re[DPD_NT], int16_t a_im[DPD_NT]);

/* a <- a + mu (a_new - a) with mu = 1 / 2^shift, in Q4.12; returns the largest absolute change */
int32_t dpd_update(int16_t a_re[DPD_NT], int16_t a_im[DPD_NT], const int16_t n_re[DPD_NT], const int16_t n_im[DPD_NT], uint8_t shift);

/* delay and complex gain of y (the observation) against u over lags -max_lag..max_lag; gain in Q15 (y ~ gain u delayed by lag) */
void dpd_align(const int16_t *u_iq, const int16_t *y_iq, uint32_t n, int32_t max_lag, int32_t *lag, int32_t *g_re_q15, int32_t *g_im_q15);

#endif
