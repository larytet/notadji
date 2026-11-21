/* sup - supervision on the main core and monitor on the second core (R33-06, R33-12 monitor part; SW-007, HSI-011).
 * Main core: tasks check in; overruns and deadline misses are logged and raise the safe request; the hardware watchdog is kicked only when
 * everyone checked in. A heartbeat goes to the monitor core through a mailbox.
 * Monitor core: watches the heartbeat and the sequencer `missed` counter; on a stall it halts the main core, takes the sequencer ownership
 * word and commits the pre-built safe table; after a hold time it releases the main core and hands the ownership back when it is alive. */
#ifndef SUP_H
#define SUP_H

#include "sched.h"
#include "crashlog.h"
#include "mbox.h"
#include "seq_drv.h"

#define SUP_MAX 16u
#define SUP_OVERRUN_LIMIT 3u        /* consecutive overruns that raise the safe request */

typedef struct {
    hal_t   *h;
    sched_t *s;
    clog_t  *log;
    mbox_t  *hb;                        /* heartbeat mailbox to the monitor */
    uint8_t  n;
    int      task[SUP_MAX];             /* scheduler task index per supervised entry */
    bool     checked[SUP_MAX];
    uint32_t last_overrun_logged[SUP_MAX];
    bool     safe_req;
    uint32_t heartbeat, kicks, starved_periods;
    bool     starved_logged;
    uint32_t main_state;                /* application defined, forwarded to the monitor */
} sup_t;

void sup_init(sup_t *u, hal_t *h, sched_t *s, clog_t *log, mbox_t *hb);
int  sup_register(sup_t *u, int sched_idx);          /* supervision id or -1 */
void sup_checkin(sup_t *u, int id);
void sup_tick(sup_t *u);                              /* once per supervision period (every frame) */
bool sup_safe_requested(const sup_t *u);
void sup_safe_clear(sup_t *u);

/* ---- monitor core ---- */
/* The ownership word: bit 0 is the owner, the upper 31 bits count the changes of ownership (the epoch). A driver that wrote the banks before a change cannot
 * trust what it believes they hold, because the other core has written them since. */
#define MON_OWNER_MAIN 0u
#define MON_OWNER_MON  1u
static inline uint32_t mon_owner_of(uint32_t w) { return w & 1u; }
static inline uint32_t mon_epoch_of(uint32_t w) { return w >> 1; }
#define MON_STALL_FRAMES 2u                  /* HSI-011: no table update (or heartbeat) for two frames */

typedef enum { MON_WATCH = 0, MON_SAFE_HOLD = 1, MON_WAIT_ALIVE = 2 } mon_state;

typedef struct {
    hal_t   *h;
    clog_t  *log;
    const mbox_t *hb;
    _Atomic uint32_t *owner;             /* sequencer ownership word shared with the main core */
    seq_drv_t drv;
    seq_entry safe[SEQ_DEPTH];           /* the safe table, built at boot */
    uint32_t  safe_n, safe_crc;
    mon_state state;
    uint32_t last_fc, last_hb, stale_frames, hold_frames, wait_frames, alive_frames;
    uint32_t hold_limit, wait_limit;     /* frames in SAFE_HOLD before the release, frames to wait for the heartbeat */
    uint32_t takeovers, bad_table, grace;
} mon_t;

/* the safe table is copied; hold/wait limits in frames */
bool mon_init(mon_t *m, hal_t *h, clog_t *log, const mbox_t *hb, _Atomic uint32_t *owner,
              const seq_entry *safe, uint32_t n, uint32_t hold_frames, uint32_t wait_frames);
void mon_poll(mon_t *m);                              /* once per frame (or faster; it acts on frame counter changes) */

/* main core side: may I write the sequencer? (the owner word is checked before every table load) */
static inline bool mon_main_owns(_Atomic uint32_t *owner) { return mon_owner_of(atomic_load_explicit(owner, memory_order_acquire)) == MON_OWNER_MAIN; }

/* the main core's way to load a sequencer table: refused while the monitor owns the sequencer, and the driver forgets what it believed the banks hold when the
 * ownership changed since its last load */
seq_status seq_load_owned(seq_drv_t *d, _Atomic uint32_t *owner, const seq_entry *t, uint32_t n);

#endif
