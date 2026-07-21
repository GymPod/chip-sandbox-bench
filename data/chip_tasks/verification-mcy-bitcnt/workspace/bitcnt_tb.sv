module testbench;
  reg  [63:0] din_data;
  reg  [2:0] din_func;
  wire [63:0] dout_data;

  bitcnt dut(.*);

  // Add self-checking coverage for all six operations and boundary cases.
endmodule
