# 11 - Patent Search (preliminary landscape, not a freedom-to-operate opinion)

Status: DRAFT, iteration 2 of the second goal. Date of search: 2026-11-10.

## 1. What this is and what it is not

This is a first-pass landscape built from a general web search tool and the Google Patents record pages. It is **not** a
freedom-to-operate (FTO) opinion, it used no commercial patent database, it covers only a handful of topics, and for
several patents only the description (not the claims) could be read. Legal status on Google Patents is explicitly an
assumption. REG-005 requires a real FTO search by a patent attorney before P2 funding; this document is the brief for it.

Confidence labels: **Read** = claims read through the tool; **Partly** = bibliographic data and description read, claims not;
**Lead** = title and abstract fragments seen in search results only.

## 2. Register

| # | Patent | Holder | Status (per Google Patents, assumption) | Confidence | Subject | Relevance to this design |
|---|---|---|---|---|---|---|
| P-1 | US 12,456,952 B2 | Skyworks Solutions | Active, expires about 2042-09-19 (granted 2025-10-28) | **Read** | Independent claims 1, 10, 14: PA, four-port coupler measuring forward and reflected power, a controller that generates digital predistortion, determines the load impedance and adjusts bias current and/or supply voltage "synchronously" with the DPD. VSWR appears only in dependent claims. | **High.** Overlaps ANT-001, CAL-005, CAL-006, CAL-008 if the PA bias or supply is adjusted from the measured load. Design-around D-1 below. |
| P-2 | US 11,070,829 B2 | ATI Technologies | Active, expires about 2039-12-16 | Read (claim 1 summary) | Wireless VR: a rendering unit renders slice 1 while the encoder encodes slice 0, with indications to the encoder and decoder that a slice is being conveyed. | Medium-low. Claim is tied to a rendering unit and indications; our source is a camera sensor. Monitor. |
| P-3 | US 12,470,764 B2 | Huawei Technologies | Active, expires about 2041-02-13 (granted 2025-11-11) | **Partly** (claims not reached) | Wireless projection: destination decodes slice 1 while slice 2 arrives, sends decoded rows to the display before the slice is complete; summary also adjusts the display Vsync from timing information. | **High to be checked.** Resembles VID-008, VID-015 and VID-018 (line-synchronised scan-out, display locked to received timing). Claims must be read. |
| P-4 | US 11,451,788 B2 | Apple | Active, expires about 2039-06-27 | Partly | Rate control for low-latency encoding and transmission in VR/MR: wavelet band decomposition of slices, per-band quantisation using wireless feedback (bit rate, dropped packets). | Medium: overlaps the idea of slice-level rate control from link feedback (VID-006, MAC-004/005); the described method is wavelet-based. Claims must be read. |
| P-5 | WO 2022/217555 A1 | SZ DJI Technology | PCT shown as "Ceased"; a Chinese application number appears in the record (CN202180087141.X) and its status was not checked | Partly (abstract and summary) | Two encoders on the UAV produce two streams; the stream sent depends on the type of the connected device (head-mounted display gets the lower-latency stream, remote controller the higher-resolution stream). | Low-medium: we send one stream and do not select by terminal type; check the CN application status. A claim of this form would not read on a single-stream design. |
| P-6 | US 9,516,335 B2 | Intel | Expired (fee lapse effective 2025-01-13) | Read | Wireless display encoder: per-slice hashing, skip of unchanged slices, per-slice quantisation from channel state. | Low (expired). |
| P-7 | US 9,049,493 B2 | Intel | Expired (fee lapse 2019) | Read | Slice alignment indication field in a 60 GHz audio/video packet header. | Low (expired). |
| P-8 | US 9,813,085 B1 | Qualcomm | Shown as "Expired - Fee Related" | Partly (summary only) | Closed-loop DPD: PA output switched to a receive path for measurements, coefficients from two feedback signals. | Low if expired; claims and lapse reason not read. |
| P-9 | US 11,228,281; US 12,021,571; US 9,979,421 (Eta Devices); US 7,492,223 family | various | Not checked | Lead | PA calibration with VSWR-dependent DPD pause; DPD skipped on antenna loading; DPD observation-receiver training; dynamic bias and predistortion | Related to P-1 (antenna-aware DPD). Read with P-1 in the FTO. |
| P-10 | US 7,603,610; US 7,529,288; US 2002/0186749 | various | Not checked (old filings, likely expired or near expiry) | Lead | Unequal error protection of video; adaptive frequency hopping by channel qualification | Generic techniques from the early 2000s; low relevance. |
| P-11 | CN 108521852 B; US 2020/0302806 (DJI) | SZ DJI | Not checked | Lead | Dual communication systems sending image/video together; OFDM with sub-channel modulation for monitoring data | Context. DJI filings on image transmission exist and have not been reviewed. |

