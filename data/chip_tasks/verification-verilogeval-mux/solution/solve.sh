#!/bin/sh
set -eu
cat > /workspace/tb.sv <<'SV'
module testbench;
reg [7:0] a,b; reg sel; wire [7:0] y; integer i;
dut d(a,b,sel,y);
initial begin
  for (i=0;i<32;i=i+1) begin
    a=i*7; b=8'hf0-i; sel=0; #1; if(y!==a) $fatal(1,"sel0");
    sel=1; #1; if(y!==b) $fatal(1,"sel1");
  end
  $display("PASS"); $finish;
end
endmodule
SV
