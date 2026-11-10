# 03 - Front-End Calibration, Temperature and Antenna Feedback

Status: DRAFT, pass 2. Supports requirements CAL-*, THM-*, ANT-*, RF-006, RF-011, RF-012, RF-024, RF-025.

## 1. Why a calibration architecture

A software-defined transceiver at 33 dBm output and 64QAM needs the analogue front end to behave like a
linear, stable instrument across band, channel, temperature, supply and antenna condition. The goal is that a
frequency hop (RF-006) or a temperature change does not interrupt video, and that a bad antenna never
damages the PA. The architecture has four parts: factory data, background loops, event-triggered re-calibration
and protection.

## 2. Signal chain and sensing points

```
 DAC/IQ -> TX mixer -> driver -> PA -> coupler -> filter/switch -> antenna
   ^           ^                    ^      |  fwd/rev
   |           | LO (PLL/VCO)       |      +--> observation receiver (ADC)   -> DPD, power, VSWR
 cal tone                      bias, temp                                       
 generator                      sensors                              antenna feedback
                                                                      (S11, tuner state)
 antenna -> switch/filter -> LNA -> RX mixer -> ADC  -> DC/IQ/gain cal, RSSI
```

Sensing points:

| Point | What is measured | Used by |
|---|---|---|
| Forward coupler | TX power, envelope for DPD | CAL-005, CAL-006 |
| Reverse coupler | Reflected power (VSWR, return loss) | ANT-002, ANT-003, CAL-008 |
| PA temperature | PA/FEM temperature | CAL-003, THM-002, THM-003 |
| Transceiver die temperature | Gain drift, LO drift | CAL-003 |
| SoC die temperature | Throttling | THM-003 |
| Board temperature near battery | Safety | THM-001 |
| Supply voltage and PA current | Efficiency, brown-out, anomaly | THM-005 |
| RX preamble RSSI per chain | Gain, diversity | ANT-006 |
| Loop-back switch | TX to RX path for IQ/LO calibration | CAL-002 |

## 3. Calibration items

| Item | Method | When | Interrupts video? | Requirement |
|---|---|---|---|---|
| TX LO leakage | Observation receiver measures the carrier, DC offset nulled in the TX path | Factory, on hop to a new channel group, temp change > 5 C | No (done in guard time and idle slots) | RF-025, CAL-002 |
| TX IQ imbalance | Tone at an offset frequency, measure the image, fit a per-frequency correction filter | Same | No | RF-025 |
| RX DC offset | Measured with the LNA input terminated or in an idle slot, subtract | Each frame, tracking | No | RF-024 |
| RX IQ imbalance | Injected tone via loop-back or the noise of the preamble statistics | Factory, background | No | RF-024 |
| RX gain steps | Table of gain per AGC step per band and temperature, factory-measured, then tracked | Factory plus background | No | RF-022 |
| TX power calibration | Detector voltage vs. power table per band, channel, temperature | Factory | No | RF-011 |
| PA bias | Quiescent current set per temperature (lookup plus loop) | Continuous | No | PWR-004 |
| DPD | Memory-polynomial (or generalised memory) model fitted from forward-path samples against the observation receiver | Cold start 200 ms, then tracking at 10 Hz or faster | No (uses the live signal) | CAL-005, RF-014, RF-015 |
| PLL/VCO band selection | Coarse (VCO band) and fine (loop) with a lookup and a lock detector | Each hop | The hop itself takes 50 us | RF-006 |
| Reference oscillator | TCXO temperature compensation plus AFC from the preamble | Continuous | No | RF-007 |
| ADC/DAC | Gain and offset, timing skew between the I and Q and the chains | Factory | No | |
| Antenna feedback loop | VSWR measured from forward/reverse power; adjusts power, DPD seed and (optional) tuner | Continuous, immediate on change | No (power step only) | ANT-*, CAL-006, CAL-008 |
| Multi-element array | Per-element phase and gain with a reference tone | Start-up | Yes (pre-flight) | CAL-010 |

## 4. Calibration data store

- Key: (band, channel group, temperature bin, antenna state). Temperature bins of 5 C, channel groups of
  about 20 MHz at 2.4 GHz and 40 MHz at 5.8 GHz [TBV].
