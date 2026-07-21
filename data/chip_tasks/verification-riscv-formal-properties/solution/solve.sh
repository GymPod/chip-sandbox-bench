#!/bin/sh
cat > /workspace/properties.sv <<'SV'
always @* begin
  assert(next_count <= 2);

  if (count == 2 && wr_en && !rd_en)
    assert(next_count == 2);

  if (count == 0 && rd_en && !wr_en)
    assert(next_count == 0);

  if (wr_en && rd_en)
    assert(next_count == count);
end
SV
