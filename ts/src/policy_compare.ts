import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { estimateCost } from "./cost_model";
import { loadTasks } from "./dataset";
import { loadResourcePolicyConfig, resolveResourceSpec, type ResourcePolicyConfig, type ResourceSpec } from "./resource_policy";
import { resolveTaskEnv } from "./task_env";
import type { BenchTask, ProviderName, ResourcePolicyName, RunKind, RunMode } from "./types";

type Args = {
  results: string[];
  resultsDir?: string;
  dataset: string;
  baselineConfig: string;
  candidateConfig: string;
  output?: string;
  format: "json" | "markdown";
  resourcePolicy: ResourcePolicyName;
  taskIndex: string;
  taskLimit?: number;
  cpu: number;
  memoryGb?: number;
  diskGb: number;
  timeoutSeconds: number;
  runtime?: string;
};

type BenchResultRow = {
  task_id: string;
  passed?: boolean;
  elapsed_seconds: number;
  estimated_cost_usd?: number;
};

type BenchFile = {
  provider: ProviderName;
  mode?: RunMode;
  kind?: RunKind;
  runtime?: string;
  task_count?: number;
  passed?: number;
  estimated_cost_usd?: number;
  results: BenchResultRow[];
};

type LoadedRun = {
  path: string;
  data: BenchFile;
};

type ComparedTask = {
  task_id: string;
  passed?: boolean;
  elapsed_seconds: number;
  baseline_cost_usd: number;
  candidate_cost_usd: number;
  reduction_pct?: number;
  baseline_resources: ResourceSpec;
  candidate_resources: ResourceSpec;
};

type RunComparison = {
  path: string;
  provider: ProviderName;
  mode?: RunMode;
  kind?: RunKind;
  task_count: number;
  passed?: number;
  input_estimated_cost_usd?: number;
  baseline_cost_usd: number;
  candidate_cost_usd: number;
  reduction_usd: number;
  reduction_pct?: number;
  resource_change_counts: Record<string, number>;
  tasks: ComparedTask[];
};

