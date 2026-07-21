#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def simulate_fifo(capacity: int, events: list[tuple[int, int]]) -> dict:
    if capacity < 0:
        raise ValueError("negative capacity")
    occupancy = accepted = dropped = underflow = 0
    trace = []
    for produced, consumed in events:
        if produced < 0 or consumed < 0:
            raise ValueError("negative event")
        actual_read = min(occupancy, consumed)
        underflow += consumed - actual_read
        occupancy -= actual_read
        actual_write = min(capacity - occupancy, produced)
        accepted += actual_write
        dropped += produced - actual_write
        occupancy += actual_write
        trace.append(occupancy)
    return {"occupancy": trace, "accepted": accepted, "dropped": dropped, "underflow": underflow}
PY
