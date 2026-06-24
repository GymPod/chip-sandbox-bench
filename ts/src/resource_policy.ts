import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { AgentTrace } from "./agent_trace";
import type { ProviderName, ResourcePolicyName, TaskEnv } from "./types";

export type ResourceSpec = {
  cpu: number;
  memoryGb: number;
  diskGb: number;
  timeoutSeconds: number;
};

export type ResourcePolicyConfig = {
  schema_version: 1;
  default_policy?: ResourcePolicyName;
  provider_defaults?: Partial<Record<ProviderName, Partial<ResourceSpec>>>;
  env_type_defaults?: Record<string, Partial<Record<ProviderName | "all", Partial<ResourceSpec>>>>;
  repo_overrides?: Record<string, Partial<Record<ProviderName | "all", Partial<ResourceSpec>>>>;
};

export type ResolvedResourceSpec = {
  requested: ResourceSpec;
  adaptive: ResourceSpec;
  effective: ResourceSpec;
  reasons: string[];
};

export type CommandUsageSummary = {
  command_count: number;
  wall_seconds: number;
  user_cpu_seconds?: number;
  system_cpu_seconds?: number;
  peak_rss_kb?: number;
  peak_rss_gb?: number;
  stdout_bytes: number;
  stderr_bytes: number;
  timed_out_count: number;
};

export type ResourceFailureClass =
  | "memory_limit"
  | "disk_full"
  | "cpu_limit"
  | "command_timeout"
  | "provider_quota"
  | "provider_rate_limit"
  | "none";

export type ResourceObservation = {
  schema_version: 1;
  observed_at: string;
  provider: ProviderName;
  resource_policy: ResourcePolicyName;
  dataset?: string;
  task_id?: string;
  env_type?: string;
  data_source?: string;
  repo_key?: string;
  source_id?: string;
  runtime?: string;
  docker_image?: string;
  image_id?: string;
  image_version?: string;
  manifest_hash?: string;
  requested: ResourceSpec;
  adaptive?: ResourceSpec;
  effective: ResourceSpec;
  concurrency?: number;
  resource_resolution_reasons?: string[];
  phase_seconds?: Record<string, number>;
  usage: CommandUsageSummary;
  disk_usage?: DiskUsageSummary;
  estimated_cost_usd?: number;
  static_estimated_cost_usd?: number;
  adaptive_estimated_cost_usd?: number;
  return_code: number;
  passed: boolean;
  failure_class: ResourceFailureClass;
};

export type DiskUsageSummary = {
  paths: Record<string, { kb: number; gb: number }>;
  total_kb: number;
  total_gb: number;
  workspace_kb?: number;
  workspace_gb?: number;
  testbed_kb?: number;
  testbed_gb?: number;
  cache_kb?: number;
  cache_gb?: number;
};

export type ResourceObservationContext = {
  observedAt?: string;
  dataset?: string;
  taskId?: string;
  taskEnv?: TaskEnv;
  runtime?: string;
  imageId?: string;
  imageVersion?: string;
  manifestHash?: string;
  requested: ResourceSpec;
  adaptive?: ResourceSpec;
  effective: ResourceSpec;
  concurrency?: number;
  resourceResolutionReasons?: string[];
  phaseSeconds?: Record<string, number>;
  diskUsage?: DiskUsageSummary;
  estimatedCostUsd?: number;
  staticEstimatedCostUsd?: number;
  adaptiveEstimatedCostUsd?: number;
};

export type AdaptiveResourceRecommendation = {
  policy: ResourcePolicyName;
  confidence: "none" | "low" | "medium" | "high";
  requested: ResourceSpec;
  recommended: ResourceSpec;
  failure_class: ResourceFailureClass;
  reasons: string[];
};

export type ResourceRetryDecision = {
  reason: string;
  previous: ResourceSpec;
  next: ResourceSpec;
};

