SIM ?= verilator
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(wildcard $(ROOT)/rtl/01-axi-library/*.sv)
EXTRA_ARGS += $(GARGS) -Wno-fatal --Wno-WIDTHEXPAND --Wno-WIDTHTRUNC
include $(shell cocotb-config --makefiles)/Makefile.sim
