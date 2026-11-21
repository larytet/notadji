#include "pair.h"
#include "curve25519.h"
#include "sha2.h"

void pair_init(pair_t *p, hal_t *h, clog_t *log, bool initiator)
{
    memset(p, 0, sizeof *p);
    p->h = h; p->log = log; p->initiator = initiator ? 1u : 0u;
}

bool pair_locked(pair_t *p)
{
    if (p->locked && (int32_t)(hal_now_us(p->h) - p->locked_until_us) >= 0) { p->locked = false; p->attempts = 0; }
    return p->locked;
}

bool pair_start(pair_t *p, uint8_t pk_out[32])
{
    uint32_t i;
    if (pair_locked(p)) return false;
    for (i = 0; i < 8; i++) fw_st32(p->sk + 4u * i, p->h->rng(p->h));
    x25519_base(p->pk, p->sk);
    memcpy(pk_out, p->pk, 32);
    p->state = PAIR_KEY_READY;
    return true;
}

bool pair_on_peer_key(pair_t *p, const uint8_t peer[32])
{
    uint8_t secret[32], salt[32], okm[68], zero[32];
    sha256_t c;
    if (p->state != PAIR_KEY_READY) return false;
    memcpy(p->peer, peer, 32);
    x25519(secret, p->sk, peer);
    memset(zero, 0, sizeof zero);
    if (ct_memcmp(secret, zero, 32) == 0) {                 /* a low-order public key gives an all-zero secret */
        fw_wipe(secret, sizeof secret); p->state = PAIR_FAILED; return false;
    }
    sha256_init(&c);
    if (p->initiator) { sha256_update(&c, p->pk, 32); sha256_update(&c, peer, 32); }
    else { sha256_update(&c, peer, 32); sha256_update(&c, p->pk, 32); }
    sha256_final(&c, salt);
    (void)hkdf_sha256(salt, 32, secret, 32, "qspark-pair-v1", 14, okm, sizeof okm);
    memcpy(p->link_key, okm, 32); memcpy(p->auth_key, okm + 32, 32);
    p->code = fw_ld32(okm + 64) % 1000000u;
    fw_wipe(secret, sizeof secret); fw_wipe(okm, sizeof okm); fw_wipe(p->sk, sizeof p->sk);
    p->state = PAIR_WAIT_CONFIRM;
    return true;
}

uint32_t pair_code(const pair_t *p) { return p->code; }

bool pair_confirm(pair_t *p, bool match)
{
    if (p->state != PAIR_WAIT_CONFIRM) return false;
    if (match) {
        p->state = PAIR_DONE; p->attempts = 0;
        clog_append(p->log, CLOG_PAIR, 0, 1, 0, 0, 0);
        return true;
    }
    fw_wipe(p->link_key, sizeof p->link_key); fw_wipe(p->auth_key, sizeof p->auth_key); p->code = 0;
    p->state = PAIR_FAILED;
    if (++p->attempts >= PAIR_MAX_ATTEMPTS) { p->locked = true; p->locked_until_us = hal_now_us(p->h) + PAIR_LOCK_US; }
    clog_append(p->log, CLOG_PAIR, 0, 0, p->attempts, p->locked ? 1u : 0u, 0);
    return false;
}
