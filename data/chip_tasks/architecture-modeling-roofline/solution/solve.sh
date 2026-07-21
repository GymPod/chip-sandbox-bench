#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def roofline(operations: float, bytes_moved: float, peak_ops_per_cycle: float, bytes_per_cycle: float) -> dict:
    if operations < 0 or bytes_moved < 0 or peak_ops_per_cycle <= 0 or bytes_per_cycle <= 0:
        raise ValueError("invalid roofline input")
    intensity = float("inf") if bytes_moved == 0 else operations / bytes_moved
    rate = peak_ops_per_cycle if bytes_moved == 0 else min(peak_ops_per_cycle, intensity * bytes_per_cycle)
    cycles = 0.0 if operations == 0 else operations / rate
    return {"arithmetic_intensity": intensity, "attainable_ops_per_cycle": rate, "cycles": cycles}
PY
