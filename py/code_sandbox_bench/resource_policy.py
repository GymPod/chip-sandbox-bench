import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from code_sandbox_bench.task_env import TaskEnv


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESOURCE_CONFIG_PATH = ROOT / "data" / "resource_policy.json"
DEFAULT_MEMORY_TIERS_GB = [2, 4, 8, 16, 32]
AWS_MICROVM_MEMORY_TIERS_GB = [1, 2, 4, 8, 16, 32]
DISK_TIERS_GB = [10, 20, 40, 80]
CPU_TIERS = [1, 2, 4, 8]
_CONFIG_CACHE: dict[Path, dict[str, Any]] = {}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_resource_policy_config(path: Path | str | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_RESOURCE_CONFIG_PATH
    if config_path not in _CONFIG_CACHE:
        _CONFIG_CACHE[config_path] = json.loads(config_path.read_text(encoding="utf-8"))
    return _CONFIG_CACHE[config_path]


def resource_spec(cpu: int, memory_gb: int, disk_gb: int, timeout_seconds: int) -> dict[str, int]:
    return {"cpu": cpu, "memoryGb": memory_gb, "diskGb": disk_gb, "timeoutSeconds": timeout_seconds}


def resolve_resource_spec(
    provider: str,
    resource_policy: str,
    base: dict[str, int],
    task_env: TaskEnv,
    config: dict[str, Any],
) -> dict[str, Any]:
    requested = apply_manifest_floor(base, task_env)
    adaptive = apply_config(requested, provider, task_env, config)
    return {
        "requested": requested,
        "adaptive": adaptive,
        "effective": adaptive if resource_policy == "adaptive" else requested,
        "reasons": adaptive_reasons(requested, adaptive, task_env) if resource_policy == "adaptive" else ["static_resource_policy"],
    }


def summarize_trace_usage(trace: dict[str, Any]) -> dict[str, Any]:
    usages = [
        event.get("command_usage")
        for event in trace.get("events", [])
        if isinstance(event, dict) and isinstance(event.get("command_usage"), dict)
    ]
    user_cpu_seconds = sum_defined([usage.get("user_cpu_seconds") for usage in usages])
    system_cpu_seconds = sum_defined([usage.get("system_cpu_seconds") for usage in usages])
    peak_rss_kb = max_defined([usage.get("peak_rss_kb") for usage in usages])
    summary: dict[str, Any] = {
        "command_count": len(usages),
        "wall_seconds": sum(float(usage.get("wall_seconds") or 0) for usage in usages),
        "stdout_bytes": sum(int(usage.get("stdout_bytes") or 0) for usage in usages),
        "stderr_bytes": sum(int(usage.get("stderr_bytes") or 0) for usage in usages),
        "timed_out_count": sum(1 for usage in usages if usage.get("timed_out")),
    }
    if user_cpu_seconds is not None:
        summary["user_cpu_seconds"] = user_cpu_seconds
    if system_cpu_seconds is not None:
        summary["system_cpu_seconds"] = system_cpu_seconds
    if peak_rss_kb is not None:
        summary["peak_rss_kb"] = peak_rss_kb
        summary["peak_rss_gb"] = peak_rss_kb / 1024 / 1024
    return summary


def build_resource_observation(
    provider: str,
    resource_policy: str,
    context: dict[str, Any],
    trace: dict[str, Any],
    return_code: int,
    passed: bool,
    stderr: str,
) -> dict[str, Any]:
    usage = summarize_trace_usage(trace)
    task_env = context.get("task_env")
    observation: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": context.get("observed_at") or iso_now(),
        "provider": provider,
        "resource_policy": resource_policy,
        "requested": context["requested"],
        "effective": context["effective"],
        "usage": usage,
        "return_code": return_code,
        "passed": passed,
        "failure_class": classify_resource_failure(return_code, stderr, usage),
    }
    optional_fields = {
        "dataset": context.get("dataset"),
        "task_id": context.get("task_id"),
        "runtime": context.get("runtime"),
        "image_id": context.get("image_id"),
        "image_version": context.get("image_version"),
        "manifest_hash": context.get("manifest_hash"),
        "adaptive": context.get("adaptive"),
        "concurrency": context.get("concurrency"),
        "resource_resolution_reasons": context.get("resource_resolution_reasons"),
        "phase_seconds": context.get("phase_seconds"),
        "disk_usage": context.get("disk_usage"),
        "estimated_cost_usd": context.get("estimated_cost_usd"),
        "static_estimated_cost_usd": context.get("static_estimated_cost_usd"),
        "adaptive_estimated_cost_usd": context.get("adaptive_estimated_cost_usd"),
    }
    if isinstance(task_env, TaskEnv):
        optional_fields.update(
            {
                "env_type": task_env.env_type,
                "data_source": task_env.data_source,
                "repo_key": task_env.repo_key,
                "source_id": task_env.source_id,
                "docker_image": task_env.docker_image,
            }
        )
    for key, value in optional_fields.items():
        if value is not None:
            observation[key] = value
    return observation


