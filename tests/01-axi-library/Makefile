# Tests for module 1 (design/01-axi-library.md). Needs the OSS CAD Suite environment:
#   source /home/arkady/tools/oss-cad-suite/environment
# Targets: test (default), lint, synth, clean.
ROOT   := $(abspath ../..)
RTL    := $(ROOT)/rtl/01-axi-library
SIMDIR := $(CURDIR)/sim_build
export PYTHONPATH := $(CURDIR):$(PYTHONPATH)

.PHONY: test lint synth clean
test:
	@./run_tests.sh

lint:
	@for t in axis_skid axis_fifo axis_width_conv axis_cdc_fifo axil_regfile; do \
	  printf "lint %s: " $$t; \
	  out=$$(verilator --lint-only -Wall --top-module $$t $(RTL)/*.sv 2>&1 | grep -E '^%(Warning|Error)'); \
	  if [ -n "$$out" ]; then echo FAIL; echo "$$out"; exit 1; else echo clean; fi; \
	done

synth:
	@for t in axis_skid axis_fifo axis_width_conv axis_cdc_fifo axil_regfile; do \
	  echo "== synth $$t"; \
	  yosys -q -p "read_verilog -sv $(RTL)/*.sv; hierarchy -top $$t; synth -top $$t; tee -o synth_$$t.txt stat; select -assert-none t:\$$dlatch t:\$$_DLATCH_?_ t:\$$_DLATCH_??_" > synth_$$t.log 2>&1 \
	    && { grep -E 'Number of cells|\$$_DFF|\$$_SDFF|\$$_DFFE|LUT|\$$_MUX|\$$_AND|\$$_XOR' synth_$$t.txt | head -3; echo "no latches"; } \
	    || { echo FAIL; tail -5 synth_$$t.log; exit 1; }; \
	done

clean:
	rm -rf sim_build results_*.xml sim_*.log synth_*.txt synth_*.log __pycache__
