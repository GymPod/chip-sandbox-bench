#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def decode_address(address: int, line_bytes: int, sets: int) -> tuple[int, int, int]:
    if address < 0 or line_bytes <= 0 or sets <= 0:
        raise ValueError("invalid cache geometry or address")
    if line_bytes & (line_bytes - 1) or sets & (sets - 1):
        raise ValueError("cache geometry must use powers of two")
    offset = address & (line_bytes - 1)
    block = address // line_bytes
    return block // sets, block & (sets - 1), offset
PY
