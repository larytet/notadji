# 15 - Requirement Rationale

Status: DRAFT. Source: review notes entries 19 and 20 and the instruction that every requirement shall be explained somewhere in the spec. Evidence labels as in `12`: **[C]** computed by `scripts/link_budget.py` or checked by `scripts/audit_numbers.py`, **[S]** sourced, **[E]** engineering estimate, **[TBV]** to be verified.

## 1. Rule

Every requirement in `01` has an explanation in this document: why the value is what it is, which alternative was considered, and which test or document proves it. There are two levels:

1. **Worked derivations** (section 2) for the requirements whose number or structure drives the design: the formula, the inputs, the assumptions, at least two options with their trade-offs, and the decision. The numbers come from `scripts/link_budget.py` and are checked by the audit.
2. **Rationale table** (section 3) for every requirement ID (the audit fails if an ID is missing): the basis of the value, the alternative that was not taken, and where it is proved. Where a full derivation already exists in `02`, `03`, `07` or `13`, the row points to it.

A requirement is not complete until it has a row here. Assumptions marked [E] are the first candidates for the measurement plan (notes entry 16).

## 2. Worked derivations

### 2.1 VID-004 slice-based encoder

Requirement (`01`): the encoder is slice-based with at least 8 slices per frame, each slice independently decodable and independently protected.

**What the words mean.** A slice is a horizontal band of the picture (a whole number of macroblock rows in AVC, coding-tree-unit rows in HEVC). *Independently decodable* means that within one frame no intra prediction, motion-vector prediction or entropy-coding context crosses a slice boundary, so a slice that arrives complete can be decoded and displayed whatever happened to the other slices of that frame. *Independently protected* means that a slice has its own header, its own authentication tag (SEC-002), its own slice-aligned codeword packing (PHY-005) and its own acknowledgement bit (MAC-004), so one lost slice costs one slice and nothing else. Independence is within a frame only: inter prediction still reads the previous frame, so a lost slice damages later frames until it is refreshed (VID-021, VID-005). Removing that dependency is option E below.

**Why slices at all: latency.** Without slices each stage of the chain (sensor, ISP, encoder, air, decoder) waits for the whole frame before passing it on, which is store-and-forward and violates LAT-005. With N slices each stage waits one slice time, 1/N of what it waited before. In the budget of `02` section 2 the part that scales with the slice time is 6.0 ms at N = 8 (sensor readout of one slice 1.0, ISP 1.0, half of the encoder 1.0, air time 2.0, half of the decoder 1.0 [E]), so

    latency(N) - latency(8) = 6.0 ms x 8 x (1/N - 1/8) = 48 ms x (1/N - 1/8)

N = 1 costs 42 ms more than N = 8, which is why vendor pipelines measure 80 to 95 ms for the camera half alone [S] (`12`).

**Why at least 8: the encoder budget.** VID-007 allows 2.0 ms from first pixel in to first slice bits out at 1080p60. The first slice cannot leave before its own rows have been read out, so the budget is the slice fill time plus the encoder core: `T_readout / N + t_core <= 2.0 ms`. With the sensor readout of 8 ms (IF-002) and the 1.0 ms the encoder core has at N = 8 [E]:

| Slices N | 1080p60: fill + core ms (budget 2.0) | 1080p120: fill + core ms (budget 1.2) |
|---|---|---|
| 2 | 5.00 fails | 2.70 fails |
| 4 | 3.00 fails | 1.70 fails |
| 6 | 2.33 fails | 1.37 fails |
| 8 | 2.00 meets | 1.20 meets |
| 16 | 1.50 meets | 0.95 meets |

N = 8 is the smallest integer that closes the budget at both frame rates; N = 7 gives 2.14 ms and fails. The 1.0 ms and 0.7 ms core times are what the VID-007 budgets leave at N = 8, so this is a consistency result, not independent evidence; the encoder core time must be measured (G-05, VID-007).

**What more slices cost.** Four costs grow with N (1080p60, 20 Mbit/s, 648-bit codewords; assumptions in `scripts/link_budget.py`, [E] until the open-encoder experiment of notes entry 16 replaces them):

- Header and tag: 26 bytes (NAL and slice header 8, authentication tag 16, length and sync 2) per slice, `N x 208 bit / 333 kbit`.
- Boundary penalty: broken intra and context prediction, 0.15% of the frame bits per boundary [E].
- Codeword padding: slice-aligned packing wastes half a 486-bit information codeword per slice on average (PHY-005); with the 1944-bit cruise codeword (1458 information bits) it is three times larger.
- Reactive refresh: a lost slice is re-coded intra (VID-021). The loss events per frame are independent of N to first order (`codewords x codeword error rate`, 686 x 1.2e-5 per frame), but each event refreshes only 1/N of the frame at 4 times the bits, so the cost is `1.2e-5 x 686 x 3 / N`.

| Slices N | MB rows per slice (68 rows) | Picture share lost per slice | Latency against N = 8, ms | Header + tag | Boundary | Padding | Reactive refresh | Total bit-rate cost |
|---|---|---|---|---|---|---|---|---|
| 1 | 68.0 | 100.0% | +42.0 | 0.06% | 0.00% | 0.07% | 2.47% | 2.6% |
| 2 | 34.0 | 50.0% | +18.0 | 0.12% | 0.15% | 0.15% | 1.23% | 1.7% |
| 4 | 17.0 | 25.0% | +6.0 | 0.25% | 0.45% | 0.29% | 0.62% | 1.6% |
| 8 | 8.5 | 12.5% | +0.0 | 0.50% | 1.05% | 0.58% | 0.31% | 2.4% |
| 16 | 4.2 | 6.2% | -3.0 | 1.00% | 2.25% | 1.17% | 0.15% | 4.6% |
| 34 | 2.0 | 2.9% | -4.6 | 2.12% | 4.95% | 2.48% | 0.07% | 9.6% |

Reading the table: the bit-rate cost has a minimum at N = 2 to 4 and rises steeply after N = 8, while the latency gain flattens. The marginal gain per percent of bit rate is 6.0 ms / 0.8% = 7.5 ms per percent from N = 4 to 8, 3.0 ms / 2.2% = 1.4 ms per percent from 8 to 16, and 1.6 ms / 5.0% = 0.3 ms per percent from 16 to 34. N = 8 is the knee. A slice loss at N = 8 hides 12.5% of the picture (a band of 8 or 9 macroblock rows), which concealment from the previous frame (VID-010) covers acceptably; at N = 4 the band is 25% and at N = 1 the whole frame.

**Geometry.** 1080 rows pad to 1088 = 68 macroblock rows = 17 coding-tree-unit rows of 64. Eight slices cannot be equal: four slices of 9 and four of 8 macroblock rows (plus or minus 6% in size); with 64-pixel CTUs the split is 2 or 3 rows, plus or minus 20%, so the HEVC mode uses 17 slices (one CTU row each) or 32-pixel CTUs. Unequal slices unbalance the per-slice budget of VID-006, which therefore sets the budget in proportion to the slice's share of the picture. 4K has 135 macroblock rows and splits more evenly.

**Options.**

