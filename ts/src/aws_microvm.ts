import { randomUUID } from "node:crypto";
import {
  CreateMicrovmAuthTokenCommand,
  GetMicrovmCommand,
  LambdaMicrovmsClient,
  ResumeMicrovmCommand,
  RunMicrovmCommand,
  SuspendMicrovmCommand,
  TerminateMicrovmCommand
} from "@aws-sdk/client-lambda-microvms";
import type { CommandResult } from "./types";

export type AwsMicrovmSessionMode = "terminate" | "auto-suspend" | "explicit-suspend";

export type AwsMicrovmKnownState =
  | "NOT_STARTED"
  | "PENDING"
  | "RUNNING"
  | "SUSPENDING"
  | "SUSPENDED"
  | "TERMINATING"
  | "TERMINATED"
  | "UNKNOWN";

export type AwsMicrovmIdlePolicy = {
  maxIdleDurationSeconds: number;
  suspendedDurationSeconds: number;
  autoResumeEnabled: boolean;
};

export type AwsMicrovmPricingConfig = {
  vcpuSecondUsd: number;
  gbSecondUsd: number;
  snapshotWriteGbUsd: number;
  snapshotReadGbUsd: number;
  snapshotStorageGbMonthUsd: number;
};

export type AwsMicrovmSandboxConfig = {
  region: string;
  imageIdentifier: string;
  imageVersion?: string;
  executionRoleArn?: string;
  cpu: number;
  memoryGb: number;
  port: number;
  authTokenExpirationMinutes: number;
  maximumDurationInSeconds: number;
  idlePolicy: AwsMicrovmIdlePolicy;
  sessionMode: AwsMicrovmSessionMode;
  ingressNetworkConnectors: string[];
  egressNetworkConnectors: string[];
  logGroup?: string;
  clientTokenPrefix: string;
  startTimeoutSeconds: number;
  quotaRetryDelaySeconds: number;
  firstRequestTimeoutSeconds: number;
  resumeTimeoutSeconds: number;
  resumeCheckAfterIdleSeconds: number;
  pricing: AwsMicrovmPricingConfig;
};

export type AwsMicrovmSandboxEnvOptions = {
  imageIdentifier?: string;
  imageVersion?: string;
  executionRoleArn?: string;
  timeoutSeconds: number;
  cpu: number;
  memoryGb: number;
};

export type AwsMicrovmLifecycleEvent = {
  event: "run_microvm" | "ready" | "resume" | "suspend" | "terminate" | "state_refresh" | "command";
  reason?: string;
  state?: AwsMicrovmKnownState;
  started_at: string;
  completed_at: string;
  duration_seconds: number;
  idle_gap_seconds?: number;
  error?: string;
};

export type AwsMicrovmLifecycleCost = {
  billable_vcpu: number;
  running_seconds: number;
  suspended_seconds: number;
  suspend_count: number;
  resume_count: number;
  launch_snapshot_read_gb: number;
  suspend_snapshot_write_gb: number;
  resume_snapshot_read_gb: number;
  running_compute_usd: number;
  snapshot_write_usd: number;
  snapshot_read_usd: number;
  suspended_storage_usd: number;
  total_usd: number;
};

export type AwsMicrovmTelemetry = {
  session_mode: AwsMicrovmSessionMode;
  microvm_id?: string;
  image_identifier: string;
  image_version?: string;
  last_known_state: AwsMicrovmKnownState;
  command_count: number;
  resume_attempts: number;
  resume_count: number;
  suspend_count: number;
  terminate_count: number;
  auto_resume_retry_count: number;
  first_request_timeout_seconds: number;
  resume_timeout_seconds: number;
  last_command_completed_at?: string;
  lifecycle_events: AwsMicrovmLifecycleEvent[];
  lifecycle_cost: AwsMicrovmLifecycleCost;
  pricing: AwsMicrovmPricingConfig;
};

