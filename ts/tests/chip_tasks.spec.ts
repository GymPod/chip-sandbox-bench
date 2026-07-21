import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { loadTasks } from "../src/dataset";

const repoRoot = resolve(process.cwd(), "..");
const datasetPath = resolve(repoRoot, "data/chip_design_smoke10.jsonl");

test("chip smoke dataset is balanced and retains provenance metadata", () => {
  const tasks = loadTasks(datasetPath, "all");
  const counts = new Map<string, number>();

  expect(tasks).toHaveLength(10);
  for (const task of tasks) {
    expect(task.env_type).toBe("chip");
    expect(task.discipline).toBeTruthy();
    expect(task.benchmark).toBeTruthy();
    expect(task.tools?.length).toBeGreaterThan(0);
    expect(task.source?.repo).toMatch(/^benchmarks\//);
    expect(task.source?.commit).toMatch(/^[0-9a-f]{40}$/);
    expect(task.archive_sha256).toMatch(/^[0-9a-f]{64}$/);
    counts.set(task.discipline!, (counts.get(task.discipline!) ?? 0) + 1);
  }

  expect(Object.fromEntries(counts)).toEqual({
    "Architecture & Microarchitecture": 2,
    "Architecture Modeling": 2,
    "RTL Design": 2,
    "Software Development": 2,
    "Verification (DV/FV)": 2
  });
});

test("chip tasks use the pinned toolchain prepare contract", () => {
  const script = [
    'import { prepareCommandFor, taskMetadata } from "./src/bench.ts";',
    'import { loadTasks } from "./src/dataset.ts";',
    'import { resolveTaskEnv } from "./src/task_env.ts";',
    `const task = loadTasks(${JSON.stringify(datasetPath)}, "0")[0];`,
    'const taskEnv = resolveTaskEnv(task, "unused:latest", "aws-microvm");',
    'console.log(JSON.stringify({ taskEnv, command: prepareCommandFor(taskEnv, "aws-microvm"), metadata: taskMetadata(task) }));'
  ].join("\n");
  const result = spawnSync("bun", ["-e", script], {
    cwd: process.cwd(),
    encoding: "utf8"
  });

  expect(result.status).toBe(0);
  const payload = JSON.parse(result.stdout);
  expect(payload.taskEnv).toMatchObject({
    envType: "chip",
    workdir: "/workspace",
    verifierCwd: "/workspace"
  });
  expect(payload.command).toContain("Icarus Verilog version 12");
  expect(payload.command).toContain("Yosys 0\\.59+0");
  expect(payload.command).toContain("pkg-config --modversion systemc");
  expect(payload.command).not.toContain("pip install");
  expect(payload.metadata).toMatchObject({
    discipline: "Architecture & Microarchitecture",
    benchmark: "ArchGym",
    tools: ["python3", "pytest"]
  });
});

test("Python dataset reader retains chip metadata", () => {
  const script = [
    "import json",
    "from pathlib import Path",
    "from code_sandbox_bench.dataset import select_tasks",
    `task = select_tasks(Path(${JSON.stringify(datasetPath)}), "0")[0]`,
    "print(json.dumps({",
    '  "discipline": task.discipline,',
    '  "benchmark": task.benchmark,',
    '  "tools": task.tools,',
    '  "source": task.source,',
    '  "archive_sha256": task.archive_sha256,',
    "}))"
  ].join("\n");
  const result = spawnSync("uv", ["run", "--project", resolve(repoRoot, "py"), "python", "-c", script], {
    cwd: repoRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONPATH: resolve(repoRoot, "py")
    }
  });

  expect(result.stderr).toBe("");
  expect(result.status).toBe(0);
  expect(JSON.parse(result.stdout)).toMatchObject({
    discipline: "Architecture & Microarchitecture",
    benchmark: "ArchGym",
    tools: ["python3", "pytest"],
    source: { repo: "benchmarks/archgym" }
  });
});

test("MicroVM runner pins the chip toolchain sources and checksums", () => {
  const dockerfile = readFileSync(resolve(process.cwd(), "aws-microvm-runner/Dockerfile"), "utf8");

  expect(dockerfile).toContain("ARG IVERILOG_VERSION=12_0");
  expect(dockerfile).toContain("ARG YOSYS_VERSION=0.59.1");
  expect(dockerfile).toContain("ARG SYSTEMC_VERSION=3.0.2");
  expect(dockerfile).toContain("/usr/local/lib/pkgconfig/systemc.pc");
  expect(dockerfile.match(/_SHA256=/g)).toHaveLength(3);
  expect(dockerfile).toContain("sha256sum -c");
});
