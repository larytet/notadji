/* regmap - versioned register map seen by the real-time core (SW-003, HSI-012). Word (32-bit) registers, byte addresses.
 * The blocks marked [RTL] exist in rtl/; the others are the interface the firmware expects from the platform and are
 * implemented by the HAL backend (the simulation backend here, board support later). */
#ifndef REGMAP_H
#define REGMAP_H

#define HAL_REGMAP_VERSION 1u

/* sequencer, module 10 [RTL]: entries are 48 bits {time[23:0], action[7:0], arg[15:0]}: DATA_LO = bits 31..0, DATA_HI = bits 47..32 */
#define SEQ_BASE        0x1000u
#define SEQ_WR_ADDR     (SEQ_BASE + 0x00u)   /* entry index in the inactive bank */
#define SEQ_WR_DATA_LO  (SEQ_BASE + 0x04u)
#define SEQ_WR_DATA_HI  (SEQ_BASE + 0x08u)
#define SEQ_WR_STROBE   (SEQ_BASE + 0x0Cu)   /* write 1: store the entry */
#define SEQ_COMMIT      (SEQ_BASE + 0x10u)   /* write 1: the inactive bank becomes pending */
#define SEQ_FORCE_SAFE  (SEQ_BASE + 0x14u)   /* bit 0 */
#define SEQ_FRAME_CNT   (SEQ_BASE + 0x18u)   /* read only */
#define SEQ_MISSED      (SEQ_BASE + 0x1Cu)   /* read only: frames without a commit */
#define SEQ_TICK        (SEQ_BASE + 0x20u)   /* read only: clocks since the frame start */
#define SEQ_STATUS      (SEQ_BASE + 0x24u)   /* bit0 active_bank, bit1 pending, bit2 forced */
#define SEQ_FRAME_LEN   (SEQ_BASE + 0x28u)   /* read only: length of the running frame in clocks, 0 = no END (frame never ends) */
#define SEQ_DEPTH       64u
#define SEQ_MIN_FRAME   16u

#define SEQ_ACT_NOP        0u
#define SEQ_ACT_SET_LINES  1u
#define SEQ_ACT_CLR_LINES  2u
#define SEQ_ACT_PULSE      3u
#define SEQ_ACT_SET_GAIN   4u
#define SEQ_ACT_SET_PLL    5u
#define SEQ_ACT_END        15u

/* MAC and modem controls (shadow registers, applied together by MAC_APPLY) */
#define MAC_BASE          0x2000u
#define MAC_MCS           (MAC_BASE + 0x00u)
#define MAC_PWR_X4        (MAC_BASE + 0x04u)   /* transmit power, 0.25 dB units, two's complement in the low 16 bits */
#define MAC_SLICE_BUDGET  (MAC_BASE + 0x08u)   /* payload bytes per slice */
#define MAC_APPLY         (MAC_BASE + 0x0Cu)   /* write 1: shadow registers take effect at the next frame start */
#define MAC_FB_LEN        (MAC_BASE + 0x10u)   /* length of the feedback message in the receive buffer, 0 = none */
#define MAC_SLICE_TGT     (MAC_BASE + 0x40u)   /* 64 words: per-slice byte targets for the encoder */
#define MAC_SLICE_TGT_N   64u

/* RF front end */
#define RF_BASE           0x3000u
#define RF_PA_EN          (RF_BASE + 0x00u)    /* bit 0: PA enable (cleared by the protection trip) */
#define RF_GAIN_CODE      (RF_BASE + 0x04u)    /* TX gain code, 0.25 dB per step */
#define RF_DET_FWD        (RF_BASE + 0x08u)    /* forward power detector, 0.01 dB units relative to 0 dBm, signed 16 bit */
#define RF_DET_REV        (RF_BASE + 0x0Cu)    /* reflected power detector, same units */
#define RF_PWR_DET        (RF_BASE + 0x10u)    /* TX power detector for the power loop, 0.25 dB units */

/* sensors */
#define SENS_BASE         0x4000u
#define SENS_TEMP(i)      (SENS_BASE + 4u * (i)) /* i = 0 PA/FEM, 1 transceiver, 2 SoC, 3 board; raw 0.25 deg C, signed 16 bit */
#define SENS_N            4u
#define SENS_HW_TRIP      (SENS_BASE + 0x20u)    /* bit 0: hardware over-temperature trip latched (THM-006) */

/* system */
#define SYS_BASE          0x5000u
#define SYS_WDOG_KICK     (SYS_BASE + 0x00u)
#define SYS_IRQ_STATUS    (SYS_BASE + 0x04u)
#define SYS_MAIN_HALT     (SYS_BASE + 0x08u)   /* written by the monitor core: 1 halts the main core, 0 releases it (reset) */

#endif
