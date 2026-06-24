import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { ProviderName } from "./types";
import type { ResourceFailureClass } from "./resource_policy";

export type ConcurrencyPressureClass = "provider_quota" | "provider_rate_limit" | "provider_transport" | "none";

export type AdaptiveConcurrencyProviderState = {
  limit: number;
  requested_limit: number;
  static_limit: number;
  success_streak: number;
  pressure_events: number;
  last_pressure_class?: ConcurrencyPressureClass;
  last_pressure_at?: string;
  updated_at: string;
};

export type AdaptiveConcurrencyStateFile = {
  schema_version: 1;
  updated_at: string;
  providers: Partial<Record<ProviderName, AdaptiveConcurrencyProviderState>>;
};

export type AdaptiveConcurrencyFeedback = {
  pressure_class: ConcurrencyPressureClass;
  reason: string;
};

export type AdaptiveConcurrencyEvent = {
  provider: ProviderName;
  previous_limit: number;
  next_limit: number;
  pressure_class: ConcurrencyPressureClass;
  reason: string;
};

export type AdaptiveConcurrencySummary = {
  enabled: boolean;
  provider: ProviderName;
  requested_limit: number;
  static_limit: number;
  initial_limit: number;
  final_limit: number;
  state_path?: string;
  events: AdaptiveConcurrencyEvent[];
};

export const DEFAULT_ADAPTIVE_CONCURRENCY_STATE_PATH = resolve(import.meta.dir, "../../results/adaptive_concurrency_state.json");

const INCREASE_AFTER_CLEAN_COMPLETIONS = 5;

export class AdaptiveConcurrencyLimiter {
  private limit: number;
  private readonly initialLimit: number;
  private state: AdaptiveConcurrencyProviderState | undefined;
  private readonly events: AdaptiveConcurrencyEvent[] = [];

  constructor(
    private readonly provider: ProviderName,
    private readonly requestedLimit: number,
    private readonly staticLimit: number,
    private readonly options: { enabled: boolean; statePath?: string }
  ) {
    const loaded = options.enabled && options.statePath ? loadAdaptiveConcurrencyState(options.statePath).providers[provider] : undefined;
    this.state = loaded;
    this.limit = options.enabled ? clampLimit(loaded?.limit ?? staticLimit, staticLimit) : staticLimit;
    this.initialLimit = this.limit;
    this.persistState();
  }

  currentLimit(): number {
    return this.limit;
  }

  recordResult(result: Record<string, unknown>): AdaptiveConcurrencyEvent {
    const feedback = concurrencyFeedbackFromResult(result);
    const previousLimit = this.limit;
    if (this.options.enabled) {
      const current = this.providerState();
      if (feedback.pressure_class === "none") {
        current.success_streak += 1;
        if (current.success_streak >= INCREASE_AFTER_CLEAN_COMPLETIONS && this.limit < this.staticLimit) {
          this.limit += 1;
          current.success_streak = 0;
        }
      } else {
        this.limit = Math.max(1, Math.floor(this.limit / 2));
        current.success_streak = 0;
        current.pressure_events += 1;
        current.last_pressure_class = feedback.pressure_class;
        current.last_pressure_at = new Date().toISOString();
      }
      current.limit = this.limit;
      current.requested_limit = this.requestedLimit;
      current.static_limit = this.staticLimit;
      current.updated_at = new Date().toISOString();
      this.persistState();
    }
    const event = {
      provider: this.provider,
      previous_limit: previousLimit,
      next_limit: this.limit,
      pressure_class: feedback.pressure_class,
      reason: feedback.reason
    };
    this.events.push(event);
    return event;
  }

  summary(): AdaptiveConcurrencySummary {
    return {
      enabled: this.options.enabled,
      provider: this.provider,
      requested_limit: this.requestedLimit,
      static_limit: this.staticLimit,
      initial_limit: this.initialLimit,
      final_limit: this.limit,
      ...(this.options.statePath ? { state_path: this.options.statePath } : {}),
      events: this.events
    };
  }

  private providerState(): AdaptiveConcurrencyProviderState {
    if (!this.state) {
      this.state = {
        limit: this.limit,
        requested_limit: this.requestedLimit,
        static_limit: this.staticLimit,
        success_streak: 0,
        pressure_events: 0,
        updated_at: new Date().toISOString()
      };
    }
    return this.state;
  }

  private persistState(): void {
    if (!this.options.enabled || !this.options.statePath) {
      return;
    }
    const file = loadAdaptiveConcurrencyState(this.options.statePath);
    file.providers[this.provider] = this.providerState();
    file.updated_at = new Date().toISOString();
    mkdirSync(dirname(this.options.statePath), { recursive: true });
    writeFileSync(this.options.statePath, `${JSON.stringify(file, null, 2)}\n`);
  }
}

export function loadAdaptiveConcurrencyState(path: string): AdaptiveConcurrencyStateFile {
  if (!existsSync(path)) {
    return { schema_version: 1, updated_at: new Date().toISOString(), providers: {} };
  }
  const parsed = JSON.parse(readFileSync(path, "utf8")) as AdaptiveConcurrencyStateFile;
  if (parsed.schema_version !== 1 || typeof parsed.providers !== "object" || parsed.providers === null) {
    return { schema_version: 1, updated_at: new Date().toISOString(), providers: {} };
  }
  return parsed;
}

export function adaptiveLimitForProvider(
  provider: ProviderName,
  requestedLimit: number,
  staticLimit: number,
  statePath: string | undefined,
  enabled: boolean
): number {
  if (!enabled || !statePath) {
    return staticLimit;
  }
  const state = loadAdaptiveConcurrencyState(statePath).providers[provider];
  return clampLimit(state?.limit ?? staticLimit, Math.min(requestedLimit, staticLimit));
}

export function concurrencyFeedbackFromResult(result: Record<string, unknown>): AdaptiveConcurrencyFeedback {
  const observation = result.resource_observation as { failure_class?: ResourceFailureClass } | undefined;
  if (observation?.failure_class === "provider_quota") {
    return { pressure_class: "provider_quota", reason: "resource_observation.provider_quota" };
  }
  if (observation?.failure_class === "provider_rate_limit") {
    return { pressure_class: "provider_rate_limit", reason: "resource_observation.provider_rate_limit" };
  }
  const stderr = String(result.stderr_tail ?? "");
  if (/servicequotaexceeded|resource_exhausted|quota/i.test(stderr)) {
    return { pressure_class: "provider_quota", reason: "stderr.quota" };
  }
  if (/rate limit|too many requests|429/i.test(stderr)) {
    return { pressure_class: "provider_rate_limit", reason: "stderr.rate_limit" };
  }
  if (
    /Stream ended before command finished|Unable to connect|operation was aborted|operation timed out|Status code 410|Deadline exceeded|Failed to read exec stdio stream|UNAVAILABLE|Received RST_STREAM|Name resolution failed|ECONNREFUSED|No connection established/i.test(
      stderr
    )
  ) {
    return { pressure_class: "provider_transport", reason: "stderr.provider_transport" };
  }
  return { pressure_class: "none", reason: "clean_provider_completion" };
}

function clampLimit(value: number, maxLimit: number): number {
  return Math.max(1, Math.min(Math.max(1, Math.floor(maxLimit)), Math.floor(value)));
}
