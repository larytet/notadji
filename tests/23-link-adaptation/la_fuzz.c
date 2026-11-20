/* Random messages under UBSan and ASan; invariants of the controller output. */
#include <stdio.h>
#include <stdlib.h>
#include "link_adapt.h"

static uint32_t lcg(uint32_t *s) { *s = *s * 1664525u + 1013904223u; return *s >> 8; }

int main(void)
{
    la_cfg c;
    la_state s;
    la_out o;
    la_fb fb;
    uint32_t r = 12345, t = 0;
    long n, changes = 0;
    int run;
    for (run = 0; run < 4; run++) {
        la_default_cfg(&c);
        if (run == 1) { c.mcs_min = 2; c.mcs_max = 6; }
        if (run == 2) { c.per_target_ppm = 100000; c.olla_step_udb = 1000000; }
        if (run == 3) { c.up_dwell_us = 0; c.pwr_dwell_us = 0; c.n_mcs = 3; c.mcs_max = 2; }
        t = 0xFFF00000u;                     /* the clock wraps during the run */
        la_init(&s, &c, t);
        for (n = 0; n < 500000; n++) {
            t += 1 + (lcg(&r) % 3000);
            if (lcg(&r) % 50 == 0) la_tick(&s, &c, t + 20000, &o);
            fb.t_us = t;
            fb.snr_x10 = (int16_t)((int32_t)(lcg(&r) % 700) - 150);
            fb.n_slices = (uint8_t)(lcg(&r) % 256);
            fb.n_lost = (uint8_t)(lcg(&r) % 256);
            fb.mcs_rec = (lcg(&r) % 4 == 0) ? (uint8_t)(lcg(&r) % 20) : LA_NO_REC;
            la_on_feedback(&s, &c, &fb, &o);
            if (o.mcs < c.mcs_min || o.mcs > c.mcs_max || o.pwr_x4 < c.pwr_min_x4 || o.pwr_x4 > c.pwr_max_x4 ||
                o.rung > 2 || s.offset_udb > 10000000 || s.offset_udb < -(int32_t)c.olla_neg_limit_udb) {
                printf("invariant violated: run %d msg %ld mcs %u pwr %d offset %d\n", run, n, o.mcs, o.pwr_x4, s.offset_udb);
                return 1;
            }
            changes += o.changed;
        }
    }
    printf("%ld changes, no violation\n", changes);
    return 0;
}
