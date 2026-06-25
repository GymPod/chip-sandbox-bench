import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import type { ProviderName, RunMode } from "./types";

type MatrixProvider = Exclude<ProviderName, "local">;

type Args = {
  run: boolean;
  providers: MatrixProvider[];
  modes: RunMode[];
  baselineResults: string[];
  dataset: string;
  taskIndex: string;
  taskLimit?: number;
  outputDir: string;
  reportsDir: string;
  resourceObservationsDir: string;
  suffix: string;
  timeoutSeconds: number;
  solveTimeoutSeconds: number;
  concurrency: number;
  runConcurrency: number;
  resourcePolicy: string;
  resourceConfig?: string;
  solveCommandFile: string;
  baselineConfig?: string;
  candidateConfig: string;
  minReductionPct: number;
  maxPassDrop: number;
  maxWallRatio: number;
  preflight: boolean;
  livePreflight: boolean;
  output?: string;
};

type Step = {
  name: string;
  argv: string[];
  output?: string;
  allowFailure?: boolean;
};

type PreflightCheck = {
  name: string;
  passed: boolean;
  required: string[];
  present: string[];
  missing: string[];
  warnings: string[];
};

type PreflightResult = {
  enabled: boolean;
  passed: boolean;
  checks: PreflightCheck[];
};

const PROVIDERS: MatrixProvider[] = ["vercel", "modal", "daytona", "aws-microvm"];
const MODES: RunMode[] = ["cold", "warm"];

function parseArgs(argv: string[]): Args {
  const values = new Map<string, string>();
  for (let index = 0; index < argv.length; index += 2) {
    values.set(argv[index], argv[index + 1]);
  }
  const outputDir = resolve(values.get("--output-dir") ?? resolve(import.meta.dir, "../../results"));
  const reportsDir = resolve(values.get("--reports-dir") ?? resolve(import.meta.dir, "../../reports"));
  const resourceObservationsDir = resolve(values.get("--resource-observations-dir") ?? resolve(outputDir, "resource-observations"));
  const suffix = values.get("--suffix") ?? `cpu1-canary-${yyyymmdd(new Date())}`;
  return {
    run: parseBoolean(values.get("--run") ?? "false"),
    providers: parseList(values.get("--providers") ?? "vercel,modal,daytona", PROVIDERS),
    modes: parseList(values.get("--modes") ?? "warm", MODES),
    baselineResults: parseCsv(values.get("--baseline-results") ?? values.get("--baseline")),
    dataset: resolve(values.get("--dataset") ?? resolve(import.meta.dir, "../../data/terminalbench_2026_03_05_smoke16.jsonl")),
    taskIndex: values.get("--task-index") ?? "all",
    taskLimit: parseOptionalInt(values.get("--task-limit") ?? "3"),
    outputDir,
    reportsDir,
    resourceObservationsDir,
    suffix,
    timeoutSeconds: Number.parseInt(values.get("--timeout-seconds") ?? "900", 10),
    solveTimeoutSeconds: Number.parseInt(values.get("--solve-timeout-seconds") ?? "300", 10),
    concurrency: Number.parseInt(values.get("--concurrency") ?? "2", 10),
    runConcurrency: Number.parseInt(values.get("--run-concurrency") ?? "1", 10),
    resourcePolicy: values.get("--resource-policy") ?? "adaptive",
    resourceConfig: values.get("--resource-config"),
    solveCommandFile: resolve(values.get("--solve-command-file") ?? resolve(import.meta.dir, "../../scripts/openrouter_solver.sh")),
    baselineConfig: values.get("--baseline-config"),
    candidateConfig: resolve(values.get("--candidate-config") ?? resolve(import.meta.dir, "../../data/resource_policy.json")),
    minReductionPct: Number.parseFloat(values.get("--min-reduction-pct") ?? "20"),
    maxPassDrop: Number.parseInt(values.get("--max-pass-drop") ?? "0", 10),
    maxWallRatio: Number.parseFloat(values.get("--max-wall-ratio") ?? "1.2"),
    preflight: parseBoolean(values.get("--preflight") ?? "true") && !parseBoolean(values.get("--skip-preflight") ?? "false"),
    livePreflight: parseBoolean(values.get("--live-preflight") ?? "true"),
    output: values.get("--output")
  };
}

