# 14 - Appendix: Foveated Video (optional P2 feature)

Status: DRAFT. Source: review notes entry 3. Evidence labels as in `12`: **[C]** computed by `scripts/link_budget.py`, **[E]** engineering estimate, **[not verified]** from memory or an unproven assumption.
Trade study: `07` T-20. Requirements: VID-023, VID-024, VID-025, MAC-013, TST-003 (IF-003 extended).

## 1. Idea and use case

Deliver high quality only where the pilot looks and exploit natural tunnel vision to save bandwidth. The main driver is the **race mode** (`07` T-05 option D, SYS-009): with 5 MHz channels the net video rate is small, so bits must go where the
pilot's eyes are. In the split-band mode of the baseline architecture a 5 MHz channel carries (`scripts/link_budget.py`, [C]):

""" + "| MCS | Net video rate at 5 MHz, Mbit/s |
|---|---|
| BPSK 1/2 | 1.4 |
| QPSK 3/4 | 4.3 |
| 16QAM 3/4 | 8.5 |
| Gaze message in the uplink: 8 bytes at 120 Hz | 7.7 kbit/s of a 1000 kbit/s uplink (0.8%) |" + """

At 4.3 Mbit/s (QPSK 3/4) the difference between a usable and a blurry picture is how the bits are spent; at race-track ranges bitrate, not range, is the constraint. Racing pilots look mostly at the line ahead and the next gate and
high speed suppresses fast peripheral detail, so a fixed or slowly moving high-quality region (head or camera direction) captures much of the benefit without gaze tracking. Freestyle flying could also gain more link types.

**Not proven:** "eyes mostly in one place" is an assumption; pilots also glance at side gates, obstacles, the horizon and the on-screen display [not verified]. Competitive racing does not forgive loss of attention, so the design rule is that
**the high-quality region must never be wrong where the pilot looks**: a wide region, soft edges and a fast fallback to uniform quality. The size of the region must be found by measurement (section 5), not by argument.

## 2. How much can it save [C arithmetic, E rule of thumb]

Region at the base QP, the rest at a higher QP, with the rule of thumb that +6 QP halves the bits of an area (`ratio = f + (1 - f) 2^(-dQP/6)`):

""" + "| High-quality region (share of the picture) | Periphery +3 QP | +6 QP | +9 QP |
|---|---|---|---|
| 25% | 78% (saves 22%) | 62% (saves 38%) | 52% (saves 48%) |
| 40% | 82% (saves 18%) | 70% (saves 30%) | 61% (saves 39%) |
| 60% | 88% (saves 12%) | 80% (saves 20%) | 74% (saves 26%) |" + """

A wide region (60% of the picture) with +6 QP outside saves about 20%; a narrow strong mode (25%, +9 QP) about 48% but is only safe if the region is right. Whole-frame PSNR or VMAF will rate foveation as worse, so quality is judged by a region-weighted metric plus pilot tests (section 5).

## 3. Software-defined modes

The foveation shape (centre, size, falloff width, strength) is a few parameters of a per-block QP-offset map in the encoder; per-macroblock (AVC) and per-coding-unit (HEVC) QP deltas are part of the bitstream syntax, so the decoder in the ground unit needs no change [not re-fetched].
Presets are stored in non-volatile memory, selected by the pilot from the goggles menu or the ground app and sent to the air unit on the uplink:

| Mode | Shape | Use |
|---|---|---|
| 0 | Uniform (default) | Long range, cinematic |
| 1 | Wide and soft | Racing, safe, small saving |
| 2 | Narrow and strong | 5 MHz race channels, maximum saving |
| 3 | Custom | Pilot-defined shape, later a gaze-tracked centre |

Optional: raise the strength automatically as the MCS and bit rate fall (graceful degradation, SYS-004), with a pilot override.

Hooks into the existing requirements: VID-020 (parameters take effect within one slice time without restart: the foveation mode is one more such parameter); VID-006 (the per-slice budget with the 105% hard cap still holds, foveation moves bits between and within slices); VID-004 (8 or more horizontal slices give vertical
selectivity, horizontal selectivity needs the per-block QP delta); VID-011 (header protection) extends to extra protection of the slices that carry the region (VID-025); MAC-004/005 carry the mode and, optionally, the gaze or head direction.

Silicon cost is small: a QP-map generator and a per-block QP path in the encoder, outside the latency-critical path, well under 0.1 mm2 [E, to be confirmed when the encoder is designed].

## 4. Gaze in the loop

A gaze message of 8 bytes at 120 Hz is 7.7 kbit/s, 0.8% of the 1 Mbit/s uplink [C]. The loop delay is the eye-tracker latency plus the frame time of the encoder plus the uplink feedback (0.25 ms in split-band mode); whether that is short enough for saccades (tens of milliseconds) is
a question for the measurement campaign [not verified]. This is why the static modes come first and a gaze-tracked centre is mode 3 later. The gaze comes from the goggles (out of scope, SYS-010) through the host interface of the ground unit (IF-003).

## 5. Open points and the measurement plan

1. **Measure before sizing** (TST-003): record gaze with an eye tracker in goggles during real races and freestyle flights and size the region and the falloff from the measured spread.
2. A fallback trigger to uniform quality (pilot button or an abrupt head or camera movement).
3. Gradual blending of the QP map over a few frames on a mode change to avoid a visible jump (VID-023).
4. A region-weighted quality metric in TG-VID (whole-frame PSNR/VMAF will rate foveation as worse) and a pilot test of each mode.
5. Interaction with reactive slice refresh (VID-021) and with the safety-net refresh wave (VID-005): refreshed areas must not lose the high-quality region.
