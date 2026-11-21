/* protect - glue of thermal and RF protection: reads the sensors and detectors through the HAL, logs state changes, merges the limits for the MAC control,
 * and drives the PA enable line (R33-09). Tasks: prot_rf_task at 1 kHz (with a fast path for the trip), prot_thermal_task at 100 Hz. */
#ifndef PROTECT_H
#define PROTECT_H

#include "hal.h"
#include "crashlog.h"
#include "mac_fb.h"
#include "thermal.h"
#include "rf_prot.h"

typedef struct {
    hal_t     *h;
    clog_t    *log;
    mac_ctl_t *mac;
    therm_t    th;
    rf_t       rf;
    therm_out  tout;
    rf_out     rout;
    uint32_t   trips;
    bool       pa_requested;           /* the PA enable the protection allows (the sequencer may still keep it off) */
} prot_t;

void prot_init(prot_t *p, hal_t *h, clog_t *log, mac_ctl_t *mac, uint32_t now_us);
void prot_thermal_task(prot_t *p);     /* 100 Hz */
void prot_rf_task(prot_t *p);          /* 1 kHz */
void prot_merge(prot_t *p);            /* limits to the MAC control (called by both tasks) and PA enable to the front end */

#endif
