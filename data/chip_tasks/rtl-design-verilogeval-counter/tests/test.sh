#!/bin/sh
set -eu
iverilog -g2012 -s tb -o /tmp/verilogeval_counter /workspace/TopModule.sv /tests/tb.sv
vvp -N /tmp/verilogeval_counter
