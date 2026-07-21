module fifo_transition (
  input  [1:0] count,
  input        wr_en,
  input        rd_en,
  output reg [1:0] next_count
);
  always @* begin
    next_count = count;
    case ({wr_en, rd_en})
      2'b10: next_count = count + 1'b1;
      2'b01: if (count > 0) next_count = count - 1'b1;
      default: next_count = count;
    endcase
  end
endmodule
