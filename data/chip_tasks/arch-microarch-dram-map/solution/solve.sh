#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def map_dram(address: int, burst_bytes: int, channels: int, banks: int, row_bytes: int) -> dict:
    values = (burst_bytes, channels, banks, row_bytes)
    if address < 0 or any(v <= 0 or v & (v - 1) for v in values) or row_bytes % burst_bytes:
        raise ValueError("invalid DRAM geometry")
    offset = address % burst_bytes
    value = address // burst_bytes
    channel = value % channels; value //= channels
    bank = value % banks; value //= banks
    columns = row_bytes // burst_bytes
    column = value % columns
    row = value // columns
    return {"offset": offset, "channel": channel, "bank": bank, "column": column, "row": row}
PY
