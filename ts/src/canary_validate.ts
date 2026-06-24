import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import type { ProviderName, RunKind, RunMode } from "./types";

type Args = {
  baselineResults: string[];
  candidateResults: string[];
  baselineResultsDir?: string;
  candidateResultsDir?: string;
  output?: string;
  format: "json" | "markdown";
  minReductionPct: number;
  maxPassDrop: number;
  maxWallRatio: number;
};

type BenchResultRow = {
  task_id: string;
  passed?: boolean;
  elapsed_seconds?: number;
  estimated_cost_usd?: number;
  resource_observation?: unknown;
  effective_resources?: unknown;
};

type BenchFile = {
  provider: ProviderName;
  mode?: RunMode;
  kind?: RunKind;
  task_count?: number;
  passed?: number;
  estimated_cost_usd?: number;
  results: BenchResultRow[];
};

type LoadedRun = {
  path: string;
  data: BenchFile;
};

type RunValidation = {
  key: string;
  baseline_path: string;
  candidate_path: string;
  provider: ProviderName;
  mode?: RunMode;
  kind?: RunKind;
  matched_tasks: number;
  baseline_passed: number;
  candidate_passed: number;
  pass_drop: number;
  baseline_elapsed_seconds: number;
  candidate_elapsed_seconds: number;
  wall_ratio?: number;
  baseline_cost_usd: number;
  candidate_cost_usd: number;
  reduction_pct?: number;
  candidate_observations: number;
  passed: boolean;
  failures: string[];
};

function parseArgs(argv: string[]): Args {
  const values = new Map<string, string>();
  for (let index = 0; index < argv.length; index += 2) {
    values.set(argv[index], argv[index + 1]);
  }
  return {
    baselineResults: parseList(values.get("--baseline-results") ?? values.get("--baseline")),
    candidateResults: parseList(values.get("--candidate-results") ?? values.get("--candidate")),
    baselineResultsDir: values.get("--baseline-results-dir"),
    candidateResultsDir: values.get("--candidate-results-dir"),
    output: values.get("--output"),
    format: parseFormat(values.get("--format") ?? "markdown"),
    minReductionPct: Number.parseFloat(values.get("--min-reduction-pct") ?? "20"),
    maxPassDrop: Number.parseInt(values.get("--max-pass-drop") ?? "0", 10),
    maxWallRatio: Number.parseFloat(values.get("--max-wall-ratio") ?? "1.2")
  };
}

