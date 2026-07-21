`timescale 1ns/1ps

module tb;
  logic clk = 0;
  logic rst_n = 0;
  logic [7:0] data_in = 0;
  logic valid_in = 0;
  logic valid_out;
  logic [9:0] data_out;

  accu dut(.*);
  always #5 clk = ~clk;

  task send(input integer value, input bit valid, input bit expect_valid,
            input integer expected_sum);
    @(negedge clk);
    data_in = value[7:0];
    valid_in = valid;
    @(posedge clk);
    #1;
    if (valid_out !== expect_valid) begin
      $display("valid_out mismatch for value %0d", value);
      $fatal(1);
    end
    if (expect_valid && data_out !== expected_sum[9:0]) begin
      $display("expected sum %0d, got %0d", expected_sum, data_out);
      $fatal(1);
    end
  endtask

  initial begin
    repeat (2) @(posedge clk);
    rst_n = 1;
    send(1, 1, 0, 0);
    send(99, 0, 0, 0);
    send(2, 1, 0, 0);
    send(3, 1, 0, 0);
    send(14, 1, 1, 20);
    send(0, 0, 0, 0);

    send(255, 1, 0, 0);
    send(255, 1, 0, 0);
    send(255, 1, 0, 0);
    send(255, 1, 1, 1020);

    send(7, 1, 0, 0);
    @(negedge clk);
    rst_n = 0;
    valid_in = 0;
    #1;
    if (valid_out !== 0) $fatal(1);
    @(negedge clk);
    rst_n = 1;
    send(4, 1, 0, 0);
    send(5, 1, 0, 0);
    send(6, 1, 0, 0);
    send(7, 1, 1, 22);
    $display("PASS");
    $finish;
  end
endmodule
