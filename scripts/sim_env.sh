# Source this file: simulation environment for the RTL tests (design/, rtl/, tests/).
#   source scripts/sim_env.sh
# Verilator, Yosys, Icarus, GTKWave come from the OSS CAD Suite; cocotb comes from a virtual
# environment on the system Python, because the suite's own cocotb libraries need glibc 2.38
# and this host has 2.35 (they fail to link). Create the venv once:
#   python3 -m venv /home/arkady/tools/venv-cocotb && /home/arkady/tools/venv-cocotb/bin/pip install cocotb
source /home/arkady/tools/oss-cad-suite/environment
export PATH=/home/arkady/tools/venv-cocotb/bin:$PATH
