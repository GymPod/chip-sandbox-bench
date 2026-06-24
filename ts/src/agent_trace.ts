import { createHash, randomUUID } from "node:crypto";
import type { CommandResult, Provider, ProviderRunTrace } from "./types";

export type AgentTraceEvent = {
  index: number;
  type: "lifecycle" | "command";
  label: string;
  status: "completed" | "failed";
  started_at: string;
  completed_at: string;
  duration_seconds: number;
  idle_gap_seconds?: number;
  command_idle_gap_seconds?: number;
  cwd?: string;
  timeout_seconds?: number;
  command_length?: number;
  command_sha256?: string;
  return_code?: number;
  error?: string;
};

export type AgentTrace = {
  schema_version: 1;
  trace_id: string;
  provider: string;
  task_id: string;
  started_at: string;
  completed_at?: string;
  event_count: number;
  command_count: number;
  idle_gap_summary: AgentTraceIdleGapSummary;
  events: AgentTraceEvent[];
};

export type AgentTraceIdleGapSummary = {
  count: number;
  max_seconds: number;
  over_10s: number;
  over_60s: number;
  over_300s: number;
};

export type AgentTraceRunSummary = AgentTraceIdleGapSummary & {
  trace_count: number;
  command_count: number;
};

export class AgentTraceRecorder {
  private readonly traceId = randomUUID();
  private readonly startedAt = new Date();
  private completedAt: Date | undefined;
  private readonly events: AgentTraceEvent[] = [];
  private lastCompletedWallMs: number | undefined;
  private lastCompletedCommandWallMs: number | undefined;

  constructor(
    private readonly provider: string,
    private readonly taskId: string
  ) {}

  async lifecycle<T>(label: string, action: () => Promise<T>): Promise<T> {
    return await this.record("lifecycle", label, undefined, action);
  }

  async command(
    label: string,
    command: string,
    cwd: string | undefined,
    timeoutSeconds: number,
    action: () => Promise<CommandResult>
  ): Promise<CommandResult> {
    return await this.record(
      "command",
      label,
      {
        cwd,
        timeout_seconds: timeoutSeconds,
        command_length: command.length,
        command_sha256: createHash("sha256").update(command).digest("hex")
      },
      action
    );
  }

  finish(): void {
    this.completedAt = new Date();
  }

  snapshot(): AgentTrace {
    return {
      schema_version: 1,
      trace_id: this.traceId,
      provider: this.provider,
      task_id: this.taskId,
      started_at: this.startedAt.toISOString(),
      completed_at: this.completedAt?.toISOString(),
      event_count: this.events.length,
      command_count: this.events.filter((event) => event.type === "command").length,
      idle_gap_summary: summarizeIdleGaps(this.events),
      events: this.events
    };
  }

  private async record<T>(
    type: AgentTraceEvent["type"],
    label: string,
    metadata: Partial<AgentTraceEvent> | undefined,
    action: () => Promise<T>
  ): Promise<T> {
    const startedAt = new Date();
    const startedWallMs = startedAt.getTime();
    const startedMonoMs = performance.now();
    const idleGapSeconds =
      this.lastCompletedWallMs === undefined ? undefined : Math.max(0, (startedWallMs - this.lastCompletedWallMs) / 1000);
    const commandIdleGapSeconds =
      type !== "command" || this.lastCompletedCommandWallMs === undefined
        ? undefined
        : Math.max(0, (startedWallMs - this.lastCompletedCommandWallMs) / 1000);
    try {
      const result = await action();
      const completedAt = new Date();
      const event: AgentTraceEvent = {
        index: this.events.length,
        type,
        label,
        status: "completed",
        started_at: startedAt.toISOString(),
        completed_at: completedAt.toISOString(),
        duration_seconds: (performance.now() - startedMonoMs) / 1000,
        ...(idleGapSeconds === undefined ? {} : { idle_gap_seconds: idleGapSeconds }),
        ...(commandIdleGapSeconds === undefined ? {} : { command_idle_gap_seconds: commandIdleGapSeconds }),
        ...metadata,
        ...(isCommandResult(result) ? { return_code: result.returnCode } : {})
      };
      this.events.push(event);
      this.lastCompletedWallMs = completedAt.getTime();
      if (type === "command") {
        this.lastCompletedCommandWallMs = completedAt.getTime();
      }
      return result;
    } catch (error) {
      const completedAt = new Date();
      this.events.push({
        index: this.events.length,
        type,
        label,
        status: "failed",
        started_at: startedAt.toISOString(),
        completed_at: completedAt.toISOString(),
        duration_seconds: (performance.now() - startedMonoMs) / 1000,
        ...(idleGapSeconds === undefined ? {} : { idle_gap_seconds: idleGapSeconds }),
        ...(commandIdleGapSeconds === undefined ? {} : { command_idle_gap_seconds: commandIdleGapSeconds }),
        ...metadata,
        error: formatError(error)
      });
      this.lastCompletedWallMs = completedAt.getTime();
      if (type === "command") {
        this.lastCompletedCommandWallMs = completedAt.getTime();
      }
      throw error;
    }
  }
}

export class TracedProvider implements Provider {
  constructor(
    private readonly provider: Provider,
    private readonly recorder: AgentTraceRecorder
  ) {}

  async start(): Promise<void> {
    await this.recorder.lifecycle("start", () => this.provider.start());
  }

  async run(command: string, cwd: string | undefined, timeoutSeconds: number, trace?: ProviderRunTrace): Promise<CommandResult> {
    return await this.recorder.command(trace?.label ?? "command", command, cwd, timeoutSeconds, () =>
      this.provider.run(command, cwd, timeoutSeconds, trace)
    );
  }

  async stop(): Promise<void> {
    await this.recorder.lifecycle("stop", () => this.provider.stop());
  }
}

export function summarizeAgentTraces(traces: AgentTrace[]): AgentTraceRunSummary {
  const idleGaps = traces.flatMap((trace) =>
    trace.events.map((event) => event.command_idle_gap_seconds).filter((value): value is number => typeof value === "number")
  );
  return {
    trace_count: traces.length,
    command_count: traces.reduce((sum, trace) => sum + trace.command_count, 0),
    ...summarizeIdleGapValues(idleGaps)
  };
}

function summarizeIdleGaps(events: AgentTraceEvent[]): AgentTraceIdleGapSummary {
  return summarizeIdleGapValues(
    events.map((event) => event.command_idle_gap_seconds).filter((value): value is number => typeof value === "number")
  );
}

function summarizeIdleGapValues(values: number[]): AgentTraceIdleGapSummary {
  return {
    count: values.length,
    max_seconds: values.length === 0 ? 0 : Math.max(...values),
    over_10s: values.filter((value) => value >= 10).length,
    over_60s: values.filter((value) => value >= 60).length,
    over_300s: values.filter((value) => value >= 300).length
  };
}

function isCommandResult(value: unknown): value is CommandResult {
  return (
    typeof value === "object" &&
    value !== null &&
    "stdout" in value &&
    "stderr" in value &&
    "returnCode" in value &&
    typeof (value as CommandResult).returnCode === "number"
  );
}

function formatError(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}
