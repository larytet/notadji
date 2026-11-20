# 14 - Soft Demapper

Plan entry: module 14 of `spec/18-development-plan.md`, class M, data plane. Requirements: PHY-004 (BPSK, QPSK, 16QAM, 64QAM, 256QAM), PHY-005 and PHY-011 (the LDPC decoder needs soft inputs), PHY-017 (soft combining). Inverse of module 6; feeds the de-interleaver (module 5, element width 8) and the LDPC decoder (module 20). Depends on module 1 and on the mapper definition of `06`.

## 1. Purpose and decision

Turns an equalised complex sample into one log-likelihood ratio (LLR) per coded bit. Convention: **positive LLR means the bit is 0** (the convention of AFF3CT and of most LDPC decoders), magnitude proportional to confidence.

Decision **[E]**: the *folded* (simplified max-log) LLR of Gray-labelled PAM per axis, a well-known cheap approximation that needs only an absolute value, a subtraction per bit and no multiplier except the per-tone reliability weight. Its sign equals the exact max-log decision (it is the nearest-neighbour hard decision); its magnitude differs from the exact max-log value in the outer regions of the constellation (the exact LLR is piecewise linear with a steeper slope there). The cost of the approximation is measured by SIM-002; the exact form can replace it without changing the interface.

## 2. Definition

Input: the sample `{Q[15:0], I[15:0]}` in the amplitude scale of the mapper (RMS 4096 per tone, `06`), a reliability weight `csi[7:0]` (0 to 255, proportional to the channel gain squared over the noise variance of the tone, supplied by the equaliser, module 17; 255 = most reliable, 0 = erased tone), and `mod[2:0]` (as in `06`: 0 BPSK, 1 QPSK, 2 16QAM, 3 64QAM, 4 256QAM, 5 to 7 act as BPSK), both sampled with every beat.

With `m` bits per axis (m = 1 for BPSK and QPSK, 2, 3, 4 for 16QAM, 64QAM, 256QAM) and the per-axis unit `d` of `06` (QPSK 2896, 16QAM 1295, 64QAM 632, 256QAM 314; for BPSK `d` = 4096 on the I axis only), the folded values for an axis amplitude `a` are:

- `f0 = -a`
- `f1 = |a| - 2^(m-1) d` (m >= 2)
- `f2 = | |a| - 2^(m-1) d | - 2^(m-2) d` (m >= 3)
- `f3 = | | |a| - 2^(m-1) d | - 2^(m-2) d | - 2^(m-3) d` (m = 4)

and `LLR_k = saturate8( round( f_k x csi / 2^sh ) )` where `sh` is `llr_shift[3:0]`, a runtime scaling (the same for every bit of the symbol), the rounding is half up and `saturate8` clips to -127..+127. The bits of a symbol are the I-axis bits g0 to g(m-1) then the Q-axis bits g0 to g(m-1), the same order as the mapper input (bit 0 first); BPSK has the single bit `-I`; QPSK has `-I` and `-Q`.

Scaling guidance: the LDPC decoder is nearly scale invariant (normalised min-sum), so `sh` only decides the quantisation: with the nominal weight `csi` = 128 a value of `sh` = 12 puts the distance `d` of 16QAM (1295) at about 40 and a QPSK decision distance (2896) at about 90, leaving headroom; the final value follows from SIM-006.

## 3. Interface

`demapper`: `clk`, `rst_n`, `mod[2:0]`, `llr_shift[3:0]`, `s_axis_*` with `s_axis_data[31:0]` and `s_csi[7:0]` (both sampled with the beat), output `m_axis_*` with `m_axis_data[63:0]` = eight 8-bit signed LLRs (LLR k in bits `8k+7 .. 8k`, unused ones 0), `m_nbits[3:0]` (number of valid LLRs: 1, 2, 4, 6 or 8) and `m_axis_last`. One register stage (latency 1) with full throughput.

`llr_serializer`: takes that beat and emits the valid LLRs one per clock as an 8-bit stream (`m_axis_data[7:0]`) with `last` on the final LLR of a beat that carried `last`; this is the stream the de-interleaver of module 5 takes (element width 8). A beat is accepted when its LLRs have all been taken.

## 4. Test plan

Python model of section 2 (integer arithmetic), a brute-force exact max-log demapper and the mapper definition of `06` (written again in the test, independent of the RTL).

