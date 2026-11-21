/* hal_sim - host simulation backend of the HAL: virtual cycle counter, frame-level model of the sequencer (module 10 semantics),
 * generic registers, retained RAM and flash with fault injection, a register-write log. Test support, not target code. */
#ifndef HAL_SIM_H
#define HAL_SIM_H

#include "hal.h"

#define SIM_RET_SIZE   65536u
#define SIM_FLASH_SIZE (256u * 1024u)
#define SIM_SECTOR     4096u
#define SIM_LOG_N      8192u
#define SIM_REGS       0x4000u    /* words */

typedef struct { uint64_t cycle; uint32_t addr, val; } sim_wr;

typedef struct {
    hal_t hal;
    uint64_t core_cycles;
    uint64_t fab_rem;                       /* fabric clock remainder (fabric 200 MHz, core 300 MHz) */
    uint32_t regs[SIM_REGS];
    /* sequencer */
    uint64_t bank[2][SEQ_DEPTH];
    uint32_t wr_addr, wr_lo, wr_hi;
    uint8_t  active, pending, forced, commit_req;
    uint32_t tick, frame_cnt, missed;
    uint32_t commits;                       /* number of commit writes seen (test aid) */
    int32_t  last_commit_tick;
    /* retained RAM */
    uint8_t  ret[SIM_RET_SIZE];
    int64_t  ret_budget;                    /* bytes that may still be written before the "reset"; < 0: unlimited */
    bool     ret_cut;
    /* flash */
    uint8_t  flash[SIM_FLASH_SIZE];
    int64_t  fl_budget;                     /* flash operations before power is lost; < 0: unlimited */
    bool     fl_cut;
    uint32_t fl_ops;
    /* misc */
    uint32_t rng_state;
    uint32_t wdog_kicks;
    uint32_t reg_cost;                      /* core cycles charged per register access (0: free) */
    sim_wr   log[SIM_LOG_N];
    uint32_t log_n;                         /* total writes logged (index modulo SIM_LOG_N) */
} hal_sim;

void hal_sim_init(hal_sim *s, uint32_t seed);
void hal_sim_burn(hal_sim *s, uint64_t core_cycles);       /* advance time by core cycles (task cost or idle) */
void hal_sim_advance_us(hal_sim *s, uint32_t us);
void hal_sim_clocks(hal_sim *s, uint32_t fabric_clocks);   /* run the sequencer for this many fabric clocks */
void hal_sim_power_cycle(hal_sim *s);                      /* the core resets: injected cuts are cleared, memories keep their contents */
uint32_t hal_sim_frame_len(const hal_sim *s);              /* length of the running frame in clocks (0: no END) */

#endif
