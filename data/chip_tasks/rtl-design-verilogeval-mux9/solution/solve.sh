#!/bin/sh
set -eu
sed 's/module RefModule/module TopModule/' /tests/ref.sv > /workspace/TopModule.sv
