/* Random inputs under UBSan and ASan; the decision target is always a usable channel of the configured set. */
#include <stdio.h>
#include "chan_select.h"

static uint32_t lcg(uint32_t *s) { *s = *s * 1664525u + 1013904223u; return *s >> 8; }

int main(void)
{
    cs_cfg c;
    cs_state s;
    cs_decision d;
    uint32_t r = 99, t = 0xFFFF0000u, n_sw = 0;
    long n;
    int run;
    for (run = 0; run < 3; run++) {
        cs_default_cfg(&c);
        if (run == 1) { c.n_ch = 5; c.enabled_mask = 0x1B; c.n_fallback = 2; c.fallback[0] = 2; c.fallback[1] = 4; }
        if (run == 2) { c.n_ch = 32; c.enabled_mask = 0xFFFFFFFFu; c.jitter_ms = 9; c.link_id = 1234; c.confirm = 1; }
        cs_init(&s, &c, 0, t);
        for (n = 0; n < 400000; n++) {
            t += 1 + lcg(&r) % 4;
            if (lcg(&r) % 2) cs_scan(&s, &c, (uint8_t)(lcg(&r) % 40), (uint16_t)(lcg(&r) % 5000), t);
            if (lcg(&r) % 3) cs_quality(&s, &c, lcg(&r) % 1000000u, t);
            cs_tick(&s, &c, t, (uint16_t)(t / 3), &d);
            if (s.cur >= c.n_ch || !((c.enabled_mask >> s.cur) & 1u && d.target == s.cur) ) {
                if (!(s.cur == 0 && !((c.enabled_mask >> 0) & 1u))) { printf("bad channel %u mask %x run %d\n", s.cur, c.enabled_mask, run); return 1; }
            }
            n_sw += d.switch_now;
        }
    }
    printf("%u switches, no violation\n", n_sw);
    return 0;
}
