import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import {
  recommendAdaptiveResources,
  type AdaptiveResourceRecommendation,
  type ResourceObservation,
  type ResourcePolicyConfig,
  type ResourceSpec
} from "./resource_policy";
import type { ProviderName } from "./types";

type Args = {
  inputs: string[];
  resultsDir?: string;
  output?: string;
  suggestedConfigOutput?: string;
  format: "json" | "markdown";
  minSamples: number;
};

type ObservationGroup = {
  key: string;
  provider: ProviderName;
  env_type?: string;
  repo_key?: string;
  source_id?: string;
  runtime?: string;
  image_id?: string;
  image_version?: string;
  manifest_hash?: string;
  observations: ResourceObservation[];
};

type AggregatedResourceSuggestion = {
  key: string;
  provider: ProviderName;
  env_type?: string;
  repo_key?: string;
  source_id?: string;
  runtime?: string;
  image_id?: string;
  image_version?: string;
  manifest_hash?: string;
  sample_count: number;
  pass_count: number;
  failure_counts: Record<string, number>;
  p95_wall_seconds?: number;
  p95_peak_rss_gb?: number;
  p95_disk_gb?: number;
  p95_prepare_seconds?: number;
  p95_verify_seconds?: number;
  recommended: ResourceSpec;
  confidence: "low" | "medium" | "high";
  reasons: string[];
};

function parseArgs(argv: string[]): Args {
  const values = new Map<string, string>();
  for (let index = 0; index < argv.length; index += 2) {
    values.set(argv[index], argv[index + 1]);
  }
  const inputText = values.get("--input") ?? "";
  return {
    inputs: inputText
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    resultsDir: values.get("--results-dir"),
    output: values.get("--output"),
    suggestedConfigOutput: values.get("--suggested-config-output"),
    format: parseFormat(values.get("--format") ?? "markdown"),
    minSamples: Number.parseInt(values.get("--min-samples") ?? "2", 10)
  };
}

function parseFormat(value: string): Args["format"] {
  if (value === "json" || value === "markdown") {
    return value;
  }
  throw new Error(`Unsupported resource report format: ${value}`);
}

function loadObservations(args: Args): ResourceObservation[] {
  const paths = [...args.inputs];
  if (args.resultsDir) {
    paths.push(
      ...readdirSync(args.resultsDir)
        .filter((file) => file.endsWith(".json") || file.endsWith(".jsonl"))
        .map((file) => join(args.resultsDir as string, file))
    );
  }
  const observations = paths.flatMap((path) => loadObservationFile(resolve(path)));
  return observations.filter(isResourceObservation);
}

function loadObservationFile(path: string): unknown[] {
  if (!existsSync(path)) {
    throw new Error(`Resource observation input not found: ${path}`);
  }
  const text = readFileSync(path, "utf8").trim();
  if (!text) {
    return [];
  }
  if (path.endsWith(".jsonl")) {
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  }
  const parsed = JSON.parse(text) as unknown;
  if (Array.isArray(parsed)) {
    return parsed;
  }
  if (isObject(parsed)) {
    const direct = parsed.resource_observation;
    const results = Array.isArray(parsed.results) ? parsed.results : [];
    return [
      ...(direct ? [direct] : []),
      ...results.map((item) => (isObject(item) ? item.resource_observation : undefined)).filter(Boolean)
    ];
  }
  return [];
}

function aggregateObservations(observations: ResourceObservation[]): AggregatedResourceSuggestion[] {
  return [...groupObservations(observations).values()]
    .map(aggregateGroup)
    .sort((left, right) => left.provider.localeCompare(right.provider) || left.key.localeCompare(right.key));
}