def recommend_adaptive_resources(observation: dict[str, Any]) -> dict[str, Any]:
    requested = dict(observation.get("effective") or observation.get("requested") or {})
    recommended = dict(requested)
    reasons: list[str] = []
    confidence = "low"
    provider = str(observation.get("provider") or "")
    usage = observation.get("usage") if isinstance(observation.get("usage"), dict) else {}
    memory_tiers = memory_tiers_for_provider(provider)

    peak_rss_gb = usage.get("peak_rss_gb")
    if is_finite_number(peak_rss_gb):
        memory_from_usage = round_up_tier(max(provider_minimum_memory_gb(provider), float(peak_rss_gb) * 1.5), memory_tiers)
        recommended["memoryGb"] = max(provider_minimum_memory_gb(provider), memory_from_usage)
        confidence = "medium"
        reasons.append("observed_peak_rss")

    if observation.get("passed") is True and observation.get("failure_class") == "none":
        cpu_from_usage = cpu_recommendation_from_usage(observation, requested)
        if cpu_from_usage is not None and cpu_from_usage < int(recommended.get("cpu") or 0):
            recommended["cpu"] = cpu_from_usage
            confidence = "medium"
            reasons.append("observed_cpu_seconds")
        disk_from_usage = disk_recommendation_from_usage(observation)
        if disk_from_usage is not None and disk_from_usage < int(recommended.get("diskGb") or 0):
            recommended["diskGb"] = disk_from_usage
            confidence = "medium"
            reasons.append("observed_disk_high_water")

    failure_class = str(observation.get("failure_class") or "none")
    if failure_class == "memory_limit":
        recommended["memoryGb"] = next_tier(int(requested.get("memoryGb") or 0), memory_tiers)
        confidence = "high"
        reasons.append("memory_failure_retry_tier")
    if failure_class == "disk_full":
        recommended["diskGb"] = next_tier(int(requested.get("diskGb") or 0), DISK_TIERS_GB)
        confidence = "high"
        reasons.append("disk_failure_retry_tier")
    if failure_class == "cpu_limit":
        if provider == "aws-microvm":
            recommended["memoryGb"] = next_tier(int(requested.get("memoryGb") or 0), memory_tiers)
            reasons.append("cpu_failure_memory_retry_tier")
        else:
            recommended["cpu"] = next_tier(int(requested.get("cpu") or 0), CPU_TIERS)
            reasons.append("cpu_failure_retry_tier")
        confidence = "high"
    if failure_class == "command_timeout":
        timeout = int(requested.get("timeoutSeconds") or 0)
        recommended["timeoutSeconds"] = min(max(timeout * 2, timeout + 60), 1800)
        reasons.append("timeout_retry_tier")
        if is_cpu_saturated(observation):
            if provider == "aws-microvm":
                recommended["memoryGb"] = next_tier(int(requested.get("memoryGb") or 0), memory_tiers)
                reasons.append("timeout_cpu_saturated_memory_retry_tier")
            else:
                recommended["cpu"] = next_tier(int(requested.get("cpu") or 0), CPU_TIERS)
                reasons.append("timeout_cpu_saturated")
        if confidence != "medium":
            confidence = "low"

    if not reasons:
        reasons.append("no_resource_pressure_observed")
        confidence = "low" if int(usage.get("command_count") or 0) > 0 else "none"

    return {
        "policy": observation.get("resource_policy"),
        "confidence": confidence,
        "requested": requested,
        "recommended": recommended,
        "failure_class": failure_class,
        "reasons": reasons,
    }