function parseBoolean(value: string): boolean {
  if (value === "1" || value.toLowerCase() === "true" || value.toLowerCase() === "yes" || value.toLowerCase() === "on") {
    return true;
  }
  if (value === "0" || value.toLowerCase() === "false" || value.toLowerCase() === "no" || value.toLowerCase() === "off") {
    return false;
  }
  throw new Error(`Unsupported boolean: ${value}`);
}

function parseList<T extends string>(value: string, allowed: readonly T[]): T[] {
  const items = value === "all" ? [...allowed] : parseCsv(value);
  for (const item of items) {
    if (!allowed.includes(item as T)) {
      throw new Error(`Unsupported value: ${item}`);
    }
  }
  return items as T[];
}

function parseCsv(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseOptionalInt(value: string | undefined): number | undefined {
  return value === undefined ? undefined : Number.parseInt(value, 10);
}

function yyyymmdd(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}${month}${day}`;
}

function candidateResults(args: Args): string[] {
  return args.providers.flatMap((provider) =>
    args.modes.map((mode) => `${args.outputDir}/ts-${provider}-${mode}-solve-all-${args.suffix}.json`)
  );
}

function candidateObservationResults(args: Args): string[] {
  return args.providers.flatMap((provider) =>
    args.modes.map((mode) => `${args.resourceObservationsDir}/ts-${provider}-${mode}-solve-all-${args.suffix}.jsonl`)
  );
}

function matrixOutput(args: Args): string {
  return `${args.outputDir}/cost-canary-matrix-${args.suffix}.json`;
}

function resourceReportOutput(args: Args): string {
  return `${args.reportsDir}/generated-resource-observations-${args.suffix}.json`;
}

function suggestedConfigOutput(args: Args): string {
  return `${args.outputDir}/generated-resource-policy-${args.suffix}.json`;
}

function policyComparisonOutput(args: Args): string {
  return `${args.reportsDir}/generated-policy-cost-comparison-${args.suffix}.json`;
}

function canaryValidationOutput(args: Args): string {
  return `${args.reportsDir}/generated-canary-validation-${args.suffix}.json`;
}

function goalAuditOutput(args: Args): string {
  return `${args.reportsDir}/generated-cost-goal-audit-${args.suffix}.json`;
}

function buildSteps(args: Args): Step[] {
  const candidates = candidateResults(args);
  const policyComparison = policyComparisonOutput(args);
  const resourceReport = resourceReportOutput(args);
  const canaryValidation = canaryValidationOutput(args);
  const matrix = matrixOutput(args);
  const steps: Step[] = [
    {
      name: "candidate_matrix",
      argv: [
        "bun",
        "src/matrix.ts",
        "--providers",
        args.providers.join(","),
        "--modes",
        args.modes.join(","),
        "--dataset",
        args.dataset,
        "--task-index",
        args.taskIndex,
        ...(args.taskLimit === undefined ? [] : ["--task-limit", String(args.taskLimit)]),
        "--timeout-seconds",
        String(args.timeoutSeconds),
        "--solve-timeout-seconds",
        String(args.solveTimeoutSeconds),
        "--concurrency",
        String(args.concurrency),
        "--run-concurrency",
        String(args.runConcurrency),
        "--resource-policy",
        args.resourcePolicy,
        "--resource-config",
        args.resourceConfig ?? args.candidateConfig,
        "--solve-command-file",
        args.solveCommandFile,
        "--output-dir",
        args.outputDir,
        "--resource-observations-dir",
        args.resourceObservationsDir,
        "--suffix",
        args.suffix,
        "--output",
        matrix
      ],
      output: matrix,
      allowFailure: true
    },
    {
      name: "resource_report",
      argv: [
        "bun",
        "src/resource_report.ts",
        "--input",
        candidateObservationResults(args).join(","),
        "--min-samples",
        "1",
        "--format",
        "json",
        "--output",
        resourceReport,
        "--suggested-config-output",
        suggestedConfigOutput(args)
      ],
      output: resourceReport
    }
  ];
  if (args.baselineConfig) {
    steps.push({
      name: "policy_compare",
      argv: [
        "bun",
        "src/policy_compare.ts",
        "--results",
        args.baselineResults.join(","),
        "--dataset",
        args.dataset,
        "--baseline-config",
        args.baselineConfig,
        "--candidate-config",
        args.candidateConfig,
        "--format",
        "json",
        "--output",
        policyComparison
      ],
      output: policyComparison
    });
  }
  steps.push(
    {
      name: "canary_validate",
      argv: [
        "bun",
        "src/canary_validate.ts",
        "--baseline-results",
        args.baselineResults.join(","),
        "--candidate-results",
        candidates.join(","),
        "--min-reduction-pct",
        String(args.minReductionPct),
        "--max-pass-drop",
        String(args.maxPassDrop),
        "--max-wall-ratio",
        String(args.maxWallRatio),
        "--format",
        "json",
        "--output",
        canaryValidation
      ],
      output: canaryValidation
    },
    {
      name: "goal_audit",
      argv: [
        "bun",
        "src/cost_goal_audit.ts",
        "--policy-comparison",
        policyComparison,
        "--resource-report",
        resourceReport,
        "--canary-validation",
        canaryValidation,
        "--min-reduction-pct",
        String(args.minReductionPct),
        "--min-observations",
        "1",
        "--format",
        "json",
        "--output",
        goalAuditOutput(args)
      ],
      output: goalAuditOutput(args)
    }
  );
  return steps;
}

function preflight(args: Args): PreflightResult {
  if (!args.preflight) {
    return { enabled: false, passed: true, checks: [] };
  }
  const checks = [
    ...args.providers.map(providerPreflight),
    ...solverPreflight(args)
  ];
  return {
    enabled: true,
    passed: checks.every((check) => check.passed),
    checks
  };
}

function providerPreflight(provider: MatrixProvider): PreflightCheck {
  if (provider === "vercel") {
    return vercelPreflight();
  }
  if (provider === "modal") {
    return modalPreflight();
  }
  if (provider === "daytona") {
    return envPreflight("daytona", ["DAYTONA_API_KEY"], ["DAYTONA_API_URL", "DAYTONA_TARGET"]);
  }
  return awsMicrovmPreflight();
}

function vercelPreflight(): PreflightCheck {
  const tokenNames = ["VERCEL_TOKEN", "VERCEL_ACCESS_TOKEN", "VERCEL_API_KEY"];
  const required = ["VERCEL_TOKEN or VERCEL_ACCESS_TOKEN or VERCEL_API_KEY", "VERCEL_TEAM_ID", "VERCEL_PROJECT_ID"];
  const present = [
    ...tokenNames.filter(envPresent),
    ...["VERCEL_TEAM_ID", "VERCEL_PROJECT_ID"].filter(envPresent)
  ];
  const missing = [
    ...(tokenNames.some(envPresent) ? [] : [required[0]]),
    ...["VERCEL_TEAM_ID", "VERCEL_PROJECT_ID"].filter((name) => !envPresent(name))
  ];
  return {
    name: "vercel",
    passed: missing.length === 0,
    required,
    present,
    missing,
    warnings: []
  };
}

function modalPreflight(): PreflightCheck {
  const configPath = process.env.MODAL_CONFIG_PATH ? resolve(process.env.MODAL_CONFIG_PATH) : join(homedir(), ".modal.toml");
  const hasTokenPair = envPresent("MODAL_TOKEN_ID") && envPresent("MODAL_TOKEN_SECRET");
  const hasConfig = existsSync(configPath);
  const present = [
    ...["MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET", "MODAL_PROFILE", "MODAL_CONFIG_PATH"].filter(envPresent),
    ...(hasConfig ? [process.env.MODAL_CONFIG_PATH ? "MODAL_CONFIG_PATH file" : "~/.modal.toml"] : [])
  ];
  const warnings =
    envPresent("MODAL_TOKEN_ID") !== envPresent("MODAL_TOKEN_SECRET")
      ? ["Both MODAL_TOKEN_ID and MODAL_TOKEN_SECRET are needed for env-based Modal auth."]
      : [];
  return {
    name: "modal",
    passed: hasTokenPair || hasConfig,
    required: ["MODAL_TOKEN_ID + MODAL_TOKEN_SECRET or ~/.modal.toml"],
    present,
    missing: hasTokenPair || hasConfig ? [] : ["MODAL_TOKEN_ID + MODAL_TOKEN_SECRET or ~/.modal.toml"],
    warnings
  };
}

function awsMicrovmPreflight(): PreflightCheck {
  const hasImage = envPresent("AWS_MICROVM_IMAGE_ID") || envPresent("AWS_MICROVM_IMAGE_ARN");
  const hasAccessKeyPair = envPresent("AWS_ACCESS_KEY_ID") && envPresent("AWS_SECRET_ACCESS_KEY");
  const hasAwsAuth =
    envPresent("AWS_PROFILE") ||
    hasAccessKeyPair ||
    envPresent("AWS_WEB_IDENTITY_TOKEN_FILE") ||
    envPresent("AWS_CONTAINER_CREDENTIALS_FULL_URI") ||
    envPresent("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI");
  const required = [
    "AWS_MICROVM_IMAGE_ID or AWS_MICROVM_IMAGE_ARN",
    "AWS_PROFILE or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY or AWS_WEB_IDENTITY_TOKEN_FILE"
  ];
  const present = [
    ...[
      "AWS_MICROVM_IMAGE_ID",
      "AWS_MICROVM_IMAGE_ARN",
      "AWS_MICROVM_IMAGE_VERSION",
      "AWS_MICROVM_EXECUTION_ROLE_ARN",
      "AWS_PROFILE",
      "AWS_ACCESS_KEY_ID",
      "AWS_WEB_IDENTITY_TOKEN_FILE",
      "AWS_CONTAINER_CREDENTIALS_FULL_URI",
      "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
      "AWS_REGION",
      "AWS_DEFAULT_REGION"
    ].filter(envPresent),
    ...(hasAccessKeyPair ? ["AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY"] : [])
  ];
  const missing = [
    ...(hasImage ? [] : [required[0]]),
    ...(hasAwsAuth ? [] : [required[1]])
  ];
  return {
    name: "aws-microvm",
    passed: missing.length === 0,
    required,
    present,
    missing,
    warnings: envPresent("AWS_ACCESS_KEY_ID") !== envPresent("AWS_SECRET_ACCESS_KEY")
      ? ["Both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are needed for static-key AWS auth."]
      : []
  };
}

function solverPreflight(args: Args): PreflightCheck[] {
  const checks = [];
  const solverContract = solverContractPreflight(args);
  if (solverContract) {
    checks.push(solverContract);
  }
  if (usesOpenRouterSolver(args.solveCommandFile)) {
    checks.push(envPreflight("openrouter-solver", ["OPENROUTER_API_KEY"], ["OPENROUTER_MODEL"]));
  }
  if (usesAiGatewaySolver(args.solveCommandFile)) {
    checks.push(authEnvPreflight("ai-gateway-solver", ["AI_GATEWAY_API_KEY", "VERCEL_OIDC_TOKEN"], ["AI_GATEWAY_MODEL"]));
  }
  return checks;
}

function solverContractPreflight(args: Args): PreflightCheck | undefined {
  const baselineContract = inferBaselineSolverContract(args.baselineResults);
  if (baselineContract !== "openrouter") {
    return undefined;
  }
  const selectedOpenRouter = usesOpenRouterSolver(args.solveCommandFile);
  const selectedAiGateway = usesAiGatewaySolver(args.solveCommandFile);
  const selectedCompatibleSolver = selectedOpenRouter || selectedAiGateway;
  return {
    name: "solver-contract",
    passed: selectedCompatibleSolver,
    required: ["candidate solver must use the LLM bash-solver contract inferred from the OpenRouter baseline"],
    present: ["baseline:openrouter", `candidate:${solverName(args.solveCommandFile)}`],
    missing: selectedCompatibleSolver ? [] : ["scripts/openrouter_solver.sh or scripts/ai_gateway_solver.sh"],
    warnings: []
  };
}

function inferBaselineSolverContract(paths: string[]): "openrouter" | "unknown" {
  for (const path of paths) {
    try {
      const data = JSON.parse(readFileSync(resolve(path), "utf8")) as unknown;
      if (resultHasOpenRouterEvidence(data)) {
        return "openrouter";
      }
    } catch {
      continue;
    }
  }
  return "unknown";
}

function resultHasOpenRouterEvidence(value: unknown): boolean {
  if (!isRecord(value) || !Array.isArray(value.results)) {
    return false;
  }
  return value.results.some((row) => {
    if (!isRecord(row)) {
      return false;
    }
    return [row.solve_stdout_tail, row.solve_stderr_tail]
      .filter((tail): tail is string => typeof tail === "string")
      .some((tail) => /openrouter solver|openrouter\.ai/i.test(tail));
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function usesOpenRouterSolver(path: string): boolean {
  return path.endsWith("openrouter_solver.sh");
}

function usesAiGatewaySolver(path: string): boolean {
  return path.endsWith("ai_gateway_solver.sh");
}

function solverName(path: string): string {
  return path.split("/").at(-1) ?? path;
}

function envPreflight(name: string, required: string[], optional: string[] = []): PreflightCheck {
  const missing = required.filter((envName) => !envPresent(envName));
  return {
    name,
    passed: missing.length === 0,
    required,
    present: [...required, ...optional].filter(envPresent),
    missing,
    warnings: []
  };
}

function authEnvPreflight(name: string, authAlternatives: string[], optional: string[] = []): PreflightCheck {
  const hasAuth = authAlternatives.some(envPresent);
  return {
    name,
    passed: hasAuth,
    required: [`one of ${authAlternatives.join(", ")}`],
    present: [...authAlternatives, ...optional].filter(envPresent),
    missing: hasAuth ? [] : authAlternatives,
    warnings: []
  };
}

function envPresent(name: string): boolean {
  const value = process.env[name];
  return value !== undefined && value !== "";
}

async function runLivePreflight(args: Args, preflightResult: PreflightResult): Promise<PreflightResult> {
  if (!args.preflight || !args.livePreflight) {
    return preflightResult;
  }
  const liveChecks = [
    ...(usesOpenRouterSolver(args.solveCommandFile) ? [await openRouterLivePreflight()] : []),
    ...(usesAiGatewaySolver(args.solveCommandFile) ? [await aiGatewayLivePreflight()] : [])
  ];
  if (liveChecks.length === 0) {
    return preflightResult;
  }
  const checks = [...preflightResult.checks, ...liveChecks];
  return {
    enabled: preflightResult.enabled,
    passed: checks.every((check) => check.passed),
    checks
  };
}

async function openRouterLivePreflight(): Promise<PreflightCheck> {
  const required = ["OpenRouter chat completion access"];
  const present = ["OPENROUTER_API_KEY", "OPENROUTER_MODEL"].filter(envPresent);
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return {
      name: "openrouter-live",
      passed: false,
      required,
      present,
      missing: required,
      warnings: ["OPENROUTER_API_KEY is required for the live OpenRouter budget/auth check."]
    };
  }
  const body = {
    messages: [{ role: "user", content: "Reply with ok." }],
    temperature: 0,
    max_tokens: 1,
    ...(process.env.OPENROUTER_MODEL ? { model: process.env.OPENROUTER_MODEL } : {})
  };
  try {
    const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        authorization: `Bearer ${apiKey}`,
        "content-type": "application/json",
        "http-referer": "https://github.com/openai/code-sandbox-bench",
        "x-title": "code-sandbox-bench canary preflight"
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000)
    });
    if (response.ok) {
      return {
        name: "openrouter-live",
        passed: true,
        required,
        present,
        missing: [],
        warnings: []
      };
    }
    return {
      name: "openrouter-live",
      passed: false,
      required,
      present,
      missing: required,
      warnings: [`HTTP ${response.status}: ${sanitizeOpenRouterError(await response.text())}`]
    };
  } catch (error) {
    return {
      name: "openrouter-live",
      passed: false,
      required,
      present,
      missing: required,
      warnings: [formatPreflightError(error)]
    };
  }
}

async function aiGatewayLivePreflight(): Promise<PreflightCheck> {
  const required = ["AI Gateway chat completion access"];
  const present = ["AI_GATEWAY_API_KEY", "VERCEL_OIDC_TOKEN", "AI_GATEWAY_MODEL"].filter(envPresent);
  const apiKey = process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN;
  if (!apiKey) {
    return {
      name: "ai-gateway-live",
      passed: false,
      required,
      present,
      missing: required,
      warnings: ["AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN is required for the live AI Gateway budget/auth check."]
    };
  }
  const body = {
    messages: [{ role: "user", content: "Reply with ok." }],
    temperature: 0,
    max_tokens: 1,
    model: process.env.AI_GATEWAY_MODEL || "deepseek/deepseek-v4-flash"
  };
  try {
    const response = await fetch("https://ai-gateway.vercel.sh/v1/chat/completions", {
      method: "POST",
      headers: {
        authorization: `Bearer ${apiKey}`,
        "content-type": "application/json",
        "x-title": "code-sandbox-bench canary preflight"
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30_000)
    });
    if (response.ok) {
      return {
        name: "ai-gateway-live",
        passed: true,
        required,
        present,
        missing: [],
        warnings: []
      };
    }
    return {
      name: "ai-gateway-live",
      passed: false,
      required,
      present,
      missing: required,
      warnings: [`HTTP ${response.status}: ${sanitizeOpenRouterError(await response.text())}`]
    };
  } catch (error) {
    return {
      name: "ai-gateway-live",
      passed: false,
      required,
      present,
      missing: required,
      warnings: [formatPreflightError(error)]
    };
  }
}

function sanitizeOpenRouterError(text: string): string {
  try {
    const payload = JSON.parse(text) as unknown;
    if (isRecord(payload) && isRecord(payload.error) && typeof payload.error.message === "string") {
      return payload.error.message.slice(0, 240);
    }
  } catch {}
  return text.replace(/\s+/g, " ").slice(0, 240) || "empty response";
}

function formatPreflightError(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}

function validateArgs(args: Args): void {
  if (args.baselineResults.length === 0) {
    throw new Error("--baseline-results is required");
  }
  if (!args.baselineConfig) {
    throw new Error("--baseline-config is required so the loop can produce projection evidence for cost:goal-audit");
  }
}

async function runStep(step: Step): Promise<{ name: string; exit_code: number; output?: string }> {
  console.log(`running ${step.name}: ${shellCommand(step.argv)}`);
  const proc = Bun.spawn(step.argv, {
    cwd: resolve(import.meta.dir, ".."),
    stdout: "inherit",
    stderr: "inherit",
    env: process.env
  });
  const exitCode = await proc.exited;
  if (exitCode !== 0 && !step.allowFailure) {
    throw new Error(`${step.name} failed with exit code ${exitCode}`);
  }
  return { name: step.name, exit_code: exitCode, ...(step.output ? { output: step.output } : {}) };
}

function shellCommand(argv: string[]): string {
  return argv.map(shellQuote).join(" ");
}

function shellQuote(value: string): string {
  return /^[A-Za-z0-9_./:=,+-]+$/.test(value) ? value : `'${value.replaceAll("'", "'\"'\"'")}'`;
}