| Option | Description | Latency | Bit-rate cost | Loss granularity | Verdict |
|---|---|---|---|---|---|
| A | One slice per frame (frame-based encoder, a stock hardware codec as shipped) | +42 ms, store-and-forward | 2.6% | whole frame | Rejected: breaks SYS-001 and LAT-005 |
| B | 4 slices | +6 ms, first slice out at 3.0 ms against 2.0 | 1.6% | 25% | Rejected: fails VID-007; acceptable only for a 30 fps cinematic mode with no latency target |
| C | 8 slices, configurable up to 34 (chosen) | baseline | 2.4% | 12.5% | **Chosen as the minimum and default** |
| D | 16 to 17 slices (one HEVC CTU row each) | -3.0 ms | 4.6% | 6.2% | Allowed by "at least 8" and selected by the race profile when the bit rate is high enough to afford it; below about 8 Mbit/s the fixed cost (headers, padding) is a larger share and N = 8 is better |
| E | Slice-confined motion vectors (motion-constrained slices): a lost slice does not damage later frames | as C | higher than C: motion cannot point across slice boundaries, the loss grows with motion and is content dependent [not verified] | 12.5%, no propagation | Rejected for the baseline because propagation is already bounded by reactive refresh (VID-021) at 0.3%; kept as a research option for a machine mode |

**Decision and consequences.** VID-004 stays at "at least 8 slices", configurable from 8 to 34 (default 8) so the race profile can go to 16 or 17. Consequences carried by other requirements: slice-aligned codeword packing (PHY-005), a per-slice acknowledgement bit (MAC-004, 8 bits for N = 8), the per-slice budget and its 105% cap (VID-006), the slice error rate target of 1e-3 (PHY-011, `07` T-07), 8 or more horizontal slices for the vertical selectivity of the foveation map (VID-023). **Verification:** an encoded 1080p stream is dissected, every slice is decoded alone with the rest removed (independent decode), a bit error is injected in one slice and the others stay bit-exact (independent protection), and the first-slice-out time is measured against VID-007 (TG-VID in `08`). **Open:** the boundary penalty and the encoder core time are [E]; the open-encoder experiment (x264 and x265 with slices, notes entry 16) replaces the first and the hardware encoder measurement the second.

### 2.2 VID-005 no I-frames, rolling intra refresh

Requirement: no I-frames in steady state; a rolling intra-refresh wave with a period of 60 frames or less is the safety net (about 5% overhead [E]); recovery from detected losses uses reactive slice refresh (VID-021).

**Why no I-frames.** At 10 Mbit/s and 60 fps the average frame is 167 kbit. An I-frame is 5 to 10 times a P-frame [E], 0.8 to 1.7 Mbit, which takes 83 to 170 ms to send at 10 Mbit/s. That frame arrives that much later, so latency jumps by about the same against the 20 ms of SYS-001, the 100 ms freeze limit of SYS-004 is broken, and the 105% slice cap of VID-006 cannot hold.

**Rolling wave.** Each frame a thin column band is coded intra and moves across the picture. With period N = 60 and 1920 columns the band is 1920 / 60 = 32 pixels wide, and a full refresh takes 60 frames = 1 s at 60 fps. Every frame has nearly the same size. If intra blocks cost k times the bits of inter blocks, the overhead is `(k - 1) / N`: with k = 4 and N = 60 it is 3 / 60 = 5%, so the 5% implies intra blocks four times as expensive (the rule that refreshed areas must not reference not-yet-refreshed areas is part of k). N = 30 with the same k gives 10%.

| Refresh period (frames) | Time at 60 fps ms | Overhead (1/N x (r - 1), r = 4) |
|---|---|---|
| 8 | 133 | 38% |
| 15 | 250 | 20% |
| 30 | 500 | 10% |
| 60 | 1000 | 5% |

**Options.** (A) Periodic I-frames: simplest, latency spikes, rejected. (B) Rolling intra-refresh wave only: constant frame size, recovery from any loss within N frames (1 s at N = 60), 5% overhead. (C) Reactive slice refresh only (VID-021): 0.3% overhead, recovery in 1 to 2 frames (17 to 35 ms) [E], but blind to a lost acknowledgement, a decoder restart, a band hop or a ground unit joining mid-stream. (D) Both, chosen: reactive refresh handles nearly all losses cheaply and the wave is the safety net that guarantees a clean picture within N frames. A column wave spreads the intra blocks evenly over the 8 slices, so every slice budget stays balanced; a row wave would make one slice fully intra each frame and unbalance VID-006. The trade-off in N is recovery time against overhead; N = 60 is the bound in the requirement and the encoder may use a smaller value when airtime allows.

**Assumptions to check:** k = 4 (content dependent) and the loss rate, with the open-encoder experiment of notes entry 16.

### 2.3 VID-002 sensor interface

Requirement: MIPI CSI-2, 4 lanes, D-PHY 2.5 Gbit/s per lane minimum.

**Formula.** Required rate = width x height x frames per second x bits per pixel x (1 + margin). 4K60 at 12 bit is 3840 x 2160 x 60 x 12 = 5.97 Gbit/s; with a 25% margin for blanking and lane utilisation [E] it is 7.46 Gbit/s, which needs 3 lanes at 2.5 Gbit/s. Four lanes give 10 Gbit/s, about 34% spare (14-bit data, HDR pass-through VID-012, sensors with inefficient bursts). Other formats with the same margin: 1080p60 RAW12 1.87, 720p240 3.32, 1080p120 3.73, 4K30 3.73 Gbit/s (1 or 2 lanes).

**Latency view.** A 1920-pixel RAW10 line is 19.2 kbit, 7.7 us on one 2.5 Gbit/s lane against a sensor row time of about 7.4 us (8 ms over 1080 rows, IF-002), so one lane has no slack; four lanes take 1.9 us. The interface is not the latency limit: the 1.0 ms row of the latency budget is dominated by waiting for the sensor. Packet overhead is small, 4 byte header plus 2 byte CRC per line is 0.25% of the line.

**Options.** (A) 4 lanes fixed (chosen for the first product): justified by 4K60 plus margin, not by the 1080p latency target. (B) Lane count configurable as 1, 2 or 4: simple products save D-PHY area and pins (no area figure yet, to be taken from the IP vendor). (C) 2 lanes: enough for 1080p up to 120 fps, rejected because VID-001 lists 4K60. Verification is inspection against the sensor datasheet (I).

## 3. Rationale table

Columns: **Basis** is why the value is what it is; **Alternative** is what was considered and not taken; **Proved by** is the document, trade study or test.

