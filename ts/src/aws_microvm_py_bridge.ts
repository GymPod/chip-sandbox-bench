import { createInterface } from "node:readline";
import { AwsMicrovm, type AwsMicrovmSandbox, type AwsMicrovmSessionMode } from "./aws_microvm";

type BridgeRequest = {
  id?: string | number;
  op?: "start" | "run" | "stop";
  timeoutSeconds?: number;
  cpu?: number;
  memoryGb?: number;
  imageIdentifier?: string;
  imageVersion?: string;
  executionRoleArn?: string;
  sessionMode?: AwsMicrovmSessionMode;
  command?: string;
  cwd?: string | null;
};

type BridgeResponse = {
  id?: string | number;
  ok: boolean;
  result?: unknown;
  metadata?: Record<string, unknown>;
  error?: string;
};

let client: AwsMicrovm | undefined;
let sandbox: AwsMicrovmSandbox | undefined;

const lines = createInterface({
  input: process.stdin,
  crlfDelay: Infinity
});

try {
  for await (const line of lines) {
    if (!line.trim()) {
      continue;
    }
    const response = await handleLine(line);
    process.stdout.write(`${JSON.stringify(response)}\n`);
  }
} finally {
  await cleanup().catch((error) => {
    console.error(`AWS MicroVM Python bridge cleanup failed: ${formatError(error)}`);
  });
}

async function handleLine(line: string): Promise<BridgeResponse> {
  let request: BridgeRequest;
  try {
    request = JSON.parse(line) as BridgeRequest;
  } catch (error) {
    return { ok: false, error: `Invalid JSON request: ${formatError(error)}` };
  }

  try {
    if (request.op === "start") {
      return await startSandbox(request);
    }
    if (request.op === "run") {
      return await runCommand(request);
    }
    if (request.op === "stop") {
      return await stopSandbox(request);
    }
    return { id: request.id, ok: false, error: `Unsupported bridge operation: ${String(request.op)}` };
  } catch (error) {
    return { id: request.id, ok: false, error: formatError(error) };
  }
}

async function startSandbox(request: BridgeRequest): Promise<BridgeResponse> {
  if (sandbox) {
    throw new Error("AWS MicroVM sandbox already started");
  }
  const timeoutSeconds = request.timeoutSeconds ?? 180;
  client = new AwsMicrovm({
    imageIdentifier: request.imageIdentifier,
    imageVersion: request.imageVersion,
    executionRoleArn: request.executionRoleArn,
    timeoutSeconds,
    cpu: request.cpu ?? 2,
    memoryGb: request.memoryGb ?? 2
  });
  sandbox = await client.create(
    {
      name: `python-aws-microvm-${Date.now().toString(36)}`,
      labels: { app: "code-sandbox-bench", runner: "python" },
      image: request.imageIdentifier,
      imageVersion: request.imageVersion,
      executionRoleArn: request.executionRoleArn,
      resources: {
        cpu: request.cpu ?? 2,
        memory: request.memoryGb ?? 2
      },
      autoStopInterval: 0,
      autoDeleteInterval: 0,
      sessionMode: request.sessionMode
    },
    { timeout: timeoutSeconds }
  );
  return { id: request.id, ok: true, metadata: metadata() };
}

async function runCommand(request: BridgeRequest): Promise<BridgeResponse> {
  if (!sandbox) {
    throw new Error("AWS MicroVM sandbox not started");
  }
  if (request.command === undefined) {
    throw new Error("AWS MicroVM bridge run requires command");
  }
  const response = await sandbox.process.executeCommand(
    request.command,
    request.cwd ?? undefined,
    undefined,
    request.timeoutSeconds ?? 180
  );
  return {
    id: request.id,
    ok: true,
    result: {
      stdout: response.artifacts?.stdout ?? response.result ?? "",
      stderr: response.artifacts?.stderr ?? "",
      returnCode: response.exitCode ?? 0,
      usage: response.usage
    },
    metadata: metadata()
  };
}

async function stopSandbox(request: BridgeRequest): Promise<BridgeResponse> {
  const stoppedMetadata = await cleanup();
  return { id: request.id, ok: true, metadata: stoppedMetadata };
}

async function cleanup(): Promise<Record<string, unknown>> {
  const activeClient = client;
  const activeSandbox = sandbox;
  sandbox = undefined;
  client = undefined;
  let stoppedMetadata: Record<string, unknown> = {};
  if (activeClient && activeSandbox) {
    await activeClient.delete(activeSandbox);
    stoppedMetadata = { aws_microvm: activeSandbox.telemetry() };
  }
  if (activeClient) {
    await activeClient[Symbol.asyncDispose]();
  }
  return stoppedMetadata;
}

function metadata(): Record<string, unknown> {
  return sandbox ? { aws_microvm: sandbox.telemetry() } : {};
}

function formatError(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}
