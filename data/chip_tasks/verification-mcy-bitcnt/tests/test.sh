#!/bin/sh
set -eu

iverilog -g2012 -s testbench -o /tmp/bitcnt_reference \
  /workspace/bitcnt.v /workspace/bitcnt_tb.sv
vvp -N /tmp/bitcnt_reference

for mutant in /tests/bitcnt_mutant_mode32.v /tests/bitcnt_mutant_zero.v; do
  iverilog -g2012 -s testbench -o /tmp/bitcnt_mutant \
    "$mutant" /workspace/bitcnt_tb.sv
  if vvp -N /tmp/bitcnt_mutant; then
    echo "mutation survived: $mutant" >&2
    exit 1
  fi
done
