# notadji - Overview and Document Map

Status: DRAFT, SRS revision 0.4
Owner: system team (arkady)
Audience: RF, baseband/FPGA, video, firmware, mechanical, regulatory, test

## 1. Purpose

Define an open, low-latency digital video link for small UAVs (FPV and cinematic) that matches or beats the
DJI O3/O4 class of systems on latency, range, robustness and power. The product is a chipset (air unit and
ground unit) built in two phases:

| Phase | Platform | Goal |
|-------|----------|------|
| P0 | Commodity WiFi (injection mode, wfb-ng/OpenIPC style) | Prove video pipeline, measure real latency, field data. Not a product. |
| P1 | FPGA + off-the-shelf RF transceiver (software-defined radio) | Full custom PHY/MAC, calibration loops, encoder. Flyable prototype. |
| P2 | ASIC (SDR-style baseband + integrated RF transceiver, external PA/FEM at first) | Product silicon. |

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

## 3. Conventions

- Requirement ID: `<AREA>-<NNN>`. IDs are never reused.
- Priority: **M** mandatory, **S** should, **O** optional.
- Phase: **P1** applies to the FPGA prototype, **P2** to the ASIC. A requirement without a phase applies to both.
- Verification: **T** test (measured), **A** analysis, **I** inspection, **D** demonstration, **S** simulation.
- Numbers marked `[TBV]` are targets or assumptions to be verified. Numbers about DJI products are our
  estimates from public information and must not be quoted as DJI specifications.
- Plain dash `-` is used throughout instead of the long dash.

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
