#!/bin/sh
set -eu
cat > /workspace/tb.sv <<'SV'
module testbench;
reg clk=0,rst=0; reg [7:0] d=8'haa; wire [7:0] q; dut u(clk,rst,d,q);
always #5 clk=~clk;
initial begin
  #1 rst=1; #1; if(q!==0) $fatal(1,"initial reset"); rst=0;
  #3; #1; if(q!==8'haa) $fatal(1,"capture");
  #2 rst=1; #1; if(q!==0) $fatal(1,"reset not asynchronous");
  rst=0; d=8'h55; #7; if(q!==8'h55) $fatal(1,"recapture");
  $display("PASS"); $finish;
end
endmodule
SV
