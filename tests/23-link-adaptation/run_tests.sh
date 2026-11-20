#!/bin/bash
# Link-adaptation firmware tests (host build). Usage: ./run_tests.sh
cd "$(dirname "$0")" || exit 1
python3 test_la.py