function parseList(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseFormat(value: string): Args["format"] {
  if (value === "json" || value === "markdown") {
    return value;
  }
  throw new Error(`Unsupported format: ${value}`);
}

function resultPaths(paths: string[], dir: string | undefined): string[] {
  const all = [...paths];
  if (dir) {
    all.push(...readdirSync(dir).filter((file) => file.endsWith(".json")).map((file) => join(dir, file)));
  }
  if (all.length === 0) {
    throw new Error("No results provided.");
  }
  return all.map((path) => resolve(path));
}

async function loadRuns(paths: string[]): Promise<LoadedRun[]> {
  return await Promise.all(paths.map(loadRun));
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

function runKey(data: BenchFile): string {
  return [data.provider, data.mode ?? "unknown-mode", data.kind ?? "unknown-kind"].join("|");
}

function validateRun(candidate: LoadedRun, baselines: Map<string, LoadedRun>, args: Args): RunValidation {
  const key = runKey(candidate.data);
  const baseline = baselines.get(key) ?? baselines.get([candidate.data.provider, "unknown-mode", "unknown-kind"].join("|"));
  if (!baseline) {
    throw new Error(`No baseline result found for candidate ${candidate.path} (${key})`);
  }
  const baselineRows = new Map(baseline.data.results.map((row) => [row.task_id, row]));
  const matched = candidate.data.results.flatMap((candidateRow) => {
    const baselineRow = baselineRows.get(candidateRow.task_id);
    return baselineRow ? [{ baselineRow, candidateRow }] : [];
  });
  if (matched.length === 0) {
    throw new Error(`No overlapping task IDs between ${baseline.path} and ${candidate.path}`);
  }
  const baselineCost = sum(matched.map(({ baselineRow }) => rowCost(baselineRow, baseline.data)));
  const candidateCost = sum(matched.map(({ candidateRow }) => rowCost(candidateRow, candidate.data)));
  const baselineElapsed = sum(matched.map(({ baselineRow }) => finiteNumber(baselineRow.elapsed_seconds) ?? 0));
  const candidateElapsed = sum(matched.map(({ candidateRow }) => finiteNumber(candidateRow.elapsed_seconds) ?? 0));
  const baselinePassed = matched.filter(({ baselineRow }) => baselineRow.passed === true).length;
  const candidatePassed = matched.filter(({ candidateRow }) => candidateRow.passed === true).length;
  const passDrop = baselinePassed - candidatePassed;
  const reductionPct = pctReduction(baselineCost, candidateCost);
  const wallRatio = baselineElapsed > 0 ? candidateElapsed / baselineElapsed : undefined;
  const failures = [
    ...(reductionPct === undefined || reductionPct < args.minReductionPct
      ? [`cost reduction ${formatPct(reductionPct)} below ${args.minReductionPct.toFixed(1)}%`]
      : []),
    ...(passDrop > args.maxPassDrop ? [`pass drop ${passDrop} above ${args.maxPassDrop}`] : []),
    ...(wallRatio !== undefined && wallRatio > args.maxWallRatio
      ? [`wall ratio ${wallRatio.toFixed(2)} above ${args.maxWallRatio.toFixed(2)}`]
      : [])
  ];
  return {
    key,
    baseline_path: baseline.path,
    candidate_path: candidate.path,
    provider: candidate.data.provider,
    ...(candidate.data.mode ? { mode: candidate.data.mode } : {}),
    ...(candidate.data.kind ? { kind: candidate.data.kind } : {}),
    matched_tasks: matched.length,
    baseline_passed: baselinePassed,
    candidate_passed: candidatePassed,
    pass_drop: passDrop,
    baseline_elapsed_seconds: baselineElapsed,
    candidate_elapsed_seconds: candidateElapsed,
    ...(wallRatio === undefined ? {} : { wall_ratio: wallRatio }),
    baseline_cost_usd: baselineCost,
    candidate_cost_usd: candidateCost,
    ...(reductionPct === undefined ? {} : { reduction_pct: reductionPct }),
    candidate_observations: matched.filter(({ candidateRow }) => candidateRow.resource_observation !== undefined).length,
    passed: failures.length === 0,
    failures
  };
}

function rowCost(row: BenchResultRow, run: BenchFile): number {
  const direct = finiteNumber(row.estimated_cost_usd);
  if (direct !== undefined) {
    return direct;
  }
  const runCost = finiteNumber(run.estimated_cost_usd);
  if (runCost === undefined) {
    return 0;
  }
  const elapsed = finiteNumber(row.elapsed_seconds) ?? 0;
  const totalElapsed = sum(run.results.map((item) => finiteNumber(item.elapsed_seconds) ?? 0));
  return totalElapsed > 0 ? runCost * (elapsed / totalElapsed) : 0;
}

function finiteNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function pctReduction(baseline: number, candidate: number): number | undefined {
  return baseline > 0 ? ((baseline - candidate) / baseline) * 100 : undefined;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function markdownReport(validations: RunValidation[], args: Args): string {
  const baselineCost = sum(validations.map((item) => item.baseline_cost_usd));
  const candidateCost = sum(validations.map((item) => item.candidate_cost_usd));
  const baselineElapsed = sum(validations.map((item) => item.baseline_elapsed_seconds));
  const candidateElapsed = sum(validations.map((item) => item.candidate_elapsed_seconds));
  const baselinePassed = sum(validations.map((item) => item.baseline_passed));
  const candidatePassed = sum(validations.map((item) => item.candidate_passed));
  const totalReduction = pctReduction(baselineCost, candidateCost);
  return [
    "# Canary Cost Validation",
    "",
    `Generated: ${new Date().toISOString()}`,
    "",
    `Minimum reduction: ${args.minReductionPct.toFixed(1)}%`,
    `Maximum pass drop: ${args.maxPassDrop}`,
    `Maximum wall ratio: ${args.maxWallRatio.toFixed(2)}`,
    "",
    "## Summary",
    "",
    "baseline cost | candidate cost | reduction | baseline passed | candidate passed | wall ratio | status",
    "---: | ---: | ---: | ---: | ---: | ---: | ---",
    [
      formatMoney(baselineCost),
      formatMoney(candidateCost),
      formatPct(totalReduction),
      String(baselinePassed),
      String(candidatePassed),
      baselineElapsed > 0 ? (candidateElapsed / baselineElapsed).toFixed(2) : "-",
      validations.every((item) => item.passed) ? "pass" : "fail"
    ].join(" | "),
    "",
    "## Runs",
    "",
    "provider | mode | tasks | cost reduction | pass drop | wall ratio | observations | status | failures",
    "--- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---",
    ...validations.map((item) =>
      [
        item.provider,
        item.mode ?? "-",
        String(item.matched_tasks),
        formatPct(item.reduction_pct),
        String(item.pass_drop),
        item.wall_ratio === undefined ? "-" : item.wall_ratio.toFixed(2),
        String(item.candidate_observations),
        item.passed ? "pass" : "fail",
        item.failures.join("; ") || "-"
      ].join(" | ")
    ),
    "",
    "## Inputs",
    "",
    ...validations.flatMap((item) => [
      `- ${item.provider}${item.mode ? ` ${item.mode}` : ""}: baseline \`${displayPath(item.baseline_path)}\`, candidate \`${displayPath(item.candidate_path)}\``
    ]),
    ""
  ].join("\n");
}

function formatMoney(value: number | undefined): string {
  return value === undefined || Number.isNaN(value) ? "-" : `$${value.toFixed(4)}`;
}

function formatPct(value: number | undefined): string {
  return value === undefined || Number.isNaN(value) ? "-" : `${value.toFixed(1)}%`;
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
  const [baselineRuns, candidateRuns] = await Promise.all([
    loadRuns(resultPaths(args.baselineResults, args.baselineResultsDir)),
    loadRuns(resultPaths(args.candidateResults, args.candidateResultsDir))
  ]);
  const baselines = new Map(baselineRuns.map((run) => [runKey(run.data), run]));
  const validations = candidateRuns
    .map((run) => validateRun(run, baselines, args))
    .sort((left, right) => left.provider.localeCompare(right.provider) || (left.mode ?? "").localeCompare(right.mode ?? ""));
  const payload = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    min_reduction_pct: args.minReductionPct,
    max_pass_drop: args.maxPassDrop,
    max_wall_ratio: args.maxWallRatio,
    passed: validations.every((item) => item.passed),
    total_baseline_cost_usd: sum(validations.map((item) => item.baseline_cost_usd)),
    total_candidate_cost_usd: sum(validations.map((item) => item.candidate_cost_usd)),
    total_reduction_pct: pctReduction(
      sum(validations.map((item) => item.baseline_cost_usd)),
      sum(validations.map((item) => item.candidate_cost_usd))
    ),
    validations
  };
  const content = args.format === "json" ? `${JSON.stringify(payload, null, 2)}\n` : markdownReport(validations, args);
  writeOutput(args.output, content);
  if (!payload.passed) {
    process.exitCode = 1;
  }
}

if (import.meta.main) {
  await main();
}
