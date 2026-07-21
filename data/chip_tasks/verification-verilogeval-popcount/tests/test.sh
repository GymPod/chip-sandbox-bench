#!/bin/sh
set -eu
iverilog -g2012 -s testbench -o /tmp/verification-verilogeval-popcount-reference /workspace/dut.sv /workspace/tb.sv
vvp -N /tmp/verification-verilogeval-popcount-reference | grep -q PASS
iverilog -g2012 -s testbench -o /tmp/verification-verilogeval-popcount-mutant /tests/mutant.sv /workspace/tb.sv
if vvp -N /tmp/verification-verilogeval-popcount-mutant >/dev/null 2>&1; then
  echo "mutation survived" >&2
  exit 1
fi
