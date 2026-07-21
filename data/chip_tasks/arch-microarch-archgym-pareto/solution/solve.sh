#!/bin/sh
cat > /workspace/dse.py <<'PY'
"""Small ArchGym-style multi-objective design-space exploration helper."""


def pareto_frontier(candidates: list[dict[str, object]]) -> list[str]:
    """Return IDs for designs not dominated on latency, energy, and area."""
    metrics = ("latency", "energy", "area")
    frontier = []
    for candidate in candidates:
        dominated = False
        for other in candidates:
            if other is candidate:
                continue
            no_worse = all(other[name] <= candidate[name] for name in metrics)
            strictly_better = any(other[name] < candidate[name] for name in metrics)
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(str(candidate["id"]))
    return sorted(frontier)
PY
