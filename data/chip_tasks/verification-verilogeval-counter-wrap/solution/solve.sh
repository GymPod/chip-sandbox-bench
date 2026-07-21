#!/bin/sh
set -eu
cat > /workspace/tb.sv <<'SV'
module testbench;
reg clk=0,reset=1; wire [3:0] q; integer i; reg [3:0] expected=1;
dut u(clk,reset,q); always #5 clk=~clk;
initial begin
 #6; if(q!==1) $fatal(1,"reset"); reset=0;
 for(i=0;i<22;i=i+1) begin
  @(posedge clk); #1; expected=(expected==10)?1:expected+1;
  if(q!==expected) $fatal(1,"count");
 end
 $display("PASS"); $finish;
end
endmodule
SV
