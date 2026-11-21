#include "hal_sim.h"

static uint32_t entry_time(uint64_t e) { return (uint32_t)((e >> 24) & 0xFFFFFFu); }
static uint32_t entry_act(uint64_t e) { return (uint32_t)((e >> 16) & 0xFFu); }

uint32_t hal_sim_frame_len(const hal_sim *s)
{
    uint32_t i;
    for (i = 0; i < SEQ_DEPTH; i++) {
        uint64_t e = s->bank[s->active][i];
        if (entry_act(e) == SEQ_ACT_END) {
            uint32_t t = entry_time(e);
            return t > SEQ_MIN_FRAME ? t : SEQ_MIN_FRAME;
        }
    }
    return 0;
}

static void log_wr(hal_sim *s, uint32_t addr, uint32_t v)
{
    sim_wr *w = &s->log[s->log_n % SIM_LOG_N];
    w->cycle = s->core_cycles; w->addr = addr; w->val = v;
    s->log_n++;
}

static uint32_t sim_rd32(hal_t *h, uint32_t a)
{
    hal_sim *s = (hal_sim *)h->ctx;
    if (s->reg_cost) hal_sim_burn(s, s->reg_cost);
    switch (a) {
    case SEQ_FRAME_CNT: return s->frame_cnt;
    case SEQ_MISSED:    return s->missed;
    case SEQ_TICK:      return s->tick;
    case SEQ_STATUS:    return (uint32_t)s->active | ((uint32_t)s->pending << 1) | ((uint32_t)s->forced << 2);
    case SEQ_FRAME_LEN: return hal_sim_frame_len(s);
    case SEQ_FORCE_SAFE: return s->forced;
    default: break;
    }
    return a / 4u < SIM_REGS ? s->regs[a / 4u] : 0u;
}

static void sim_wr32(hal_t *h, uint32_t a, uint32_t v)
{
    hal_sim *s = (hal_sim *)h->ctx;
    if (s->reg_cost) hal_sim_burn(s, s->reg_cost);
    log_wr(s, a, v);
    switch (a) {
    case SEQ_WR_ADDR:    s->wr_addr = v; return;
    case SEQ_WR_DATA_LO: s->wr_lo = v; return;
    case SEQ_WR_DATA_HI: s->wr_hi = v & 0xFFFFu; return;
    case SEQ_WR_STROBE:
        if (v & 1u) {
            /* write into the inactive bank only (module 10) */
            s->bank[s->active ^ 1u][s->wr_addr % SEQ_DEPTH] = (uint64_t)s->wr_lo | ((uint64_t)s->wr_hi << 32);
        }
        return;
    case SEQ_COMMIT:
        if (v & 1u) {
            s->commit_req = 1; s->commits++; s->last_commit_tick = (int32_t)s->tick;
        }
        return;
    case SEQ_FORCE_SAFE: s->forced = (uint8_t)(v & 1u); return;
    default: break;
    }
    if (a / 4u < SIM_REGS) s->regs[a / 4u] = v;
}

static uint64_t sim_cycles(hal_t *h) { return ((hal_sim *)h->ctx)->core_cycles; }

static void sim_ret_read(hal_t *h, uint32_t off, void *dst, uint32_t n)
{
    hal_sim *s = (hal_sim *)h->ctx;
    if ((uint64_t)off + n > SIM_RET_SIZE) { memset(dst, 0, n); return; }
    memcpy(dst, s->ret + off, n);
}

static void sim_ret_write(hal_t *h, uint32_t off, const void *src, uint32_t n)
{
    hal_sim *s = (hal_sim *)h->ctx;
    uint32_t i;
    if ((uint64_t)off + n > SIM_RET_SIZE) return;
    for (i = 0; i < n; i++) {
        if (s->ret_budget == 0) { s->ret_cut = true; return; }
        s->ret[off + i] = ((const uint8_t *)src)[i];
        if (s->ret_budget > 0) s->ret_budget--;
    }
}

/* Flash: one operation = one program or erase call. A cut during an operation completes only part of it (program: the first half of
 * the bytes, erase: the first half of the sector erased, the rest left unchanged); after the cut every operation fails. */
static int sim_fl_read(hal_t *h, uint32_t off, void *dst, uint32_t n)
{
    hal_sim *s = (hal_sim *)h->ctx;
    if ((uint64_t)off + n > SIM_FLASH_SIZE) return -1;
    memcpy(dst, s->flash + off, n);
    return 0;
}

