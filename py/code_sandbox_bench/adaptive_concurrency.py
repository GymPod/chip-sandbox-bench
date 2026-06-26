import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADAPTIVE_CONCURRENCY_STATE_PATH = ROOT / "results" / "adaptive_concurrency_state.json"
INCREASE_AFTER_CLEAN_COMPLETIONS = 5


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AdaptiveConcurrencyLimiter:
    def __init__(self, provider: str, requested_limit: int, static_limit: int, enabled: bool, state_path: Path | None) -> None:
        self.provider = provider
        self.requested_limit = requested_limit
        self.static_limit = max(1, static_limit)
        self.enabled = enabled
        self.state_path = state_path
        self.events: list[dict[str, Any]] = []
        loaded = load_adaptive_concurrency_state(state_path).get("providers", {}).get(provider) if enabled and state_path else None
        self.state = loaded if isinstance(loaded, dict) else None
        self.limit = clamp_limit(int(self.state.get("limit", self.static_limit)) if self.state else self.static_limit, self.static_limit)
        self.initial_limit = self.limit
        self._persist_state()

    def current_limit(self) -> int:
        return self.limit

    def record_result(self, result: dict[str, Any]) -> dict[str, Any]:
        feedback = concurrency_feedback_from_result(result)
        previous = self.limit
        if self.enabled:
            current = self._provider_state()
            if feedback["pressure_class"] == "none":
                current["success_streak"] = int(current.get("success_streak") or 0) + 1
                if current["success_streak"] >= INCREASE_AFTER_CLEAN_COMPLETIONS and self.limit < self.static_limit:
                    self.limit += 1
                    current["success_streak"] = 0
            else:
                self.limit = max(1, self.limit // 2)
                current["success_streak"] = 0
                current["pressure_events"] = int(current.get("pressure_events") or 0) + 1
                current["last_pressure_class"] = feedback["pressure_class"]
                current["last_pressure_at"] = iso_now()
            current["limit"] = self.limit
            current["requested_limit"] = self.requested_limit
            current["static_limit"] = self.static_limit
            current["updated_at"] = iso_now()
            self._persist_state()
        event = {
            "provider": self.provider,
            "previous_limit": previous,
            "next_limit": self.limit,
            "pressure_class": feedback["pressure_class"],
            "reason": feedback["reason"],
        }
        self.events.append(event)
        return event

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "requested_limit": self.requested_limit,
            "static_limit": self.static_limit,
            "initial_limit": self.initial_limit,
            "final_limit": self.limit,
            **({"state_path": str(self.state_path)} if self.state_path else {}),
            "events": self.events,
        }

    def _provider_state(self) -> dict[str, Any]:
        if self.state is None:
            self.state = {
                "limit": self.limit,
                "requested_limit": self.requested_limit,
                "static_limit": self.static_limit,
                "success_streak": 0,
                "pressure_events": 0,
                "updated_at": iso_now(),
            }
        return self.state

    def _persist_state(self) -> None:
        if not self.enabled or self.state_path is None:
            return
        payload = load_adaptive_concurrency_state(self.state_path)
        payload.setdefault("providers", {})[self.provider] = self._provider_state()
        payload["updated_at"] = iso_now()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_adaptive_concurrency_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"schema_version": 1, "updated_at": iso_now(), "providers": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "updated_at": iso_now(), "providers": {}}
    if not isinstance(parsed, dict) or parsed.get("schema_version") != 1 or not isinstance(parsed.get("providers"), dict):
        return {"schema_version": 1, "updated_at": iso_now(), "providers": {}}
    return parsed


def adaptive_limit_for_provider(
    provider: str,
    requested_limit: int,
    static_limit: int,
    state_path: Path | None,
    enabled: bool,
) -> int:
    if not enabled or state_path is None:
        return static_limit
    state = load_adaptive_concurrency_state(state_path).get("providers", {}).get(provider)
    value = state.get("limit", static_limit) if isinstance(state, dict) else static_limit
    return clamp_limit(int(value), min(requested_limit, static_limit))


def concurrency_feedback_from_result(result: dict[str, Any]) -> dict[str, str]:
    observation = result.get("resource_observation")
    failure_class = observation.get("failure_class") if isinstance(observation, dict) else None
    if failure_class == "provider_quota":
        return {"pressure_class": "provider_quota", "reason": "resource_observation.provider_quota"}
    if failure_class == "provider_rate_limit":
        return {"pressure_class": "provider_rate_limit", "reason": "resource_observation.provider_rate_limit"}
    stderr = str(result.get("stderr_tail") or "")
    lowered = stderr.lower()
    if any(token in lowered for token in ["servicequotaexceeded", "resource_exhausted", "quota"]):
        return {"pressure_class": "provider_quota", "reason": "stderr.quota"}
    if any(token in lowered for token in ["rate limit", "too many requests", "429"]):
        return {"pressure_class": "provider_rate_limit", "reason": "stderr.rate_limit"}
    transport_patterns = [
        "stream ended before command finished",
        "unable to connect",
        "operation was aborted",
        "operation timed out",
        "status code 410",
        "deadline exceeded",
        "failed to read exec stdio stream",
        "unavailable",
        "received rst_stream",
        "name resolution failed",
        "econnrefused",
        "no connection established",
    ]
    if any(pattern in lowered for pattern in transport_patterns):
        return {"pressure_class": "provider_transport", "reason": "stderr.provider_transport"}
    return {"pressure_class": "none", "reason": "clean_provider_completion"}


def static_worker_count(provider: str, task_env_types: list[str], requested: int, task_count: int, memory_gb: int) -> int:
    limit = max(1, min(requested, task_count))
    if provider == "daytona" and "harbor_swesmith" in task_env_types:
        return 1
    if provider == "aws-microvm":
        account_memory_gb = float(os.environ.get("AWS_MICROVM_ACCOUNT_MEMORY_GB", "4"))
        memory_cap = max(1, int(account_memory_gb // max(1, memory_gb)))
        max_concurrency = int(os.environ.get("AWS_MICROVM_MAX_CONCURRENCY", "1"))
        return min(limit, max_concurrency, memory_cap)
    return limit


def clamp_limit(value: int, max_limit: int) -> int:
    return max(1, min(max(1, int(max_limit)), int(value)))