const DEFAULT_MEMORY_TIERS_GB = [2, 4, 8, 16, 32];
const AWS_MICROVM_MEMORY_TIERS_GB = [1, 2, 4, 8, 16, 32];
const DISK_TIERS_GB = [10, 20, 40, 80];
const CPU_TIERS = [1, 2, 4, 8];
export const DEFAULT_RESOURCE_CONFIG_PATH = resolve(import.meta.dir, "../../data/resource_policy.json");

const configCache = new Map<string, ResourcePolicyConfig>();

export function loadResourcePolicyConfig(path: string = process.env.BENCH_RESOURCE_CONFIG ?? DEFAULT_RESOURCE_CONFIG_PATH): ResourcePolicyConfig {
  let cached = configCache.get(path);
  if (!cached) {
    cached = JSON.parse(readFileSync(path, "utf8")) as ResourcePolicyConfig;
    configCache.set(path, cached);
  }
  return cached;
}

export function resolveResourceSpec(
  provider: ProviderName,
  resourcePolicy: ResourcePolicyName,
  base: ResourceSpec,
  taskEnv: TaskEnv,
  config: ResourcePolicyConfig
): ResolvedResourceSpec {
  const requested = applyManifestFloor(base, taskEnv);
  const adaptive = applyConfig(requested, provider, taskEnv, config);
  return {
    requested,
    adaptive,
    effective: resourcePolicy === "adaptive" ? adaptive : requested,
    reasons: resourcePolicy === "adaptive" ? adaptiveReasons(requested, adaptive, taskEnv) : ["static_resource_policy"]
  };
}

export function summarizeTraceUsage(trace: AgentTrace): CommandUsageSummary {
  const usages = trace.events.flatMap((event) => (event.command_usage ? [event.command_usage] : []));
  const userCpuSeconds = sumDefined(usages.map((usage) => usage.user_cpu_seconds));
  const systemCpuSeconds = sumDefined(usages.map((usage) => usage.system_cpu_seconds));
  const peakRssKb = maxDefined(usages.map((usage) => usage.peak_rss_kb));
  return {
    command_count: usages.length,
    wall_seconds: sum(usages.map((usage) => usage.wall_seconds ?? 0)),
    ...(userCpuSeconds === undefined ? {} : { user_cpu_seconds: userCpuSeconds }),
    ...(systemCpuSeconds === undefined ? {} : { system_cpu_seconds: systemCpuSeconds }),
    ...(peakRssKb === undefined ? {} : { peak_rss_kb: peakRssKb, peak_rss_gb: peakRssKb / 1024 / 1024 }),
    stdout_bytes: sum(usages.map((usage) => usage.stdout_bytes ?? 0)),
    stderr_bytes: sum(usages.map((usage) => usage.stderr_bytes ?? 0)),
    timed_out_count: usages.filter((usage) => usage.timed_out).length
  };
}