def resource_retry_decision(recommendation: dict[str, Any], attempts_already_used: int) -> dict[str, Any] | None:
    if attempts_already_used > 0:
        return None
    if recommendation.get("failure_class") in {"none", "provider_quota", "provider_rate_limit"}:
        return None
    previous = recommendation.get("requested")
    next_spec = recommendation.get("recommended")
    if not isinstance(previous, dict) or not isinstance(next_spec, dict):
        return None
    if (
        int(next_spec.get("cpu") or 0) <= int(previous.get("cpu") or 0)
        and int(next_spec.get("memoryGb") or 0) <= int(previous.get("memoryGb") or 0)
        and int(next_spec.get("diskGb") or 0) <= int(previous.get("diskGb") or 0)
        and int(next_spec.get("timeoutSeconds") or 0) <= int(previous.get("timeoutSeconds") or 0)
    ):
        return None
    return {"reason": ",".join(str(reason) for reason in recommendation.get("reasons", [])), "previous": previous, "next": next_spec}


def classify_resource_failure(return_code: int, stderr: str, usage: dict[str, Any] | None = None) -> str:
    text = stderr.lower()
    if any(token in text for token in ["total memory limit exceeded", "out of memory", "oom", "cannot allocate memory", "memoryerror", "killed"]):
        return "memory_limit"
    if any(token in text for token in ["no space left on device", "disk quota exceeded", "enospc"]):
        return "disk_full"
    if "total cpu limit exceeded" in text or "cpu limit" in text:
        return "cpu_limit"
    if any(token in text for token in ["servicequotaexceeded", "resource_exhausted", "quota"]):
        return "provider_quota"
    if any(token in text for token in ["rate limit", "too many requests", "429"]):
        return "provider_rate_limit"
    timed_out_count = int((usage or {}).get("timed_out_count") or 0)
    if return_code == 124 or timed_out_count > 0 or "timed out after" in text or "deadline exceeded" in text:
        return "command_timeout"
    return "none"


def apply_manifest_floor(base: dict[str, int], task_env: TaskEnv) -> dict[str, int]:
    resources = task_env.resources or {}
    return {
        "cpu": max(int(base["cpu"]), int(resources.get("cpu") or 0)),
        "memoryGb": max(int(base["memoryGb"]), int(resources.get("memoryGb") or 0)),
        "diskGb": max(int(base["diskGb"]), int(resources.get("diskGb") or 0)),
        "timeoutSeconds": int(base["timeoutSeconds"]),
    }


def apply_config(base: dict[str, int], provider: str, task_env: TaskEnv, config: dict[str, Any]) -> dict[str, int]:
    resolved = dict(base)
    resolved = merge_spec(resolved, scoped_dict(config.get("provider_defaults")).get(provider))
    resolved = merge_provider_scoped_spec(resolved, scoped_dict(config.get("env_type_defaults")).get(task_env.env_type), provider)
    if task_env.repo_key:
        resolved = merge_provider_scoped_spec(resolved, scoped_dict(config.get("repo_overrides")).get(task_env.repo_key), provider)
    return resolved


