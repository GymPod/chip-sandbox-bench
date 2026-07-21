#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
import math

def sparse_storage(dense_elements: int, density: float, value_bytes: int, metadata_bits: int) -> dict:
    if dense_elements < 0 or not 0 <= density <= 1 or value_bytes <= 0 or metadata_bits < 0:
        raise ValueError("invalid sparse tensor")
    nonzeros = math.ceil(dense_elements * density)
    data_bytes = nonzeros * value_bytes
    metadata_bytes = (nonzeros * metadata_bits + 7) // 8
    total = data_bytes + metadata_bytes
    ratio = float("inf") if total == 0 else dense_elements * value_bytes / total
    return {"nonzeros": nonzeros, "data_bytes": data_bytes, "metadata_bytes": metadata_bytes,
            "total_bytes": total, "compression_ratio": ratio}
PY
