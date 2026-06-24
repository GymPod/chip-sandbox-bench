import { expect, test } from "@playwright/test";
import { Daytona, type Sandbox as DaytonaSandbox } from "@daytona/sdk";
import { AwsMicrovm, type AwsMicrovmSandbox } from "../src/aws_microvm";

const runLive = process.env.SDK_CONTRACT_LIVE === "1" || process.env.SDK_CONTRACT_LIVE === "true";

test.describe("live SDK process contract", () => {
  test.skip(!runLive, "Set SDK_CONTRACT_LIVE=1 to run live AWS MicroVM and Daytona contract tests.");

  test("AWS MicroVM executes the shared process command contract", async () => {
    test.skip(!process.env.AWS_MICROVM_IMAGE_ID && !process.env.AWS_MICROVM_IMAGE_ARN, "AWS_MICROVM_IMAGE_ID is required.");
    const client = new AwsMicrovm({
      imageIdentifier: process.env.AWS_MICROVM_IMAGE_ID ?? process.env.AWS_MICROVM_IMAGE_ARN,
      imageVersion: process.env.AWS_MICROVM_IMAGE_VERSION,
      executionRoleArn: process.env.AWS_MICROVM_EXECUTION_ROLE_ARN,
      timeoutSeconds: Number.parseInt(process.env.SDK_CONTRACT_TIMEOUT_SECONDS ?? "180", 10),
      cpu: Number.parseInt(process.env.SDK_CONTRACT_CPU ?? "2", 10),
      memoryGb: Number.parseInt(process.env.SDK_CONTRACT_MEMORY_GB ?? "1", 10)
    });
    let sandbox: AwsMicrovmSandbox | undefined;
    try {
      sandbox = await client.create(
        {
          name: `sdk-contract-aws-${Date.now().toString(36)}`,
          resources: {
            cpu: Number.parseInt(process.env.SDK_CONTRACT_CPU ?? "2", 10),
            memory: Number.parseInt(process.env.SDK_CONTRACT_MEMORY_GB ?? "1", 10)
          }
        },
        { timeout: Number.parseInt(process.env.SDK_CONTRACT_TIMEOUT_SECONDS ?? "180", 10) }
      );
      const result = await sandbox.process.executeCommand("printf aws-live-ok", "/workspace", undefined, 60);
      expect(result.exitCode).toBe(0);
      expect(result.artifacts?.stdout ?? result.result).toContain("aws-live-ok");
    } finally {
      if (sandbox) {
        await client.delete(sandbox).catch(() => undefined);
      }
      await client[Symbol.asyncDispose]();
    }
  });

  test("Daytona executes the shared process command contract", async () => {
    test.skip(!process.env.DAYTONA_API_KEY, "DAYTONA_API_KEY is required.");
    const client = new Daytona({
      apiKey: process.env.DAYTONA_API_KEY,
      apiUrl: process.env.DAYTONA_API_URL,
      target: process.env.DAYTONA_TARGET || undefined
    });
    let sandbox: DaytonaSandbox | undefined;
    try {
      sandbox = await client.create(
        {
          name: `sdk-contract-daytona-${Date.now().toString(36)}`,
          image: process.env.DAYTONA_TEST_IMAGE ?? "python:3.13",
          resources: {
            cpu: Number.parseInt(process.env.SDK_CONTRACT_CPU ?? "2", 10),
            memory: Number.parseInt(process.env.SDK_CONTRACT_MEMORY_GB ?? "1", 10),
            disk: Number.parseInt(process.env.SDK_CONTRACT_DISK_GB ?? "10", 10)
          },
          autoStopInterval: 0,
          autoDeleteInterval: 0
        },
        { timeout: Number.parseInt(process.env.SDK_CONTRACT_TIMEOUT_SECONDS ?? "180", 10) }
      );
      const result = await sandbox.process.executeCommand("printf daytona-live-ok", "/workspace", undefined, 60);
      expect(result.exitCode ?? 0).toBe(0);
      expect(result.artifacts?.stdout ?? result.result ?? "").toContain("daytona-live-ok");
    } finally {
      if (sandbox) {
        await client.delete(sandbox).catch(() => undefined);
      }
      await client[Symbol.asyncDispose]();
    }
  });
});
