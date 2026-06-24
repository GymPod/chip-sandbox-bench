import { expect, test } from "@playwright/test";
import { AwsMicrovm, type AwsMicrovmControlPlane, type AwsMicrovmExecuteCommandResponse } from "../src/aws_microvm";

type RecordedControlPlaneCommand = {
  name: string;
  input: Record<string, unknown>;
};

type RecordedRunnerRequest = {
  method: string;
  path: string;
  headers: Record<string, string>;
  body?: Record<string, unknown>;
};

class FakeMicrovmControlPlane implements AwsMicrovmControlPlane {
  readonly commands: RecordedControlPlaneCommand[] = [];
  private state = "RUNNING";

  async send(command: unknown): Promise<unknown> {
    const name = command instanceof Object ? command.constructor.name : "UnknownCommand";
    const input = ((command as { input?: Record<string, unknown> }).input ?? {}) as Record<string, unknown>;
    this.commands.push({ name, input });
    if (name === "RunMicrovmCommand") {
      this.state = "RUNNING";
      return { microvmId: "microvm-test-1", endpoint: "https://microvm.test" };
    }
    if (name === "GetMicrovmCommand") {
      return { state: this.state, endpoint: "https://microvm.test" };
    }
    if (name === "CreateMicrovmAuthTokenCommand") {
      return { authToken: { "X-aws-proxy-auth": "proxy-token" } };
    }
    if (name === "SuspendMicrovmCommand") {
      this.state = "SUSPENDED";
      return {};
    }
    if (name === "ResumeMicrovmCommand") {
      this.state = "RUNNING";
      return {};
    }
    if (name === "TerminateMicrovmCommand") {
      this.state = "TERMINATED";
      return {};
    }
    throw new Error(`Unexpected command: ${name}`);
  }

  commandNames(): string[] {
    return this.commands.map((command) => command.name);
  }

  lastInput(name: string): Record<string, unknown> {
    const command = [...this.commands].reverse().find((item) => item.name === name);
    if (!command) {
      throw new Error(`Missing command: ${name}`);
    }
    return command.input;
  }
}

function createRunnerFetch(stdout: string) {
  const requests: RecordedRunnerRequest[] = [];
  const fetchImpl = Object.assign(async (input: URL | RequestInfo, init?: RequestInit | BunFetchRequestInit) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    const headers = Object.fromEntries(new Headers(init?.headers).entries());
    const body =
      typeof init?.body === "string" && init.body.length > 0
        ? (JSON.parse(init.body) as Record<string, unknown>)
        : undefined;
    requests.push({ method: init?.method ?? "GET", path: url.pathname, headers, body });
    if (url.pathname === "/health") {
      return jsonResponse({ ok: true });
    }
    if (url.pathname === "/commands" && init?.method === "POST") {
      return jsonResponse({ jobId: "job-test-1" });
    }
    if (url.pathname === "/commands/job-test-1") {
      return jsonResponse({
        status: "completed",
        stdout,
        stderr: "",
        returnCode: 0,
        usage: {
          wall_seconds: 0.01,
          stdout_bytes: Buffer.byteLength(stdout),
          stderr_bytes: 0
        }
      });
    }
    return jsonResponse({ error: `unexpected path: ${url.pathname}` }, 404);
  }, { preconnect: fetch.preconnect }) as typeof fetch;
  return { fetchImpl, requests };
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" }
  });
}

async function exerciseCommandContract(
  label: string,
  sandbox: { process: { executeCommand(command: string, cwd?: string, env?: Record<string, string>, timeoutSeconds?: number): Promise<AwsMicrovmExecuteCommandResponse> } }
): Promise<void> {
  const result = await sandbox.process.executeCommand(`printf ${label}`, "/workspace", { CONTRACT_LABEL: label }, 10);
  expect(result.exitCode).toBe(0);
  expect(result.artifacts?.stdout ?? result.result).toContain(label);
  expect(result.artifacts?.stderr ?? "").toBe("");
}

