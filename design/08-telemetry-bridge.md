# 08 - Serial Telemetry Bridge (UART, MSP, MAVLink framing)

Plan entry: module 8 of `spec/18-development-plan.md`, class S, data plane. Requirements: MAC-007 (telemetry and control channel carrying MAVLink, MSP and generic serial with a latency of 5 ms or less), IF-001 (flight-controller UART up to 3 Mbaud; MSP and MAVLink 2). Depends on module 1 (`axis_fifo`).

## 1. Purpose

Connects the flight controller's UART to the radio's telemetry channel: it turns the byte stream of a UART into frames (so the MAC can send one flight-controller message per telemetry packet and the ground side can reproduce the stream) and turns frames back into a UART byte stream. The framing is protocol-aware only as far as needed to find frame boundaries; it does **not** validate checksums (MAVLink needs the per-message CRC_EXTRA table; MSP has an XOR or CRC-8 checksum) - the endpoints do that, and a corrupted frame is forwarded as received.

## 2. Blocks

### 2.1 `uart_rx`

8N1 receiver, runtime bit period `div[15:0]` (clocks per bit, at least 4; 3 Mbaud at 200 MHz is 66). Two-flop synchroniser on `rxd`; start-bit detection on the falling edge, confirmed at the middle of the start bit (a pulse shorter than half a bit is rejected); data sampled at the middle of each bit, LSB first; stop bit sampled at its middle: if it is 0, the byte is still delivered and the pulse `frame_err` is raised. The receiver is ready for the next start bit as soon as the stop bit has been sampled, so back-to-back bytes are received. Output: byte stream `m_axis_valid`, `m_axis_data[7:0]` (no ready: a UART cannot be stopped; a FIFO follows).

### 2.2 `uart_tx`

8N1 transmitter, same `div`. Input byte stream with `valid` and `ready` (ready is high only while idle or in the last stop-bit clock so the next byte follows with no gap). Output `txd` (idle high) and `busy`.

### 2.3 `tlm_framer`

Input: byte stream from a FIFO (module 1), output: byte stream with `m_axis_last` at the end of every frame and `m_axis_err` valid with `last` (1 = the frame ended abnormally). Runtime configuration: `proto[1:0]`, `idle_bits[7:0]` (timeout in bit times of `div`), `max_len[8:0]` (largest frame in bytes, 1 to 511), `div` (same value as the UART).

| `proto` | Meaning |
|---|---|
| 0 | Raw: no protocol; a frame ends when the line has been idle for `idle_bits` bit times, or when `max_len` bytes have been collected. The last byte of the frame is held back until the end is known, so a raw frame is delayed by `idle_bits` bit times |
| 1 | MAVLink v1 and v2: start byte 0xFE (v1) or 0xFD (v2); v1 total length = payload length + 8; v2 total = payload length + 12, plus 13 if the incompatibility flag byte has bit 0 set (signed frame) |
| 2 | MSP v1 and v2: start `$`, then `M` (v1) or `X` (v2), then `<`, `>` or `!`; v1 total = size + 6 (size at byte index 3); v2 total = size + 9 (size is the little-endian 16-bit value at byte indices 6 and 7) |
| 3 | Auto: the first byte decides per frame: 0xFE or 0xFD as MAVLink, `$` as MSP, anything else as raw (the raw frame then ends by idle timeout) |

Protocol modes forward every byte immediately (no hold-back; latency is one byte time) and set `last` on the byte that completes the frame (`err` = 0). Special cases:
- Bytes outside a frame (not a valid start byte of the selected protocol) are dropped and counted by the pulse `drop`.
- Invalid MSP header (byte 1 not `M` or `X`, or byte 2 not one of `<`, `>`, `!`): the offending byte is forwarded as the last byte with `err` = 1; the following bytes are dropped until a start byte.
- A length larger than `max_len`: the byte that reveals it is forwarded as last with `err` = 1 (the rest of that frame is dropped as bytes outside a frame; payload bytes equal to a start byte can cause a false start, accepted as a limitation).
- Idle timeout in the middle of a protocol frame: a dummy byte 0x00 is emitted as last with `err` = 1 (truncated frame).
- Raw mode: `err` = 0 at the end of every frame.

### 2.4 `tlm_uart` (top)

`uart_rx` followed by an `axis_fifo` (16 bytes) and `tlm_framer` for the uplink direction (flight controller to radio), and `uart_tx` for the other direction (frames from the radio are written to the UART unchanged; frame boundaries are not marked on the line). Output pulses: `rx_frame_err`, `rx_overflow` (a byte lost because the FIFO was full), `drop`.

## 3. Test plan

A cocotb UART model drives `rxd` and samples `txd` bit by bit; frames are built in Python.

| ID | Test | Pass criterion |
|---|---|---|
| T8-01 | `uart_rx`: random bytes with random gaps, and back-to-back; divisors 4, 8 and 66 | All bytes received in order; no spurious bytes |
| T8-02 | `uart_rx`: bad stop bit; a start glitch shorter than half a bit | `frame_err` pulses for the bad stop bit, byte still delivered; the glitch produces no byte |
| T8-03 | `uart_tx`: waveform | Start bit, 8 data bits LSB first and stop bit each last exactly `div` clocks; back-to-back bytes have no idle gap; `busy` correct |
| T8-04 | Loop-back `uart_tx` to `uart_rx` at divisors 4, 8, 66 and 3000 | Data equal |
| T8-05 | Framer MAVLink v1 and v2, unsigned and signed, payload 0 to 255, back-to-back frames | `last` exactly at the frame ends; all bytes forwarded in order; `err` = 0 |
| T8-06 | Framer MSP v1 and v2, payload 0 to 255 (and a 300-byte v2 payload with `max_len` 511) | Same |
| T8-07 | Garbage bytes between frames | Dropped (counted); frames unaffected |
| T8-08 | Raw mode | Frames end by idle timeout (`last` on the last byte, after `idle_bits` bit times) and by `max_len` |
| T8-09 | Truncated protocol frame | After the timeout a 0x00 byte with `last` and `err` = 1 is emitted; the next frame is received correctly |
| T8-10 | Invalid MSP header; length above `max_len` | `err` = 1 on the terminating byte; resynchronisation on the next valid start byte |
| T8-11 | Auto mode | MAVLink, MSP and raw data mixed in one stream are framed per their own rules |
| T8-12 | `tlm_uart` top: frames in on `rxd` appear on the output stream; stream in appears on `txd`; a stalled sink with a long burst raises `rx_overflow` | As stated |
| T8-13 | Latency | In protocol mode a byte appears at the output within a fixed small number of clocks after its stop bit has been sampled (measured and recorded; bound: 8 clocks) |
| L-08, S-08 | Lint and synthesis | `-Wall` clean; no latches; counts recorded |

Configurations: framer tests run with `div` = 8 (fast simulation); the UART tests also use 4, 66 and 3000.

## 4. Deliverables

`rtl/08-telemetry-bridge/{uart_rx,uart_tx,tlm_framer,tlm_uart}.sv`, `tests/08-telemetry-bridge/`, results below, row in `design/README.md`.

## 5. Open items

- Whether the 5 ms of MAC-007 includes the serial transfer of a long frame (a 280-byte MAVLink v2 frame is 24 ms at 115200 baud and 0.9 ms at 3 Mbaud): the latency target is only meaningful at the higher baud rates, or with byte-level forwarding (a streaming mode without framing is available as `proto` 0 with a short idle timeout).
- Checksum validation at the endpoints and the MAVLink CRC_EXTRA table are not part of this module.
- Flow control (RTS/CTS) is not implemented.
