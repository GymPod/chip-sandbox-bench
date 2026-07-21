#!/bin/sh
set -eu
iverilog -g2012 -s tb -o /tmp/rtl-design-verilogeval-dff8-async-reset /workspace/TopModule.sv /tests/ref.sv /tests/tb.sv
output=$(vvp -N /tmp/rtl-design-verilogeval-dff8-async-reset)
printf '%s
' "$output"
printf '%s
' "$output" | grep -Eq 'Mismatches: 0 in [1-9][0-9]* samples'