export class AwsMicrovmSandbox {
  private readonly client: LambdaMicrovmsClient;
  private microvmId: string | undefined;
  private lastMicrovmId: string | undefined;
  private endpoint: string | undefined;
  private authToken: string | undefined;
  private authTokenExpiresAt = 0;
  private lastKnownState: AwsMicrovmKnownState = "NOT_STARTED";
  private lastCommandCompletedAtMs: number | undefined;
  private commandCount = 0;
  private resumeAttempts = 0;
  private resumeCount = 0;
  private suspendCount = 0;
  private terminateCount = 0;
  private autoResumeRetryCount = 0;
  private runningStartedAtMs: number | undefined;
  private suspendedStartedAtMs: number | undefined;
  private accumulatedRunningSeconds = 0;
  private accumulatedSuspendedSeconds = 0;
  private readonly lifecycleEvents: AwsMicrovmLifecycleEvent[] = [];

  constructor(private readonly config: AwsMicrovmSandboxConfig) {
    this.client = new LambdaMicrovmsClient({ region: config.region });
  }

  async start(): Promise<void> {
    const response = await this.recordLifecycle("run_microvm", "start", () => this.runMicrovmWithQuotaRetry());
    this.microvmId = required(response.microvmId, "RunMicrovm did not return a microvmId");
    this.lastMicrovmId = this.microvmId;
    this.endpoint = required(response.endpoint, "RunMicrovm did not return an endpoint");
    this.lastKnownState = "RUNNING";
    this.markRunning();
    await this.recordLifecycle("ready", "start", () => this.waitForReady());
  }

  async run(command: string, cwd: string | undefined, timeoutSeconds: number): Promise<CommandResult> {
    if (!this.microvmId || !this.endpoint) {
      throw new Error("AWS MicroVM sandbox not started");
    }
    await this.ensureRunnableBeforeCommand();
    const idleGapSeconds =
      this.lastCommandCompletedAtMs === undefined ? undefined : Math.max(0, (Date.now() - this.lastCommandCompletedAtMs) / 1000);
    const result = await this.recordLifecycle("command", "run", () => this.postCommand(command, cwd, timeoutSeconds), {
      idleGapSeconds
    });
    this.commandCount += 1;
    this.lastCommandCompletedAtMs = Date.now();
    return result;
  }

  async suspend(reason = "manual"): Promise<void> {
    if (!this.microvmId || isSuspendedOrTerminated(this.lastKnownState)) {
      return;
    }
    await this.refreshState("before-suspend").catch(() => undefined);
    if (!this.microvmId || isSuspendedOrTerminated(this.lastKnownState)) {
      return;
    }
    const microvmIdentifier = this.microvmId;
    let suspendedByThisCall = false;
    try {
      await this.recordLifecycle("suspend", reason, () => this.client.send(new SuspendMicrovmCommand({ microvmIdentifier })));
      suspendedByThisCall = true;
    } catch (error) {
      if (!isConflict(error)) {
        throw error;
      }
      await this.refreshState("suspend-conflict").catch(() => undefined);
      if (!isSuspended(this.lastKnownState)) {
        throw error;
      }
    }
    if (suspendedByThisCall) {
      this.suspendCount += 1;
    }
    this.authToken = undefined;
    await this.refreshState("after-suspend").catch(() => undefined);
    this.lastKnownState = "SUSPENDED";
    this.markSuspended();
  }

  async resume(reason = "manual"): Promise<void> {
    if (!this.microvmId || isRunning(this.lastKnownState)) {
      return;
    }
    await this.refreshState("before-resume").catch(() => undefined);
    if (!this.microvmId || isRunning(this.lastKnownState)) {
      return;
    }
    const microvmIdentifier = this.microvmId;
    this.resumeAttempts += 1;
    let resumedByThisCall = false;
    try {
      await this.recordLifecycle("resume", reason, () => this.client.send(new ResumeMicrovmCommand({ microvmIdentifier })));
      resumedByThisCall = true;
    } catch (error) {
      if (!isConflict(error)) {
        throw error;
      }
      await this.refreshState("resume-conflict").catch(() => undefined);
      if (!isRunning(this.lastKnownState)) {
        throw error;
      }
    }
    if (resumedByThisCall) {
      this.resumeCount += 1;
    }
    this.authToken = undefined;
    await this.waitForRunningAfterResume();
    await this.recordLifecycle("ready", "resume", () => this.waitForReady());
  }

