// SRC:
/* T33-01: HAL sim sequencer reproduces the module 10 frame-level behaviour (tests T10-02, 03, 04, 05, 08) */
#include "tcheck.h"
#include "hal_sim.h"

static void wr_entry(hal_sim *s, uint32_t idx, uint32_t time, uint32_t act, uint32_t arg)
{
    uint64_t e = ((uint64_t)time << 24) | ((uint64_t)act << 16) | arg;
    hal_wr(&s->hal, SEQ_WR_ADDR, idx);
    hal_wr(&s->hal, SEQ_WR_DATA_LO, (uint32_t)e);
    hal_wr(&s->hal, SEQ_WR_DATA_HI, (uint32_t)(e >> 32));
    hal_wr(&s->hal, SEQ_WR_STROBE, 1);
}

TEST(reset_state)   /* T10-04 */
{
    hal_sim s; hal_sim_init(&s, 1);
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_LEN), 1000);
    hal_sim_clocks(&s, 3500);
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_CNT), 3);
    CHECK_EQ(hal_rd(&s.hal, SEQ_TICK), 500);
}

TEST(min_frame)     /* T10-08 */
{
    uint32_t times[3] = {0, 5, 16}, i;
    for (i = 0; i < 3; i++) {
        hal_sim s; hal_sim_init(&s, 1);
        wr_entry(&s, 0, times[i], SEQ_ACT_END, 0);
        hal_wr(&s.hal, SEQ_COMMIT, 1);
        hal_sim_clocks(&s, 1000);                    /* finish the safe frame, swap */
        CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_LEN), 16);
        CHECK_EQ(hal_rd(&s.hal, SEQ_STATUS) & 1u, 1);
    }
    {
        hal_sim s; hal_sim_init(&s, 1);
        wr_entry(&s, 0, 100, SEQ_ACT_END, 0);
        hal_wr(&s.hal, SEQ_COMMIT, 1);
        hal_sim_clocks(&s, 1000);
        CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_LEN), 100);
    }
}

TEST(stall_counts_missed)  /* T10-02 */
{
    hal_sim s; hal_sim_init(&s, 1);
    uint32_t f0;
    wr_entry(&s, 0, 200, SEQ_ACT_END, 0);
    hal_wr(&s.hal, SEQ_COMMIT, 1);
    hal_sim_clocks(&s, 1000);                        /* safe frame ends, table swapped in, missed = 0 */
    CHECK_EQ(hal_rd(&s.hal, SEQ_MISSED), 0);
    f0 = hal_rd(&s.hal, SEQ_FRAME_CNT);
    hal_sim_clocks(&s, 200u * 50u);
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_CNT) - f0, 50);
    CHECK_EQ(hal_rd(&s.hal, SEQ_MISSED), 50);
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_LEN), 200);    /* the table keeps replaying */
}

TEST(commit_timing)  /* T10-03: commit one clock before END takes effect at this frame end, later waits one frame */
{
    hal_sim s; hal_sim_init(&s, 1);
    wr_entry(&s, 0, 100, SEQ_ACT_END, 0);
    hal_wr(&s.hal, SEQ_COMMIT, 1);
    hal_sim_clocks(&s, 1000);                        /* active table: 100-clock frames */
    /* write a 50-clock table into the inactive bank mid-frame: no effect on the running frame */
    hal_sim_clocks(&s, 10);
    wr_entry(&s, 0, 50, SEQ_ACT_END, 0);
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_LEN), 100);
    hal_sim_clocks(&s, 80);                          /* tick = 90 */
    hal_wr(&s.hal, SEQ_COMMIT, 1);                   /* commit at tick 90 <= 98 */
    hal_sim_clocks(&s, 10);                          /* frame ends */
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_LEN), 50);
    /* late commit: at tick len-1 (the END clock) it must not apply */
    wr_entry(&s, 0, 70, SEQ_ACT_END, 0);
    hal_sim_clocks(&s, 49);                          /* tick 49 = len - 1 */
    hal_wr(&s.hal, SEQ_COMMIT, 1);
    hal_sim_clocks(&s, 1);
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_LEN), 50);
    hal_sim_clocks(&s, 50);
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_LEN), 70);
}

TEST(force_safe_readback)
{
    hal_sim s; hal_sim_init(&s, 1);
    hal_wr(&s.hal, SEQ_FORCE_SAFE, 1);
    CHECK_EQ(hal_rd(&s.hal, SEQ_STATUS) & 4u, 4);
    hal_wr(&s.hal, SEQ_FORCE_SAFE, 0);
    CHECK_EQ(hal_rd(&s.hal, SEQ_STATUS) & 4u, 0);
}

TEST(time_conversion)
{
    hal_sim s; hal_sim_init(&s, 1);
    hal_sim_advance_us(&s, 1000);                    /* 1 ms = 300000 core cycles = 200000 fabric clocks */
    CHECK_EQ(hal_now_us(&s.hal), 1000);
    CHECK_EQ(hal_rd(&s.hal, SEQ_FRAME_CNT), 200);    /* 200000 / 1000 */
}

TEST(retained_ram_cut)
{
    hal_sim s; hal_sim_init(&s, 1);
    uint8_t a[8] = {1,2,3,4,5,6,7,8}, b[8];
    s.ret_budget = 5;
    s.hal.ret_write(&s.hal, 0, a, 8);
    s.hal.ret_read(&s.hal, 0, b, 8);
    CHECK(s.ret_cut);
    CHECK_EQ(b[4], 5); CHECK_EQ(b[5], 0);
}

TEST(flash_semantics)
{
    hal_sim s; hal_sim_init(&s, 1);
    uint8_t d[4] = {0xF0, 0x0F, 0xFF, 0x00}, r[4];
    CHECK_EQ(s.hal.fl_program(&s.hal, 0, d, 4), 0);
    d[0] = 0x3C;
    CHECK_EQ(s.hal.fl_program(&s.hal, 0, d, 1), 0);  /* programming only clears bits */
    s.hal.fl_read(&s.hal, 0, r, 4);
    CHECK_EQ(r[0], 0x30); CHECK_EQ(r[3], 0x00);
    CHECK_EQ(s.hal.fl_erase(&s.hal, 0), 0);
    s.hal.fl_read(&s.hal, 0, r, 4);
    CHECK_EQ(r[0], 0xFF);
    s.fl_budget = 0;
    CHECK(s.hal.fl_program(&s.hal, 0, d, 4) != 0);
    CHECK(s.fl_cut);
    CHECK(s.hal.fl_erase(&s.hal, 0) != 0);           /* power is gone */
    hal_sim_power_cycle(&s);
    CHECK_EQ(s.hal.fl_erase(&s.hal, 0), 0);
}

int main(void)
{
    RUN(reset_state); RUN(min_frame); RUN(stall_counts_missed); RUN(commit_timing); RUN(force_safe_readback);
    RUN(time_conversion); RUN(retained_ram_cut); RUN(flash_semantics);
    TC_DONE();
}
