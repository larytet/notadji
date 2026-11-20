# AXI-Stream and AXI-Lite library

Module 1 of `spec/18-development-plan.md`. Design spec and test plan: `design/01-*.md`; tests: `tests/01-axi-library/`.

## Purpose

Common plumbing for every other block: skid buffer (`axis_skid`), FIFO (`axis_fifo`), width converter (`axis_width_conv`), clock-crossing FIFO (`axis_cdc_fifo`) and AXI-Lite register file (`axil_regfile`). Defines the valid/ready/data/last stream convention used everywhere.

## Interacts with

Used by all modules. `axis_cdc_fifo` is used by 11 (radio interface) for the radio-clock to system-clock crossing; `axil_regfile` is the configuration path between the processor and the blocks (10, 15, 16 and others).
