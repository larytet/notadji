# 11 - Radio Interface Wrapper

Plan entry: module 11 of `spec/18-development-plan.md`, class M, data plane. Requirements: PRO-007 (phase A radio configurations), RF-006 (hop and turn-around timing), HSI-001 and HSI-002 (control lines come from the sequencer), `13` section 3. Depends on module 1 (`axis_cdc_fifo`) and module 10 (`lines`, `pulses`, `gain_val`, `pll_val`).

## 1. Scope and what is not simulated

This module is the **digital** boundary between the modem (system clock domain, 200 MHz class) and a transceiver (AD9361 or ADRV9002, trade study T-11): the sample streams across the clock-domain boundary with overflow and underrun accounting, an SPI master to program the transceiver, the mapping of sequencer lines onto the transceiver's control pins, and the hardware fault override. The electrical layer of the data port (LVDS or CMOS double-data-rate input and output cells, frame signals, delay tuning) is vendor- and board-specific, uses FPGA I/O primitives that cannot be simulated here, and is **not** part of this module; it connects to the `radio-clock` ports below once the board is chosen (HSI-010, phase A). Which pins the AD9361 or ADRV9002 expose and with which polarity is a configuration of the pin map (section 5), not hard-wired, because the exact pin-level behaviour has not been checked against the data sheets (UG-570 and the ADRV9002 documents are not among the downloaded sources).

## 2. Sample paths

Sample word: 32 bits, I in bits 15..0, Q in bits 31..16 (as in `04` and `06`); a 12-bit converter sample is sign-extended or left-aligned by the electrical layer.

- **`rx_path`** (radio to modem): radio-clock side `rx_clk`, `rx_valid`, `rx_data[31:0]` (the radio cannot be stopped); an asynchronous FIFO (module 1, depth 2^`AW`, default 16) crosses to the system clock; the output is a stream (`m_axis_*`, no `last`). When the FIFO is full a sample is dropped and counted: `rx_overrun_cnt[15:0]` (system domain, saturating), updated through a Gray-coded two-flop synchroniser so a multi-bit value is never sampled mid-change.
- **`tx_path`** (modem to radio): system-side stream `s_axis_*` into an asynchronous FIFO; radio-clock side `tx_clk`, `tx_req` (the radio takes one sample per clock in which `tx_req` is high and `tx_run` is high), `tx_data[31:0]`, `tx_valid`. If the FIFO is empty when a sample is requested, `tx_data` is **zero** (silence, not a stale sample) and the underrun is counted: `tx_underrun_cnt[15:0]` (system domain, saturating, Gray-synchronised). `tx_run` (a system-domain level, synchronised into `tx_clk`) lets the sequencer gate the transmitter; while it is low the FIFO is not read and zeros are sent without counting an underrun.

## 3. SPI master (`spi_master`)

Register programming of the transceiver. Mode 0 (idle clock low, data driven on the falling edge and sampled on the rising edge), MSB first, chip select active low. Runtime configuration: `div[7:0]` (system clocks per half SCLK period, at least 1) and `nbits[5:0]` (frame length 1 to 32 bits, 24 for the AD9361 style 16-bit instruction plus 8-bit data). A command is a 32-bit word whose low `nbits` bits are sent; a response word with the bits sampled on MISO (right-aligned in `nbits` bits) is returned on a second stream for every command. Commands wait in a small FIFO (module 1, 8 entries); frames are separated by at least two half-periods with chip select high. The SPI mode is fixed at 0 in this revision (the AD9361 and ADRV9002 modes are to be confirmed; if another mode is needed the clock polarity and phase become parameters).

## 4. Control pins (`pin_map`)

`lines[15:0]` and `pulses[15:0]` come from the sequencer (module 10). Six control outputs `pin[5:0]` (for example ENABLE, TXNRX, PA enable, antenna switch bits) are registered (one clock latency, glitch-free): `pin[k] = lines[sel[k]] XOR inv[k]` with `sel` (6 x 4 bits) and `inv` (6 bits) configured at run time. A seventh output `hop_trig` is `pulses[hop_sel]` registered, and `profile[3:0]` is `pll_val[3:0]` registered (frequency profile index of the transceiver). Hardware fault override: while `force_safe` is high all `pin` outputs take `safe_val[5:0]` (default: everything off) and `hop_trig` is suppressed, independently of the table and of the configuration; this is the same signal as the sequencer's `force_safe` and acts in one clock.

