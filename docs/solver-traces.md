# Solver trace format

AI Gateway solver runs write a versioned trace to `/logs/solver/trace.json`.
The benchmark runner reads that file after the solver exits and stores it as
`solver_trace` on the task result. Traces are written atomically after each
state transition, so a model, script, verifier, or API failure still leaves a
viewable partial trace.

## Schema

```json
{
  "schema_version": 1,
  "trace_id": "uuid",
  "task_id": "task-id",
  "provider": "aws-microvm",
  "solver": "ai-gateway",
  "model": "moonshotai/kimi-k3",
  "status": "running | passed | failed | error",
  "started_at": "ISO-8601",
  "completed_at": "ISO-8601",
  "step_count": 1,
  "steps": [
    {
      "index": 1,
      "status": "running | passed | failed | error",
      "started_at": "ISO-8601",
      "completed_at": "ISO-8601",
      "request": {
        "message_count": 2,
        "prompt": "The user message sent for this step"
      },
      "response": {
        "model": "moonshotai/kimi-k3",
        "content": "Raw model response",
        "usage": {}
      },
      "action": {
        "command": "Extracted shell script",
        "command_sha256": "sha256"
      },
      "execution": {
        "return_code": 0,
        "stdout": "",
        "stderr": "",
        "duration_seconds": 1.2,
        "timed_out": false
      },
      "verification": {
        "return_code": 0,
        "stdout": "",
        "stderr": "",
        "duration_seconds": 0.4,
        "timed_out": false
      }
    }
  ]
}
```

Credentials and forwarded environment values are not included. Command output
is bounded by the solver before it is added to the trace.

The top-level benchmark result also contains `solver_trace_summary`, with trace
and step counts plus passed, failed, and error totals.

Open [`viewer/trace-viewer.html`](../viewer/trace-viewer.html) directly in a
browser and select a benchmark result JSON or JSONL file to inspect all traces
and steps without running a server.
