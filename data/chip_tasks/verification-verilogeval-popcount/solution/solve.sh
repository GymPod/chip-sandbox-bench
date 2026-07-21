#!/bin/sh
set -eu
cat > /workspace/tb.sv <<'SV'
module testbench;
reg [3:0] in; wire [2:0] count; integer i; reg [2:0] expected;
dut d(in,count);
initial begin
  for(i=0;i<16;i=i+1) begin
    in=i; expected=((i>>0)&1)+((i>>1)&1)+((i>>2)&1)+((i>>3)&1);
    #1; if(count!==expected) $fatal(1,"count");
  end
  $display("PASS"); $finish;
end
endmodule
SV
