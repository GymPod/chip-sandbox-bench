#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def mesh_latency(src: int, dst: int, width: int, height: int, router_cycles: int, link_cycles: int) -> int:
    if width <= 0 or height <= 0 or not 0 <= src < width * height or not 0 <= dst < width * height:
        raise ValueError("invalid mesh node")
    if router_cycles < 0 or link_cycles < 0:
        raise ValueError("negative latency")
    sx, sy = src % width, src // width
    dx, dy = dst % width, dst // width
    hops = abs(sx - dx) + abs(sy - dy)
    return (hops + 1) * router_cycles + hops * link_cycles
PY
