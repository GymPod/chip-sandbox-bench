#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def commit_ready(entries: list[dict], width: int) -> list[int]:
    if width < 0:
        raise ValueError("negative width")
    committed = []
    for index, entry in enumerate(entries[:width]):
        if not entry["ready"]:
            break
        committed.append(index)
        if entry.get("exception", False):
            break
    return committed
PY
