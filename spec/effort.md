# Silicon size and engineering effort estimate

Status: DRAFT, engineering estimate **[E]**, written against SRS rev 1.8. Not a measured result. Treat every number as plus or minus a factor of 1.5 on area and a factor of 2 on effort. The spec itself only states die-area targets (ASC-004: digital SoC 30 mm2 or less, RF die 15 mm2 or less, [TBV, G-23]) and an A2 NRE of USD 5 to 10 M [TBV] (`04` section 5). This document adds a block-level estimate behind those targets.

Assumptions: 22 nm class FD-SOI for the digital SoC; mature RF CMOS or FD-SOI for the RF die (ASC-001, T-08 option B); one digital SoC design for both the air-unit and the ground-unit role; person-year (PY) means one engineer for one year.

## 1. Silicon size

### 1.1 Digital SoC (one design for both roles)

| Block | mm2 [E] |
|---|---|
| OFDM modem (2 RX chains, MRC) | 1.5 |
| LDPC FEC (3 decoder instances, `13`) | 0.7 |
| Video encoder (AVC and HEVC, slice-based) | 3.0 |
| Video decoder and display synchronisation | 1.5 |
| ISP-lite and MIPI CSI | 1.0 |
| CPU subsystem (real-time cores plus power-gated application core) | 2.5 |
| LPDDR PHY and controller | 4.0 |
| Display output PHY (HDMI/DP/DSI) | 2.0 |
| On-chip SRAM, about 4 MB | 4.0 |
| DPD and calibration engine, security, peripherals | 3.0 |
| Subtotal | about 23 |
| Pads, power distribution and routing overhead (+20 to 25%) | **about 29 (range 25 to 45)** |

This agrees with ASC-004 (30 mm2).

Additions for the beamforming options (`notes.md` entries 11 and 12): beamforming logic 0.5 to 2 mm2; chip-to-chip interface (a few SerDes lanes) 1 to 2 mm2.

Savings not counted in the table (hardware sharing): the transmit and receive modem do not run at the same time in TDD, so the FFT/IFFT and equaliser memory can be shared; a unit uses either the encoder (air) or the decoder (ground), so the transform, prediction and deblocking fabric can be role-switched. Potential saving about 1 to 2 mm2, at the price of mode-switching logic and the cut-through latency constraint (LAT-005).

### 1.2 RF die

2 TX, 2 RX, observation receiver, PLLs for 0.9, 2.4 and 5.8 GHz, converters and filters: **15 to 25 mm2**. The ASC-004 target of 15 mm2 looks optimistic; inductors and the three bands dominate.

### 1.3 Single die and separate air and ground chips

| Option | Area [E] | Comment |
|---|---|---|
| Single die (T-08 option A) | about 45 to 50 mm2 | highest RF-in-digital-node risk |
| Two dice, shared by both roles (baseline) | about 29 + 18 mm2 | two tape-outs, the same two for every product |
| Separate air chip | about 25 mm2 (digital) | no decoder, no display PHY |
| Separate ground chip | about 24 mm2 (digital) | no encoder, no ISP, no CSI |

Separate air and ground digital chips save only about 5 mm2 each (about 15%, roughly USD 0.5 per unit [E]). A second tape-out costs about 3 M for masks plus about 50 to 60 PY, so break-even is in the tens of millions of units. At the 100k units per year of ASC-005 it does not pay. The ground module's extra capability (`notes.md` entry 5) is better delivered by the same die plus external filters, ADCs and extra chips.

## 2. Effort

Verification is taken as roughly 1.3 to 2 times design effort for blocks with novel algorithms.

### 2.1 Gross estimate (blocks counted independently)