def merge_provider_scoped_spec(base: dict[str, int], scoped: Any, provider: str) -> dict[str, int]:
    scoped_map = scoped if isinstance(scoped, dict) else {}
    return merge_spec(merge_spec(base, scoped_map.get("all")), scoped_map.get(provider))


def merge_spec(base: dict[str, int], override: Any) -> dict[str, int]:
    if not isinstance(override, dict):
        return dict(base)
    return {
        "cpu": int(override.get("cpu", base["cpu"])),
        "memoryGb": int(override.get("memoryGb", base["memoryGb"])),
        "diskGb": int(override.get("diskGb", base["diskGb"])),
        "timeoutSeconds": int(override.get("timeoutSeconds", base["timeoutSeconds"])),
    }


def adaptive_reasons(requested: dict[str, int], adaptive: dict[str, int], task_env: TaskEnv) -> list[str]:
    reasons = []
    for key in ("cpu", "memoryGb", "diskGb", "timeoutSeconds"):
        if adaptive[key] != requested[key]:
            reasons.append(f"{key}:{requested[key]}->{adaptive[key]}")
    reasons.append(f"repo:{task_env.repo_key}" if task_env.repo_key else f"env:{task_env.env_type}")
    return reasons


def provider_minimum_memory_gb(provider: str) -> int:
    return 1 if provider == "aws-microvm" else 2


def memory_tiers_for_provider(provider: str) -> list[int]:
    return AWS_MICROVM_MEMORY_TIERS_GB if provider == "aws-microvm" else DEFAULT_MEMORY_TIERS_GB


def is_cpu_saturated(observation: dict[str, Any]) -> bool:
    usage = observation.get("usage") if isinstance(observation.get("usage"), dict) else {}
    requested = observation.get("effective") or observation.get("requested") or {}
    wall_seconds = float(usage.get("wall_seconds") or 0)
    cpu_seconds = float(usage.get("user_cpu_seconds") or 0) + float(usage.get("system_cpu_seconds") or 0)
    cpu = float(requested.get("cpu") or 0)
    return wall_seconds > 0 and cpu_seconds > 0 and cpu_seconds / wall_seconds >= cpu * 0.85


def cpu_recommendation_from_usage(observation: dict[str, Any], requested: dict[str, Any]) -> int | None:
    if observation.get("provider") == "aws-microvm":
        return None
    usage = observation.get("usage") if isinstance(observation.get("usage"), dict) else {}
    wall = float(usage.get("wall_seconds") or 0)
    cpu_seconds = float(usage.get("user_cpu_seconds") or 0) + float(usage.get("system_cpu_seconds") or 0)
    if int(requested.get("cpu") or 0) <= 1 or wall <= 0 or cpu_seconds <= 0:
        return None
    return round_up_tier(max(1, (cpu_seconds / wall) * 1.5), CPU_TIERS)


def disk_recommendation_from_usage(observation: dict[str, Any]) -> int | None:
    disk_usage = observation.get("disk_usage") if isinstance(observation.get("disk_usage"), dict) else {}
    total_gb = disk_usage.get("total_gb")
    if not is_finite_number(total_gb):
        return None
    return round_up_tier(max(10, float(total_gb) * 1.4), DISK_TIERS_GB)


def round_up_tier(value: float, tiers: list[int]) -> int:
    return next((tier for tier in tiers if tier >= value), tiers[-1] if tiers else math.ceil(value))


def next_tier(current: int, tiers: list[int]) -> int:
    return next((tier for tier in tiers if tier > current), current)


def sum_defined(values: list[Any]) -> float | None:
    numbers = [float(value) for value in values if is_finite_number(value)]
    return sum(numbers) if numbers else None


def max_defined(values: list[Any]) -> float | None:
    numbers = [float(value) for value in values if is_finite_number(value)]
    return max(numbers) if numbers else None


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def scoped_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
