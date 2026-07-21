#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def average_memory_access_time(levels: list[dict], memory_latency: float) -> float:
    if memory_latency < 0:
        raise ValueError("negative latency")
    expected = 0.0
    reach = 1.0
    for level in levels:
        latency = float(level["hit_latency"])
        rate = float(level["local_hit_rate"])
        if latency < 0 or not 0.0 <= rate <= 1.0:
            raise ValueError("invalid cache level")
        expected += reach * latency
        reach *= 1.0 - rate
    return expected + reach * memory_latency
PY