### 3.1 System (SYS)

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| SYS-001 | Glass to glass 20 ms at 1080p60 is the sum of the stage budget in `02` section 2 (15.0 ms plus 3.0 ms reserve = 18.0 ms); 12 ms at 1080p120 from the same table (10.7 ms). Vendor pipelines measure 80 to 95 ms for the camera half alone [S], so the target is a design goal, [TBV] | 33 ms (two frames at 60 fps, what frame-based pipelines reach) is easy but gives no gain over existing digital links | `02` section 2; TG-LAT; PRO-006 baseline and TST-002 rig |
| SYS-002 | First FPGA milestone relaxed by 10 ms: the prototype uses a hard codec (VCU) and an evaluation transceiver whose stage latencies are not tuned (`13`) | Require 20 ms already in P1: not credible before the stage latencies are measured | TG-LAT in phase A and B |
| SYS-003 | Range classes S/X/L (5, 10, 14 km) are the link budget of `02` section 1: free-space path loss plus 6 dB margin at the lowest MCS that carries 10 Mbit/s; classes differ in antenna gain; free space only, so real range is lower (G-02) | A single class, or range stated without margin; both hide the antenna trade (`07` T-01) | `scripts/link_budget.py`; range flights |
| SYS-004 | Graceful degradation needs a quality ladder because a hard drop to a frozen picture is the failure mode of existing links; 100 ms is six frames at 60 fps, the longest a pilot tolerates before the picture is useless. Feasibility review and rewrite proposal in notes entry 15 | Analogue-like continuous degradation by joint source-channel coding (`07` T-07 option B), a research track | Region-weighted quality against SNR, freeze measured at the display |
| SYS-005 | Input power follows from output power and PA efficiency: `P_in = P_out / PAE` with `PAE = 0.55 sqrt(P/Psat)` and a modulation back-off (`02` section 3, `scripts/link_budget.py` pa_mode_table): 3.5, 4.1, 6.0 W; the efficiency is a model [E] | A fixed 30 dBm limit for all modulations: 64QAM at 30 dBm would need 6.3 W (RF-031) | PA study (T-14), bench power measurement |
| SYS-006 | 25 g is a mass budget: electronics 6 to 8 g, PA 1 g, shield 2 to 3 g, antennas and cables 3 to 4 g, heatsink 8 to 12 g (notes entry 17); heat, not electronics, sets the mass | Mass per power class (25 g to 27 dBm, more at 30 dBm), proposed in entry 17 | Weighing, THM-004 hover test |
| SYS-007 | Ground unit battery life: energy = power x time; 3 h at 6 to 15 W needs 18 to 45 Wh, which a 1S pack (about 11 Wh) cannot give; a change to 1 h with hot swap is proposed in notes entry 18 | Keep 3 h and require a 2S or larger pack | Battery run test |
| SYS-008 | One pilot may fly several drones or share a ground unit; 4 is the group size of the relay and mesh options (notes entry 14) and costs only a table of keys and channels | Strictly one to one (simpler pairing, SEC-001) | Pairing test with 4 air units |
| SYS-009 | Channel counts follow from band width and the adjacent-channel rule: 5.8 GHz band 125 MHz gives 6 links at 20 MHz, 12 at 10 MHz, 25 at 5 MHz; the 7 m separation and 500 m range come from the near-far levels in `07` T-05 (184 m and 7 m separation) | Fewer, widely spaced channels (no adjacent use), halving the race capacity | `07` T-05; near-far test with real units |
| SYS-010 | Goggles optics and head tracking are separate products; the ground unit outputs standard video (VID-015) | Integrate the display (a product, not a link) | Inspection |
| SYS-011 | Allowing separate silicon for each unit keeps the air unit at minimum mass and power and lets the ground unit use many chains; the cost is a second tape-out (break-even 21 to 24 million units, `07` T-22) | One identical chip for both (baseline) | Conformance test of the on-air protocol (SW-003) |

### 3.2 Video (VID) and latency (LAT)

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| VID-001 | Formats of common FPV and cinematic cameras; 4K may exceed the latency by 1.5 frame times because a 4K encoder is not yet cut-through | 1080p only (smaller encoder, no cinematic market) | Format test |
| VID-002 | Derived in section 2.3 (5.97 Gbit/s for 4K60 at 12 bit, 7.46 with margin, 3 lanes needed, 4 given) | 1, 2 or 4 lanes configurable | Inspection of sensor and D-PHY |
| VID-003 | AVC is the baseline because hard encoders and decoders exist and the slice tools are mature; HEVC gives about 30% less rate for the quality mode [not verified for this use]; codec-agnostic slicing keeps a custom codec possible (`07` T-06) | AV1 or a custom intra codec (T-06): licence free but no low-latency hardware | T-06; latency measurement per codec |
| VID-004 | Derived in section 2.1 | See the options table in 2.1 | Slice dissection test |
| VID-005 | Derived in section 2.2 | Periodic I-frames; reactive refresh only | Loss injection with the open encoder |
| VID-006 | A rate buffer of one slice bounds the delay a rate overshoot can add to one slice time (2.1 ms at N = 8); the 105% cap keeps a slice inside its airtime; source review S-4 found vendor caps that never bound (all 863 access units over a 6000 byte cap) [S] | Frame-level rate control, a buffer of several frames: smoother quality, tens of ms of latency | Bitstream analysis, not encoder readback |
| VID-007 | Slice fill time 8 / N plus core time: 1.0 + 1.0 = 2.0 ms at N = 8 (section 2.1) | Frame-based encoder, 16.7 ms and more | Hardware measurement (G-05) |
| VID-008 | Mirror of VID-007: slice bits in, first line out, so display scan-out starts before the frame is complete | Decode the whole frame, +16 ms | Hardware measurement (G-05) |
| VID-009 | 80 Mbit/s is the high end (4K, cinematic) and fits 40 MHz 64QAM 3/4 at 10 km (audit); 1 Mbit/s is the lowest useful picture | Fix a smaller range (no cinematic mode) | Rate sweep test |
| VID-010 | Concealing from the previous frame hides a slice for one to two frames at no airtime cost; motion compensation is optional because it costs decoder area | Freeze the whole frame (visible), or retransmit (MAC-006, only if time) | Loss injection |
| VID-011 | A header error loses the slice and sometimes the frame, residual data errors only degrade it; 6 dB more protection costs a lower code rate on a few hundred bits | Equal protection (simpler, header loss rate equals data loss rate) | Header error rate test (`07` T-07) |
| VID-012 | 10-bit and HDR pass-through for cinematic users; optional because it costs 25% more interface rate and encoder area | 8-bit only | Format test |
| VID-013 | Electronic stabilisation needs one frame of delay; optional and switchable so the zero-latency path remains | Gimbal only (mass) | Latency with the mode on and off |
| VID-014 | A local full-quality copy makes the air link a monitoring path, which is what cinematic users expect; independent of the radio | Record at link quality only | Recording test |
| VID-015 | A line-synchronised scan-out starts displaying before the frame is complete, saving up to one frame (`02` section 2); a fixed-rate panel scanning independently adds up to 16.7 ms | Frame buffer plus vsync, +8 ms average | Photodiode test |
| VID-016 | Pilots need flight data on the picture; MSP DisplayPort and MAVLink are the existing sources | Draw in the flight controller (the existing analogue practice) | Interop test |
| VID-017 | AVC and HEVC are covered by patent pools whose terms depend on volume and product; a review before P2 funding avoids a surprise (search results were conflicting) | Ship with the codec disabled by region | Legal review |
| VID-018 | Two free-running 20 ppm crystals drift 2.4 ms per minute, two TCXOs 0.24 ms per minute (`07` T-17); locking the display to the received frame timing removes the drift; steering of +/-50 ppm covers the worst crystal pair | Drop or repeat frames when the buffer over- or underruns: visible judder | Display lock test over 10 minutes |
| VID-019 | Audio is optional; 48 kHz at 32 to 128 kbit/s is voice and music quality; the 40 ms lip-sync bound is the perceptual limit | No audio (smaller design) | Audio test |
| VID-020 | Source review S-4 to S-7 found hidden encoder limits in a vendor stack: a 120 fps ceiling with a silent reset to 30 fps and SDK calls that succeeded without effect; the requirement forbids silent replacement and demands the stated ceilings | Accept vendor limits | Parameter sweep test |
| VID-021 | Reactive refresh costs `1.2e-5 x 686 x 3 / 8 = 0.31%` (section 2.1) against 5% for the wave; it needs the acknowledgement within one frame (MAC-004 gives 1 ms) | Wave only (5%), retransmission (needs airtime and time) | Loss injection |
| VID-022 | At BPSK 1/2 the video band carries 6.9 Mbit/s (`02`), so 6 Mbit/s of video at 720p30 is the usable minimum that reaches 10.3 km at 5.8 GHz and 25 km at 2.4 GHz with 6 dB margin | Report range at 1080p60 only | Reference video set and range flight |
| VID-023 | Per-block QP offsets are in the AVC and HEVC syntax, so the decoder needs no change; saving by region and offset in `14` section 2 (20% to 48%) | A separate high-quality slice (coarse, only vertical) | Region-weighted quality test (TST-003) |
| VID-024 | A few presets make the feature usable from a goggles menu; mode 3 leaves room for gaze | Free parameters only (hard to use) | Pilot test |
| VID-025 | The slices carrying the region may use a lower code rate (1/2 against 3/4) when airtime exists, so the region survives fades the rest does not | Equal protection | Slice error rate test |
| LAT-001 | A photodiode or camera at 1000 fps resolves 1 ms; the register-step method (OpenIPC latency probe) splits the camera half from the rest on one clock | Visual stopwatch photo (accuracy 10 ms) | Rig calibration |
| LAT-002 | A pilot feels jitter more than a constant delay; p99 within 3 ms and p99.9 within 8 ms of the mean is under half a frame; a stale frame is dangerous for machines too (notes entry 22) | Mean only | Histogram over 10 minutes |
| LAT-003 | 2.5 ms covers the airtime of one slice (about 2.0 ms) plus modem pipeline; the budget row in `02` | A frame of air time (16 ms) | Modem loopback with timestamps |
| LAT-004 | Without a per-stage timestamp the latency budget cannot be audited or improved | End-to-end measurement only | Trace port output |
| LAT-005 | Cut-through is what makes slice latency (2.1) possible; store-and-forward of a frame costs 16.7 ms per stage | Frame buffers for simplicity | Inspection and timestamps |
| LAT-006 | Retransmission and interleaving buy robustness at the cost of delay (2 sub-frame retransmissions, deeper interleaving, up to 40 ms); a switch lets one product serve racing and cruising (`07` T-07, T-16) | One compromise mode | Mode test |

