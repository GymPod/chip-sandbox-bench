#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
from itertools import product

def enumerate_tiles(extents: tuple[int, ...], capacity: int) -> list[tuple[int, ...]]:
    if not extents or any(value <= 0 for value in extents) or capacity <= 0:
        raise ValueError("invalid tiling input")
    divisors = [[d for d in range(1, value + 1) if value % d == 0] for value in extents]
    return sorted(shape for shape in product(*divisors) if _product(shape) <= capacity)

def _product(values):
    result = 1
    for value in values: result *= value
    return result
PY
