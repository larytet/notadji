/* hal - hardware abstraction used by all firmware modules (R33-01). One instance per core; every function takes the instance.
 * Backends: hal_sim.c (host tests); board support for the target provides the same table. */
#ifndef HAL_H
#define HAL_H

#include "fw_types.h"
#include "regmap.h"

#define HAL_CORE_MHZ 300u          /* cycle counter rate assumed by the cost model */

typedef struct hal hal_t;
struct hal {
    void *ctx;
    uint32_t (*rd32)(hal_t *h, uint32_t addr);
    void     (*wr32)(hal_t *h, uint32_t addr, uint32_t v);
    uint64_t (*cycles)(hal_t *h);
    /* retained RAM: survives a reset of the core (crash log) */
    uint32_t ret_size;
    void     (*ret_read)(hal_t *h, uint32_t off, void *dst, uint32_t n);
    void     (*ret_write)(hal_t *h, uint32_t off, const void *src, uint32_t n);
    /* flash: erase by sector, program by byte range within a sector (bits can only go 1 -> 0) */
    uint32_t flash_size, flash_sector;
    int      (*fl_read)(hal_t *h, uint32_t off, void *dst, uint32_t n);
    int      (*fl_program)(hal_t *h, uint32_t off, const void *src, uint32_t n);
    int      (*fl_erase)(hal_t *h, uint32_t sector_off);
    uint32_t (*rng)(hal_t *h);
    void     (*wdog_kick)(hal_t *h);
};

static inline uint32_t hal_rd(hal_t *h, uint32_t a) { return h->rd32(h, a); }
static inline void hal_wr(hal_t *h, uint32_t a, uint32_t v) { h->wr32(h, a, v); }
static inline uint64_t hal_cycles(hal_t *h) { return h->cycles(h); }
static inline uint32_t hal_now_us(hal_t *h) { return (uint32_t)(h->cycles(h) / HAL_CORE_MHZ); }

#endif
