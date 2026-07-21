#!/bin/sh
set -eu
iverilog -g2012 -s testbench -o /tmp/verification-verilogeval-mux-reference /workspace/dut.sv /workspace/tb.sv
vvp -N /tmp/verification-verilogeval-mux-reference | grep -q PASS
iverilog -g2012 -s testbench -o /tmp/verification-verilogeval-mux-mutant /tests/mutant.sv /workspace/tb.sv
if vvp -N /tmp/verification-verilogeval-mux-mutant >/dev/null 2>&1; then
  echo "mutation survived" >&2
  exit 1
fi
