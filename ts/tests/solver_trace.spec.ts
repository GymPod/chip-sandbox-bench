import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  isSolverTrace,
  parseSolverTrace,
  summarizeSolverTraces,
  type SolverTrace
} from "../src/solver_trace";

const sample: SolverTrace = {
  schema_version: 1,
  trace_id: "trace-1",
  task_id: "task-1",
  provider: "aws-microvm",
  solver: "ai-gateway",
  model: "moonshotai/kimi-k3",
  status: "passed",
  started_at: "2026-07-21T00:00:00Z",
  completed_at: "2026-07-21T00:00:03Z",
  step_count: 1,
  steps: [
    {
      index: 1,
      status: "passed",
      started_at: "2026-07-21T00:00:00Z",
      completed_at: "2026-07-21T00:00:03Z",
      request: { message_count: 2, prompt: "Fix the task." },
      response: { model: "moonshotai/kimi-k3", content: "echo fixed" },
      action: { command: "echo fixed", command_sha256: "abc" },
      execution: { return_code: 0, stdout: "fixed\n", stderr: "", duration_seconds: 1, timed_out: false },
      verification: { return_code: 0, stdout: "pass\n", stderr: "", duration_seconds: 1, timed_out: false }
    }
  ]
};

test("solver trace parser accepts the versioned step format", () => {
  expect(parseSolverTrace(JSON.stringify(sample))).toEqual(sample);
  expect(isSolverTrace({ ...sample, schema_version: 2 })).toBe(false);
});

test("solver trace summary counts steps and terminal states", () => {
  expect(summarizeSolverTraces([sample, { ...sample, trace_id: "trace-2", status: "failed", step_count: 3 }])).toEqual({
    trace_count: 2,
    step_count: 4,
    passed: 1,
    failed: 1,
    errors: 0
  });
});

test("AI Gateway shell uses the shared trace-writing solver", () => {
  const repoRoot = resolve(process.cwd(), "..");
  const shell = readFileSync(resolve(repoRoot, "scripts/ai_gateway_solver.sh"), "utf8");
  const bench = readFileSync(resolve(repoRoot, "ts/src/bench.ts"), "utf8");
  const solver = readFileSync(resolve(repoRoot, "py/code_sandbox_bench/ai_gateway_solver.py"), "utf8");

  expect(shell).toContain("/tmp/code_sandbox_bench_ai_gateway_solver.py");
  expect(bench).toContain("upload_ai_gateway_solver");
  expect(bench).toContain("read_solver_trace");
  expect(solver).toContain('"schema_version": 1');
  expect(solver).toContain("persist_trace(trace)");
});