## 5. Interface summary

| Block | Ports (besides `clk`, `rst_n`) |
|---|---|
| `rx_path` | `rx_clk`, `rx_rst_n`, `rx_valid`, `rx_data`; system side `m_axis_valid`, `m_axis_ready`, `m_axis_data[31:0]`; `rx_overrun_cnt[15:0]` |
| `tx_path` | `s_axis_valid`, `s_axis_ready`, `s_axis_data[31:0]`, `tx_run`; `tx_clk`, `tx_rst_n`, `tx_req`, `tx_data[31:0]`, `tx_valid`; `tx_underrun_cnt[15:0]` |
| `spi_master` | `div`, `nbits`, `s_axis_*` (command), `m_axis_*` (response), `sclk`, `mosi`, `cs_n`, `miso`, `busy` |
| `pin_map` | `lines`, `pulses`, `pll_val`, `sel[23:0]`, `inv[5:0]`, `hop_sel[3:0]`, `safe_val[5:0]`, `force_safe`; `pin[5:0]`, `hop_trig`, `profile[3:0]` |
| `radio_if` (top) | all of the above in one module |

## 6. Test plan

A behavioural radio model in cocotb: generates RX samples on its own clock (a different frequency from the system clock), requests TX samples, and acts as an SPI slave with a register file.

| ID | Test | Pass criterion |
|---|---|---|
| T11-01 | SPI waveform | For div = 1, 2, 5 and nbits = 8, 16, 24, 32: SCLK idle low, MOSI MSB first, stable at each rising edge, changes only on falling edges; CS low exactly during the frame; the right number of SCLK pulses |
| T11-02 | SPI read-back and queueing | A slave model returns data on MISO; response words equal the slave data, right-aligned; 20 queued commands produce 20 responses in order; at least two half-periods of CS high between frames |
| T11-03 | Pin map | For random `sel` and `inv`: `pin[k]` equals `lines[sel[k]]` XOR `inv[k]` one clock later; `hop_trig` and `profile` likewise |
| T11-04 | Fault override | With `force_safe` high all pins equal `safe_val` and `hop_trig` is 0 regardless of the lines; effective within one clock; table state shows again afterwards |
| T11-05 | RX path | Radio clock 61.44 MHz-class against the 200 MHz system clock (and the reverse ratio): random samples with gaps arrive in order with no loss when the sink keeps up |
| T11-06 | RX overrun | With the sink stalled, extra samples are dropped, `rx_overrun_cnt` equals the exact number dropped; stream resumes in order |
| T11-07 | TX path | Samples are delivered in order to the radio side on `tx_req`; zero fill on underrun with an exact `tx_underrun_cnt`; no underrun counted while `tx_run` is low; back-pressure on `s_axis` when the FIFO is full |
| T11-08 | Integration loop | TX samples looped back by the behavioural radio into RX return unchanged through `radio_if`; SPI and pins operate at the same time |
| L-11, S-11 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

Configurations: `AW` = 4 (default depth 16) for both paths; clock ratios in the tests (radio slower and radio faster).

## 7. Deliverables

`rtl/11-radio-interface/{gray_cnt_sync,rx_path,tx_path,spi_master,pin_map,radio_if}.sv`, `tests/11-radio-interface/`, results below, row in `design/README.md`.

## 8. Open items

- The electrical data-port layer (LVDS or CMOS DDR cells, frame pins, delay calibration) and the FPGA clocking of the radio data clock are board work for phase A.
- Pin-level behaviour and SPI mode of AD9361 and ADRV9002 are to be checked against the data sheets (configuration only).
- Fast-lock and hop sequences (the transceiver-specific SPI or pin sequences behind `hop_trig` and `profile`) belong to the front-end firmware and the sequencer tables.
