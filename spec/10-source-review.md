# 10 - Source Review (iteration 1 of the second goal)

Status: DRAFT. Method: read the protocol drafts, specs and docs inside the downloaded reference set
(`reference/`, 372 repositories) looking for facts that confirm, contradict or sharpen the SRS. Only statements found in the
files are recorded here, with the file. Vendor and retailer claims are labelled as claims.

## 1. Findings

| # | Source (file under `reference/`) | Fact | Effect on the spec |
|---|---|---|---|
| S-1 | `wifibroadcast/wfb-ng/doc/wfb-ng-std-draft.md` | The 802.11 ACK mechanism stops working beyond about 200 m ("may vary"), so raw-injection links must supply their own MAC. Payload rates up to 8 Mbit/s (MCS 1) over "tens of kilometers" on RTL8812AU/EU. | Confirms that an own MAC without ACK timing (MAC-002) is needed; shows commodity-WiFi range is limited by rate, consistent with the 6 Mbit/s closure found in `02`. P0 cannot test timing advance (MAC-011). |
| S-2 | same | Packet pipeline: UDP/RTP, FEC (Reed-Solomon on a Vandermonde matrix, `fec_k`/`fec_n`), ChaCha20-Poly1305 AEAD (libsodium), one WiFi frame per FEC fragment. | ChaCha20-Poly1305 needs no AES hardware and is a proven choice for per-packet AEAD: made the default in SEC-002 (AES-256-GCM kept as the hardware option). |
| S-3 | `openipc/latency-probe/README.md` | A latency method that needs no LED or photodiode: step a sensor register over I2C and timestamp the write and the arrival of the first changed frame on one clock. Measured camera half on stock IP-camera SoCs: write to loopback p50 82 to 95 ms at a frame period of 18.5 ms, of which about 25 to 27 ms are ISP tail, encoder and packetising; the register-step method overstates glass-to-wire by about one frame period because the sensor applies the gain 1 to 2 frames later. | (a) Vendor pipelines spend 25 ms or more between capture stamp and the first packet; our budget for the same stages is about 4.5 ms (`02` section 2). This is the main reason for a custom encoder path. (b) The method is added as a secondary measurement for LAT-001/TST-002 and the P0 baseline. |
| S-4 | `openipc/waybeam/specs/2026-07-17-capped-vbr-rc-mode/requirements.md` (withdrawn spec) | On SSC338Q, H.265 CBR with GDR, `maxPBytes` and `maxIBytes` did not bind: with a 6000 byte cap all 863 access units exceeded it; the I-size cap left IDRs at 66 to 81 KB. "An SDK call that returns success and reports its value back on read can still be a no-op; the only trustworthy check is the encoded bitstream." | VID-006 (per-slice constant bit budget) cannot be met with this class of vendor encoder. The requirement is made verifiable on the bitstream and a hard bound is added (VID-006 rev 0.4, new VID-020). |
| S-5 | `openipc/waybeam/specs/2026-07-06-star6e-144fps-bitrate-overshoot/requirements.md` | The Infinity6E encoder rejects input frame rates above 120 fps and silently resets to 30 fps, causing a 4.7x bitrate overshoot; a driver also extended VMAX when auto-exposure asked for the full frame time. | Hidden ceilings and silent resets are a failure class: new VID-020 (no hidden limits, fail loudly). Frame-rate-locked exposure policy added to IF-002 (fixed frame period, exposure clamped below the frame time). |
| S-6 | `openipc/waybeam/GOAL.md` | Encoder reference-structure changes (`rally`, `range`, `fpv` presets with reference frames) need a pipeline respawn, while GOP and intra-refresh changes are live. Intra-refresh is "GDR-style rolling stripe". | Our rate and refresh control must be live per slice (VID-005, VID-006); structural changes mid-flight must not interrupt video (new text in VID-020). |
| S-7 | `openipc/waybeam/README.md`, `docs/` | Intra-refresh QP parameter is accepted but ignored by the SigmaStar encoder for I-frame QP; the working lever is another rate-control input. | Same class as S-4; supports requiring an open, fully controllable encoder (PRO-002, T-11 recommendation). |
| S-8 | `sdr-phy/openwifi/README.md` and `doc/app_notes/frequent_trick.md` | 10 microsecond SIFS achieved in an FPGA MAC; DCF engine can be disabled for fixed timing; injection and CSI available; licence AGPLv3, with a separate commercial licence. | Confirms an FPGA MAC can hit microsecond timing (our RF-009 5 us, MAC turn-around 10 us); licence stance unchanged. |
| S-9 | `hd-zero/hdzero-docs`, `hdzero-goggle2/README.md` (vendor claims) | "Lowest and fixed latency" with a 540p60 camera; HDMI input routed to the display in under 1 ms with no frame buffer; "4 ms glass-to-glass sub-frame latency" for an integrated goggle pipeline. | Vendor claims, not measured by us. Consistent with the display scan-out allocation in `02` (4.0 ms at 60 Hz, 2.5 ms at 120 Hz); shows the target is realistic only with a line-synchronised display path (VID-015, VID-018). |
| S-10 | `openipc/docs/.../fpv` FAQ | "As low as about 25 ms at 720p 120 fps" depending on ground hardware (claim). | Baseline claim to be re-measured in P0 (observation 3 of `05`). |
| S-12 | `svpcom/rtl8812eu/hal/phydm/halrf/` and `svpcom/rtl8812au/...` (Realtek driver, GPLv2) | The open WiFi driver code contains the chip's RF calibration framework by file name: IQ calibration (`halrf_iqk*`), LC-tank/VCO calibration (LCK), digital pre-distortion calibration (`halrf_dpk_8822e.c`), TX signal strength indicator (TSSI) and thermal-meter-based power tracking (`halrf_powertracking*`), TX gap calibration, and factory-offset handling (`halrf_kfree`). Names only; behaviour not verified by running it. | Cross-check of `03`: our list (LO leakage, IQ, LC/VCO, DPD, power detector, temperature tracking, factory data) matches what a commercial WiFi chip does; this is a behavioural reference only (GPL). Added to `03` section 9. |
| S-11 | `reference/MANIFEST.tsv` | 86 of 372 repositories have no licence file. | Unchanged policy (REG-005); verified count now stated. |

