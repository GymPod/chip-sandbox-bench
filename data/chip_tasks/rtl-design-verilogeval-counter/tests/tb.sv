`timescale 1ns/1ps

module tb;
  logic clk = 0;
  logic reset = 1;
  logic [3:0] q;

  TopModule dut(.clk(clk), .reset(reset), .q(q));
  always #5 clk = ~clk;

  task check_q(input integer expected);
    #1;
    if (q !== expected[3:0]) begin
      $display("expected q=%0d, got %0d", expected, q);
      $fatal(1);
    end
  endtask

  initial begin
    @(posedge clk);
    check_q(1);
    reset = 0;

    for (integer expected = 2; expected <= 10; expected++) begin
      @(posedge clk);
      check_q(expected);
    end
    @(posedge clk);
    check_q(1);

    @(negedge clk);
    reset = 1;
    if (q !== 1) begin
      $display("reset changed q before a positive edge");
      $fatal(1);
    end
    @(posedge clk);
    check_q(1);
    $display("PASS");
    $finish;
  end
endmodule