  async stop(): Promise<void> {
    if (!this.microvmId) {
      return;
    }
    if (this.config.sessionMode !== "terminate") {
      await this.suspend("stop");
      return;
    }
    await this.terminate("stop");
  }

  async terminate(reason = "manual"): Promise<void> {
    if (!this.microvmId) {
      return;
    }
    const microvmIdentifier = this.microvmId;
    try {
      await this.recordLifecycle("terminate", reason, () => this.client.send(new TerminateMicrovmCommand({ microvmIdentifier })));
      this.terminateCount += 1;
      this.lastKnownState = "TERMINATED";
      this.markStopped();
    } catch (error) {
      if (!isResourceNotFound(error)) {
        throw error;
      }
      this.lastKnownState = "TERMINATED";
      this.markStopped();
    }
    this.microvmId = undefined;
    this.endpoint = undefined;
    this.authToken = undefined;
  }

  telemetry(): AwsMicrovmTelemetry {
    const lifecycleCost = this.lifecycleCost();
    return {
      session_mode: this.config.sessionMode,
      microvm_id: this.microvmId ?? this.lastMicrovmId,
      image_identifier: this.config.imageIdentifier,
      image_version: this.config.imageVersion,
      last_known_state: this.lastKnownState,
      command_count: this.commandCount,
      resume_attempts: this.resumeAttempts,
      resume_count: this.resumeCount,
      suspend_count: this.suspendCount,
      terminate_count: this.terminateCount,
      auto_resume_retry_count: this.autoResumeRetryCount,
      first_request_timeout_seconds: this.config.firstRequestTimeoutSeconds,
      resume_timeout_seconds: this.config.resumeTimeoutSeconds,
      last_command_completed_at: this.lastCommandCompletedAtMs ? new Date(this.lastCommandCompletedAtMs).toISOString() : undefined,
      lifecycle_events: this.lifecycleEvents,
      lifecycle_cost: lifecycleCost,
      pricing: this.config.pricing
    };
  }

  private async runMicrovmWithQuotaRetry(): Promise<{
    microvmId?: string;
    endpoint?: string;
  }> {
    const started = performance.now();
    let lastError: unknown;
    while ((performance.now() - started) / 1000 < this.config.startTimeoutSeconds) {
      try {
        return await this.client.send(
          new RunMicrovmCommand({
            imageIdentifier: this.config.imageIdentifier,
            imageVersion: this.config.imageVersion,
            executionRoleArn: this.config.executionRoleArn,
            maximumDurationInSeconds: this.config.maximumDurationInSeconds,
            idlePolicy: this.config.idlePolicy,
            ingressNetworkConnectors: this.config.ingressNetworkConnectors,
            egressNetworkConnectors: this.config.egressNetworkConnectors,
            logging: this.config.logGroup ? { cloudWatch: { logGroup: this.config.logGroup } } : undefined,
            clientToken: `${this.config.clientTokenPrefix}-${randomUUID()}`
          })
        );
      } catch (error) {
        lastError = error;
        if (!isQuotaExceeded(error)) {
          throw error;
        }
        await sleep(this.config.quotaRetryDelaySeconds * 1000);
      }
    }
    throw new Error(`AWS MicroVM start timed out waiting for quota: ${formatError(lastError)}`);
  }

