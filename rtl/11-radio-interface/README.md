# Radio interface wrapper

Module 11 of `spec/18-development-plan.md`. Design spec and test plan: `design/11-*.md`; tests: `tests/11-radio-interface/`.

## Purpose

Digital boundary to the transceiver: receive and transmit sample paths with clock crossing and overrun/underrun counters, SPI master for transceiver programming, mapping of sequencer lines to control pins. The electrical LVDS/CMOS layer is not included.

## Interacts with

Receive samples go to 18 (sync); transmit samples come from 16. Control comes from 10. Uses 1 (CDC FIFO). Connects to an AD9361 or ADRV9002 on the board.
