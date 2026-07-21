module dut(input [3:0] req,output reg valid,output reg [1:0] index);
always @* begin valid=|req; casex(req) 4'b???1:index=0;4'b??10:index=1;4'b?100:index=2;default:index=3;endcase end endmodule