function dryRunReport(args: Args, steps: Step[], preflightResult: PreflightResult): string {
  return [
    "# Cost Canary Loop Dry Run",
    "",
    `Generated: ${new Date().toISOString()}`,
    "",
    `Providers: ${args.providers.join(", ")}`,
    `Modes: ${args.modes.join(", ")}`,
    `Suffix: ${args.suffix}`,
    `Run enabled: ${args.run}`,
    `Preflight enabled: ${preflightResult.enabled}`,
    `Preflight passed: ${preflightResult.passed}`,
    "",
    "## Preflight",
    "",
    ...preflightReportLines(preflightResult),
    "",
    "## Candidate Results",
    "",
    ...candidateResults(args).map((path) => `- \`${path}\``),
    "",
    "## Candidate Observations",
    "",
    ...candidateObservationResults(args).map((path) => `- \`${path}\``),
    "",
    "## Steps",
    "",
    ...steps.flatMap((step, index) => [`${index + 1}. ${step.name}`, "", "```bash", shellCommand(step.argv), "```", ""])
  ].join("\n").trimEnd() + "\n";
}

function preflightReportLines(preflightResult: PreflightResult): string[] {
  if (!preflightResult.enabled) {
    return ["Preflight disabled.", ""];
  }
  if (preflightResult.checks.length === 0) {
    return ["No credential checks are required for this loop.", ""];
  }
  return [
    "check | status | present | missing",
    "--- | --- | --- | ---",
    ...preflightResult.checks.map((check) => [
      check.name,
      check.passed ? "pass" : "fail",
      check.present.length === 0 ? "none" : check.present.map(markdownCode).join(", "),
      check.missing.length === 0 ? "none" : check.missing.map(markdownCode).join(", ")
    ].join(" | ")),
    "",
    ...preflightResult.checks
      .flatMap((check) => check.warnings.map((warning) => `- ${check.name}: ${warning}`)),
    ""
  ];
}

