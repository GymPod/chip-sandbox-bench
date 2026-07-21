#!/bin/sh
set -eu

assert_count=$(grep -c 'assert' /workspace/properties.sv || true)
if [ "$assert_count" -lt 4 ]; then
  echo "expected at least four assertions" >&2
  exit 1
fi

run_proof() {
  dut=$1
  yosys -q -p "read_verilog -formal -sv -I/workspace $dut /tests/formal_top.sv; prep -top formal_top -flatten; chformal -lower; sat -verify -prove-asserts -set-assumes -show-all"
}

run_proof /tests/fifo_correct.sv
if run_proof /tests/fifo_mutant.sv; then
  echo "formal properties did not detect the full-FIFO write mutation" >&2
  exit 1
fi
