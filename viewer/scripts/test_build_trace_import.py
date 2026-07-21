import json
import tempfile
import unittest
from pathlib import Path

from build_trace_import import build_trace_import


class BuildTraceImportTest(unittest.TestCase):
    def test_builds_run_and_step_documents(self):
        trace = {
            "schema_version": 1,
            "trace_id": "trace-1",
            "task_id": "task-1",
            "provider": "aws-microvm",
            "solver": "ai-gateway",
            "model": "moonshotai/kimi-k3",
            "status": "passed",
            "started_at": "2026-07-21T00:00:00Z",
            "completed_at": "2026-07-21T00:00:02Z",
            "step_count": 1,
            "steps": [
                {
                    "index": 1,
                    "status": "passed",
                    "started_at": "2026-07-21T00:00:00Z",
                    "request": {"message_count": 2, "prompt": "Fix it."},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tempdir:
            result = Path(tempdir) / "result.json"
            result.write_text(json.dumps({"results": [{"solver_trace": trace}]}), encoding="utf-8")
            runs, steps = build_trace_import([result])

        self.assertEqual(runs[0]["traceId"], "trace-1")
        self.assertEqual(runs[0]["stepCount"], 1)
        self.assertEqual(steps[0]["payload"]["request"]["prompt"], "Fix it.")


if __name__ == "__main__":
    unittest.main()