### 3.3 Physical layer (PHY)

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| PHY-001 | A constant 78.125 kHz spacing makes the FFT size proportional to bandwidth (64 to 512 for 5 to 40 MHz) so one engine serves all widths; `FFT x 78.125 kHz = bandwidth` (audit) | Fixed FFT with varying spacing: different symbol times per width complicate the MAC (`07` T-04) | `07` T-04; audit |
| PHY-002 | 5 MHz for race channel counts and the split-band uplink, 20 MHz baseline, 40 MHz for 80 Mbit/s; 80 MHz optional because it halves the channel count | 20 MHz only | Spectrum test |
| PHY-003 | Symbol 12.8 us with a 1/16 cyclic prefix (13.6 us) covers the delay spread of line-of-sight links; at 3.5 kHz Doppler (about 650 km/h at 5.8 GHz) inter-carrier interference is about -22 dB (Jakes approximation, audit), 1.0 kHz for 256QAM which needs -32 dB or better | 802.11 spacing 312.5 kHz: shorter symbol, 3.2 us prefix, worse efficiency at long delay | Doppler simulation (G-25) |
| PHY-004 | Constellations to 64QAM for the bit rate; 256QAM only where EVM allows (RF-014) | Stop at 64QAM | EVM test |
| PHY-005 | LDPC outperforms convolutional codes at short blocks and is hardware friendly; 648 bits keeps the decode time (about 10 us) and the slice padding (0.58% at N = 8) small in race mode, 1944 bits gains about 1 dB in cruise mode (`07` T-16) | Turbo or polar codes (T-16) | Link simulation |
| PHY-006 | Two receive chains give maximal-ratio combining (about +3 dB and fading resilience); more branches are the ground-unit lever in PHY-016 | One chain with antenna switching (-3 dB) | Diversity test |
| PHY-007 | The channel can change within a frame (3.5 kHz Doppler, coherence time about 100 us); pilots every 0.25 ms keep estimation current | Pilots only in the preamble (fails above about 300 Hz) | Fading simulation |
| PHY-008 | Cheap crystals are 20 to 25 ppm off at start (5.8 GHz: 145 kHz); acquisition removes it, residual 0.1 ppm keeps the phase error below the OFDM limit | TCXO only (RF-007) | Acquisition test |
| PHY-009 | OFDM peak-to-average power of 8 to 10 dB needs back-off; the PAE model puts 64QAM at 7 dB and QPSK/16QAM at 6 dB (`02` section 3); the 4 dB of rev 0.6 was wrong | Constant-envelope modulation (low rate) or DFT-s-OFDM (PHY-014) | PA bench test |
| PHY-010 | Preamble acquisition (detect, AGC settle, sync) of 40 us is 0.2% of a 20 ms frame and fits the 0.5 ms receive budget | Longer preamble: better acquisition at low SNR, costs airtime | Modem test |
| PHY-011 | A slice error rate of 1e-3 is one lost slice per 17 s at N = 8 and 60 fps (0.48 slices per second at the limit); it is a codeword error rate of 1.2e-5 for 86 codewords per slice at 20 Mbit/s (`scripts/link_budget.py`) | 1e-2 (0.3% to 3% refresh cost, visible damage), 1e-4 (needs about 1 dB more SNR) | Link simulation; PER test |
| PHY-012 | Adaptation four times per second tracks shadowing; up to once per frame follows fast fades; MAC-005 sets the response | Fixed MCS with margin (loses 6 dB or more) | Adaptation test |
| PHY-013 | Programmable numerology lets the prototype run an 802.11-compatible reference mode (PRO-001) on the same engine | Separate WiFi chip | Mode test |
| PHY-014 | DFT-spread OFDM has 3 to 4 dB lower PAPR [E], so the PA can run at higher efficiency; optional because it costs some spectral efficiency; trigger is a PA study showing PAE below 27% | Accept the lower efficiency or a larger PA | Simulation, PA bench |
| PHY-015 | 155 Mbit/s of decoded information with a 10 us codeword time follows from 80 Mbit/s peak video with 1.9 times margin in the layered-decoder model of `07` T-16 [E] | Smaller decoder with fewer iterations (loses about 0.3 dB) | Synthesis; RTL simulation |
| PHY-016 | Combining across N branches gives `10 log N` dB of array gain in the noise-limited case (3 dB per doubling), minus up to 1.5 dB of correlation loss [E] (`02` section 1.3) | More transmit power: not possible for the uplink, and not wanted (regulation is a profile) | Branch test |
| PHY-017 | More decoder iterations and soft combining of retransmitted slices buy about 0.5 to 1 dB [E]; the decoder area grows to keep the 0.5 ms latency | Same decoder as the basic unit | Simulation; latency test |

