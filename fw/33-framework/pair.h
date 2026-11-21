/* pair - pairing by X25519 with a short authentication code (R33-11; SEC-001, MAC-009).
 * No default key: both units generate a key pair from the HAL random source, exchange public keys over the unauthenticated channel, derive the
 * link key, an authentication key and a six-digit code from the shared secret and the transcript, and the user compares the code on both screens.
 * A man in the middle that substitutes keys ends up with different codes on the two sides (probability of equal codes 10^-6 per attempt);
 * three wrong comparisons lock the pairing for a timeout. */
#ifndef PAIR_H
#define PAIR_H

#include "hal.h"
#include "crashlog.h"

#define PAIR_MAX_ATTEMPTS 3u
#define PAIR_LOCK_US      60000000u        /* 60 s */

typedef enum { PAIR_IDLE = 0, PAIR_KEY_READY = 1, PAIR_WAIT_CONFIRM = 2, PAIR_DONE = 3, PAIR_FAILED = 4 } pair_state;

typedef struct {
    hal_t   *h;
    clog_t  *log;
    uint8_t  initiator;                    /* the initiator's key comes first in the transcript */
    uint8_t  sk[32], pk[32], peer[32];
    uint8_t  link_key[32], auth_key[32];
    uint32_t code;
    pair_state state;
    uint8_t  attempts;
    uint32_t locked_until_us;
    bool     locked;
} pair_t;

void pair_init(pair_t *p, hal_t *h, clog_t *log, bool initiator);
/* generate a fresh key pair; false while locked */
bool pair_start(pair_t *p, uint8_t pk_out[32]);
/* the peer's public key arrived: derive keys and code; false if the key is unusable (low order) or the state is wrong */
bool pair_on_peer_key(pair_t *p, const uint8_t peer[32]);
uint32_t pair_code(const pair_t *p);                  /* 0..999999 for display */
/* the user compared the codes; true when pairing is complete (keys stay valid), false on a mismatch (keys wiped) */
bool pair_confirm(pair_t *p, bool codes_match);
bool pair_locked(pair_t *p);

#endif