| Area | Design PY | Verification PY |
|---|---|---|
| Modem (channel models, bit-exact comparison with the C model) | 8 | 14 |
| LDPC and MCS | 4 | 6 |
| MAC, TDD sequencer, hopping | 5 | 8 |
| Video encoder (conformance streams, VID-006 hard bound) | 15 | 25 |
| Video decoder, display sync | 8 | 12 |
| ISP, MIPI | 5 | 7 |
| DPD and calibration engine | 5 | 7 |
| Security | 2 | 3 |
| CPU subsystem integration, power management | 6 | 10 |
| Beamforming logic and chip-to-chip interface | 4 | 8 |
| Top level: physical design, DFT, signoff (design); gate-level and power-aware checks (verification) | 25 | 10 |
| **Digital SoC subtotal** | **about 87** | **about 110** |
| Firmware, HAL, bring-up software | about 40 | |
| RF die: analog design 40, layout 15, mixed-signal verification and corners 25, characterisation 15 | | about 95 |
| **Total** | | **about 330 PY (range 200 to 450)** |

### 2.2 Adjustment for reuse and overlap

Reuse that the gross table ignores:

1. **Hardware sharing inside the chip:** TDD lets TX and RX share the FFT and memories; the encoder and decoder fabric can be role-switched; AVC and HEVC share much datapath (T-06 asks for a codec-agnostic encoder at slice level); the observation receiver serves DPD, VSWR, power control and spectrum scan.
2. **Repeated instances:** 2 TX and 2 RX chains, three LDPC decoders and the per-chain beamforming blocks are copies; design effort is for one, verification is for one plus the interaction of copies.
3. **P1 to ASIC reuse:** PRO-005 requires ASIC-portable RTL, so the modem, FEC, MAC and encoder RTL written for the FPGA prototype carry over together with testbenches, models and test vectors. The ASIC effort is then mostly integration, physical design, DFT and signoff.
4. **Verification environments:** channel models, bit-exact C/Python references, video conformance streams and CPU-level tests are shared across blocks and between P1 and the ASIC.

Limits on the reuse:

- Most open code is GPL or AGPL, so REG-005 (clean-room) allows little direct copying; only Apache or MIT items (for example openofdm) help directly. Most of the reuse comes from our own P1 work and licensed IP.
- Shared hardware adds mode-switching logic, and verifying every role, option and fuse state partly cancels the saving.
- Verification of integration and configurations does not shrink with reuse.

| Area | Gross PY | After reuse PY |
|---|---|---|
| Digital design | 87 | about 65 (-25%) |
| Digital verification | 110 | about 85 (-20%) |
| Firmware | 40 | about 35 |
| RF die | 95 | about 80 (replicated chains) |
| **Total** | **330** | **about 265 (range 170 to 380)** |

The P1 FPGA effort is **not** in either total; it is a separate program item that the ASIC then reuses, so the program total is higher than the ASIC figure alone.

### 2.3 Schedule check

About 265 to 330 PY with a team of about 60 people gives about 2.5 years. The spec's 18 to 24 months for A2 (`04` section 5) needs a bigger team or more parallelism.

### 2.4 Effect of the single-silicon beamforming options (`notes.md` entries 11 and 12)

- About 10 to 15% extra verification, because every option state must be verified even when disabled.
- The test matrix multiplies: options A to D, fuse states, bands and roles.
- Mitigation: keep the options orthogonal and verify the power and clock gating once.
- Multi-chip phase coherence can only be proven in the lab, so it belongs in the bring-up plan.

### 2.5 Second tape-out for separate air and ground chips

Shared blocks (modem, FEC, MAC) are reused; the cost is the second physical design, DFT, signoff, top-level verification and bring-up: about 50 to 60 PY plus the mask set (about 3 M [E]), roughly 15 to 20% on top of the single-chip program.

## 3. Inconsistency with `04` section 5

At USD 0.15 M per PY the roughly 240 PY of digital SoC work (design, verification, firmware) come to about USD 35 M. The A2 figure of USD 5 to 10 M therefore looks like masks, IP licences and tools only, not team labour. `04` should say which it is (G-23: "NRE and volume assumptions are missing").

## 4. To do

- Replace the block areas by synthesis and IP-vendor figures when available (G-23).
- Check the RF die area against a published 2T2R transceiver in the chosen node.
- Decide whether the effort numbers are to be included in `04` or kept here.
