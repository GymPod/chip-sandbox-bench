#!/bin/sh
set -eu
cat > /workspace/tb.sv <<'SV'
module testbench;
reg [7:0] data; wire parity; integer i,j; reg expected;
dut u(data,parity);
initial begin
 for(i=0;i<256;i=i+1) begin
  data=i; expected=0; for(j=0;j<8;j=j+1) expected=expected^((i>>j)&1);
  #1; if(parity!==expected) $fatal(1,"parity");
 end
 $display("PASS"); $finish;
end
endmodule
SV
