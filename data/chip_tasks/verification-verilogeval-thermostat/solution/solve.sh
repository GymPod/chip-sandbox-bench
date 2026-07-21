#!/bin/sh
set -eu
cat > /workspace/tb.sv <<'SV'
module testbench;
reg mode,cold,hot,fan_req; wire heater,ac,fan; integer i; reg eh,ea,ef;
dut u(mode,cold,hot,fan_req,heater,ac,fan);
initial begin
 for(i=0;i<16;i=i+1) begin
  {mode,cold,hot,fan_req}=i; eh=mode&cold; ea=(~mode)&hot; ef=eh|ea|fan_req;
  #1; if({heater,ac,fan}!={eh,ea,ef}) $fatal(1,"thermostat");
 end
 $display("PASS"); $finish;
end
endmodule
SV