### 3.4 MAC

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| MAC-001 | In-band TDD needs the uplink slot and a guard of one round-trip: 1 ms frames to 7 km, 2 ms to 15 km, 4 ms beyond; the downlink share is 0.76 to 0.93 (`02` section 4, `07` T-03) | Fixed 1 ms (guard dominates beyond 7 km) or 2 ms (adds latency at short range) | `scripts/link_budget.py` tdd_table |
| MAC-002 | Contention (CSMA) adds random delay that cannot be bounded; a scheduled link has none, and coexistence is handled by channel choice (ADA-001) | CSMA for WiFi coexistence: unbounded jitter | Scheduling test |
| MAC-003 | 1 us timing is 0.5% of a symbol and well inside the 0.8 us guard interval | Looser sync with wider guard (loses airtime) | Preamble timing test |
| MAC-004 | Feedback once per millisecond gives the ACK bitmap to the encoder within 1 ms, so reactive refresh (VID-021) acts on the next frame; content (CSI, MCS, RSSI, 8 ACK bits) is 100 bits (`scripts/link_budget.py`) | Feedback once per frame (adds up to 16 ms) | Uplink test |
| MAC-005 | 2 ms is one slice time of video, so the encoder adapts within about one slice; slower response loses slices in a fade | Frame-level adaptation (16 ms) | Adaptation test |
| MAC-006 | A retransmitted slice that arrives after its display deadline is useless and wastes airtime; the rule retransmits only when the deadline can be met | Always retransmit (late data), never retransmit (loses the cheap recovery) | Deadline test |
| MAC-007 | Telemetry and control at 1 Mbit/s uplink with 6 dB margin at class range; margins 17.0, 11.0 and 12.4 dB for classes S, X, L in split-band mode (`02` section 1.1b); 5 ms latency keeps MSP and MAVLink usable | Lower rate uplink (100 kbit/s, less capacity for gaze and machine data) | Uplink budget; test |
| MAC-008 | An optional 1 kHz RC channel with 3 ms latency and a 100 ms failsafe serves the pilots who want one radio; most use a separate control link | Separate control link only | Latency and failsafe test |
| MAC-009 | Field pairing without a network: key exchange by SEC-001, 10 s keeps a repair from grounding a flight | Pairing by cable or app | Pairing test |
| MAC-010 | A channel change costs at most one frame (16.7 ms): hop settling 50 us (RF-006), re-sync, one refresh wave of the lost slices | Re-acquire from scratch (hundreds of ms) | Hop test |
| MAC-011 | The uplink must arrive aligned with the air unit's slot; the round-trip delay is 67 us at 10 km, so timing advance with 0.1 us resolution (15 m) places it in the guard | No advance and a wider guard (loses airtime beyond 7 km) | Range test |
| MAC-012 | Split-band removes the uplink slot from the video band: downlink share 0.95 against 0.76 to 0.93 and an uplink margin of 11 to 17 dB; costs a second radio (`07` T-03, T-15) | In-band TDD only (MAC-001, kept as fallback); out-of-band beacon only | `02` section 1.1b |
| MAC-013 | 8 bytes at 120 Hz is 7.7 kbit/s, 0.8% of the 1 Mbit/s uplink (`14` section 4); the loop delay for saccades is unproven | Static modes only | Gaze loop test (TST-003) |