export function buildResourceObservation(
  provider: ProviderName,
  resourcePolicy: ResourcePolicyName,
  context: ResourceObservationContext,
  trace: AgentTrace,
  returnCode: number,
  passed: boolean,
  stderr: string
): ResourceObservation {
  const usage = summarizeTraceUsage(trace);
  return {
    schema_version: 1,
    observed_at: context.observedAt ?? new Date().toISOString(),
    provider,
    resource_policy: resourcePolicy,
    ...(context.dataset ? { dataset: context.dataset } : {}),
    ...(context.taskId ? { task_id: context.taskId } : {}),
    ...(context.taskEnv?.envType ? { env_type: context.taskEnv.envType } : {}),
    ...(context.taskEnv?.dataSource ? { data_source: context.taskEnv.dataSource } : {}),
    ...(context.taskEnv?.repoKey ? { repo_key: context.taskEnv.repoKey } : {}),
    ...(context.taskEnv?.sourceId ? { source_id: context.taskEnv.sourceId } : {}),
    ...(context.runtime ? { runtime: context.runtime } : {}),
    ...(context.taskEnv?.dockerImage ? { docker_image: context.taskEnv.dockerImage } : {}),
    ...(context.imageId ? { image_id: context.imageId } : {}),
    ...(context.imageVersion ? { image_version: context.imageVersion } : {}),
    ...(context.manifestHash ? { manifest_hash: context.manifestHash } : {}),
    requested: context.requested,
    ...(context.adaptive ? { adaptive: context.adaptive } : {}),
    effective: context.effective,
    ...(context.concurrency === undefined ? {} : { concurrency: context.concurrency }),
    ...(context.resourceResolutionReasons ? { resource_resolution_reasons: context.resourceResolutionReasons } : {}),
    ...(context.phaseSeconds ? { phase_seconds: context.phaseSeconds } : {}),
    usage,
    ...(context.diskUsage ? { disk_usage: context.diskUsage } : {}),
    ...(context.estimatedCostUsd === undefined ? {} : { estimated_cost_usd: context.estimatedCostUsd }),
    ...(context.staticEstimatedCostUsd === undefined ? {} : { static_estimated_cost_usd: context.staticEstimatedCostUsd }),
    ...(context.adaptiveEstimatedCostUsd === undefined ? {} : { adaptive_estimated_cost_usd: context.adaptiveEstimatedCostUsd }),
    return_code: returnCode,
    passed,
    failure_class: classifyResourceFailure(returnCode, stderr, usage)
  };
}

export function recommendAdaptiveResources(observation: ResourceObservation): AdaptiveResourceRecommendation {
  const requested = observation.effective ?? observation.requested;
  const recommended: ResourceSpec = { ...requested };
  const reasons: string[] = [];
  let confidence: AdaptiveResourceRecommendation["confidence"] = "low";
  const memoryTiers = memoryTiersForProvider(observation.provider);

  if (observation.usage.peak_rss_gb !== undefined && Number.isFinite(observation.usage.peak_rss_gb)) {
    const memoryFromUsage = roundUpTier(
      Math.max(providerMinimumMemoryGb(observation.provider), observation.usage.peak_rss_gb * 1.5),
      memoryTiers
    );
    recommended.memoryGb = Math.max(providerMinimumMemoryGb(observation.provider), memoryFromUsage);
    confidence = "medium";
    reasons.push("observed_peak_rss");
  }

  if (observation.passed && observation.failure_class === "none") {
    const cpuFromUsage = cpuRecommendationFromUsage(observation, requested);
    if (cpuFromUsage !== undefined && cpuFromUsage < recommended.cpu) {
      recommended.cpu = cpuFromUsage;
      confidence = "medium";
      reasons.push("observed_cpu_seconds");
    }

    const diskFromUsage = diskRecommendationFromUsage(observation);
    if (diskFromUsage !== undefined && diskFromUsage < recommended.diskGb) {
      recommended.diskGb = diskFromUsage;
      confidence = "medium";
      reasons.push("observed_disk_high_water");
    }
  }

  if (observation.failure_class === "memory_limit") {
    recommended.memoryGb = nextTier(requested.memoryGb, memoryTiers);
    confidence = "high";
    reasons.push("memory_failure_retry_tier");
  }

  if (observation.failure_class === "disk_full") {
    recommended.diskGb = nextTier(requested.diskGb, DISK_TIERS_GB);
    confidence = "high";
    reasons.push("disk_failure_retry_tier");
  }

  if (observation.failure_class === "cpu_limit") {
    if (observation.provider === "aws-microvm") {
      recommended.memoryGb = nextTier(requested.memoryGb, memoryTiers);
    } else {
      recommended.cpu = nextTier(requested.cpu, CPU_TIERS);
    }
    confidence = "high";
    reasons.push(observation.provider === "aws-microvm" ? "cpu_failure_memory_retry_tier" : "cpu_failure_retry_tier");
  }

  if (observation.failure_class === "command_timeout") {
    recommended.timeoutSeconds = Math.min(Math.max(requested.timeoutSeconds * 2, requested.timeoutSeconds + 60), 1800);
    reasons.push("timeout_retry_tier");
    if (isCpuSaturated(observation)) {
      if (observation.provider === "aws-microvm") {
        recommended.memoryGb = nextTier(requested.memoryGb, memoryTiers);
      } else {
        recommended.cpu = nextTier(requested.cpu, CPU_TIERS);
      }
      reasons.push(observation.provider === "aws-microvm" ? "timeout_cpu_saturated_memory_retry_tier" : "timeout_cpu_saturated");
    }
    confidence = confidence === "medium" ? "medium" : "low";
  }

  if (reasons.length === 0) {
    reasons.push("no_resource_pressure_observed");
    confidence = observation.usage.command_count > 0 ? "low" : "none";
  }

  return {
    policy: observation.resource_policy,
    confidence,
    requested,
    recommended,
    failure_class: observation.failure_class,
    reasons
  };
}