test("AWS MicroVM SDK maps Daytona-shaped create and execute calls onto AWS platform details", async () => {
  const controlPlane = new FakeMicrovmControlPlane();
  const runner = createRunnerFetch("aws-contract-ok\n");
  const client = new AwsMicrovm({
    region: "us-test-1",
    controlPlane,
    fetch: runner.fetchImpl,
    sleep: async () => undefined,
    env: {
      AWS_MICROVM_AUTH_TOKEN_MINUTES: "5",
      AWS_MICROVM_FIRST_REQUEST_TIMEOUT_SECONDS: "1"
    }
  });

  const sandbox = await client.create(
    {
      name: "aws sdk contract",
      image: "image-arn",
      imageVersion: "1.2",
      executionRoleArn: "execution-role-arn",
      resources: {
        cpu: 4,
        memory: 2
      },
      autoStopInterval: 0,
      autoDeleteInterval: 0
    },
    { timeout: 90 }
  );

  const runInput = controlPlane.lastInput("RunMicrovmCommand");
  expect(runInput.imageIdentifier).toBe("image-arn");
  expect(runInput.imageVersion).toBe("1.2");
  expect(runInput.executionRoleArn).toBe("execution-role-arn");
  expect(runInput.maximumDurationInSeconds).toBe(270);
  expect(runInput.clientToken).toEqual(expect.stringMatching(/^aws-sdk-contract-/));
  expect(runInput.ingressNetworkConnectors).toEqual([
    "arn:aws:lambda:us-test-1:aws:network-connector:aws-network-connector:ALL_INGRESS"
  ]);
  expect(runInput.egressNetworkConnectors).toEqual([
    "arn:aws:lambda:us-test-1:aws:network-connector:aws-network-connector:INTERNET_EGRESS"
  ]);

  const result = await sandbox.process.executeCommand(
    "printf \"$GREETING\"",
    "/workspace",
    { GREETING: "aws contract", OMITTED: undefined },
    12
  );
  expect(result.exitCode).toBe(0);
  expect(result.artifacts?.stdout).toBe("aws-contract-ok\n");
  expect(result.usage?.stdout_bytes).toBe(Buffer.byteLength("aws-contract-ok\n"));

  const commandRequest = runner.requests.find((request) => request.method === "POST" && request.path === "/commands");
  expect(commandRequest?.headers["x-aws-proxy-auth"]).toBe("proxy-token");
  expect(commandRequest?.headers["x-aws-proxy-port"]).toBe("8080");
  expect(commandRequest?.body).toMatchObject({
    cwd: "/workspace",
    timeoutSeconds: 12
  });
  expect(String(commandRequest?.body?.command)).toContain("GREETING='aws contract'");
  expect(String(commandRequest?.body?.command)).not.toContain("OMITTED");

  expect(sandbox.telemetry()).toMatchObject({
    session_mode: "terminate",
    microvm_id: "microvm-test-1",
    image_identifier: "image-arn",
    command_count: 1,
    last_known_state: "RUNNING"
  });

  await client.delete(sandbox);
  expect(controlPlane.commandNames()).toContain("TerminateMicrovmCommand");
  expect(sandbox.telemetry().last_known_state).toBe("TERMINATED");
});

test("AWS MicroVM explicit-suspend mode resumes before the next process command", async () => {
  const controlPlane = new FakeMicrovmControlPlane();
  const runner = createRunnerFetch("resumed\n");
  const client = new AwsMicrovm({
    region: "us-test-1",
    imageIdentifier: "image-arn",
    controlPlane,
    fetch: runner.fetchImpl,
    sleep: async () => undefined,
    env: {
      AWS_MICROVM_SESSION_MODE: "explicit-suspend",
      AWS_MICROVM_RESUME_TIMEOUT_SECONDS: "1"
    }
  });
  const sandbox = await client.create({}, { timeout: 30 });

  await sandbox.suspend("test");
  await sandbox.process.executeCommand("printf resumed", "/workspace", undefined, 10);

  expect(controlPlane.commandNames()).toContain("SuspendMicrovmCommand");
  expect(controlPlane.commandNames()).toContain("ResumeMicrovmCommand");
  expect(sandbox.telemetry()).toMatchObject({
    session_mode: "explicit-suspend",
    resume_attempts: 1,
    resume_count: 1,
    suspend_count: 1,
    command_count: 1,
    last_known_state: "RUNNING"
  });

  await sandbox.terminate("test-cleanup");
});

test("AWS MicroVM and Daytona expose the same process command response contract", async () => {
  const controlPlane = new FakeMicrovmControlPlane();
  const runner = createRunnerFetch("aws-contract-ok\n");
  const aws = new AwsMicrovm({
    region: "us-test-1",
    imageIdentifier: "image-arn",
    controlPlane,
    fetch: runner.fetchImpl,
    sleep: async () => undefined
  });
  const awsSandbox = await aws.create({}, { timeout: 30 });

  const daytonaEquivalent = {
    process: {
      executeCommand: async (): Promise<AwsMicrovmExecuteCommandResponse> => ({
        artifacts: { stdout: "daytona-contract-ok\n", stderr: "" },
        result: "daytona-contract-ok\n",
        exitCode: 0,
        usage: { wall_seconds: 0.01, stdout_bytes: Buffer.byteLength("daytona-contract-ok\n"), stderr_bytes: 0 }
      })
    }
  };

  await exerciseCommandContract("aws-contract-ok", awsSandbox);
  await exerciseCommandContract("daytona-contract-ok", daytonaEquivalent);
  await aws.delete(awsSandbox);
});
