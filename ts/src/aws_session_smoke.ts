import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { AwsMicrovmSandbox, awsMicrovmConfigFromEnv, type AwsMicrovmSessionMode } from "./aws_microvm";

type SessionSmokeArgs = {
  mode: AwsMicrovmSessionMode;
  output?: string;
  imageIdentifier?: string;
  imageVersion?: string;
  executionRoleArn?: string;
  timeoutSeconds: number;
  idleSeconds: number;
  cpu: number;
  memoryGb: number;
  keepSession: boolean;
};

function parseArgs(argv: string[]): SessionSmokeArgs {
  const values = new Map<string, string>();
  const flags = new Set<string>();
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === "--keep-session") {
      flags.add(item);
      continue;
    }
    values.set(item, argv[index + 1]);
    index += 1;
  }
  return {
    mode: parseSessionMode(values.get("--mode") ?? process.env.AWS_MICROVM_SESSION_MODE ?? "explicit-suspend"),
    output: values.get("--output"),
    imageIdentifier: values.get("--aws-microvm-image-id") ?? process.env.AWS_MICROVM_IMAGE_ID,
    imageVersion: values.get("--aws-microvm-image-version") ?? process.env.AWS_MICROVM_IMAGE_VERSION,
    executionRoleArn: values.get("--aws-microvm-execution-role-arn") ?? process.env.AWS_MICROVM_EXECUTION_ROLE_ARN,
    timeoutSeconds: Number.parseInt(values.get("--timeout-seconds") ?? "180", 10),
    idleSeconds: Number.parseInt(values.get("--idle-seconds") ?? "0", 10),
    cpu: Number.parseInt(values.get("--cpu") ?? "2", 10),
    memoryGb: Number.parseInt(values.get("--memory-gb") ?? "2", 10),
    keepSession: flags.has("--keep-session")
  };
}

async function main(): Promise<void> {
  const args = parseArgs(Bun.argv.slice(2));
  const previousMode = process.env.AWS_MICROVM_SESSION_MODE;
  process.env.AWS_MICROVM_SESSION_MODE = args.mode;
  const sandbox = new AwsMicrovmSandbox(
    awsMicrovmConfigFromEnv({
      imageIdentifier: args.imageIdentifier,
      imageVersion: args.imageVersion,
      executionRoleArn: args.executionRoleArn,
      timeoutSeconds: args.timeoutSeconds,
      cpu: args.cpu,
      memoryGb: args.memoryGb
    })
  );
  if (previousMode === undefined) {
    delete process.env.AWS_MICROVM_SESSION_MODE;
  } else {
    process.env.AWS_MICROVM_SESSION_MODE = previousMode;
  }

  let passed = false;
  let verifyOutput = "";
  let error: string | undefined;
  try {
    await sandbox.start();
    const first = await sandbox.run("mkdir -p /workspace && printf 'first\\n' > /workspace/session-smoke.txt", "/workspace", args.timeoutSeconds);
    if (first.returnCode !== 0) {
      throw new Error(first.stderr || first.stdout);
    }
    if (args.mode === "explicit-suspend") {
      await sandbox.suspend("session-smoke");
      await sandbox.resume("session-smoke");
    } else if (args.idleSeconds > 0) {
      await sleep(args.idleSeconds * 1000);
    }
    const second = await sandbox.run(
      "cat /workspace/session-smoke.txt && printf 'second\\n' >> /workspace/session-smoke.txt && cat /workspace/session-smoke.txt",
      "/workspace",
      args.timeoutSeconds
    );
    verifyOutput = second.stdout;
    passed = second.returnCode === 0 && verifyOutput.includes("first") && verifyOutput.includes("second");
    if (!passed && second.stderr) {
      error = second.stderr;
    }
  } catch (caught) {
    error = caught instanceof Error ? `${caught.name}: ${caught.message}` : String(caught);
  } finally {
    if (args.keepSession) {
      await sandbox.suspend("session-smoke-keep").catch(() => undefined);
    } else {
      await sandbox.terminate("session-smoke-cleanup").catch(() => undefined);
    }
  }

  const summary = {
    passed,
    mode: args.mode,
    keep_session: args.keepSession,
    verify_stdout_tail: verifyOutput.slice(-2000),
    error,
    aws_microvm: sandbox.telemetry()
  };
  const output = `${JSON.stringify(summary, null, 2)}\n`;
  if (args.output) {
    mkdirSync(dirname(args.output), { recursive: true });
    writeFileSync(args.output, output);
  }
  console.log(output);
  if (!passed) {
    process.exitCode = 1;
  }
}

function parseSessionMode(value: string): AwsMicrovmSessionMode {
  if (value === "terminate" || value === "auto-suspend" || value === "explicit-suspend") {
    return value;
  }
  throw new Error(`Unsupported session smoke mode: ${value}`);
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

await main();
