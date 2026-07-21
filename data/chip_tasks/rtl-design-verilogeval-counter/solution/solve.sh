#!/bin/sh
cat > /workspace/TopModule.sv <<'SV'
module TopModule (
  input  logic       clk,
  input  logic       reset,
  output logic [3:0] q
);
  always_ff @(posedge clk) begin
    if (reset || q == 4'd10)
      q <= 4'd1;
    else
      q <= q + 1'b1;
  end
endmodule
SV
