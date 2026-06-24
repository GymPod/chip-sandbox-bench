import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

test("Python AWS MicroVM provider routes through the persistent TypeScript bridge", async () => {
  const repoRoot = resolve(process.cwd(), "..");
  const providers = await readFile(resolve(repoRoot, "py/code_sandbox_bench/providers.py"), "utf8");
  const bench = await readFile(resolve(repoRoot, "py/code_sandbox_bench/bench.py"), "utf8");
  const bridge = await readFile(resolve(process.cwd(), "src/aws_microvm_py_bridge.ts"), "utf8");

  expect(providers).toContain("class AwsMicrovmProvider");
  expect(providers).toContain("aws_microvm_py_bridge.ts");
  expect(providers).toContain('name == "aws-microvm"');
  expect(bench).toContain('"aws-microvm"');
  expect(bridge).toContain("let sandbox: AwsMicrovmSandbox | undefined");
  expect(bridge).toContain("client.create");
  expect(bridge).toContain("sandbox.process.executeCommand");
  expect(bridge).toContain("activeClient.delete(activeSandbox)");
});

test("AWS MicroVM Python bridge handles stop without live AWS configuration", async () => {
  const bridgePath = resolve(process.cwd(), "src/aws_microvm_py_bridge.ts");
  const child = spawn("bun", [bridgePath], {
    cwd: process.cwd(),
    stdio: ["pipe", "pipe", "pipe"]
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk;
  });
  child.stdin.write(`${JSON.stringify({ id: 1, op: "stop" })}\n`);
  child.stdin.end();

  const code = await new Promise<number | null>((resolveExit, reject) => {
    const timeout = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("Timed out waiting for AWS MicroVM Python bridge"));
    }, 5000);
    child.on("error", reject);
    child.on("exit", (exitCode) => {
      clearTimeout(timeout);
      resolveExit(exitCode);
    });
  });

  expect(stderr).toBe("");
  expect(code).toBe(0);
  expect(JSON.parse(stdout.trim())).toMatchObject({ id: 1, ok: true });
});