- Content: LO-null codes, IQ filter taps, gain tables, PA bias, DPD coefficient sets (a seed set per bin),
  power detector table.
- On hop (RF-006): load the entry for the target key in 10 microseconds from on-chip SRAM, then run the
  fast refinement in the background. A miss falls back to the nearest key and flags the data stale (CAL-009).
- Factory data in flash with CRC and version (CAL-001); working copy in SRAM; the in-field refinements are
  written back at power-down and every 10 minutes.

## 5. Antenna feedback in the loop

The antenna is part of the RF circuit. The measured VSWR changes the PA load line, hence gain, compression
point and linearity. The feedback is therefore applied at three levels.

1. **Protection (microseconds).** Reverse power above a threshold reduces drive within 10 microseconds and
   shuts down within 1 ms for a bad mismatch (ANT-003).
2. **Calibration (milliseconds).** A VSWR change of 0.5 or more triggers a re-calibration of the power
   detector offset, the PA gain model and the DPD seed (CAL-008). The system keeps the EVM and ACLR
   inside RF-014 and RF-015 even with VSWR up to 2:1.
3. **Adaptation (tens of milliseconds).** The optional tunable match (ANT-005) moves the match toward minimum
   reflected power (hill-climb or model-based). The link budget estimator (ANT-011) updates the predicted
   range because a poor match is a lost-gain term.

With a switched-beam or phased array ground antenna (ANT-008, ANT-009) the beam choice per frame uses the
preamble RSSI and the array calibration (CAL-010); the antenna pattern database (ANT-007) provides the gain per
beam for the power control and for the margin display.

## 6. Temperature handling

- Four or more sensors (THM-001); the PA sensor is sampled at 100 Hz.
- Temperature feeds: (a) calibration bin selection and triggers (CAL-003), (b) the derating state machine,
  (c) the TCXO compensation, and (d) the log (SW-005).
- Derating state machine (THM-003): normal, then at the PA temperature of 85 C reduce power by 3 dB; at 95 C
  reduce the video bit rate; at 105 C reduce the frame rate and TX power to the minimum that keeps the link; at
  115 C send a warning to the pilot and prepare shutdown; at 125 C (or the hardware comparator, THM-006) shut down.
  Thresholds are placeholders [TBV] and depend on the PA datasheet.
- Hysteresis of 5 C, minimum dwell of 2 s in each state to avoid oscillation, and a rate-limited recovery.

## 7. Ramp (rise and fall) times and TDD burst shape

"Rall time" in the original request is read as the TX burst rise/fall time and also the roll time of the
rolling shutter (assumption A-03).

- **TX burst ramp (RF-012).** The PA must ramp up in 2 microseconds or less and down in 2 microseconds or less
  with spectral splatter within the mask (a raised-cosine ramp shaped in the DAC, with the PA bias enabled
  early). This matters because a 1 ms super-frame has two turn-arounds and any slow ramp reduces airtime.
  The ramp shape and the TX-off leakage (-70 dBc within 5 microseconds) are verified with a time-gated
  spectrum measurement.
- **Rolling-shutter roll time.** Sensor readout over about 8 ms is the largest contributor in the latency
  budget (see `02`). The FSIN sync (IF-002) lets the air unit align the sensor frame start to the TDD
  super-frame so that slices leave the encoder just before their airtime slot, keeping the buffering to a minimum.

## 8. Verification

| Test | Equipment | Pass criterion |
|---|---|---|
| EVM/ACLR across temperature | VSA, thermal chamber | RF-014, RF-015 over -10 to +50 C |
| Hop settling | Real-time spectrum analyser, trigger on the burst | RF-006 |
| VSWR sweep (open, short, 2:1, 3:1, 6:1) | Mismatch tuner or attenuators with open/short | ANT-002, ANT-003 |
| Calibration under vibration | Shaker | no calibration loss, ENV-002 |
| Thermal soak without airflow | Chamber | THM-003, THM-004 |
| Power-up cold start | Chamber at -20 C | DPD converges in 200 ms, EVM met |