| ID | Test | Pass criterion |
|---|---|---|
| T14-01 | Bit-exact | For every modulation and 40000 (I, Q, csi, shift) points (structured grid plus random): DUT output equals the model |
| T14-02 | Ideal points | The mapper output of every bit pattern (all five modulations) demaps to LLR signs equal to the bits (positive means 0) at `csi` = 255; with `csi` = 0 every LLR is 0 |
| T14-03 | Hard decisions equal nearest-point detection | For 20000 random noisy points per modulation, the sign of every LLR equals the bit of the nearest constellation point found by brute force (ties excluded) |
| T14-04 | Agreement with exact max-log | The sign of the folded LLR equals the sign of the brute-force exact max-log LLR for all random points (reported as a percentage; expected 100%); the magnitude ratio folded/exact is recorded |
| T14-05 | Saturation and csi linearity | Large amplitudes saturate at +/-127; the LLR magnitude scales with `csi` (doubling `csi` doubles the pre-saturation value within rounding) |
| T14-06 | Per-beat configuration and handshakes | Random valid and ready, `mod`, `csi` and `llr_shift` changing every beat (the `pre` hook): equal to the model; protocol stability check passes; `last` passes through |
| T14-07 | Serializer | The LLR stream order is bit 0 first; the right number of LLRs per beat; `last` on the final LLR of the final beat; back-pressure honoured |
| T14-08 | Chain with the mapper model | Random bits, mapped with the mapper definition, noise added (numpy), demapped by the DUT: hard-decision bit errors at high SNR are zero and at 10 dB Es/N0 for QPSK within 20% of the theoretical `Q(sqrt(Es/N0))` value |
| L-14, S-14 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

## 5. Deliverables

`rtl/14-demapper/demapper.sv`, `llr_serializer.sv`, `tests/14-demapper/`, results below, row in `design/README.md`.

## 6. Open items

- Exact max-log instead of the folded approximation (a ROM or piecewise slope per region); to be decided by SIM-002.
- The scale of `csi` against the noise variance is defined by the equaliser (module 17).
- Soft combining of retransmitted slices (PHY-017) adds LLRs of two receptions; a saturating adder stage, not part of this module.

## 7. Results (implementation commit)

Run: `source scripts/sim_env.sh && tests/common/run_tests.sh tests/14-demapper && tests/common/lint_synth.sh tests/14-demapper`.

| Check | Result |
|---|---|
| T14-01 to T14-08 (7 tests in 2 simulations: `demapper`, `llr_serializer`) | 7 of 7 pass: bit-exact equality with the model over about 30000 points covering every modulation, extremes, random `csi` and `llr_shift`; ideal constellation points give the right bits (and zero LLRs at `csi` = 0); random handshakes with configuration changing every beat and `last` pass-through; serializer order, counts and `last` |
| Hard decisions (T14-03) | 0 of 59000 checked bits (QPSK, 16QAM, 64QAM, 256QAM, noisy points) differ from the nearest-constellation-point decision |
| Agreement with exact max-log (T14-04) | 0 differences in sign against the brute-force exact max-log LLR over the same points, as expected for the folded form (same hard decision; only the magnitude differs) |
| Channel check (T14-08), measured | QPSK at Es/N0 = 6 dB over 80000 bits: bit error rate 2.2975e-2 against the theoretical 2.3007e-2 (relative difference 0.14%); 16QAM noisy points: hard decisions equal nearest point |
| Test sensitivity | A deliberate bug (a threshold changed from 628 to 600) failed three tests; the RTL was restored |
| Lint (`verilator -Wall`) | Clean (both tops) |
| Yosys generic synthesis | `demapper` 10108 cells, 70 flip-flops (combinational datapath for both axes and one output register); `llr_serializer` 146 cells, 3 flip-flops; no latches |

Notes:
- The thresholds in the RTL are the rounded `2^(m-1) x unit`, `2^(m-2) x unit`, `2^(m-3) x unit` (2591 for 16QAM; 2528 and 1264 for 64QAM; 2513, 1257 and 628 for 256QAM); the test recomputes them from the exact unit.
- The LLR magnitude of the folded form is not the exact max-log value; the effect on the decoder's frame error rate is the open item for SIM-002 (section 6). The sign agreement above is what makes the approximation safe for hard decisions.
- A first version of the csi-linearity test used amplitudes that saturate the LLR (a test mistake); the amplitudes were reduced.
