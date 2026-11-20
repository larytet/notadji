SIM ?= verilator
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(SRCS)
EXTRA_ARGS += $(GARGS) -Wno-fatal --Wno-WIDTHEXPAND --Wno-WIDTHTRUNC
include $(shell cocotb-config --makefiles)/Makefile.sim