export function resourceRetryDecision(
  recommendation: AdaptiveResourceRecommendation,
  attemptsAlreadyUsed: number
): ResourceRetryDecision | undefined {
  if (attemptsAlreadyUsed > 0) {
    return undefined;
  }
  if (recommendation.failure_class === "none" || recommendation.failure_class === "provider_quota" || recommendation.failure_class === "provider_rate_limit") {
    return undefined;
  }
  const previous = recommendation.requested;
  const next = recommendation.recommended;
  if (next.cpu <= previous.cpu && next.memoryGb <= previous.memoryGb && next.diskGb <= previous.diskGb && next.timeoutSeconds <= previous.timeoutSeconds) {
    return undefined;
  }
  return {
    reason: recommendation.reasons.join(","),
    previous,
    next
  };
}

export function classifyResourceFailure(
  returnCode: number,
  stderr: string,
  usage: Pick<CommandUsageSummary, "timed_out_count"> = { timed_out_count: 0 }
): ResourceFailureClass {
  const text = stderr.toLowerCase();
  if (/total memory limit exceeded|out of memory|oom|cannot allocate memory|memoryerror|killed/.test(text)) {
    return "memory_limit";
  }
  if (/no space left on device|disk quota exceeded|enospc/.test(text)) {
    return "disk_full";
  }
  if (/total cpu limit exceeded|cpu limit/.test(text)) {
    return "cpu_limit";
  }
  if (/servicequotaexceeded|resource_exhausted|quota/.test(text)) {
    return "provider_quota";
  }
  if (/rate limit|too many requests|429/.test(text)) {
    return "provider_rate_limit";
  }
  if (returnCode === 124 || usage.timed_out_count > 0 || /timed out after|deadline exceeded/.test(text)) {
    return "command_timeout";
  }
  return "none";
}

function providerMinimumMemoryGb(provider: ProviderName): number {
  return provider === "aws-microvm" ? 1 : 2;
}

function memoryTiersForProvider(provider: ProviderName): number[] {
  return provider === "aws-microvm" ? AWS_MICROVM_MEMORY_TIERS_GB : DEFAULT_MEMORY_TIERS_GB;
}

function isCpuSaturated(observation: ResourceObservation): boolean {
  const user = observation.usage.user_cpu_seconds ?? 0;
  const system = observation.usage.system_cpu_seconds ?? 0;
  const requested = observation.effective ?? observation.requested;
  if (observation.usage.wall_seconds <= 0 || user + system <= 0) {
    return false;
  }
  return (user + system) / observation.usage.wall_seconds >= requested.cpu * 0.85;
}

function cpuRecommendationFromUsage(observation: ResourceObservation, requested: ResourceSpec): number | undefined {
  if (observation.provider === "aws-microvm") {
    return undefined;
  }
  const user = observation.usage.user_cpu_seconds ?? 0;
  const system = observation.usage.system_cpu_seconds ?? 0;
  const wall = observation.usage.wall_seconds;
  if (requested.cpu <= 1 || wall <= 0 || user + system <= 0) {
    return undefined;
  }
  return roundUpTier(Math.max(1, ((user + system) / wall) * 1.5), CPU_TIERS);
}

