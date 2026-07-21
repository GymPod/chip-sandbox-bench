#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def pipeline_cycles(instructions: int, stages: int, issue_width: int, stalls: list[int]) -> int:
    if instructions < 0 or stages <= 0 or issue_width <= 0 or any(s < 0 for s in stalls):
        raise ValueError("invalid pipeline input")
    if instructions == 0:
        return 0
    return stages - 1 + (instructions + issue_width - 1) // issue_width + sum(stalls)
PY
