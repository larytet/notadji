# Serial telemetry bridge

Module 8 of `spec/18-development-plan.md`. Design spec and test plan: `design/08-*.md`; tests: `tests/08-telemetry-bridge/`.

## Purpose

UART receive and transmit with a framer for MAVLink, MSP or raw bytes, providing the low-latency telemetry and control channel.

## Interacts with

Faces the flight controller UART on one side and the radio link on the other (expected: MAC engine 22 and slice or packet path 9). Uses module 1 streams. Not yet connected to other modules.
