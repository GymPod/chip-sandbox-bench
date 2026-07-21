export type SolverTraceCommand = {
  command: string;
  command_sha256: string;
};

export type SolverTraceExecution = {
  return_code: number;
  stdout: string;
  stderr: string;
  duration_seconds: number;
  timed_out: boolean;
};

export type SolverTraceStep = {
  index: number;
  status: "running" | "passed" | "failed" | "error";
  started_at: string;
  completed_at?: string;
  request: {
    message_count: number;
    prompt: string;
  };
  response?: {
    model: string;
    content: string;
    usage?: Record<string, unknown>;
  };
  action?: SolverTraceCommand;
  execution?: SolverTraceExecution;
  verification?: SolverTraceExecution;
  error?: string;
};

export type SolverTrace = {
  schema_version: 1;
  trace_id: string;
  task_id: string;
  provider: string;
  solver: string;
  model?: string;
  status: "running" | "passed" | "failed" | "error";
  started_at: string;
  completed_at?: string;
  step_count: number;
  steps: SolverTraceStep[];
  error?: string;
};

export type SolverTraceRunSummary = {
  trace_count: number;
  step_count: number;
  passed: number;
  failed: number;
  errors: number;
};

export function parseSolverTrace(text: string): SolverTrace | undefined {
  if (!text.trim()) {
    return undefined;
  }
  const value: unknown = JSON.parse(text);
  if (!isSolverTrace(value)) {
    throw new Error("Unsupported solver trace format");
  }
  return value;
}

export function isSolverTrace(value: unknown): value is SolverTrace {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const trace = value as Partial<SolverTrace>;
  return (
    trace.schema_version === 1 &&
    typeof trace.trace_id === "string" &&
    typeof trace.task_id === "string" &&
    typeof trace.provider === "string" &&
    typeof trace.solver === "string" &&
    typeof trace.status === "string" &&
    typeof trace.started_at === "string" &&
    typeof trace.step_count === "number" &&
    Array.isArray(trace.steps) &&
    trace.steps.every(isSolverTraceStep)
  );
}

export function summarizeSolverTraces(traces: SolverTrace[]): SolverTraceRunSummary {
  return {
    trace_count: traces.length,
    step_count: traces.reduce((total, trace) => total + trace.step_count, 0),
    passed: traces.filter((trace) => trace.status === "passed").length,
    failed: traces.filter((trace) => trace.status === "failed").length,
    errors: traces.filter((trace) => trace.status === "error").length
  };
}

function isSolverTraceStep(value: unknown): value is SolverTraceStep {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const step = value as Partial<SolverTraceStep>;
  return (
    Number.isInteger(step.index) &&
    typeof step.status === "string" &&
    typeof step.started_at === "string" &&
    typeof step.request === "object" &&
    step.request !== null &&
    typeof step.request.message_count === "number" &&
    typeof step.request.prompt === "string"
  );
}
