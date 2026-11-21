# R31 - DFT-spread OFDM low-PAPR mode (PHY-014)

Source: `spec/01` PHY-014: *"Optional low-PAPR mode: DFT-spread OFDM for BPSK, QPSK and 16QAM with a PAPR at least 3 dB below plain OFDM at a CCDF of 1e-3 [E], selectable per link; it is the mitigation if the PA study shows less than 27% PAE at OFDM QPSK/16QAM."* Priority O (optional), phase P2. Related: PHY-009 (PAPR reduction plus DPD, back-off at most 7 dB / 6 dB; not met together at 7 dB by module 26, see `design/26`), PHY-001/003/004, PHY-013, RF-014/RF-015 (emission mask, EVM), SYS-005 (air-unit power).

## 1. Scope

In scope: the transmit-side DFT spreading stage and the receive-side despreading (IDFT) stage with frequency-domain MMSE weighting, for the FFT sizes 64 to 512 of the existing tone plan (module 7); their integration into the transmit chain (module 16) and the receive chain (module 21) behind a per-frame mode bit; the measurement of the PAPR gain and of the link-level cost; the signalling constraints.

Out of scope: the 80 MHz mode (N = 1024), DFT-s-OFDM for 64QAM and 256QAM (not required; the mode exists for the power-limited case), a hardware noise-variance estimator (the receiver gets the noise level as a parameter), a header bit and its protection (the mode bit is a frame configuration input), pi/2-BPSK pulse shaping variants.

## 2. Definitions

- **Plain OFDM**: modules 6, 7, 12, 16 as built.
- **DFT-s-OFDM**: the data symbols of the frame carry `M` constellation points per OFDM symbol that are first transformed by an `M`-point DFT; the `M` outputs occupy `M` **contiguous** tones around DC (`k` = -M/2 .. M/2 without `k` = 0), the rest of the spectrum is null. Training symbols (STF, LTF), prefix and the IFFT are unchanged. **There are no frequency-domain pilot tones in a DFT-s data symbol** (see section 4).
- **M**: `3N/4` (48, 96, 192, 384 for N = 64, 128, 256, 512). It is a product of a power of two and 3, so the DFT is built from power-of-two FFTs and one radix-3 stage. The tones used are `|k|` <= `3N/8` (inside the plan of module 7: 24 <= 26, 48 <= 58, 96 <= 122, 192 <= 244); the data tones of plain OFDM that fall outside (0, 12+, 42+, 84+) stay null, which costs a throughput of 0, 11%, 18%, 18% of the plain OFDM data tones and also lowers the out-of-band energy.
- **PAPR**: peak to mean power of the oversampled (4x) complex baseband signal of the data symbols (the preamble excluded), complementary CCDF at 1e-3.
- **Mode bit** `dsofdm`: per frame, sampled with the frame start like the other configuration inputs.

## 3. Requirements