  private async waitForReady(): Promise<void> {
    const started = performance.now();
    const timeoutMs = Math.min(120_000, Math.max(30_000, this.config.maximumDurationInSeconds * 1000));
    let lastError: unknown;
    while (performance.now() - started < timeoutMs) {
      try {
        await this.refreshState("wait-ready");
        await this.authedFetch("/health", {
          method: "GET",
          signal: AbortSignal.timeout(10_000)
        });
        return;
      } catch (error) {
        lastError = error;
        await sleep(2000);
      }
    }
    throw new Error(`AWS MicroVM did not become ready: ${formatError(lastError)}`);
  }

  private async refreshState(reason: string): Promise<void> {
    if (!this.microvmId) {
      return;
    }
    const response = await this.recordLifecycle("state_refresh", reason, () =>
      this.client.send(new GetMicrovmCommand({ microvmIdentifier: this.microvmId }))
    );
    if (response.endpoint) {
      this.endpoint = response.endpoint;
    }
    this.setKnownState(normalizeMicrovmState(response.state));
  }

  private async postCommand(command: string, cwd: string | undefined, timeoutSeconds: number): Promise<CommandResult> {
    const started = performance.now();
    const startResponse = await this.startCommandWithResumeRetry(command, cwd, timeoutSeconds);
    const startedJob = (await startResponse.json()) as { jobId?: string; error?: string };
    if (!startedJob.jobId) {
      throw new Error(startedJob.error ?? "AWS MicroVM command did not return a jobId");
    }
    let lastPollError: unknown;
    while ((performance.now() - started) / 1000 < timeoutSeconds + 30) {
      try {
        const response = await this.authedFetch(`/commands/${encodeURIComponent(startedJob.jobId)}`, {
          method: "GET",
          signal: AbortSignal.timeout(15_000)
        });
        lastPollError = undefined;
        const parsed = (await response.json()) as Partial<CommandResult> & { status?: string; error?: string };
        if (parsed.status === "completed") {
          return {
            stdout: String(parsed.stdout ?? ""),
            stderr: String(parsed.stderr ?? ""),
            returnCode: Number(parsed.returnCode ?? 1),
            usage: isCommandUsage(parsed.usage) ? parsed.usage : undefined
          };
        }
        if (parsed.error) {
          return { stdout: "", stderr: parsed.error, returnCode: 1 };
        }
      } catch (error) {
        lastPollError = error;
        if (!isRetryablePollError(error)) {
          throw error;
        }
        await this.refreshState("poll-error").catch(() => undefined);
        this.authToken = undefined;
      }
      await sleep(2000);
    }
    return {
      stdout: "",
      stderr: `Command timed out after ${timeoutSeconds}s${lastPollError ? `; last poll error: ${formatError(lastPollError)}` : ""}`,
      returnCode: 124
    };
  }