### 3.5 RF and antenna (RF, ANT)

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| RF-001 | 2.4 and 5.8 GHz are the licence-free bands where FPV exists today; band limits are the allowed edges (R) | One band only | Conducted test |
| RF-002 | 5 GHz U-NII bands with DFS add channels; 900 MHz and 863 MHz give range and the uplink band for 2.4 GHz video | Not supported | Conducted test |
| RF-003 | 1.2, 1.3 GHz (amateur) and 2.3 GHz (licensed) serve special users and are covered by the software-defined front end | Not supported | Option test |
| RF-004 | P1 uses an off-the-shelf SDR that tunes 70 MHz to 6 GHz; P2 narrows to the product bands | Fixed bands in P1 (no sub-GHz tests) | Datasheet |
| RF-005 | 1 MHz raster allows the channel plans of `07` T-05 and 5 MHz uplink channels | 5 MHz raster (fewer channel positions) | Tune test |
| RF-006 | Hop in 50 us and between bands in 150 us so a hop costs under 1% of a 20 ms frame; AD9361 fast lock 15 to 25 us [S] and ADRV9002 13 us hop frames [S] are in range | Slower PLL (hop costs a frame) | Hop timing test |
| RF-007 | 2 ppm TCXO plus AFC from the preamble keeps the residual under the PHY-008 limit; 20 ppm crystals drift 2.4 ms per minute (VID-018) | Plain crystal (less cost, more drift) | Frequency counter |
| RF-008 | At 5.8 GHz 0.6 degrees RMS integrated phase noise gives an error vector contribution about -40 dB, below the -35 dB of 256QAM | Looser phase noise (limits 256QAM) | Phase noise analyser |
| RF-009 | 5 us is a quarter of a symbol and 0.5% of 1 ms; AD9361 reaches TDD turn-around through the ALERT state and 5 us is not demonstrated [at risk in P1] | 10 us (the TDD budget uses 10 us with ramps, `02` section 4) | Bench test |
| RF-010 | 33 dBm is the capability ceiling (FCC rule is a profile, REG-008); standard classes 25, 27 and 30 dBm follow the mass and power budget (SYS-005, SYS-006) | Capability equal to the FCC limit only | Conducted power |
| RF-011 | 40 dB of range lets the link reduce power for near range and coexistence; 1 dB accuracy keeps the regional limit with margin | 20 dB range | Power calibration |
| RF-012 | A ramp of 2 us (about 15% of a symbol) limits splatter; the -70 dBc leak within 5 us protects the uplink receiver in the same unit | Slower ramp (smaller spectrum cost, more airtime lost) | Spectrum analyser |
| RF-013 | Masks of the rules in REG-001 with 3 dB margin for production spread | Exactly at the mask | Conducted test |
| RF-014 | Error vector magnitude -32 dB at 64QAM (needs 21 dB SNR plus margin) and -35 dB at 256QAM after DPD, aggressive and unproven at 1 W (`12`) | Fix the EVM to what the PA gives and restrict constellations | EVM test |
| RF-015 | -45 dBc adjacent-channel leakage protects the neighbour channel in race mode (`07` T-05) | -40 dBc (a neighbour at 10 m would lose 1 dB) | ACLR test |
| RF-016 | FCC general limit of -41.25 dBm/MHz outside the band (R); 50 dB for the second and third harmonic with the FEM filter | Separate harmonic filter (mass) | Spurious test |
| RF-020 | Sensitivity `-101 dBm + 10 log(BW/20 MHz) + NF + SNR + 2 dB` (audit): -93 dBm at BPSK 1/2 with NF 4 dB at 20 MHz | A datasheet figure without a model | Conducted sensitivity |
| RF-021 | 3.5 and 4.0 dB are what a transceiver with an internal LNA and a switch reaches (AD9361 datasheet 2 dB best case [S]) | 2 dB with a discrete LNA (RF-032) | Noise figure meter |
| RF-022 | Close range at 10 dBm EIRP and 5 dBi antennas gives -10 dBm; survive +10 dBm; AGC settles in 20 us so the preamble is not lost | Narrower range (needs attenuators on the aircraft) | AGC test |
| RF-023 | A co-located WiFi or ELRS radio is the realistic interferer: -40 dBm at 20 MHz and -25 dBm at 100 MHz offset | Rely on filters in the system | Blocking test |
| RF-024 | 40 dB image rejection leaves the image 40 dB below the signal, better than the 21 dB SNR of 64QAM | 30 dB (limits 256QAM) | Calibration test |
| RF-025 | -45 dBc LO leakage and image keep the transmit EVM budget (RF-014) | -35 dBc | Calibration test |
| RF-026 | A GNSS receiver is the most sensitive device on the drone; 3 dB desensitisation at 10 cm is the integration limit (`03`) | 1 dB (hard to reach without shielding) | Desensitisation test |
| RF-027 | Two ports give diversity (ANT-006) and two transmit streams | One port | Inspection |
| RF-028 | External PA control lines let PAs of three vendors be used; the PA is the biggest unknown (T-14) | Fixed PA (single supplier risk) | Inspection |
| RF-029 | Race mode neighbours: a 35 dBm EIRP air unit at 10 m gives about -33 dBm; the receiver must tolerate -30 dBm adjacent and -25 dBm alternate channel with 1 dB desensitisation (`07` T-05) | Larger separation (restricts the race pit) | Receiver blocking test |
| RF-030 | The 5.8 GHz transmitter at 30 dBm with its broadband noise must not desensitise the 2.4 GHz uplink receiver in the same 25 g unit; 70 dB is the antenna separation plus the filtering [E, TBV] (`02` section 1.1b) | In-band TDD (MAC-001) | Isolation measurement |
| RF-031 | Efficiency falls with back-off: 64QAM at 30 dBm would need 6.3 W against 4.1 W at 27 dBm (`02` section 3) | A single cap for all modulations | PA table check |
| RF-032 | A discrete LNA and a preselector reach 2.0 dB system NF against 4.0 dB for the integrated front end, a 2 dB sensitivity gain in the unit that can afford it | Integrated front end only | Noise figure meter |
| ANT-001 | A coupler at the PA output gives forward and reflected power for DPD, power control and VSWR; the technique is known in patents, so not novel (REG-006) | Detector in the PA only (no VSWR) | Bench test |
| ANT-002 | VSWR 1 to 10:1 with 0.3 accuracy at 3:1 distinguishes a good antenna from a damaged one; once per second in the background | VSWR from DC current only (inaccurate) | Calibrated load test |
| ANT-003 | Above 3:1 the PA is at risk; fold-back 6 dB and shut-down within 1 ms above 6:1 protect it from a missing antenna | Hardware limiter only | Open and short test |
| ANT-004 | A hand over the antenna or a broken antenna is the most common field fault; the pilot needs an indication | Silent power reduction | Fault injection |
| ANT-005 | A tunable match recovers 1 to 2 dB when the antenna is detuned; optional because it adds parts and loss | No tuner | Detuned antenna test |
| ANT-006 | Diversity per frame in the guard time or combining on two chains is the cheapest fading protection | Single antenna | Diversity test |
| ANT-007 | The link budget estimator and tracking need gain, beamwidth and polarisation per antenna | Fixed assumptions | Inspection |
| ANT-008 | Six sectors of 60 degrees azimuth and 40 degrees elevation or narrower give 10 dBi or more per beam (`07` T-13); four sectors give only 6.6 to 9.6 dBi | Omni antenna (5 dBi), tracker dish (fixed sites only) | `scripts/link_budget.py` sector_table; field test |
| ANT-009 | Electronic steering with 4 or more elements gains `10 log N` plus tracking without moving parts; per-element calibration is needed (CAL-010) | Switched sectors only | Beam pattern test |
| ANT-010 | Circular versus linear polarisation mismatch loses 3 dB; a two-antenna receiver covers both | One polarisation | Polarisation test |
| ANT-011 | A predicted range and margin on the OSD tells the pilot when to turn back | No prediction | Field test |
| ANT-012 | Coax loss 0.41 dB/m at 5.8 GHz [E]: a passive cable to 2 m costs about 0.8 dB; beyond 5 m the loss equals a noise figure penalty (Friis), so an LNA sits at the antenna (`02` section 1.4) | Mount the unit at the antenna (mass, access) | Cable loss and Friis table |
| ANT-013 | Angle of arrival from the per-beam preamble level (coarse) and the per-branch phase (fine): 1.6 degrees of bearing per 5 degrees of phase error at half-wavelength spacing, 139 m of cross-range at 5 km (`02` section 1.5) | Receive-only direction finder as a separate device | Bearing test |
| ANT-014 | Air-unit beamforming options A to D trade gain (0 to 6 dB) against mass (0 to 15 g) and power; only for large drones because 25 g does not hold (notes entry 17) | Omni only | `02` section 1.5; flight test |