| ID | Requirement | Acceptance criterion | Verified by |
|---|---|---|---|
| R31-01 | A transmit stage shall compute the `M`-point DFT of the `M` mapper samples of a symbol, scaled to keep the RMS amplitude (4096 for the mapper scale of `06`), for N = 64, 128, 256, 512. | RTL output equals the integer model; against a floating-point DFT the error is below 0.5% of the RMS. | T31-01, T31-02 |
| R31-02 | A receive stage shall compute the `M`-point inverse DFT of the equalised tones, weighted per tone by a minimum-mean-square-error gain derived from `csi`, with the output scaled to the mapper amplitude (unbiased), the common phase removed using the reference symbols, and one `csi` value for the whole symbol. | RTL equals the integer model; against floating-point MMSE equalisation + IDFT the error is below 1% of the RMS. | T31-03, T31-04 |
| R31-03 | The PAPR of DFT-s-OFDM at a CCDF of 1e-3 shall be at least 3 dB below plain OFDM (same modulation, same tone plan, pilots included in the OFDM reference) for BPSK, QPSK and 16QAM, for N = 64 to 512, measured on the output of the real transmit chain (reference symbols, null edge tones and the DC tone included). | Measured gain on 20000 symbols per case; any case below 3.0 dB is reported as not met. | T31-05 |
| R31-04 | In an AWGN channel the uncoded bit error rate of DFT-s-OFDM shall equal that of plain OFDM within 0.2 dB (same modulation, same energy per bit; edge tones null) for BPSK, QPSK, 16QAM. | Simulated BER at 3 SNR points within the confidence interval of the plain OFDM curve (+/- 0.2 dB). | T31-06 |
| R31-05 | In a frequency-selective channel (the 2-tap channel of module 21 and a deep-fade case) the coded frame error rate of DFT-s-OFDM with MMSE weighting shall be reported against plain OFDM; the loss shall be quantified (it is the price of the mode). | Table in the results; no pass limit, the numbers are the deliverable. | T31-07 |
| R31-06 | The mode shall be selectable per frame (`ref_boost` and the mode itself are frame configuration inputs of the blocks), the existing transmit and receive chains staying unchanged and bit-exact (the only change to an existing block is the parameter `MIN_LOG2` of the FFT, default unchanged). | Module 12 tests pass unchanged. | T31-08 |
| R31-07 | The blocks shall work in a symbol-level loop with the real mapper, IFFT, cyclic prefix and demapper (transmit chain of models equal sample for sample; receive stage equal to the models; recovery over a multipath channel with noise and common rotation). Integration into `tx_chain` and `rx_chain` (frame structure, equaliser without pilots) is an open item of the design. | T31-09 results. | T31-09 |
| R31-08 | The stage shall keep up with the symbol rate: a symbol (useful part plus prefix) lasts 14.4 us at the 1/8 prefix, 2880 clocks at 200 MHz. | Clocks per symbol measured for every N; reported against 2880. | T31-10 |
| R31-09 | The limits and the signalling needs shall be documented. | Sections 4 and 5 of this file and the design file. | review |

## 4. Interaction with the PA study and the other requirements

- DFT-s-OFDM is the planned mitigation for PHY-009 if the PA study gives less than 27% PAE (`07` T-14). This module measures how much back-off the lower PAPR buys with the PA model of module 26 only as a PAPR figure; a closed-loop DPD measurement with DFT-s signals is an open item.
- Spectral efficiency: the edge tones carry no data (`M = 3N/4`), so the useful rate of the mode is 100%, 89%, 82%, 82% of plain OFDM for N = 64, 128, 256, 512.
- **Pilots.** A preliminary experiment (numpy, 4x oversampling, N = 64 to 512) put the unspread pilot tones of module 7 into the DFT-s symbol and loaded the data tones around them: the PAPR gain over plain OFDM fell to 0 to 1.8 dB, because every pilot (and the wider null around DC of the plan) displaces the spread samples by a tone and destroys the contiguous allocation that makes the waveform low-PAPR. With M contiguous tones and no pilots the gain is 2.0 to 3.4 dB. The mode therefore uses **no frequency pilots**; the common phase of a symbol is measured on `R` known reference symbols among the `M` constellation points (BPSK at fixed positions, `R` = 8, amplitude 1x or, selectable per frame with `ref_boost`, 2x the data amplitude: the 2x setting removes the BER cost of the noisy phase estimate and raises the PAPR) after the despreading; the receiver channel estimate comes from the LTF as before. The equaliser (module 17) is used without its pilot phase correction in this mode.
- **Expected outcome of R31-03 (from the same experiment, to be confirmed on the real chain):** QPSK about 3.2 dB, BPSK about 2.2 to 2.5 dB (pi/2-BPSK), 16QAM about 2.0 dB; so the `[E]` target of 3 dB is expected to be met for QPSK only. The measured numbers go into the results; no spectral shaping is added (a time-domain shaping `[a, 1, a]` was tried and moved the gains by less than 0.5 dB, at a cost of inter-symbol interference).
- 64QAM and 256QAM stay on plain OFDM.

## 5. Signalling and assumptions

1. The receiver must know the mode before the first data symbol: one bit in the frame header (MAC, module 9/22), protected like the rest of the header; not defined here.
2. The receiver needs the noise level relative to the channel gain (`nv`, in `csi` units) to form the MMSE weights; it comes from the noise estimate of the front end (module 25/18 statistics) and is a register here.
3. Tone order: the spread symbols are placed on the data tones in the bin order of the tone plan; the PAPR properties equal those of contiguous allocation up to a sign alternation of the data symbols (argued in the design).
