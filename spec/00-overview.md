# notadji - Overview and Document Map

Status: DRAFT, SRS revision 0.6
Owner: system team (arkady)
Audience: RF, baseband/FPGA, video, firmware, mechanical, regulatory, test

## 1. Purpose

Define an open, low-latency digital video link for small UAVs (FPV and cinematic) that closely matches or beats the
DJI O3/O4 class of systems on latency, range, robustness and power. The product is a chipset (air unit and
ground unit) built in two phases:

| Phase | Platform | Goal |
|-------|----------|------|
| P0 | Commodity WiFi (injection mode, wfb-ng/OpenIPC style) | Prove video pipeline, measure real latency, field data. Not a product. |
| P1 | FPGA + off-the-shelf RF transceiver (software-defined radio) | Full custom PHY/MAC, calibration loops, encoder. Bench and large-airframe test flights (about 14 W input, `02`); not a 250 g class flyer. |
| P2 | ASIC (SDR-style baseband + integrated RF transceiver, external PA/FEM at first) | Product silicon. |

### Platform phases (document 13) against the labels above

| Platform phase (`13`, HSI-010) | Hardware | Labels in the SRS |
|---|---|---|
| A | Low-cost evaluation boards: PlutoSDR-class pair (2.4 GHz + 915 MHz), AD9361/ADRV9002 pair (5.8 + 2.4 GHz), K26-class video board, Rockchip/Pi-class ground decoder | P0 and P1 (bring-up) |
| B | Custom board with the target controllers (ADRV9002-class transceiver, Zynq UltraScale+ EV-class device) | P1 (latency, thermal, mass) |
| C | ASIC (two dice) | P2 |

## 2. Reading order

| File | Content |
|------|---------|
| `01-system-requirements.md` | Numbered requirements (the normative document) |
| `02-link-and-latency-budgets.md` | Link budget, latency budget, power budget (pass 2) |
| `03-calibration-and-monitoring.md` | Front-end calibration, temperature, antenna feedback (pass 2) |
| `04-prototype-and-asic-plan.md` | WiFi/BLE prototype mapping, FPGA plan, ASIC roadmap (pass 2) |
| `05-reference-survey.md` | What the existing open projects do and what we take from each (pass 2) |
| `06-review-gaps.md` | Gaps, contradictions and assumptions found on re-read (pass 3) |
| `07-trade-studies.md` | Two or three options with pros and cons for every open decision (pass 4) |
| `08-verification-plan.md` | Test groups, equipment, staged execution (pass 5) |
| `09-traceability-matrix.md` | Generated requirement to test-group matrix (`scripts/trace_matrix.py`) |
| `10-source-review.md` | Facts from the downloaded sources and their effect on the spec (second goal, iteration 1) |
| `12-claim-audit-and-feasibility.md` | Claim audit, errors corrected, external facts, feasibility register, per-requirement evidence class (verification pass) |
| `14-appendix-foveated-video.md` | Optional foveated-video feature for race mode (notes entry 3, T-20) |
| `15-requirement-rationale.md` | Why each requirement has its value: worked derivations (slices, intra refresh, sensor interface) and one rationale row per requirement (notes entry 19) |
| `13-hardware-software-integration.md` | Execution domains, CPU workload, two-phase platform plan (evaluation boards, then custom board), processor options and power |
| `11-patent-search.md` | Preliminary patent landscape, design-around constraints, brief for the patent attorney (iteration 2) |

## 3. Conventions

- Requirement ID: `<AREA>-<NNN>`. IDs are never reused.
- Priority: **M** mandatory, **S** should, **O** optional.
- Phase: **P1** applies to the FPGA prototype, **P2** to the ASIC. A requirement without a phase applies to both.
- Verification: **T** test (measured), **A** analysis, **I** inspection, **D** demonstration, **S** simulation.
- Numbers marked `[TBV]` are targets or assumptions to be verified. Numbers about DJI products are our
  estimates from public information and must not be quoted as DJI specifications.
- Design stance: regional compliance (FCC, ETSI and others) is configuration, not a design driver; budgets are for the hardware capability and region profiles are derived (REG-008, `02` section 1.2). Operating rule: a prototype that radiates is operated only conducted into a load, in a shielded enclosure, or under a test or experimental authorisation.

## 4. Glossary

| Term | Meaning |
|------|---------|
| Air unit (AU) | Camera, encoder, modem and RF on the vehicle |
| Ground unit (GU) | Receiver, decoder and display interface (goggles, monitor or phone) |
| G2G | Glass-to-glass latency: photon on the sensor to photon on the display |
| MCS | Modulation and coding scheme |
| UEP | Unequal error protection |
| JSCC | Joint source-channel coding |
| DPD | Digital pre-distortion |
| VSWR | Voltage standing wave ratio at the antenna port |
| CSI | Channel state information |
| FEM | RF front-end module (PA, LNA, switch, filters) |
| DFS/AFS | Dynamic/adaptive frequency selection |
| RID | Remote ID (FAA Part 89, ASTM F3411) |