static int sim_fl_program(hal_t *h, uint32_t off, const void *src, uint32_t n)
{
    hal_sim *s = (hal_sim *)h->ctx;
    uint32_t i, m = n;
    if (s->fl_cut) return -1;
    if ((uint64_t)off + n > SIM_FLASH_SIZE) return -1;
    s->fl_ops++;
    if (s->fl_budget == 0) { s->fl_cut = true; m = n / 2; }
    else if (s->fl_budget > 0) s->fl_budget--;
    for (i = 0; i < m; i++) s->flash[off + i] &= ((const uint8_t *)src)[i];
    return s->fl_cut ? -1 : 0;
}

static int sim_fl_erase(hal_t *h, uint32_t off)
{
    hal_sim *s = (hal_sim *)h->ctx;
    uint32_t m = SIM_SECTOR;
    if (s->fl_cut) return -1;
    if (off % SIM_SECTOR || (uint64_t)off + SIM_SECTOR > SIM_FLASH_SIZE) return -1;
    s->fl_ops++;
    if (s->fl_budget == 0) { s->fl_cut = true; m = SIM_SECTOR / 2; }
    else if (s->fl_budget > 0) s->fl_budget--;
    memset(s->flash + off, 0xFF, m);
    return s->fl_cut ? -1 : 0;
}

static uint32_t sim_rng(hal_t *h)
{
    hal_sim *s = (hal_sim *)h->ctx;
    uint32_t x = s->rng_state;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    s->rng_state = x;
    return x;
}

static void sim_wdog(hal_t *h) { ((hal_sim *)h->ctx)->wdog_kicks++; }

void hal_sim_init(hal_sim *s, uint32_t seed)
{
    memset(s, 0, sizeof *s);
    s->hal.ctx = s;
    s->hal.rd32 = sim_rd32; s->hal.wr32 = sim_wr32; s->hal.cycles = sim_cycles;
    s->hal.ret_size = SIM_RET_SIZE; s->hal.ret_read = sim_ret_read; s->hal.ret_write = sim_ret_write;
    s->hal.flash_size = SIM_FLASH_SIZE; s->hal.flash_sector = SIM_SECTOR;
    s->hal.fl_read = sim_fl_read; s->hal.fl_program = sim_fl_program; s->hal.fl_erase = sim_fl_erase;
    s->hal.rng = sim_rng; s->hal.wdog_kick = sim_wdog;
    s->rng_state = seed ? seed : 0x2545F491u;
    s->ret_budget = -1; s->fl_budget = -1;
    memset(s->flash, 0xFF, sizeof s->flash);
    /* reset state of the sequencer: bank 0 holds the safe table (a single END at 1000 clocks) */
    s->bank[0][0] = ((uint64_t)1000u << 24) | ((uint64_t)SEQ_ACT_END << 16);
}

void hal_sim_power_cycle(hal_sim *s)
{
    s->ret_budget = -1; s->ret_cut = false;
    s->fl_budget = -1; s->fl_cut = false;
}

void hal_sim_burn(hal_sim *s, uint64_t cyc)
{
    uint64_t f;
    s->core_cycles += cyc;
    f = s->fab_rem + cyc * 2u;
    s->fab_rem = f % 3u;
    hal_sim_clocks(s, (uint32_t)(f / 3u));
}

void hal_sim_advance_us(hal_sim *s, uint32_t us) { hal_sim_burn(s, (uint64_t)us * HAL_CORE_MHZ); }

/* One fabric clock of the sequencer: tick, and at the clock in which END executes (tick = len - 1) the frame ends.
 * A commit written during a clock becomes pending after it (registered), so it takes effect at this frame end only if it was written
 * at least one clock before the END clock (module 10); one written in the END clock itself stays pending for the next frame end. */
static void seq_clock(hal_sim *s)
{
    uint32_t len = hal_sim_frame_len(s);
    uint8_t cr = s->commit_req;
    s->commit_req = 0;
    if (len != 0 && s->tick + 1u >= len) {
        s->tick = 0;
        s->frame_cnt++;
        if (s->pending) { s->active ^= 1u; s->pending = cr; s->missed = 0; }
        else {
            if (s->missed != 0xFFFFu) s->missed++;
            s->pending = cr;
        }
    } else {
        s->tick++;
        if (cr) s->pending = 1;
    }
}

void hal_sim_clocks(hal_sim *s, uint32_t n)
{
    while (n) {
        uint32_t len = hal_sim_frame_len(s), rem;
        if (s->commit_req) { seq_clock(s); n--; continue; }
        if (len == 0) { s->tick += n; return; }             /* no END: the frame never ends */
        rem = (s->tick + 1u >= len) ? 0u : (len - 1u) - s->tick;   /* plain ticks before the END clock */
        if (n <= rem) { s->tick += n; return; }
        s->tick += rem; n -= rem;
        seq_clock(s); n--;
    }
}