### 3.6 Adaptation, calibration, thermal, power (ADA, CAL, THM, PWR)

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| ADA-001 | The ground unit has the better receiver and the power; a 50 us dwell per channel scans 20 channels in 1 ms of receiver time | Air unit scans (more load on the 25 g unit) | Scan test |
| ADA-002 | 20 ms decision latency is about one frame: faster decisions flap on noise, slower ones lose video | Immediate switch on one bad frame | Interference injection |
| ADA-003 | A static adaptive channel is the default because hopping costs settling time and airtime; fast hopping (1 to 10 ms dwell, 20 channels) is kept for anti-jam only; ETSI non-adaptive hopping limits are in the search summary of EN 300 328 and are to be checked | Hopping always (ELRS practice) | Hop test; `07` T-15 |
| ADA-004 | Band hop when the link is lost: 300 ms by the stored hop sequence and the control channel; link-loss recovery otherwise takes seconds | Re-scan from scratch | Link loss test |
| ADA-005 | The control channel must stay robust and low rate so a lost video link can be re-established; in split-band mode the uplink is that channel | One band for everything (no recovery path) | Recovery test |
| ADA-006 | Region compliance as signed data (REG-008) avoids per-country code paths and keeps one binary | Per-region firmware | Region table test |
| ADA-007 | The spectrum view the pilot gets before flight prevents most interference surprises | No view | Display test |
| ADA-008 | Radar detection in the DFS bands is required by regulation where those bands are used; 10 s move time and 260 ms closing transmission are the rule values (R) | Do not use DFS bands | Radar test pattern |
| ADA-009 | Adaptivity rules (listen before talk, frame-based idle) are met inside the TDD slot structure so the 2.5 ms of LAT-003 holds; the 5% idle share of the split-band downlink is for this | Separate sensing time | Regulatory test |
| ADA-010 | A strong adjacent signal above -60 dBm desensitises the receiver (RF-029); the scan finds it and lowers power or changes channel | Ignore | Neighbour test |
| ADA-011 | A second receiver scans continuously so the video receiver gives up no airtime and radar detection runs in parallel; costs one more chain | Scan with the video receiver (basic unit) | Scan test |
| CAL-001 | Per-unit factory calibration stored with a CRC and version (`03` section 3): production spread of gain, IQ and leakage is larger than the specification | Typical values (spread lost) | Production test |
| CAL-002 | Drift in the field (temperature, aging) must be tracked without breaking video, so the observation receiver works in guard and idle slots (`03`) | Calibrate only at start (drifts with temperature) | Long run test |
| CAL-003 | 5 degrees C is about the drift that moves gain by 0.5 dB; every 60 s covers slow drift | Fixed 5 minute interval | Thermal chamber |
| CAL-004 | A table per (band, channel group, temperature bin) lets a hop restore calibration in 50 us (RF-006) instead of recalibrating | Recalibrate after a hop (ms) | Hop timing test |
| CAL-005 | DPD must converge in 200 ms and track thermal change at 10 Hz; PA memory effects settle in that time | Offline DPD only (drifts) | DPD test |
| CAL-006 | A closed power loop with 100 us settling corrects temperature and load changes within a frame | Open loop (1 to 2 dB error) | Power step test |
| CAL-007 | A calibration tone outside the mask would be an illegal emission; the limiter applies during calibration too | None | Spectrum test during calibration |
| CAL-008 | A changed antenna (VSWR step above 0.5) changes the PA load and the power detector offset; recalibrate within 50 ms. Overlaps the Skyworks patent only if bias or supply were adjusted (REG-006) | Ignore (power drifts) | Antenna swap test |
| CAL-009 | The pilot and the log need to know if calibration is stale | Hidden | Telemetry check |
| CAL-010 | A beamformer needs per-element phase and gain to a few degrees (ANT-013) | No beamforming | Calibration test |
| THM-001 | Four sensors (PA, transceiver, SoC, board) are the heat sources and the battery side; 100 Hz at the PA follows its thermal time constant of tens of ms | One die sensor | Sensor test |
| THM-002 | Calibration and derating use the same data (CAL-003) | Separate sensing | Test |
| THM-003 | Stepwise derating (power, bitrate, frame rate, shut-down) keeps the link alive as long as possible; 125 degrees C is the silicon limit | Hard shut-down at one threshold | Thermal chamber (G-17) |
| THM-004 | 10 minutes in a hover without airflow at 40 degrees C ambient and 4 W is the worst realistic case; the heatsink is the largest mass item (notes entry 17) | Require airflow (fails on the ground) | Thermal test |
| THM-005 | Supply and PA current at 1 kHz give efficiency tracking and detect faults | Voltage only | Sensor test |
| THM-006 | A hardware comparator trips even if software is dead | Software only | Fault injection |
| PWR-001 | 2S to 6S (6 to 30 V) covers FPV and cinematic packs; 60 V 1 ms surge and 2 Vpp ripple from ESCs are typical on the bus | 1S to 4S (smaller converter) | Surge test |
| PWR-002 | A 3 s boot means a restart after a brown-out is tolerable (HSI-007 target 1.5 s) | 10 s | Boot test |
| PWR-003 | ASIC 1.5 W is the line in `02` section 3; the FPGA prototype is 7.5 W [S] plus 1.5 W transceiver | Lower target (needs a smaller process) | Power measurement |
| PWR-004 | PAE 27.5% at 30 dBm with DPD for QPSK/16QAM is a model value `0.55 sqrt(P/Psat)` [E]; typical class-AB PAs reach less | Lower PAE and a larger input power budget | PA study (T-14) |
| PWR-005 | Standby of 1 W keeps a link alive without video; PA and encoder are off | Same as streaming | Power test |
| PWR-006 | 5 mW sleep with RAM retention; Remote ID runs on its own module (REG-002) | Full off (no fast restart) | Power test |

### 3.7 Security, regulatory, environment (SEC, REG, ENV)

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| SEC-001 | ECDH with an authenticated short code avoids shared default keys that were the weakness of earlier links | Pre-shared key | Pairing test, review |
| SEC-002 | ChaCha20-Poly1305 needs no AES hardware and is used by wfb-ng [S]; a tag per slice authenticates each independent slice (VID-004) at 16 bytes; below 0.2 ms | AES-256-GCM (hardware option), no authentication (injection risk) | Latency test |
| SEC-003 | Signed firmware, bitstreams and tables stop modified software from changing RF limits | Unsigned (open to tampering) | Boot test |
| SEC-004 | Detection of wideband jamming and fallback to fast hopping and lower rate | No anti-jam | Jammer test |
| SEC-005 | A hardware limiter locked by a signed table keeps compliance while the stack is open (47 CFR 2.944 and U-NII security guidance [R]) | Fully open RF control (not certifiable) | Limiter test; counsel |
| SEC-006 | Options are entitled the same way as regions; one mechanism | Separate fuses | Boot test |
| REG-001 | The rules that apply to the bands in RF-001 and RF-002, plus the cyber-security delegated act of the Radio Equipment Directive | Region by region | Certification |
| REG-002 | Remote ID is mandatory for most drones; a separate certified module works with the main device off | RID in the main chip (certification of the whole) | Certification |
| REG-003 | Encryption makes export classification necessary before shipping | None | Legal review |
| REG-004 | Standard product compliance | None | Legal review |
| REG-005 | Several references are GPL, AGPL, non-commercial or unlicensed (`04`, MANIFEST); clean-room writing avoids contamination; the patent search is preliminary (`11`) | Reuse code | Licence register |
| REG-006 | US 12,456,952 claims bias and supply adjustment from load impedance with DPD; setting them from temperature and current only avoids the claim (`11`) [attorney to confirm] | Licence | Design review |
| REG-007 | 47 CFR 2.944 and the U-NII guidance require a software security statement before certification | None | Counsel |
| REG-008 | Compliance as configuration lets one design serve every region and keeps range requirements for the hardware capability (notes entry 9); operation must still be lawful (conducted, shielded or experimental licence) | Design to the strictest rule | Region table review |
| ENV-001 | -10 to +50 degrees C full specification covers consumer practice; -20 to +60 operating with 3 dB EVM relaxation; storage to 85 degrees C | Narrower range | Chamber test |
| ENV-002 | Random vibration 10 g RMS at propeller harmonics; TCXO microphonics below 1 dB | 5 g | Vibration test |
| ENV-003 | 100 g for 6 ms is a typical crash; the unit must boot afterwards for the next flight | 50 g | Shock test |
| ENV-004 | IEC 61000-4-2 levels for user and antenna ports | Lower | ESD test |
| ENV-005 | Humidity and IPX4 for field use | Dry only | Test |
| ENV-006 | 5000 m with thermal derating (air density) | Sea level only | Analysis |
| ENV-007 | Video pipeline clocks (MIPI, DDR) radiate; more than 1 dB desensitisation loses range directly | Shielding by case only | Desensitisation test |