function diskRecommendationFromUsage(observation: ResourceObservation): number | undefined {
  const totalGb = observation.disk_usage?.total_gb;
  if (totalGb === undefined || !Number.isFinite(totalGb)) {
    return undefined;
  }
  return roundUpTier(Math.max(10, totalGb * 1.4), DISK_TIERS_GB);
}

function roundUpTier(value: number, tiers: number[]): number {
  return tiers.find((tier) => tier >= value) ?? tiers.at(-1) ?? value;
}

function nextTier(current: number, tiers: number[]): number {
  return tiers.find((tier) => tier > current) ?? current;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function sumDefined(values: Array<number | undefined>): number | undefined {
  const defined = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return defined.length === 0 ? undefined : sum(defined);
}

function maxDefined(values: Array<number | undefined>): number | undefined {
  const defined = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  return defined.length === 0 ? undefined : Math.max(...defined);
}

function applyManifestFloor(base: ResourceSpec, taskEnv: TaskEnv): ResourceSpec {
  return {
    cpu: Math.max(base.cpu, taskEnv.resources?.cpu ?? 0),
    memoryGb: Math.max(base.memoryGb, taskEnv.resources?.memoryGb ?? 0),
    diskGb: Math.max(base.diskGb, taskEnv.resources?.diskGb ?? 0),
    timeoutSeconds: base.timeoutSeconds
  };
}

function applyConfig(base: ResourceSpec, provider: ProviderName, taskEnv: TaskEnv, config: ResourcePolicyConfig): ResourceSpec {
  let resolved: ResourceSpec = { ...base };
  resolved = mergeSpec(resolved, config.provider_defaults?.[provider]);
  resolved = mergeProviderScopedSpec(resolved, config.env_type_defaults?.[taskEnv.envType], provider);
  if (taskEnv.repoKey) {
    resolved = mergeProviderScopedSpec(resolved, config.repo_overrides?.[taskEnv.repoKey], provider);
  }
  return resolved;
}

function mergeProviderScopedSpec(
  base: ResourceSpec,
  scoped: Partial<Record<ProviderName | "all", Partial<ResourceSpec>>> | undefined,
  provider: ProviderName
): ResourceSpec {
  return mergeSpec(mergeSpec(base, scoped?.all), scoped?.[provider]);
}

function mergeSpec(base: ResourceSpec, override: Partial<ResourceSpec> | undefined): ResourceSpec {
  return {
    cpu: override?.cpu ?? base.cpu,
    memoryGb: override?.memoryGb ?? base.memoryGb,
    diskGb: override?.diskGb ?? base.diskGb,
    timeoutSeconds: override?.timeoutSeconds ?? base.timeoutSeconds
  };
}

function adaptiveReasons(requested: ResourceSpec, adaptive: ResourceSpec, taskEnv: TaskEnv): string[] {
  const reasons: string[] = [];
  if (adaptive.cpu !== requested.cpu) {
    reasons.push(`cpu:${requested.cpu}->${adaptive.cpu}`);
  }
  if (adaptive.memoryGb !== requested.memoryGb) {
    reasons.push(`memoryGb:${requested.memoryGb}->${adaptive.memoryGb}`);
  }
  if (adaptive.diskGb !== requested.diskGb) {
    reasons.push(`diskGb:${requested.diskGb}->${adaptive.diskGb}`);
  }
  if (adaptive.timeoutSeconds !== requested.timeoutSeconds) {
    reasons.push(`timeoutSeconds:${requested.timeoutSeconds}->${adaptive.timeoutSeconds}`);
  }
  if (taskEnv.repoKey) {
    reasons.push(`repo:${taskEnv.repoKey}`);
  } else {
    reasons.push(`env:${taskEnv.envType}`);
  }
  return reasons;
}