function parseArgs(argv: string[]): Args {
  const values = new Map<string, string>();
  for (let index = 0; index < argv.length; index += 2) {
    values.set(argv[index], argv[index + 1]);
  }
  const results = (values.get("--results") ?? values.get("--input") ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const baselineConfig = values.get("--baseline-config") ?? resolve(import.meta.dir, "../../data/resource_policy.json");
  const candidateConfig = values.get("--candidate-config");
  if (!candidateConfig) {
    throw new Error("--candidate-config is required");
  }
  return {
    results,
    resultsDir: values.get("--results-dir"),
    dataset: resolve(values.get("--dataset") ?? resolve(import.meta.dir, "../../data/terminalbench_2026_03_05_smoke16.jsonl")),
    baselineConfig: resolve(baselineConfig),
    candidateConfig: resolve(candidateConfig),
    output: values.get("--output"),
    format: parseFormat(values.get("--format") ?? "markdown"),
    resourcePolicy: parseResourcePolicy(values.get("--resource-policy") ?? "adaptive"),
    taskIndex: values.get("--task-index") ?? "all",
    taskLimit: parseOptionalInt(values.get("--task-limit")),
    cpu: Number.parseInt(values.get("--cpu") ?? "2", 10),
    memoryGb: parseOptionalInt(values.get("--memory-gb")),
    diskGb: Number.parseInt(values.get("--disk-gb") ?? "10", 10),
    timeoutSeconds: Number.parseInt(values.get("--timeout-seconds") ?? "180", 10),
    runtime: values.get("--runtime")
  };
}

function parseOptionalInt(value: string | undefined): number | undefined {
  return value === undefined ? undefined : Number.parseInt(value, 10);
}

function parseFormat(value: string): Args["format"] {
  if (value === "json" || value === "markdown") {
    return value;
  }
  throw new Error(`Unsupported format: ${value}`);
}

function parseResourcePolicy(value: string): ResourcePolicyName {
  if (value === "static" || value === "observe" || value === "adaptive") {
    return value;
  }
  throw new Error(`Unsupported resource policy: ${value}`);
}

function resultPaths(args: Args): string[] {
  const paths = [...args.results];
  if (args.resultsDir) {
    paths.push(
      ...readdirSync(args.resultsDir)
        .filter((file) => file.endsWith(".json"))
        .map((file) => join(args.resultsDir as string, file))
    );
  }
  if (paths.length === 0) {
    throw new Error("No result inputs. Use --results or --results-dir.");
  }
  return paths.map((path) => resolve(path));
}

async function loadRun(path: string): Promise<LoadedRun> {
  if (!existsSync(path)) {
    throw new Error(`Result input not found: ${path}`);
  }
  const data = (await Bun.file(path).json()) as BenchFile;
  if (!data.provider || !Array.isArray(data.results)) {
    throw new Error(`Unsupported benchmark result file: ${path}`);
  }
  return { path, data };
}

function taskMap(args: Args): Map<string, BenchTask> {
  return new Map(loadTasks(args.dataset, args.taskIndex, args.taskLimit).map((task) => [task.task_id, task]));
}

function compareRun(
  run: LoadedRun,
  tasks: Map<string, BenchTask>,
  baselineConfig: ResourcePolicyConfig,
  candidateConfig: ResourcePolicyConfig,
  args: Args
): RunComparison {
  const rows = run.data.results.filter((row) => Number.isFinite(row.elapsed_seconds));
  const comparedTasks = rows.map((row) => compareTask(run.data, row, tasks, baselineConfig, candidateConfig, args));
  const baselineCost = sum(comparedTasks.map((task) => task.baseline_cost_usd));
  const candidateCost = sum(comparedTasks.map((task) => task.candidate_cost_usd));
  return {
    path: run.path,
    provider: run.data.provider,
    ...(run.data.mode ? { mode: run.data.mode } : {}),
    ...(run.data.kind ? { kind: run.data.kind } : {}),
    task_count: comparedTasks.length,
    ...(typeof run.data.passed === "number" ? { passed: run.data.passed } : {}),
    ...(typeof run.data.estimated_cost_usd === "number" ? { input_estimated_cost_usd: run.data.estimated_cost_usd } : {}),
    baseline_cost_usd: baselineCost,
    candidate_cost_usd: candidateCost,
    reduction_usd: baselineCost - candidateCost,
    reduction_pct: pctReduction(baselineCost, candidateCost),
    resource_change_counts: resourceChangeCounts(comparedTasks),
    tasks: comparedTasks
  };
}

function compareTask(
  run: BenchFile,
  row: BenchResultRow,
  tasks: Map<string, BenchTask>,
  baselineConfig: ResourcePolicyConfig,
  candidateConfig: ResourcePolicyConfig,
  args: Args
): ComparedTask {
  const task = tasks.get(row.task_id);
  if (!task) {
    throw new Error(`Task ${row.task_id} from result file was not found in dataset ${args.dataset}`);
  }
  const runtime = run.runtime ?? args.runtime ?? defaultRuntime(run.provider);
  const taskEnv = resolveTaskEnv(task, runtime, run.provider);
  const base = baseResourceSpec(run.provider, args);
  const baseline = resolveResourceSpec(run.provider, args.resourcePolicy, base, taskEnv, baselineConfig).effective;
  const candidate = resolveResourceSpec(run.provider, args.resourcePolicy, base, taskEnv, candidateConfig).effective;
  const baselineCost = estimateCost(run.provider, row.elapsed_seconds, baseline.cpu, baseline.memoryGb, billableDiskGb(run.provider, baseline.diskGb));
  const candidateCost = estimateCost(run.provider, row.elapsed_seconds, candidate.cpu, candidate.memoryGb, billableDiskGb(run.provider, candidate.diskGb));
  return {
    task_id: row.task_id,
    ...(row.passed === undefined ? {} : { passed: row.passed }),
    elapsed_seconds: row.elapsed_seconds,
    baseline_cost_usd: baselineCost,
    candidate_cost_usd: candidateCost,
    reduction_pct: pctReduction(baselineCost, candidateCost),
    baseline_resources: baseline,
    candidate_resources: candidate
  };
}

function baseResourceSpec(provider: ProviderName, args: Args): ResourceSpec {
  return {
    cpu: args.cpu,
    memoryGb: args.memoryGb ?? (provider === "aws-microvm" ? 2 : 4),
    diskGb: args.diskGb,
    timeoutSeconds: args.timeoutSeconds
  };
}

function defaultRuntime(provider: ProviderName): string {
  return provider === "modal" || provider === "daytona" ? "python:3.13" : "python3.13";
}

function billableDiskGb(provider: ProviderName, diskGb: number): number {
  return provider === "daytona" ? Math.min(diskGb, 10) : diskGb;
}

function resourceChangeCounts(tasks: ComparedTask[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const task of tasks) {
    const key = `${formatSpec(task.baseline_resources)} -> ${formatSpec(task.candidate_resources)}`;
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

function pctReduction(baseline: number, candidate: number): number | undefined {
  return baseline > 0 ? ((baseline - candidate) / baseline) * 100 : undefined;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function markdownReport(
  runs: RunComparison[],
  args: Args,
  baselineConfig: ResourcePolicyConfig,
  candidateConfig: ResourcePolicyConfig
): string {
  const baseline = sum(runs.map((run) => run.baseline_cost_usd));
  const candidate = sum(runs.map((run) => run.candidate_cost_usd));
  return [
    "# Resource Policy Cost Comparison",
    "",
    `Generated: ${new Date().toISOString()}`,
    "",
    `Dataset: \`${displayPath(args.dataset)}\``,
    `Baseline config: \`${displayPath(args.baselineConfig)}\``,
    `Candidate config: \`${displayPath(args.candidateConfig)}\``,
    `Resource policy: \`${args.resourcePolicy}\``,
    "",
    "This projection holds observed task elapsed seconds constant and replays each task through the same provider cost model used by `bench.ts`.",
    "",
    "## Summary",
    "",
    "scope | runs | tasks | baseline cost | candidate cost | reduction",
    "--- | ---: | ---: | ---: | ---: | ---:",
    ["total", String(runs.length), String(sum(runs.map((run) => run.task_count))), fmtMoney(baseline), fmtMoney(candidate), fmtPct(pctReduction(baseline, candidate))].join(
      " | "
    ),
    "",
    "## Runs",
    "",
    "provider | mode | tasks | passed | input cost | baseline cost | candidate cost | reduction",
    "--- | --- | ---: | ---: | ---: | ---: | ---: | ---:",
    ...runs.map((run) =>
      [
        run.provider,
        run.mode ?? "-",
        String(run.task_count),
        run.passed === undefined ? "-" : String(run.passed),
        fmtMoney(run.input_estimated_cost_usd),
        fmtMoney(run.baseline_cost_usd),
        fmtMoney(run.candidate_cost_usd),
        fmtPct(run.reduction_pct)
      ].join(" | ")
    ),
    "",
    "## Resource Changes",
    "",
    ...runs.flatMap((run) => [
      `### ${run.provider}${run.mode ? ` ${run.mode}` : ""}`,
      "",
      "change | tasks",
      "--- | ---:",
      ...Object.entries(run.resource_change_counts).map(([change, count]) => `\`${change}\` | ${count}`),
      ""
    ]),
    "## Config Snapshot",
    "",
    `Baseline provider defaults: \`${JSON.stringify(baselineConfig.provider_defaults ?? {})}\``,
    "",
    `Candidate provider defaults: \`${JSON.stringify(candidateConfig.provider_defaults ?? {})}\``,
    ""
  ].join("\n");
}

function fmtMoney(value: number | undefined): string {
  return value === undefined || Number.isNaN(value) ? "-" : `$${value.toFixed(4)}`;
}

function fmtPct(value: number | undefined): string {
  return value === undefined || Number.isNaN(value) ? "-" : `${value.toFixed(1)}%`;
}

function formatSpec(spec: ResourceSpec): string {
  return `${spec.cpu} CPU / ${spec.memoryGb} GB / ${spec.diskGb} GB / ${spec.timeoutSeconds}s`;
}

function displayPath(path: string): string {
  const rel = relative(process.cwd(), path);
  return rel.startsWith("..") ? path : rel;
}

function writeOutput(path: string | undefined, content: string): void {
  if (!path) {
    console.log(content);
    return;
  }
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content);
  console.log(`wrote ${path}`);
}

async function main(): Promise<void> {
  const args = parseArgs(Bun.argv.slice(2));
  const [runs, baselineConfig, candidateConfig] = await Promise.all([
    Promise.all(resultPaths(args).map(loadRun)),
    Promise.resolve(loadResourcePolicyConfig(args.baselineConfig)),
    Promise.resolve(loadResourcePolicyConfig(args.candidateConfig))
  ]);
  const tasks = taskMap(args);
  const comparisons = runs
    .map((run) => compareRun(run, tasks, baselineConfig, candidateConfig, args))
    .sort((left, right) => left.provider.localeCompare(right.provider) || (left.mode ?? "").localeCompare(right.mode ?? ""));
  const payload = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    dataset: args.dataset,
    baseline_config: args.baselineConfig,
    candidate_config: args.candidateConfig,
    resource_policy: args.resourcePolicy,
    total_baseline_cost_usd: sum(comparisons.map((run) => run.baseline_cost_usd)),
    total_candidate_cost_usd: sum(comparisons.map((run) => run.candidate_cost_usd)),
    total_reduction_pct: pctReduction(
      sum(comparisons.map((run) => run.baseline_cost_usd)),
      sum(comparisons.map((run) => run.candidate_cost_usd))
    ),
    runs: comparisons
  };
  const content =
    args.format === "json"
      ? `${JSON.stringify(payload, null, 2)}\n`
      : markdownReport(comparisons, args, baselineConfig, candidateConfig);
  writeOutput(args.output, content);
}

if (import.meta.main) {
  await main();
}