function groupObservations(observations: ResourceObservation[]): Map<string, ObservationGroup> {
  const groups = new Map<string, ObservationGroup>();
  for (const observation of observations) {
    const key = groupKey(observation);
    const existing = groups.get(key);
    if (existing) {
      existing.observations.push(observation);
      continue;
    }
    groups.set(key, {
      key,
      provider: observation.provider,
      env_type: observation.env_type,
      repo_key: observation.repo_key,
      source_id: observation.source_id,
      runtime: observation.runtime,
      image_id: observation.image_id,
      image_version: observation.image_version,
      manifest_hash: observation.manifest_hash,
      observations: [observation]
    });
  }
  return groups;
}

function groupKey(observation: ResourceObservation): string {
  return [
    observation.provider,
    observation.env_type ?? "unknown-env",
    observation.repo_key ?? observation.task_id ?? "unknown-scope",
    observation.runtime ?? "unknown-runtime",
    observation.image_id ?? observation.docker_image ?? "no-image",
    observation.manifest_hash ?? "no-manifest"
  ].join("|");
}

function aggregateGroup(group: ObservationGroup): AggregatedResourceSuggestion {
  const recommendations = group.observations.map((observation) => recommendAdaptiveResources(observation));
  const recommended = combineRecommendations(group.observations, recommendations);
  const failures = failureCounts(group.observations);
  const sampleCount = group.observations.length;
  return {
    key: group.key,
    provider: group.provider,
    ...(group.env_type ? { env_type: group.env_type } : {}),
    ...(group.repo_key ? { repo_key: group.repo_key } : {}),
    ...(group.source_id ? { source_id: group.source_id } : {}),
    ...(group.runtime ? { runtime: group.runtime } : {}),
    ...(group.image_id ? { image_id: group.image_id } : {}),
    ...(group.image_version ? { image_version: group.image_version } : {}),
    ...(group.manifest_hash ? { manifest_hash: group.manifest_hash } : {}),
    sample_count: sampleCount,
    pass_count: group.observations.filter((observation) => observation.passed).length,
    failure_counts: failures,
    p95_wall_seconds: percentile(group.observations.map((observation) => observation.usage.wall_seconds).filter(isFiniteNumber), 95),
    p95_peak_rss_gb: percentile(group.observations.map((observation) => observation.usage.peak_rss_gb).filter(isFiniteNumber), 95),
    p95_disk_gb: percentile(group.observations.map((observation) => observation.disk_usage?.total_gb).filter(isFiniteNumber), 95),
    p95_prepare_seconds: percentile(group.observations.map((observation) => observation.phase_seconds?.prepare_seconds).filter(isFiniteNumber), 95),
    p95_verify_seconds: percentile(group.observations.map((observation) => observation.phase_seconds?.verify_seconds).filter(isFiniteNumber), 95),
    recommended,
    confidence: confidenceFor(sampleCount, failures),
    reasons: [...new Set(recommendations.flatMap((recommendation) => recommendation.reasons))]
  };
}

function combineRecommendations(observations: ResourceObservation[], recommendations: AdaptiveResourceRecommendation[]): ResourceSpec {
  const recommended = recommendations.map((recommendation) => recommendation.recommended);
  const diskFromUsage = observations
    .map((observation) => observation.disk_usage?.total_gb)
    .filter(isFiniteNumber)
    .map((gb) => roundUpTier(gb * 1.4, [10, 20, 40, 80]));
  return {
    cpu: Math.max(...recommended.map((item) => item.cpu)),
    memoryGb: Math.max(...recommended.map((item) => item.memoryGb)),
    diskGb: Math.max(...recommended.map((item) => item.diskGb), ...diskFromUsage),
    timeoutSeconds: Math.max(...recommended.map((item) => item.timeoutSeconds))
  };
}

function failureCounts(observations: ResourceObservation[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const observation of observations) {
    counts[observation.failure_class] = (counts[observation.failure_class] ?? 0) + 1;
  }
  return counts;
}

function confidenceFor(sampleCount: number, failures: Record<string, number>): AggregatedResourceSuggestion["confidence"] {
  const resourceFailures = (failures.memory_limit ?? 0) + (failures.disk_full ?? 0) + (failures.cpu_limit ?? 0);
  if (sampleCount >= 5 && resourceFailures === 0) {
    return "high";
  }
  if (sampleCount >= 2) {
    return "medium";
  }
  return "low";
}

