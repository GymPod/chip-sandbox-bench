import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

type Args = {
  policyComparison?: string;
  resourceReport?: string;
  canaryValidation?: string;
  output?: string;
  format: "json" | "markdown";
  minReductionPct: number;
  minObservations: number;
};

type AuditCheck = {
  name: string;
  passed: boolean;
  evidence?: string;
  reason?: string;
};

function parseArgs(argv: string[]): Args {
  const values = new Map<string, string>();
  for (let index = 0; index < argv.length; index += 2) {
    values.set(argv[index], argv[index + 1]);
  }
  return {
    policyComparison: values.get("--policy-comparison"),
    resourceReport: values.get("--resource-report"),
    canaryValidation: values.get("--canary-validation"),
    output: values.get("--output"),
    format: parseFormat(values.get("--format") ?? "markdown"),
    minReductionPct: Number.parseFloat(values.get("--min-reduction-pct") ?? "20"),
    minObservations: Number.parseInt(values.get("--min-observations") ?? "1", 10)
  };
}

function parseFormat(value: string): Args["format"] {
  if (value === "json" || value === "markdown") {
    return value;
  }
  throw new Error(`Unsupported format: ${value}`);
}

function policyComparisonCheck(args: Args): AuditCheck {
  if (!args.policyComparison) {
    return { name: "policy_projection", passed: false, reason: "--policy-comparison not provided" };
  }
  const parsed = readJson(args.policyComparison);
  const reduction = numberAt(parsed, "total_reduction_pct");
  if (reduction === undefined) {
    return { name: "policy_projection", passed: false, reason: "total_reduction_pct missing" };
  }
  return {
    name: "policy_projection",
    passed: reduction >= args.minReductionPct,
    evidence: `${reduction.toFixed(1)}% projected reduction`,
    ...(reduction >= args.minReductionPct ? {} : { reason: `below ${args.minReductionPct.toFixed(1)}%` })
  };
}

function resourceObservationCheck(args: Args): AuditCheck {
  if (!args.resourceReport) {
    return { name: "resource_observations", passed: false, reason: "--resource-report not provided" };
  }
  const parsed = readJson(args.resourceReport);
  const count = numberAt(parsed, "observation_count");
  if (count === undefined) {
    return { name: "resource_observations", passed: false, reason: "observation_count missing" };
  }
  return {
    name: "resource_observations",
    passed: count >= args.minObservations,
    evidence: `${count} observations`,
    ...(count >= args.minObservations ? {} : { reason: `below ${args.minObservations}` })
  };
}

function canaryValidationCheck(args: Args): AuditCheck {
  if (!args.canaryValidation) {
    return {
      name: "remote_canary_validation",
      passed: false,
      reason: "--canary-validation not provided"
    };
  }
  if (!existsSync(args.canaryValidation)) {
    return {
      name: "remote_canary_validation",
      passed: false,
      reason: `canary validation file not found: ${args.canaryValidation}`
    };
  }
  const parsed = readJson(args.canaryValidation);
  const passed = booleanAt(parsed, "passed");
  const reduction = numberAt(parsed, "total_reduction_pct");
  if (passed !== true) {
    return {
      name: "remote_canary_validation",
      passed: false,
      evidence: reduction === undefined ? undefined : `${reduction.toFixed(1)}% actual reduction`,
      reason: "canary validator did not pass"
    };
  }
  if (reduction === undefined || reduction < args.minReductionPct) {
    return {
      name: "remote_canary_validation",
      passed: false,
      evidence: reduction === undefined ? undefined : `${reduction.toFixed(1)}% actual reduction`,
      reason: `actual reduction below ${args.minReductionPct.toFixed(1)}%`
    };
  }
  return {
    name: "remote_canary_validation",
    passed: true,
    evidence: `${reduction.toFixed(1)}% actual reduction`
  };
}

function readJson(path: string): unknown {
  if (!existsSync(path)) {
    throw new Error(`Input not found: ${path}`);
  }
  return JSON.parse(readFileSync(path, "utf8")) as unknown;
}

function numberAt(value: unknown, key: string): number | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const item = value[key];
  return typeof item === "number" && Number.isFinite(item) ? item : undefined;
}

function booleanAt(value: unknown, key: string): boolean | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const item = value[key];
  return typeof item === "boolean" ? item : undefined;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function markdownReport(checks: AuditCheck[], args: Args): string {
  return [
    "# Cost Reduction Goal Audit",
    "",
    `Generated: ${new Date().toISOString()}`,
    "",
    `Minimum reduction: ${args.minReductionPct.toFixed(1)}%`,
    `Minimum observations: ${args.minObservations}`,
    "",
    "check | status | evidence | reason",
    "--- | --- | --- | ---",
    ...checks.map((check) =>
      [check.name, check.passed ? "pass" : "fail", check.evidence ?? "-", check.reason ?? "-"].join(" | ")
    ),
    "",
    `Overall: ${checks.every((check) => check.passed) ? "pass" : "fail"}`,
    ""
  ].join("\n");
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
  const checks = [policyComparisonCheck(args), resourceObservationCheck(args), canaryValidationCheck(args)];
  const passed = checks.every((check) => check.passed);
  const payload = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    min_reduction_pct: args.minReductionPct,
    min_observations: args.minObservations,
    passed,
    checks
  };
  const content = args.format === "json" ? `${JSON.stringify(payload, null, 2)}\n` : markdownReport(checks, args);
  writeOutput(args.output, content);
  if (!passed) {
    process.exitCode = 1;
  }
}

if (import.meta.main) {
  await main();
}
