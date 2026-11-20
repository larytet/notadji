/* start_rule - scan-out start time from the measured decode lateness per slice (design/27-display-sync.md section 1.5).
 * Portable C99, integer arithmetic only, no heap. Times in microseconds, internal Q4. */
#ifndef START_RULE_H
#define START_RULE_H

#include <stdint.h>

#define SR_MAX_SLICES 64

typedef struct {
    int32_t  mean_q4[SR_MAX_SLICES];     /* EWMA of x_k = T_k - a_k t_line */
    uint32_t var_q8[SR_MAX_SLICES];      /* EWMA of (x_k - mean)^2 */
    uint8_t  seen[SR_MAX_SLICES];
    uint8_t  n_slices;
} sr_state;

void     sr_init(sr_state *s, uint8_t n_slices);
/* one measurement: slice k was decoded t_us after the frame timing; its first line is scanned line_us after the scan-out start */
void     sr_report(sr_state *s, uint8_t k, int32_t t_us, int32_t line_us);
/* the smallest start offset L (us) that keeps the late-slice probability below the target: max over slices of mean + z sigma, plus margin;
 * z_q8: the one-sided Gaussian quantile in Q8 (794 = 3.1 for 1e-3) */
int32_t  sr_start(const sr_state *s, int32_t z_q8, int32_t margin_us);

#endif
