module dut(input [3:0] req,output reg valid,output reg [1:0] index);
always @* begin valid=|req; casex(req) 4'b1???:index=3;4'b01??:index=2;4'b001?:index=1;default:index=0;endcase end endmodule
