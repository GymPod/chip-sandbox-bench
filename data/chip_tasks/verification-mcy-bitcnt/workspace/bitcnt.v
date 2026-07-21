module bitcnt (
  input  [63:0] din_data,
  input  [2:0]  din_func,
  output [63:0] dout_data
);
  wire mode32 = din_func[0];
  wire revmode = !din_func[1];
  wire czmode = !din_func[2];
  integer i;
  reg [63:0] tmp;
  reg [7:0] cnt;

  always @* begin
    for (i = 0; i < 64; i = i + 1)
      tmp[i] = (i < 32 && mode32) ? din_data[(63-i) % 32] : din_data[63-i];
    if (!revmode)
      tmp = din_data;
    if (mode32)
      tmp = tmp[31:0];
    if (czmode)
      tmp = (tmp-1) & ~tmp;
    cnt = 0;
    for (i = 0; i < 64; i = i + 1)
      cnt = cnt + (tmp[i] && (i < 32 || !mode32));
  end

  assign dout_data = cnt;
endmodule
