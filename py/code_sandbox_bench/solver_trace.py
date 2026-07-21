import json
from typing import Any


TRACE_PATH = "/logs/solver/trace.json"


def parse_solver_trace(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None
    value = json.loads(text)
    if not is_solver_trace(value):
        raise ValueError("Unsupported solver trace format")
    return value


def is_solver_trace(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    steps = value.get("steps")
    return (
        value.get("schema_version") == 1
        and isinstance(value.get("trace_id"), str)
        and isinstance(value.get("task_id"), str)
        and isinstance(value.get("provider"), str)
        and isinstance(value.get("solver"), str)
        and isinstance(value.get("status"), str)
        and isinstance(value.get("started_at"), str)
        and isinstance(value.get("step_count"), int)
        and isinstance(steps, list)
        and all(is_solver_trace_step(step) for step in steps)
    )


def summarize_solver_traces(traces: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "trace_count": len(traces),
        "step_count": sum(int(trace.get("step_count") or 0) for trace in traces),
        "passed": sum(1 for trace in traces if trace.get("status") == "passed"),
        "failed": sum(1 for trace in traces if trace.get("status") == "failed"),
        "errors": sum(1 for trace in traces if trace.get("status") == "error"),
    }


def is_solver_trace_step(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    request = value.get("request")
    return (
        isinstance(value.get("index"), int)
        and isinstance(value.get("status"), str)
        and isinstance(value.get("started_at"), str)
        and isinstance(request, dict)
        and isinstance(request.get("message_count"), int)
        and isinstance(request.get("prompt"), str)
    )
