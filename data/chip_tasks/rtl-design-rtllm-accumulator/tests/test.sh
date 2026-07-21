#!/bin/sh
set -eu
iverilog -g2012 -s tb -o /tmp/rtllm_accu /workspace/accu.sv /tests/tb.sv
vvp -N /tmp/rtllm_accu
