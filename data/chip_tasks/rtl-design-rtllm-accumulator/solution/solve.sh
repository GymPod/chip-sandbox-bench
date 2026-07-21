#!/bin/sh
cat > /workspace/accu.sv <<'SV'
module accu (
  input  logic       clk,
  input  logic       rst_n,
  input  logic [7:0] data_in,
  input  logic       valid_in,
  output logic       valid_out,
  output logic [9:0] data_out
);
  logic [1:0] count;
  logic [9:0] sum;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      count <= 0;
      sum <= 0;
      data_out <= 0;
      valid_out <= 0;
    end else begin
      valid_out <= 0;
      if (valid_in) begin
        if (count == 3) begin
          data_out <= sum + data_in;
          valid_out <= 1;
          count <= 0;
          sum <= 0;
        end else begin
          sum <= sum + data_in;
          count <= count + 1'b1;
        end
      end
    end
  end
endmodule
SV