  private async startCommandWithResumeRetry(command: string, cwd: string | undefined, timeoutSeconds: number): Promise<Response> {
    const init = () => ({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command, cwd, timeoutSeconds }),
      signal: AbortSignal.timeout(this.config.firstRequestTimeoutSeconds * 1000)
    });
    try {
      return await this.authedFetch("/commands", init());
    } catch (error) {
      if (!this.shouldRetryFirstRequestAfterIdle(error)) {
        throw error;
      }
      this.autoResumeRetryCount += 1;
      await this.refreshState("first-request-error").catch(() => undefined);
      if (this.lastKnownState === "SUSPENDED") {
        await this.resume("first-request-retry");
      }
      this.authToken = undefined;
      return await this.authedFetch("/commands", init());
    }
  }

  private async ensureRunnableBeforeCommand(): Promise<void> {
    if (this.config.sessionMode === "explicit-suspend") {
      await this.refreshState("before-explicit-command").catch(() => undefined);
      if (this.lastKnownState === "SUSPENDED" || this.lastKnownState === "SUSPENDING") {
        await this.resume("before-command");
      }
      return;
    }
    const idleSeconds =
      this.lastCommandCompletedAtMs === undefined ? 0 : Math.max(0, (Date.now() - this.lastCommandCompletedAtMs) / 1000);
    if (this.config.sessionMode === "auto-suspend" && idleSeconds >= this.config.resumeCheckAfterIdleSeconds) {
      await this.refreshState("before-auto-command").catch(() => undefined);
    }
  }

  private async waitForRunningAfterResume(): Promise<void> {
    const started = performance.now();
    let lastError: unknown;
    while ((performance.now() - started) / 1000 < this.config.resumeTimeoutSeconds) {
      try {
        await this.refreshState("wait-resume");
        if (this.lastKnownState === "RUNNING") {
          this.markRunning();
          return;
        }
      } catch (error) {
        lastError = error;
      }
      await sleep(1000);
    }
    throw new Error(`AWS MicroVM did not resume within ${this.config.resumeTimeoutSeconds}s: ${formatError(lastError)}`);
  }

  private shouldRetryFirstRequestAfterIdle(error: unknown): boolean {
    if (!isRetryablePollError(error)) {
      return false;
    }
    if (this.config.sessionMode === "terminate") {
      return false;
    }
    if (this.lastCommandCompletedAtMs === undefined) {
      return true;
    }
    return (Date.now() - this.lastCommandCompletedAtMs) / 1000 >= this.config.resumeCheckAfterIdleSeconds;
  }

  private async authedFetch(path: string, init: RequestInit): Promise<Response> {
    const token = await this.getAuthToken();
    const response = await fetch(this.url(path), {
      ...init,
      headers: {
        ...Object.fromEntries(new Headers(init.headers).entries()),
        "X-aws-proxy-auth": token,
        "X-aws-proxy-port": String(this.config.port)
      }
    });
    if (!response.ok) {
      throw new AwsMicrovmHttpError(response.status, await response.text());
    }
    return response;
  }

  private async getAuthToken(): Promise<string> {
    if (this.authToken && Date.now() < this.authTokenExpiresAt - 60_000) {
      return this.authToken;
    }
    if (!this.microvmId) {
      throw new Error("AWS MicroVM sandbox not started");
    }
    const response = await this.client.send(
      new CreateMicrovmAuthTokenCommand({
        microvmIdentifier: this.microvmId,
        expirationInMinutes: this.config.authTokenExpirationMinutes,
        allowedPorts: [{ port: this.config.port }]
      })
    );
    const token = response.authToken?.["X-aws-proxy-auth"];
    if (!token) {
      throw new Error("CreateMicrovmAuthToken did not return X-aws-proxy-auth");
    }
    this.authToken = token;
    this.authTokenExpiresAt = Date.now() + this.config.authTokenExpirationMinutes * 60_000;
    return token;
  }

  private url(path: string): string {
    if (!this.endpoint) {
      throw new Error("AWS MicroVM endpoint is unavailable");
    }
    const base = this.endpoint.startsWith("http") ? this.endpoint : `https://${this.endpoint}`;
    return new URL(path, base.endsWith("/") ? base : `${base}/`).toString();
  }

  private async recordLifecycle<T>(
    event: AwsMicrovmLifecycleEvent["event"],
    reason: string,
    action: () => Promise<T>,
    options: { idleGapSeconds?: number } = {}
  ): Promise<T> {
    const startedAt = new Date();
    const started = performance.now();
    try {
      const result = await action();
      this.lifecycleEvents.push({
        event,
        reason,
        state: this.lastKnownState,
        started_at: startedAt.toISOString(),
        completed_at: new Date().toISOString(),
        duration_seconds: (performance.now() - started) / 1000,
        ...(options.idleGapSeconds === undefined ? {} : { idle_gap_seconds: options.idleGapSeconds })
      });
      return result;
    } catch (error) {
      this.lifecycleEvents.push({
        event,
        reason,
        state: this.lastKnownState,
        started_at: startedAt.toISOString(),
        completed_at: new Date().toISOString(),
        duration_seconds: (performance.now() - started) / 1000,
        ...(options.idleGapSeconds === undefined ? {} : { idle_gap_seconds: options.idleGapSeconds }),
        error: formatError(error)
      });
      throw error;
    }
  }

  private setKnownState(state: AwsMicrovmKnownState): void {
    if (state === this.lastKnownState) {
      return;
    }
    this.lastKnownState = state;
    if (state === "RUNNING") {
      this.markRunning();
    } else if (state === "SUSPENDED") {
      this.markSuspended();
    } else if (state === "TERMINATED" || state === "TERMINATING") {
      this.markStopped();
    }
  }

  private markRunning(): void {
    if (this.runningStartedAtMs !== undefined) {
      return;
    }
    if (this.suspendedStartedAtMs !== undefined) {
      this.accumulatedSuspendedSeconds += Math.max(0, (Date.now() - this.suspendedStartedAtMs) / 1000);
      this.suspendedStartedAtMs = undefined;
    }
    this.runningStartedAtMs = Date.now();
  }

  private markSuspended(): void {
    if (this.runningStartedAtMs !== undefined) {
      this.accumulatedRunningSeconds += Math.max(0, (Date.now() - this.runningStartedAtMs) / 1000);
      this.runningStartedAtMs = undefined;
    }
    this.suspendedStartedAtMs ??= Date.now();
  }

  private markStopped(): void {
    if (this.runningStartedAtMs !== undefined) {
      this.accumulatedRunningSeconds += Math.max(0, (Date.now() - this.runningStartedAtMs) / 1000);
      this.runningStartedAtMs = undefined;
    }
    if (this.suspendedStartedAtMs !== undefined) {
      this.accumulatedSuspendedSeconds += Math.max(0, (Date.now() - this.suspendedStartedAtMs) / 1000);
      this.suspendedStartedAtMs = undefined;
    }
  }

  private lifecycleCost(): AwsMicrovmLifecycleCost {
    const now = Date.now();
    const runningSeconds =
      this.accumulatedRunningSeconds +
      (this.runningStartedAtMs === undefined ? 0 : Math.max(0, (now - this.runningStartedAtMs) / 1000));
    const suspendedSeconds =
      this.accumulatedSuspendedSeconds +
      (this.suspendedStartedAtMs === undefined ? 0 : Math.max(0, (now - this.suspendedStartedAtMs) / 1000));
    const billableVcpu = awsMicrovmBillableVcpu(this.config.memoryGb);
    const runningComputeUsd =
      runningSeconds * (billableVcpu * this.config.pricing.vcpuSecondUsd + this.config.memoryGb * this.config.pricing.gbSecondUsd);
    const launchSnapshotReadGb = this.config.memoryGb;
    const suspendSnapshotWriteGb = this.suspendCount * this.config.memoryGb;
    const resumeSnapshotReadGb = this.resumeCount * this.config.memoryGb;
    const snapshotWriteUsd = suspendSnapshotWriteGb * this.config.pricing.snapshotWriteGbUsd;
    const snapshotReadUsd = (launchSnapshotReadGb + resumeSnapshotReadGb) * this.config.pricing.snapshotReadGbUsd;
    const suspendedStorageUsd =
      this.config.memoryGb * (suspendedSeconds / (30 * 24 * 3600)) * this.config.pricing.snapshotStorageGbMonthUsd;
    return {
      billable_vcpu: billableVcpu,
      running_seconds: runningSeconds,
      suspended_seconds: suspendedSeconds,
      suspend_count: this.suspendCount,
      resume_count: this.resumeCount,
      launch_snapshot_read_gb: launchSnapshotReadGb,
      suspend_snapshot_write_gb: suspendSnapshotWriteGb,
      resume_snapshot_read_gb: resumeSnapshotReadGb,
      running_compute_usd: runningComputeUsd,
      snapshot_write_usd: snapshotWriteUsd,
      snapshot_read_usd: snapshotReadUsd,
      suspended_storage_usd: suspendedStorageUsd,
      total_usd: runningComputeUsd + snapshotWriteUsd + snapshotReadUsd + suspendedStorageUsd
    };
  }
}