### 3.8 Interfaces, software, integration (IF, SW, HSI)

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| IF-001 | UART up to 3 Mbaud with MSP and MAVLink 2 is the flight-controller practice; USB and CAN-FD for bigger platforms | UART only | Interop |
| IF-002 | Sensor readout 8 ms at 1080p60 and 4 ms at 1080p120 is the assumption of the latency budget (G-15); a fixed frame period keeps the pipeline timing (source review S-5) | Free exposure (the sensor stretches the frame) | Sensor test |
| IF-003 | HDMI, DP and DSI are what displays take; USB-C and Ethernet for the app | HDMI only | Interop |
| IF-004 | JTAG, UART and a trace port for latency stamps are needed for bring-up | None | Inspection |
| SW-001 | The control plane may be slow and complex, the data plane must not stop; 100 ms is the video freeze limit (SYS-004) | All in software | Stall test |
| SW-002 | A HAL lets prototype and ASIC share software | Direct register access | Inspection |
| SW-003 | Open interfaces are the purpose of the project | Closed | Inspection |
| SW-004 | Over-the-link update with rollback is needed for fleets in the field | Cable update | Update test |
| SW-005 | A 1 kHz ring buffer that survives a crash gives forensic data | Logging to flash (slow) | Crash test |
| HSI-001 | Three domains (`13` section 1); the data plane carries on for 100 ms with every processor stalled | Everything on one processor | Stall test |
| HSI-002 | A sequencer executes the microsecond actions (hops, turn-arounds) from a table committed a frame ahead; software cannot meet 5 us | Software timing (jitter above 5 us) | Timing test |
| HSI-003 | A 5 ns counter at every stage boundary gives LAT-004 | Software timestamps | Trace check |
| HSI-004 | DPD correlation (73.7 Mcycles/s) and crypto (40 Mcycles/s) in software would load a 300 MHz core to 49% against 11% (`13` section 2, audit) | Software with a faster core (power) | `scripts/cpu_budget.py` |
| HSI-005 | 50% worst-case load leaves margin for estimation error (the workload is estimated) | 80% | Measurement |
| HSI-006 | Estimates in `13` section 2 must become measurements | Estimates only | Measurement |
| HSI-007 | The real-time path boots alone in 1.5 to 3 s, the application core is not in the critical path | Boot Linux first (10 s) | Boot test |
| HSI-008 | 5 us interrupt entry at 300 MHz (1500 cycles) supports 20 us AGC and 100 us loops [TBV] | Polling | Measurement |
| HSI-009 | 100 mW streaming and 5 mW sleep fit the 0.7 W baseband line of `02` section 3 [target] | Higher | Power measurement |
| HSI-010 | Two-phase platform plan (`13` section 3): evaluation boards first, then a custom board, then ASIC; limits cost and risk early | Custom board first | Phase gates |
| HSI-011 | A stalled control core is detected by the sequencer and the link falls to a safe schedule (lowest MCS, reduced power) | Watchdog reset (video loss) | Fault injection |
| HSI-012 | One register map and a versioned HAL for phases A, B and C | Per-phase interfaces | Inspection |
| HSI-013 | The DPD solve is a matrix problem sensitive to conditioning; validate before choosing the core | Pick a core first | Numerical test |
| HSI-014 | A blocking queue lets a slow core stall a fast one | Locks | Code review, stress test |
| HSI-015 | A fault in one task must not corrupt the others | Flat memory | Fault injection |

### 3.9 Prototype, ASIC, test (PRO, ASC, TST)

| ID | Basis | Alternative | Proved by |
|---|---|---|---|
| PRO-001 | A WiFi mode on the same video pipeline gives a fair comparison with the custom PHY (`07` T-11) | Compare with a separate WiFi chip | Comparison test |
| PRO-002 | A Zynq UltraScale+ class device has a hard video codec (VCU) so the first encoder exists without writing one; VCU presence on the K26 is unconfirmed (`12`) | Soft encoder core (months of work) | Phase A and B tests |
| PRO-003 | An AD9361/AD9364/ADRV9002 class transceiver has an observation path for calibration and DPD experiments | Different SDR (`07` T-12) | Datasheet; bring-up |
| PRO-004 | BLE for pairing, RID and out-of-band control in the prototype; never video | Wi-Fi sideband | Test |
| PRO-005 | ASIC-portable RTL (wrapper layer, CDC clean) avoids a rewrite | FPGA-specific code | Lint and CDC |
| PRO-006 | A measured baseline of a stock camera pipeline is the reference for the budget | Assume the figures | Measurement |
| PRO-007 | Phase A in two configurations: PlutoSDR pair (2.4 GHz video, 915 MHz uplink, inside its 325 MHz to 3.8 GHz range [S]) and an AD9361-class pair for 5.8 GHz | One configuration | Bring-up |
| ASC-001 | Two dice: RF in a mature node and the digital in 12 to 22 nm, 29 plus 18 mm2 against 45 to 50 mm2 for one die, isolating RF from digital noise (`07` T-08, notes entry 21) | Single die in 22 nm FD-SOI (later cost-down) | T-08; RF noise test |
| ASC-002 | Integration list so that the product needs only the PA, memory and sensor | Separate codec chip | Block review |
| ASC-003 | Production test time dominates cost at volume; 60 s per unit with scan, BIST and RF loopback | Functional test only | Test plan |
| ASC-004 | Area targets from `effort.md` (29 mm2 digital, 18 mm2 RF) rounded up [TBV, G-23] | Larger die | Synthesis |
| ASC-005 | USD 12 per chip at 100k units per year [TBV]; cost model open (G-23) | No target | Cost model |
| ASC-006 | The inter-die interface 2.95 Gbit/s (2 chains, 12-bit I/Q, 40 MHz) at 5 to 20 pJ per bit is 15 to 59 mW per end (`scripts/link_budget.py`) | Single die (no interface) | Interface table |
| ASC-007 | Replicating the RF die gives 8 receive chains on one digital SoC (11.8 Gbit/s at 40 MHz) without a second tape-out | Dedicated ground chip | `07` T-22 |
| ASC-008 | All options in the silicon with signed selection avoids per-class tape-outs; unused gates are gated; area cost 1.5 to 4 mm2 [E] | One chip per class | `07` T-23 |
| ASC-009 | Provisions made at day one (chain count, chip-to-chip interface, shared clock, calibration path) avoid a respin when larger options are used | Add later (respin) | Design review |
| TST-001 | A requirement without a test is a wish; `08` maps each to a case and `09` is generated | Manual matrix | Script |
| TST-002 | 0.5 ms accuracy is half a millisecond against a 20 ms target (2.5%) | 1 ms | Rig calibration |
| TST-003 | The foveation region size must be measured before it is sized (`14` section 5) | Argue from assumption | Campaign |

