#!/bin/sh
cat > /workspace/bitcnt_tb.sv <<'SV'
module testbench;
  reg  [63:0] din_data;
  reg  [2:0] din_func;
  wire [63:0] dout_data;

  bitcnt dut(.*);

  task check;
    input [2:0] operation;
    input [63:0] value;
    input [63:0] expected;
    begin
      din_func = operation;
      din_data = value;
      #1;
      if (dout_data !== expected) begin
        $display("op=%b value=%h expected=%0d got=%0d",
                 operation, value, expected, dout_data);
        $fatal(1);
      end
    end
  endtask

  initial begin
    check(3'b000, 64'h8000000000000000, 0);
    check(3'b000, 64'h0000000000000001, 63);
    check(3'b000, 64'h0000000000000000, 64);
    check(3'b001, 64'hffff000080000000, 0);
    check(3'b001, 64'hffff000000000001, 31);
    check(3'b001, 64'hffff000000000000, 32);

    check(3'b010, 64'h0000000000000001, 0);
    check(3'b010, 64'h8000000000000000, 63);
    check(3'b010, 64'h0000000000000000, 64);
    check(3'b011, 64'hffff000000000001, 0);
    check(3'b011, 64'hffff000080000000, 31);
    check(3'b011, 64'hffff000000000000, 32);

    check(3'b100, 64'hf0f000000000000f, 12);
    check(3'b100, 64'hffffffffffffffff, 64);
    check(3'b100, 64'h0000000000000000, 0);
    check(3'b101, 64'hffffffff0000000f, 4);
    check(3'b101, 64'h12345678ffffffff, 32);
    check(3'b101, 64'hffffffff00000000, 0);
    $display("PASS");
    $finish;
  end
endmodule
SV
