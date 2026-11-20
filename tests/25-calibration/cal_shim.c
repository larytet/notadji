/* Test shim: one global calibration manager with a flat interface for ctypes. */
#include <string.h>
#include "cal_mgr.h"

static cal_table tab;
static cal_mgr mgr;
static cal_lim lim = {1024u, 100u, 8192, 4000};

void shim_init(void) { memset(&tab, 0, sizeof tab); cal_init(&mgr, &tab); }

int shim_result(int job, const int64_t *sums, uint32_t n, uint32_t now_ms, int temp_x10, int16_t out[8])
{
    cal_sums s;
    int st;
    s.sum_i = sums[0];
    s.sum_q = sums[1];
    s.sum_ii = (uint64_t)sums[2];
    s.sum_qq = (uint64_t)sums[3];
    s.sum_iq = sums[4];
    s.n = n;
    st = (int)cal_result(&mgr, (cal_job)job, &s, &lim, now_ms, (int16_t)temp_x10);
    cal_regs(&mgr.work, out);
    return st;
}

void shim_set_lim(uint32_t min_n, uint32_t min_power, int eps_max, int dc_max)
{
    lim.min_n = min_n;
    lim.min_power_x = min_power;
    lim.eps_max = (int16_t)eps_max;
    lim.dc_max = (int16_t)dc_max;
}

int shim_estimate(const int64_t *sums, uint32_t n, int16_t out[4])
{
    cal_sums s;
    cal_coeff c;
    int st;
    s.sum_i = sums[0];
    s.sum_q = sums[1];
    s.sum_ii = (uint64_t)sums[2];
    s.sum_qq = (uint64_t)sums[3];
    s.sum_iq = sums[4];
    s.n = n;
    st = (int)cal_stats_to_coeff(&s, &lim, &c);
    out[0] = c.dc_i;
    out[1] = c.dc_q;
    out[2] = c.eps_r;
    out[3] = c.eps_i;
    return st;
}

void shim_regs(int16_t out[8]) { cal_regs(&mgr.work, out); }

static uint8_t nv_img[CAL_ENTRIES][CAL_NV_BYTES];

int shim_load(const uint8_t *img, uint16_t n)
{
    memset(nv_img, 0xFF, sizeof nv_img);
    memcpy(nv_img, img, (size_t)n * CAL_NV_BYTES);
    cal_table_load(&tab, (const uint8_t (*)[CAL_NV_BYTES])nv_img, n);
    return tab.n_bad;
}

int shim_lookup(int band, int group, int temp_x10, int *steps)
{
    uint8_t st = 0;
    int r = cal_lookup(&tab, (uint8_t)band, (uint8_t)group, (int16_t)temp_x10, &st);
    *steps = st;
    return r;
}

void shim_hop(int band, int group, int temp_x10, uint32_t now_ms) { cal_on_hop(&mgr, (uint8_t)band, (uint8_t)group, (int16_t)temp_x10, now_ms); }
int shim_tick(uint32_t now_ms, int temp_x10, int windows) { return (int)cal_tick(&mgr, now_ms, (int16_t)temp_x10, (uint8_t)windows); }
int shim_default_used(void) { return mgr.default_used; }
int shim_n_rej(void) { return (int)mgr.n_rej; }
void shim_set_gap(uint32_t gap_ms) { mgr.min_gap_ms = gap_ms; }