export function awsMicrovmConfigFromEnv(options: AwsMicrovmSandboxEnvOptions): AwsMicrovmSandboxConfig {
  const region = process.env.AWS_REGION ?? process.env.AWS_DEFAULT_REGION ?? "us-east-1";
  const imageIdentifier = options.imageIdentifier ?? process.env.AWS_MICROVM_IMAGE_ID ?? process.env.AWS_MICROVM_IMAGE_ARN;
  if (!imageIdentifier) {
    throw new Error("AWS MicroVM provider requires AWS_MICROVM_IMAGE_ID or --aws-microvm-image-id");
  }
  const maximumDurationInSeconds = envInt(
    "AWS_MICROVM_MAX_DURATION_SECONDS",
    Math.max(180, Math.min(3600, options.timeoutSeconds + 180))
  );
  const port = envInt("AWS_MICROVM_PORT", 8080);
  const sessionMode = envSessionMode("AWS_MICROVM_SESSION_MODE", "terminate");
  const idlePolicy =
    sessionMode === "terminate"
      ? {
          maxIdleDurationSeconds: envInt("AWS_MICROVM_MAX_IDLE_DURATION_SECONDS", 120),
          suspendedDurationSeconds: envInt("AWS_MICROVM_SUSPENDED_DURATION_SECONDS", 0),
          autoResumeEnabled: envBool("AWS_MICROVM_AUTO_RESUME", false)
        }
      : {
          maxIdleDurationSeconds: envInt("AWS_MICROVM_MAX_IDLE_DURATION_SECONDS", 300),
          suspendedDurationSeconds: envInt("AWS_MICROVM_SUSPENDED_DURATION_SECONDS", 25_200),
          autoResumeEnabled: envBool("AWS_MICROVM_AUTO_RESUME", sessionMode === "auto-suspend")
        };
  return {
    region,
    imageIdentifier,
    imageVersion: options.imageVersion ?? process.env.AWS_MICROVM_IMAGE_VERSION,
    executionRoleArn: options.executionRoleArn ?? process.env.AWS_MICROVM_EXECUTION_ROLE_ARN,
    cpu: options.cpu,
    memoryGb: options.memoryGb,
    port,
    authTokenExpirationMinutes: envInt("AWS_MICROVM_AUTH_TOKEN_MINUTES", 30),
    maximumDurationInSeconds,
    startTimeoutSeconds: envInt("AWS_MICROVM_START_TIMEOUT_SECONDS", 600),
    quotaRetryDelaySeconds: envInt("AWS_MICROVM_QUOTA_RETRY_SECONDS", 15),
    firstRequestTimeoutSeconds: envInt("AWS_MICROVM_FIRST_REQUEST_TIMEOUT_SECONDS", sessionMode === "terminate" ? 15 : 60),
    resumeTimeoutSeconds: envInt("AWS_MICROVM_RESUME_TIMEOUT_SECONDS", 120),
    resumeCheckAfterIdleSeconds: envInt("AWS_MICROVM_RESUME_CHECK_AFTER_IDLE_SECONDS", 60),
    sessionMode,
    idlePolicy,
    ingressNetworkConnectors: envList("AWS_MICROVM_INGRESS_CONNECTORS", [
      `arn:aws:lambda:${region}:aws:network-connector:aws-network-connector:ALL_INGRESS`
    ]),
    egressNetworkConnectors: envList("AWS_MICROVM_EGRESS_CONNECTORS", [
      `arn:aws:lambda:${region}:aws:network-connector:aws-network-connector:INTERNET_EGRESS`
    ]),
    logGroup: process.env.AWS_MICROVM_LOG_GROUP,
    clientTokenPrefix: process.env.AWS_MICROVM_CLIENT_TOKEN_PREFIX ?? "code-sandbox-bench",
    pricing: {
      vcpuSecondUsd: envNumber("AWS_MICROVM_ESTIMATE_VCPU_SECOND_USD", envNumber("AWS_MICROVM_ESTIMATE_VCPU_HOUR_USD", 0) / 3600 || 0.0000276944),
      gbSecondUsd: envNumber("AWS_MICROVM_ESTIMATE_GB_SECOND_USD", envNumber("AWS_MICROVM_ESTIMATE_GB_HOUR_USD", 0) / 3600 || 0.0000036667),
      snapshotWriteGbUsd: envNumber("AWS_MICROVM_ESTIMATE_SNAPSHOT_WRITE_GB_USD", 0.0038),
      snapshotReadGbUsd: envNumber("AWS_MICROVM_ESTIMATE_SNAPSHOT_READ_GB_USD", 0.00155),
      snapshotStorageGbMonthUsd: envNumber("AWS_MICROVM_ESTIMATE_SNAPSHOT_STORAGE_GB_MONTH_USD", 0.08)
    }
  };
}

