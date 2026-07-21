#!/usr/bin/env python3
"""Build Convex imports for versioned solver traces in benchmark results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


def result_rows(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        text = path.read_text(encoding="utf-8")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            for line in text.splitlines():
                if line.strip():
                    row = json.loads(line)
                    if isinstance(row, dict):
                        yield row
            continue
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            yield from (row for row in payload["results"] if isinstance(row, dict))
        elif isinstance(payload, dict):
            yield payload


def build_trace_import(paths: Iterable[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    runs: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in result_rows(paths):
        trace = row.get("solver_trace")
        if not isinstance(trace, dict) or trace.get("schema_version") != 1:
            continue
        trace_id = str(trace["trace_id"])
        if trace_id in seen:
            continue
        seen.add(trace_id)
        task_id = str(trace["task_id"])
        runs.append(
            {
                "traceId": trace_id,
                "taskId": task_id,
                "provider": str(trace["provider"]),
                "solver": str(trace["solver"]),
                **({"model": str(trace["model"])} if trace.get("model") else {}),
                "status": str(trace["status"]),
                "startedAt": str(trace["started_at"]),
                **({"completedAt": str(trace["completed_at"])} if trace.get("completed_at") else {}),
                "stepCount": int(trace.get("step_count") or 0),
            }
        )
        for step in trace.get("steps", []):
            if not isinstance(step, dict):
                continue
            steps.append(
                {
                    "traceId": trace_id,
                    "taskId": task_id,
                    "index": int(step["index"]),
                    "status": str(step["status"]),
                    "startedAt": str(step["started_at"]),
                    **({"completedAt": str(step["completed_at"])} if step.get("completed_at") else {}),
                    "payload": step,
                }
            )
    runs.sort(key=lambda run: (run["taskId"], run["startedAt"], run["traceId"]))
    steps.sort(key=lambda step: (step["taskId"], step["traceId"], step["index"]))
    return runs, steps


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--output-dir", type=Path, default=Path(".convex-import"))
    args = parser.parse_args()
    runs, steps = build_trace_import(path.resolve() for path in args.results)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "traceRuns.json").write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "traceSteps.json").write_text(json.dumps(steps, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(runs)} trace runs and {len(steps)} trace steps to {args.output_dir}")


if __name__ == "__main__":
    main()