## 2. Spec re-read (items found while cross-checking documents 00 to 09)

| # | Item | Resolution |
|---|---|---|
| R-1 | `08` lists the G2G rig as a photodiode/camera only | Add the register-step method as a second method (S-3) |
| R-2 | `02` section 2 budgets encoder 2.0 ms and "MIPI and ISP-lite 1.0 ms" with no evidence; sources show vendor values 10x larger | Keep targets but mark the encoder and ISP-lite rows as "no open reference exists", P0 and P1c measurements to confirm (done in `02`) |
| R-3 | `05` observation 3 quotes latency claims without the camera-half measurement | Added to `05` as observation 5 |
| R-4 | `04` P0 exit criterion does not say which latency method is used | P0 exit now references PRO-006 |
| R-5 | `00` document map lacks `10` | Added |

## 3. Spec changes made in rev 0.4

| Requirement | Change |
|---|---|
| VID-006 | Adds a hard bound (no slice over 105% of its budget) verified on the encoded bitstream, not from encoder readback |
| VID-020 (new) | No hidden encoder limits: every rate, refresh and structure parameter takes effect within one slice time, unsupported values are rejected with an error (never silently replaced), frame-rate ceilings of at least 120 fps at 1080p and 240 fps at 720p |
| IF-002 | Adds fixed frame period policy: exposure limited below the frame time so that the sensor never stretches the frame |
| LAT-001, TST-002 | Add the register-step timing method as a secondary measurement |
| SEC-002 | Default cipher ChaCha20-Poly1305, AES-256-GCM as the hardware option |
| PRO-006 (new) | P0 baseline: measure camera half and G2G of a stock IP-camera pipeline with the latency-probe method and with the rig, and record them as the reference |

## 4. Not found in the sources

Verified by search across all 372 repositories:

- No open RTL for a low-latency slice encoder or a video codec: the only HDL is ADI libraries (763 files), openofdm,
  openwifi-hw (109), BTLE (44); no file matching `*h264*`, `*h265*` or `*hevc*` in HDL.
- No published HDZero FPGA/ASIC design (the repositories are firmware and documentation).
- No FPV project implements its own calibration. The calibration code that exists (IQK, LCK, DPK, TSSI, thermal
  tracking) is the Realtek WiFi chip's driver-side framework (S-12); the others rely on it.
- No antenna VSWR sensing in any FPV software (the `vswr`/`return loss` hits are in the Realtek driver headers, not an
  antenna-feedback loop).
