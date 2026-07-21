#!/bin/sh
set -eu
cat > /workspace/tb.sv <<'SV'
module testbench;
reg clk=0; reg [7:0] d=0; wire [7:0] q; dut u(clk,d,q);
always #5 clk=~clk;
initial begin
  #2 d=8'h12; #4; if(q!==8'h12) $fatal(1,"posedge capture");
  d=8'h34; #4; if(q!==8'h12) $fatal(1,"changed before edge");
  #1; if(q!==8'h12) $fatal(1,"negedge capture");
  #3 d=8'h56; #2; if(q!==8'h56) $fatal(1,"second edge");
  $display("PASS"); $finish;
end
endmodule
SV
