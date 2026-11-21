#!/usr/bin/env python3
"""Mutation check of the firmware framework (T33-M): each mutant is a one-line change of a copy of fw/33-framework; the named tests must fail.
Usage: ./mutate.py [step-prefix]    (a mutant that survives is a hole in the tests)"""
import shutil, subprocess, sys, os
from pathlib import Path
HERE = Path(__file__).resolve().parent
FW = HERE.parent.parent / "fw" / "33-framework"
# (id, file, old, new, tests that must fail)
M = [
 ("S1-spsc-full",      "spsc.h", "if (h - t > q->mask) return false;", "if (h - t >= q->mask) return false;", ["t_spsc"]),
 ("S1-spsc-release",   "spsc.h", "atomic_store_explicit(&q->head, h + 1u, memory_order_release);", "atomic_store_explicit(&q->head, h + 1u, memory_order_relaxed);", ["audit"]),
 ("S1-spsc-acquire",   "spsc.h", "uint32_t h = atomic_load_explicit(&q->head, memory_order_acquire);\n    if (h == t)", "uint32_t h = atomic_load_explicit(&q->head, memory_order_relaxed);\n    if (h == t)", ["audit"]),
 ("S1-sched-prio",     "sched.c", "s->tasks[s->order[j - 1]].cfg.prio > s->tasks[v].cfg.prio", "s->tasks[s->order[j - 1]].cfg.prio < s->tasks[v].cfg.prio", ["t_sched"]),
 ("S1-sched-miss",     "sched.c", "if (end > release + dl_c)", "if (end > now + dl_c)", ["t_sched"]),
 ("S1-sched-skip",     "sched.c", "(now - t->next_rel) / period_c + 1u", "(now - t->next_rel) / period_c", ["t_sched"]),
 ("S1-sched-overrun",  "sched.c", "cyc > t->cfg.budget_cycles", "cyc >= t->cfg.budget_cycles + 1000u", ["t_sched"]),
 ("S1-sched-consec",   "sched.c", "else t->st.consec_overrun = 0;", "else { }", ["t_sched"]),
 ("S1-sched-event",    "sched.c", "atomic_exchange_explicit(&s->events, 0, memory_order_acquire)", "atomic_load_explicit(&s->events, memory_order_acquire)", ["t_sched"]),
 ("S1-sim-commit",     "hal_sim.c", "if (cr) s->pending = 1;", "", ["t_hal_sim"]),
 ("S1-sim-frame",      "hal_sim.c", "        s->frame_cnt++;\n", "", ["t_hal_sim"]),
 ("S1-sim-swapped",    "hal_sim.c", "if (s->pending) { s->active ^= 1u;", "if (s->pending) { s->active ^= 1u; s->active ^= 1u;", ["t_hal_sim"]),
 ("S1-sim-missed",     "hal_sim.c", "if (s->missed != 0xFFFFu) s->missed++;", "", ["t_hal_sim"]),
 ("S1-mbox-recheck",   "mbox.h", "if (atomic_load_explicit(&((mbox_t *)m)->seq, memory_order_relaxed) == s1) return s1;", "return s1;", ["t_mbox"]),
 ("S1-mbox-odd",       "mbox.h", "if (s1 & 1u) continue;", "", ["t_mbox"]),
 ("S1-mbox-fence",     "mbox.h", "atomic_thread_fence(memory_order_acquire);", "", ["audit"]),
 ("S2-crc32-poly",     "crc.c", "0xEDB88320u, 0xF00F9344u", "0xEDB88321u, 0xF00F9344u", ["t_crc", "t_clog"]),
 ("S2-crc16-poly",     "crc.c", "0x8408u", "0x8409u", ["t_crc"]),
 ("S2-clog-crc-len",   "crashlog.c", "fw_st32(b + 28, crc32_ieee(b, 28));", "fw_st32(b + 28, crc32_ieee(b, 27));", ["t_clog"]),
 ("S2-clog-oldest",    "crashlog.c", "if (c->next_seq - c->oldest > c->cap) c->oldest = c->next_seq - c->cap;", "", ["t_clog"]),
 ("S2-clog-slot",      "crashlog.c", "((seq - 1u) % c->cap)", "((seq) % c->cap)", ["t_clog"]),
 ("S2-clog-wrap",      "crashlog.c", "if (c->next_seq == 0xFFFFFFFFu) clog_clear(c);", "", ["t_clog"]),
 ("S2-seq-noend",      "seq_drv.c", "if (t[n - 1u].act != SEQ_ACT_END) return SEQ_ERR_NO_END;", "", ["t_seqdrv"]),
 ("S2-seq-sorted",     "seq_drv.c", "if (t[i].time < last) return SEQ_ERR_UNSORTED;", "if (t[i].time < last && 0) return SEQ_ERR_UNSORTED;", ["t_seqdrv"]),
 ("S2-seq-guard",      "seq_drv.c", "len - tick < need + SEQ_COMMIT_MARGIN", "len - tick < need", ["t_seqdrv"]),
 ("S2-seq-race",       "seq_drv.c", "if ((hal_rd(h, SEQ_STATUS) & 1u) != (st & 1u)) {", "if (0) {", ["t_seqdrv"]),
 ("S2-seq-skip",       "seq_drv.c", "d->known[inactive] && d->sum[inactive] == sum) ? 0u", "false) ? 0u", ["t_seqdrv"]),
 ("S2-sup-limit",      "sup.c", "st->consec_overrun >= SUP_OVERRUN_LIMIT &&", "st->consec_overrun > SUP_OVERRUN_LIMIT &&", ["t_sup"]),
 ("S2-sup-kick",       "sup.c", "    if (all) {\n        u->h->wdog_kick(u->h);", "    if (all || 1) {\n        u->h->wdog_kick(u->h);", ["t_sup"]),
 ("S2-sup-clearmiss",  "sup.c", "sched_clear_miss(u->s, u->task[i]);", "", ["t_sup"]),
 ("S2-sup-deadline",   "sup.c", "if (st->miss_flag) {", "if (0) {", ["t_sup"]),
 ("S2-mon-halt",       "sup.c", "hal_wr(m->h, SYS_MAIN_HALT, 1);                  /* stop", "                  /* stop", ["t_monitor"]),
 ("S2-mon-crc",        "sup.c", "if (safe_sum(m) != m->safe_crc) {", "if (0) {", ["t_monitor"]),
 ("S2-mon-missed",     "sup.c", "|| missed >= MON_STALL_FRAMES) {", ") {", ["t_monitor"]),
 ("S2-mon-owner",      "sup.c", "atomic_compare_exchange_strong(m->owner, &expected, MON_OWNER_MON)", "(expected == 0)", ["t_monitor"]),
 ("S3-fb-crc",         "mac_fb.c", "if (fw_ld16(b + total - 2u) != crc16_mcrf4xx(b, total - 2u)) return FB_ERR_CRC;", "", ["t_macfb"]),
 ("S3-fb-len",         "mac_fb.c", "if (len != total) return FB_ERR_LEN;", "", ["t_macfb"]),
 ("S3-fb-n",           "mac_fb.c", "if (b[6] < 1u || b[6] > FB_MAX_SLICES) return FB_ERR_N;", "if (b[6] > FB_MAX_SLICES) return FB_ERR_N;", ["t_macfb"]),
 ("S3-fb-mask",        "mac_fb.c", "(1u << (m->n_slices & 7u)) - 1u", "(1u << (m->n_slices & 7u))", ["t_macfb"]),
 ("S3-fb-lost",        "mac_fb.c", "if (!(((uint32_t)m->ack[i >> 3] >> (i & 7u)) & 1u)) lost++;", "if ((((uint32_t)m->ack[i >> 3] >> (i & 7u)) & 1u)) lost++;", ["t_macfb"]),
 ("S3-fb-seq",         "mac_fb.c", "if (c->have_seq && d <= 0)", "if (c->have_seq && d < 0)", ["t_macfb"]),
 ("S3-fb-seqwrap",     "mac_fb.c", "d = (int8_t)(uint8_t)(m.seq - c->last_seq);", "d = (int8_t)(m.seq > c->last_seq ? 1 : -1);", ["t_macfb"]),
 ("S3-fb-clearlen",    "mac_fb.c", "    hal_wr(c->h, MAC_FB_LEN, 0);                      /* the buffer may be reused */\n", "", ["t_macfb"]),
 ("S3-apply-apply",    "mac_fb.c", "    hal_wr(c->h, MAC_APPLY, 1);\n", "", ["t_macfb"]),
 ("S3-apply-skip",     "mac_fb.c", "c->shadow_mcs == mcs && c->shadow_pwr == pw && c->shadow_budget == budget", "c->shadow_mcs == mcs && c->shadow_budget == budget", ["t_macfb"]),
 ("S3-apply-backoff",  "mac_fb.c", "int32_t p = c->out.pwr_x4 - c->lim.pwr_backoff_x4;", "int32_t p = c->out.pwr_x4;", ["t_macfb"]),
 ("S3-apply-inhibit",  "mac_fb.c", "if (c->lim.tx_inhibit) budget = 0;", "", ["t_macfb"]),
 ("S3-safe-force",     "mac_fb.c", "c->la.last_fb_us = now - c->cfg.fb_timeout_us - 1u;", "", ["t_macfb"]),
 ("S3-rate-pct",       "mac_fb.c", "(bitrate_pct > 100u ? 100u : bitrate_pct)", "(bitrate_pct > 100u ? 100u : 100u)", ["t_macfb"]),
 ("S3-rate-tele",      "mac_fb.c", "total = total > tele_bytes ? total - tele_bytes : 0u;", "total = total > tele_bytes ? total : 0u;", ["t_macfb"]),
 ("S3-rate-rem",       "mac_fb.c", "(i < rem ? 1u : 0u)", "(i + 1u < rem ? 1u : 0u)", ["t_macfb"]),
 ("S3-rate-shadow",    "mac_fb.c", "if (shadow[i] != t) { hal_wr(h, MAC_SLICE_TGT + 4u * i, t); shadow[i] = t; }", "{ hal_wr(h, MAC_SLICE_TGT + 4u * i, t); shadow[i] = t; }", ["t_macfb"]),
 ("S4-th-enter",       "thermal.c", "if (hot >= c->enter_x4[i]) target = (uint8_t)(i + 1u);", "if (hot > c->enter_x4[i]) target = (uint8_t)(i + 1u);", ["t_thermal"]),
 ("S4-th-leave",       "thermal.c", "hot < c->leave_x4[t->level - 1u]", "hot <= c->leave_x4[t->level - 1u]", ["t_thermal"]),
 ("S4-th-leave-enter", "thermal.c", "hot < c->leave_x4[t->level - 1u]", "hot < c->enter_x4[t->level - 1u]", ["t_thermal"]),
 ("S4-th-dwell",       "thermal.c", "(uint32_t)(now_ms - t->level_since_ms) >= c->min_dwell_ms", "(uint32_t)(now_ms - t->level_since_ms) > c->min_dwell_ms", ["t_thermal"]),
 ("S4-th-fallback",    "thermal.c", "if (inv && fallback > hot) hot = fallback;", "", ["t_thermal"]),
 ("S4-th-allbad",      "thermal.c", "if (nvalid == 0) hot = (int16_t)(c->enter_x4[3] + 1);", "", ["t_thermal"]),
 ("S4-th-range",       "thermal.c", "raw[i] < c->valid_min_x4 || raw[i] > c->valid_max_x4 || t->stuck[i]", "raw[i] < c->valid_min_x4 || t->stuck[i]", ["t_thermal"]),
 ("S4-th-stuck",       "thermal.c", "absd(raw[j], t->anchor[i][j]) > c->stuck_move_x4", "absd(raw[j], t->anchor[i][j]) > 4000", ["t_thermal"]),
 ("S4-th-stucktime",   "thermal.c", ">= c->stuck_ms) {", ">= c->stuck_ms * 10u) {", ["t_thermal"]),
 ("S4-th-hw",          "thermal.c", "if (hw_trip) target = 4;", "", ["t_thermal"]),
 ("S4-th-hwhold",      "thermal.c", "t->level > 0 && !hw_trip &&", "t->level > 0 &&", ["t_thermal"]),
 ("S4-th-recal-dt",    "thermal.c", "absd(ref, t->t_cal_x4) >= c->recal_dt_x4", "absd(ref, t->t_cal_x4) > c->recal_dt_x4", ["t_thermal"]),
 ("S4-th-recal-time",  "thermal.c", ">= c->recal_period_ms) t->recal_due = true;", ">= c->recal_period_ms * 2u) t->recal_due = true;", ["t_thermal"]),
 ("S4-th-recal-init",  "thermal.c", "    t->recal_due = true;                                   /* no calibration yet at power-up */\n", "", ["t_thermal"]),
 ("S4-rf-zero",        "rf_prot.c", "if (d >= 0) return VSWR_MAX_Q8;", "if (d > 0) return VSWR_MAX_Q8;", ["t_rfprot"]),
 ("S4-rf-interp",      "rf_prot.c", "* frac + 12u) / 25u;", "* frac) / 25u + 0u * 25u;", []),
 ("S4-rf-gamma",       "rf_prot.c", "uint64_t v = ((uint64_t)(32768u + g) << 8) / (32768u - g);", "uint64_t v = ((uint64_t)(32768u + g) << 8) / (32768u + g / 2u);", ["t_rfprot"]),
 ("S4-rf-trip",        "rf_prot.c", "if (v >= c->trip_q8) { if (r->over_trip", "if (v > c->trip_q8 + 256u) { if (r->over_trip", ["t_rfprot"]),
 ("S4-rf-foldconf",    "rf_prot.c", "r->over_fold >= c->fold_confirm) set_state(r, RF_FOLDBACK", "r->over_fold >= 1u) set_state(r, RF_FOLDBACK", ["t_rfprot"]),
 ("S4-rf-recover",     "rf_prot.c", "if (v < c->fold_rec_q8) {", "if (v < c->fold_q8) {", ["t_rfprot"]),
 ("S4-rf-recover-t",   "rf_prot.c", ">= c->fold_rec_us) set_state(r, RF_OK, now_us);", ">= 0u) set_state(r, RF_OK, now_us);", ["t_rfprot"]),
 ("S4-rf-hold",        "rf_prot.c", ">= c->trip_hold_us) set_state(r, RF_PROBE, now_us);", ">= c->trip_hold_us / 2u) set_state(r, RF_PROBE, now_us);", ["t_rfprot"]),
 ("S4-rf-probe-n",     "rf_prot.c", "if (++r->good_probe >= c->probe_samples) {", "if (++r->good_probe >= 1u) {", ["t_rfprot"]),
 ("S4-rf-probe-bad",   "rf_prot.c", "if (valid && v >= c->trip_rec_q8) { set_state(r, RF_TRIP, now_us); break; }", "", ["t_rfprot"]),
 ("S4-rf-probe-to",    "rf_prot.c", "if ((uint32_t)(now_us - r->state_since_us) >= c->probe_timeout_us) set_state(r, RF_TRIP, now_us);   /* no forward power seen */", "", ["t_rfprot"]),
 ("S4-rf-pa",          "rf_prot.c", "o->pa_enable = r->state != RF_TRIP;", "o->pa_enable = true;", ["t_rfprot", "t_protect"]),
 ("S4-rf-floor",       "rf_prot.c", "bool valid = fwd_x100 >= c->fwd_floor_x100;", "bool valid = true;", ["t_rfprot"]),
 ("S4-rf-gross",       "rf_prot.c", "if (valid && v >= c->gross_q8) flags |= ANT_FLAG_GROSS;", "", ["t_rfprot"]),
 ("S4-rf-detune",      "rf_prot.c", "r->cal_valid && (uint32_t)v >= (uint32_t)r->vswr_cal_q8 + c->detune_delta_q8", "r->cal_valid", ["t_rfprot"]),
 ("S4-rf-recal-n",     "rf_prot.c", "if (r->recal_cnt >= c->recal_confirm) r->recal_due = true;", "if (r->recal_cnt >= 1u) r->recal_due = true;", ["t_rfprot"]),
 ("S4-rf-caldone",     "rf_prot.c", "void rf_cal_done(rf_t *r) { r->vswr_cal_q8 = r->vswr_q8;", "void rf_cal_done(rf_t *r) { ", ["t_rfprot"]),
 ("S4-pl-round",       "rf_prot.c", "step = err >= 0 ? (err + den - 1) / den : -((-err + den - 1) / den);", "step = err / den;", ["t_rfprot"]),
 ("S4-pl-clamp",       "rf_prot.c", "if (l->code > l->code_max) l->code = l->code_max;", "", ["t_rfprot"]),
 ("S4-pl-sign",        "rf_prot.c", "int32_t err = (int32_t)l->target_x4 - measured_x4,", "int32_t err = (int32_t)measured_x4 - l->target_x4,", ["t_rfprot"]),
 ("S4-pr-inhibit",     "protect.c", "l.tx_inhibit = p->tout.shutdown || !p->rout.pa_enable;", "l.tx_inhibit = p->tout.shutdown;", ["t_protect"]),
 ("S4-pr-cap",         "protect.c", "(bo > 120 ? 120 : bo)", "bo", ["t_protect"]),
 ("S4-pr-sum",         "protect.c", "int32_t bo = (int32_t)p->tout.pwr_backoff_x4 + p->rout.backoff_x4;", "int32_t bo = p->tout.pwr_backoff_x4 > p->rout.backoff_x4 ? p->tout.pwr_backoff_x4 : p->rout.backoff_x4;", ["t_protect"]),
 ("S4-pr-pa",          "protect.c", "hal_wr(p->h, RF_PA_EN, p->pa_requested ? 1u : 0u);", "", ["t_protect"]),
 ("S4-pr-fast",        "protect.c", "if (p->rout.changed || !p->rout.pa_enable) prot_merge(p);", "if (p->rout.changed) prot_merge(p);", []),
 ("S4-pr-hw",          "protect.c", "(hal_rd(p->h, SENS_HW_TRIP) & 1u) != 0u", "false", ["t_protect"]),
 ("S4-pr-log",         "protect.c", "if (p->tout.invalid_mask != prev_inv) clog_append", "if (0) clog_append", ["t_protect"]),
 ("S2-mon-release",    "sup.c", "hal_wr(m->h, SYS_MAIN_HALT, 0);                  /* release", "                  /* release", ["t_monitor"]),
]
def run(tests, fwdir, bdir):
    env = dict(os.environ, FW=str(fwdir), B=str(bdir), NO_A64="1")
    r = subprocess.run([str(HERE / "run_tests.sh")] + tests, env=env, capture_output=True, text=True, cwd=HERE)
    return r.returncode, r.stdout + r.stderr
prefix = sys.argv[1] if len(sys.argv) > 1 else ""
surv = 0; n = 0
for mid, f, old, new, tests in M:
    if not mid.startswith(prefix) or not tests: continue
    n += 1
    d = HERE / "build" / "mut" / "fw"
    shutil.rmtree(d.parent, ignore_errors=True); shutil.copytree(FW, d); shutil.copytree(FW.parent / '23-link-adaptation', d.parent / '23-link-adaptation')
    src = (d / f).read_text()
    if old not in src:
        print(f"  BAD PATTERN {mid}"); surv += 1; continue
    (d / f).write_text(src.replace(old, new, 1))
    rc, out = run(tests, d, HERE / "build" / "mut" / "b")
    # the mutant build must be compiled; a compile error is not a kill
    if "error:" in out or "Error " in out:
        print(f"  BUILD ERROR  {mid}\n{out[-600:]}"); surv += 1; continue
    killed = rc != 0
    print(f"  {'killed' if killed else 'SURVIVED'}  {mid}")
    if not killed: surv += 1
print(f"{n - surv} of {n} mutants killed")
sys.exit(1 if surv else 0)
