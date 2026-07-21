import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from code_sandbox_bench import ai_gateway_solver
from code_sandbox_bench.solver_trace import is_solver_trace, parse_solver_trace, summarize_solver_traces


class SolverTraceTest(unittest.TestCase):
    def sample(self):
        return {
            "schema_version": 1,
            "trace_id": "trace-1",
            "task_id": "task-1",
            "provider": "aws-microvm",
            "solver": "ai-gateway",
            "status": "passed",
            "started_at": "2026-07-21T00:00:00Z",
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

    def test_parse_and_summarize(self):
        trace = self.sample()
        self.assertEqual(parse_solver_trace(json.dumps(trace)), trace)
        self.assertFalse(is_solver_trace({**trace, "schema_version": 2}))
        failed = {**trace, "trace_id": "trace-2", "status": "failed", "step_count": 2}
        self.assertEqual(
            summarize_solver_traces([trace, failed]),
            {"trace_count": 2, "step_count": 3, "passed": 1, "failed": 1, "errors": 0},
        )

    def test_trace_write_is_atomic_and_updates_step_count(self):
        trace = self.sample()
        trace["step_count"] = 0
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "trace.json"
            with patch.object(ai_gateway_solver, "TRACE_PATH", target):
                ai_gateway_solver.persist_trace(trace)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["step_count"], 1)
            self.assertFalse(target.with_suffix(".json.tmp").exists())

    def test_solver_main_persists_a_complete_step(self):
        response = {"model": "moonshotai/kimi-k3", "content": "echo fixed", "usage": {"total_tokens": 10}}
        execution = {
            "return_code": 0,
            "stdout": "fixed\n",
            "stderr": "",
            "duration_seconds": 0.1,
            "timed_out": False,
        }
        verification = {
            "return_code": 0,
            "stdout": "pass\n",
            "stderr": "",
            "duration_seconds": 0.2,
            "timed_out": False,
        }
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "trace.json"
            with (
                patch.object(ai_gateway_solver, "TRACE_PATH", target),
                patch.object(ai_gateway_solver, "read_text", return_value="fixture"),
                patch.object(ai_gateway_solver, "workspace_context", return_value="workspace"),
                patch.object(ai_gateway_solver, "chat", return_value=response),
                patch.object(ai_gateway_solver, "run_captured", side_effect=[execution, verification]),
            ):
                ai_gateway_solver.main()
            trace = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(trace["status"], "passed")
        self.assertEqual(trace["step_count"], 1)
        self.assertEqual(trace["steps"][0]["response"]["model"], "moonshotai/kimi-k3")
        self.assertEqual(trace["steps"][0]["verification"]["return_code"], 0)


if __name__ == "__main__":
    unittest.main()
