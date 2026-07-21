#!/bin/sh
set -eu
cat > /workspace/tb.sv <<'SV'
module testbench;
reg [3:0] req; wire valid; wire [1:0] index; integer i; reg [1:0] expected;
dut u(req,valid,index);
initial begin
 for(i=0;i<16;i=i+1) begin
  req=i;
  if(i&1) expected=0; else if(i&2) expected=1; else if(i&4) expected=2; else expected=3;
  #1; if(valid!==(i!=0)) $fatal(1,"valid");
  if(i!=0 && index!==expected) $fatal(1,"priority");
 end
 $display("PASS"); $finish;
end
endmodule
SV