function suggestedConfig(rows: AggregatedResourceSuggestion[], minSamples: number): ResourcePolicyConfig {
  const config: ResourcePolicyConfig = {
    schema_version: 1,
    default_policy: "adaptive",
    provider_defaults: {},
    env_type_defaults: {},
    repo_overrides: {}
  };
  for (const row of rows.filter((item) => item.sample_count >= minSamples)) {
    if (row.repo_key) {
      config.repo_overrides ??= {};
      config.repo_overrides[row.repo_key] ??= {};
      config.repo_overrides[row.repo_key][row.provider] = row.recommended;
      continue;
    }
    if (row.env_type) {
      config.env_type_defaults ??= {};
      config.env_type_defaults[row.env_type] ??= {};
      config.env_type_defaults[row.env_type][row.provider] = row.recommended;
    }
  }
  return config;
}

function markdownReport(rows: AggregatedResourceSuggestion[], observationCount: number, minSamples: number): string {
  return [
    "# Resource Observation Report",
    "",
    `Generated: ${new Date().toISOString()}`,
    "",
    `Observations: ${observationCount}`,
    `Suggested config min samples: ${minSamples}`,
    "",
    "provider | scope | samples | passed | failures | p95 wall | p95 rss GB | p95 disk GB | recommended",
    "--- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---",
    ...rows.map((row) =>
      [
        row.provider,
        row.repo_key ?? row.env_type ?? "unknown",
        String(row.sample_count),
        String(row.pass_count),
        failureSummary(row.failure_counts),
        formatNumber(row.p95_wall_seconds),
        formatNumber(row.p95_peak_rss_gb),
        formatNumber(row.p95_disk_gb),
        formatSpec(row.recommended)
      ].join(" | ")
    ),
    ""
  ].join("\n");
}

function failureSummary(counts: Record<string, number>): string {
  return Object.entries(counts)
    .filter(([, count]) => count > 0)
    .map(([failure, count]) => `${failure}:${count}`)
    .join(", ");
}

function formatSpec(spec: ResourceSpec): string {
  return `${spec.cpu} CPU / ${spec.memoryGb} GB / ${spec.diskGb} GB disk / ${spec.timeoutSeconds}s`;
}

function formatNumber(value: number | undefined): string {
  return value === undefined || Number.isNaN(value) ? "-" : value.toFixed(2);
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

function percentile(values: number[], p: number): number | undefined {
  if (values.length === 0) {
    return undefined;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[index];
}

function roundUpTier(value: number, tiers: number[]): number {
  return tiers.find((tier) => tier >= value) ?? tiers.at(-1) ?? Math.ceil(value);
}

function isResourceObservation(value: unknown): value is ResourceObservation {
  return (
    isObject(value) &&
    typeof value.provider === "string" &&
    typeof value.resource_policy === "string" &&
    isObject(value.requested) &&
    isObject(value.effective) &&
    isObject(value.usage) &&
    typeof value.return_code === "number" &&
    typeof value.passed === "boolean" &&
    typeof value.failure_class === "string"
  );
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

async function main(): Promise<void> {
  const args = parseArgs(Bun.argv.slice(2));
  const observations = loadObservations(args);
  const rows = aggregateObservations(observations);
  const config = suggestedConfig(rows, args.minSamples);
  const payload = {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    observation_count: observations.length,
    group_count: rows.length,
    min_samples: args.minSamples,
    groups: rows,
    suggested_config: config
  };
  const content = args.format === "json" ? `${JSON.stringify(payload, null, 2)}\n` : markdownReport(rows, observations.length, args.minSamples);
  writeOutput(args.output, content);
  if (args.suggestedConfigOutput) {
    writeOutput(args.suggestedConfigOutput, `${JSON.stringify(config, null, 2)}\n`);
  }
}

if (import.meta.main) {
  await main();
}
