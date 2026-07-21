#!/bin/sh
set -eu
iverilog -g2012 -s tb -o /tmp/rtl-design-verilogeval-popcount3 /workspace/TopModule.sv /tests/ref.sv /tests/tb.sv
output=$(vvp -N /tmp/rtl-design-verilogeval-popcount3)
printf '%s
' "$output"
printf '%s
' "$output" | grep -Eq 'Mismatches: 0 in [1-9][0-9]* samples'