### 2.1 Codec royalties (not patents of a single holder)

| Item | Finding (from web search summaries, not read at source) | Action |
|---|---|---|
| HEVC pools | Access Advance's HEVC Advance pool states over 29,000 patents; the pool previously run by Via LA is now the VCL Advance programme under Access Advance; Velos Media was not covered by the search | Confirm the current pools and rates with the administrators |
| Rate increase | One source says a planned 25% rate and cap increase was delayed and that licensees joining by 2026-06-30 keep current rates; another says current rates and caps are extended through 2030. The two statements conflict and the date has now passed | Ask Access Advance for the current schedule before any HEVC commitment (VID-017) |
| AVC | Not searched; AVC has its own pool (administrator not confirmed) | Include in the same review |
| Patent landscape for DJI-style products | No DJI OcuSync patent claims were retrieved; the Autel/DJI ITC disputes found concern drone hardware, not video links; DJI v Insta360 (2026) and DJI v Irdeto (2025) concern other products | Run a proper assignee search (SZ DJI, Qualcomm, Texas Instruments, Huawei, Apple, Intel, Skyworks, Analog Devices) |

## 3. Topics searched and result

| Topic | Result |
|---|---|
| DJI image transmission, low-latency slice encoding | One DJI application (P-5); no DJI slice-encoding claim found; slice encoding is described as a known technique in general literature |
| DJI adaptive frequency hopping / OcuSync | No DJI hopping claim retrieved; only general adaptive-hopping patents and a UAV-detection family that describes OcuSync as derived from Lightbridge |
| JSCC / UEP / OFDM / slice rate adaptation | Only generic and old patents; no hit on the combination |
| PA DPD with antenna feedback | Several (P-1, P-8, P-9); P-1 is active and close |
| TDD timing advance / guard period for UAV video | Cellular and satellite concepts only; no UAV-specific patent retrieved (timing advance is standard cellular technology) |
| HDZero, Walksnail, Caddx patents | No patent found (product pages only) |

## 4. Design-around constraints adopted in the spec (pending counsel)

| ID | Constraint | Why | Spec item |
|---|---|---|---|
| D-1 | PA bias current and supply voltage shall be set from temperature and PA current only; they shall **not** be adjusted as a function of the measured load impedance or VSWR while DPD is active. The measured reflection may be used for power fold-back, for selecting a DPD coefficient set, for the optional tunable match and for alarms. | Avoids the combination recited in the independent claims of P-1 (DPD plus load impedance plus bias/supply adjustment, synchronously) | New requirement REG-006; text in ANT-003, CAL-008 and `03` section 5 checked |
| D-2 | Decoded rows reach the display through a line-synchronised scan-out; read the claims of P-3 first. If they read on VID-008/015/018, options are to licence, to change the mechanism (for example frame-start-aligned scan-out with a small elastic buffer instead of per-row hand-off) or to restrict the feature to regions without cover. | P-3 description is close to the design | Open item O-1 |
| D-3 | Rate control uses link feedback to set the per-slice budget but does not use wavelet band decomposition | P-4 describes a wavelet-band method | Open item O-2 |
| D-4 | One video stream, no terminal-type-dependent stream selection | P-5 | Noted |
| D-5 | Non-adaptive fast hopping is not used in ETSI regions (EN 300 328 limits non-adaptive hopping to 5 ms on-time followed by a 5 ms gap [from search summary, to be checked in the standard]); fast hopping must be adaptive there | Regulatory (not a patent) | ADA-003 note |

## 5. Open items for the patent attorney

| # | Item |
|---|---|
| O-1 | Read the claims of P-3 (US 12,470,764) and judge reading on VID-008, VID-015, VID-018 |
| O-2 | Read the claims of P-4 (US 11,451,788) and its family |
| O-3 | Check CN 202180087141.X (P-5 national phase) status and claims |
| O-4 | Full assignee search on SZ DJI Technology for image transmission, frequency selection, OFDM link adaptation and low-latency encoding (CPC H04N 19, H04L 5, H04B 7, H04W 56) |
| O-5 | Search Qualcomm, Texas Instruments, Analog Devices, Skyworks, Qorvo for DPD plus antenna sensing (extend P-1, P-8, P-9) |
| O-6 | Confirm HEVC/AVC pool membership, rates and the 2026 rate schedule |
| O-7 | TDD timing advance for point-to-point drone links; LDPC short-block code families and their holders |
| O-8 | Patent status of the Remote ID and Bluetooth stacks (use of certified module reduces exposure) |