function awsMicrovmBillableVcpu(memoryGb: number): number {
  return memoryGb / 2;
}

function envInt(name: string, fallback: number): number {
  const value = process.env[name];
  return value ? Number.parseInt(value, 10) : fallback;
}

function envBool(name: string, fallback: boolean): boolean {
  const value = process.env[name];
  if (value === undefined) {
    return fallback;
  }
  return value === "1" || value.toLowerCase() === "true";
}

function envNumber(name: string, fallback: number): number {
  const value = process.env[name];
  return value === undefined ? fallback : Number.parseFloat(value);
}

function envSessionMode(name: string, fallback: AwsMicrovmSessionMode): AwsMicrovmSessionMode {
  const value = process.env[name] ?? fallback;
  if (value === "terminate" || value === "auto-suspend" || value === "explicit-suspend") {
    return value;
  }
  throw new Error(`${name} must be one of terminate, auto-suspend, explicit-suspend`);
}

function envList(name: string, fallback: string[]): string[] {
  const value = process.env[name];
  if (!value) {
    return fallback;
  }
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function required(value: string | undefined, message: string): string {
  if (!value) {
    throw new Error(message);
  }
  return value;
}

function isResourceNotFound(error: unknown): boolean {
  return error instanceof Error && error.name === "ResourceNotFoundException";
}

function isQuotaExceeded(error: unknown): boolean {
  return error instanceof Error && error.name === "ServiceQuotaExceededException";
}

function isConflict(error: unknown): boolean {
  return error instanceof Error && error.name === "ConflictException";
}

function isRunning(state: AwsMicrovmKnownState): boolean {
  return state === "RUNNING";
}

function isSuspended(state: AwsMicrovmKnownState): boolean {
  return state === "SUSPENDED";
}

function isSuspendedOrTerminated(state: AwsMicrovmKnownState): boolean {
  return state === "SUSPENDED" || state === "TERMINATED";
}

function normalizeMicrovmState(state: string | undefined): AwsMicrovmKnownState {
  if (
    state === "PENDING" ||
    state === "RUNNING" ||
    state === "SUSPENDING" ||
    state === "SUSPENDED" ||
    state === "TERMINATING" ||
    state === "TERMINATED"
  ) {
    return state;
  }
  return "UNKNOWN";
}

function formatError(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function isCommandUsage(value: unknown): CommandResult["usage"] | undefined {
  return typeof value === "object" && value !== null ? (value as CommandResult["usage"]) : undefined;
}

class AwsMicrovmHttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: string
  ) {
    super(`AWS MicroVM request failed with ${status}: ${body}`);
    this.name = "AwsMicrovmHttpError";
  }
}

function isRetryablePollError(error: unknown): boolean {
  if (error instanceof AwsMicrovmHttpError) {
    return error.status === 408 || error.status === 409 || error.status === 429 || error.status >= 500;
  }
  if (error instanceof Error) {
    return /AbortError|TimeoutError|ECONNRESET|ETIMEDOUT|fetch failed|network/i.test(`${error.name}: ${error.message}`);
  }
  return false;
}
