module formal_top;
  (* anyconst *) reg [1:0] count;
  (* anyconst *) reg wr_en;
  (* anyconst *) reg rd_en;
  wire [1:0] next_count;

  fifo_transition dut(
    .count(count),
    .wr_en(wr_en),
    .rd_en(rd_en),
    .next_count(next_count)
  );

  always @* assume(count <= 2);
  `include "properties.sv"
endmodule