function markdownCode(value: string): string {
  return `\`${value.replaceAll("`", "\\`")}\``;
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
  validateArgs(args);
  const steps = buildSteps(args);
  const preflightResult = preflight(args);
  if (!args.run) {
    writeOutput(args.output, dryRunReport(args, steps, preflightResult));
    return;
  }
  const finalPreflightResult = preflightResult.passed ? await runLivePreflight(args, preflightResult) : preflightResult;
  if (!finalPreflightResult.passed) {
    const payload = {
      generated_at: new Date().toISOString(),
      suffix: args.suffix,
      status: "preflight_failed",
      preflight: finalPreflightResult,
      candidate_results: candidateResults(args),
      steps: steps.map((step) => ({ name: step.name, argv: step.argv, ...(step.output ? { output: step.output } : {}) }))
    };
    writeOutput(args.output, `${JSON.stringify(payload, null, 2)}\n`);
    process.exitCode = 1;
    return;
  }
  const results = [];
  for (const step of steps) {
    results.push(await runStep(step));
  }
  const payload = {
    generated_at: new Date().toISOString(),
    suffix: args.suffix,
    status: results.some((result) => result.exit_code !== 0) ? "failed" : "passed",
    preflight: finalPreflightResult,
    candidate_results: candidateResults(args),
    steps: results
  };
  writeOutput(args.output, `${JSON.stringify(payload, null, 2)}\n`);
  if (results.some((result) => result.exit_code !== 0)) {
    process.exitCode = 1;
  }
}

if (import.meta.main) {
  await main();
}
