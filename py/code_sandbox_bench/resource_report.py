import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from code_sandbox_bench.resource_policy import recommend_adaptive_resources


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--suggested-config-output", type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--min-samples", type=int, default=2)
    return parser.parse_args()


def load_observations(args: argparse.Namespace) -> list[dict[str, Any]]:
    paths = [Path(item) for item in args.input.split(",") if item.strip()]
    if args.results_dir:
        paths.extend(path for path in args.results_dir.iterdir() if path.suffix in {".json", ".jsonl"})
    observations: list[dict[str, Any]] = []
    for path in paths:
        observations.extend(load_observation_file(path))
    return [item for item in observations if is_resource_observation(item)]


def load_observation_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Resource observation input not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    parsed = json.loads(text)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        observations = []
        if isinstance(parsed.get("resource_observation"), dict):
            observations.append(parsed["resource_observation"])
        if isinstance(parsed.get("results"), list):
            observations.extend(
                item["resource_observation"]
                for item in parsed["results"]
                if isinstance(item, dict) and isinstance(item.get("resource_observation"), dict)
            )
        return observations
    return []


def aggregate_observations(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for observation in observations:
        key = group_key(observation)
        group = groups.setdefault(
            key,
            {
                "key": key,
                "provider": observation.get("provider"),
                "env_type": observation.get("env_type"),
                "repo_key": observation.get("repo_key"),
                "source_id": observation.get("source_id"),
                "runtime": observation.get("runtime"),
                "image_id": observation.get("image_id"),
                "image_version": observation.get("image_version"),
                "manifest_hash": observation.get("manifest_hash"),
                "observations": [],
            },
        )
        group["observations"].append(observation)
    return sorted((aggregate_group(group) for group in groups.values()), key=lambda row: (str(row.get("provider")), row["key"]))


def group_key(observation: dict[str, Any]) -> str:
    return "|".join(
        [
            str(observation.get("provider") or "unknown-provider"),
            str(observation.get("env_type") or "unknown-env"),
            str(observation.get("repo_key") or observation.get("task_id") or "unknown-scope"),
            str(observation.get("runtime") or "unknown-runtime"),
            str(observation.get("image_id") or observation.get("docker_image") or "no-image"),
            str(observation.get("manifest_hash") or "no-manifest"),
        ]
    )


def aggregate_group(group: dict[str, Any]) -> dict[str, Any]:
    observations = group["observations"]
    recommendations = [recommend_adaptive_resources(observation) for observation in observations]
    failures = failure_counts(observations)
    row = {
        "key": group["key"],
        "provider": group.get("provider"),
        "sample_count": len(observations),
        "pass_count": sum(1 for observation in observations if observation.get("passed") is True),
        "failure_counts": failures,
        "p95_wall_seconds": percentile([number_at(observation, "usage", "wall_seconds") for observation in observations], 95),
        "p95_peak_rss_gb": percentile([number_at(observation, "usage", "peak_rss_gb") for observation in observations], 95),
        "p95_disk_gb": percentile([number_at(observation, "disk_usage", "total_gb") for observation in observations], 95),
        "p95_prepare_seconds": percentile([number_at(observation, "phase_seconds", "prepare_seconds") for observation in observations], 95),
        "p95_verify_seconds": percentile([number_at(observation, "phase_seconds", "verify_seconds") for observation in observations], 95),
        "recommended": combine_recommendations(observations, recommendations),
        "confidence": confidence_for(len(observations), failures),
        "reasons": sorted({reason for recommendation in recommendations for reason in recommendation.get("reasons", [])}),
    }
    for key in ("env_type", "repo_key", "source_id", "runtime", "image_id", "image_version", "manifest_hash"):
        if group.get(key):
            row[key] = group[key]
    return row


def combine_recommendations(observations: list[dict[str, Any]], recommendations: list[dict[str, Any]]) -> dict[str, int]:
    recommended = [item["recommended"] for item in recommendations if isinstance(item.get("recommended"), dict)]
    disk_from_usage = [
        round_up_tier(value * 1.4, [10, 20, 40, 80])
        for value in [number_at(observation, "disk_usage", "total_gb") for observation in observations]
        if is_finite_number(value)
    ]
    return {
        "cpu": max(int(item.get("cpu") or 1) for item in recommended),
        "memoryGb": max(int(item.get("memoryGb") or 1) for item in recommended),
        "diskGb": max([int(item.get("diskGb") or 10) for item in recommended] + disk_from_usage),
        "timeoutSeconds": max(int(item.get("timeoutSeconds") or 180) for item in recommended),
    }


def failure_counts(observations: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for observation in observations:
        key = str(observation.get("failure_class") or "none")
        counts[key] = counts.get(key, 0) + 1
    return counts


def confidence_for(sample_count: int, failures: dict[str, int]) -> str:
    resource_failures = failures.get("memory_limit", 0) + failures.get("disk_full", 0) + failures.get("cpu_limit", 0)
    if sample_count >= 5 and resource_failures == 0:
        return "high"
    if sample_count >= 2:
        return "medium"
    return "low"


def suggested_config(rows: list[dict[str, Any]], min_samples: int) -> dict[str, Any]:
    config: dict[str, Any] = {"schema_version": 1, "default_policy": "adaptive", "provider_defaults": {}, "env_type_defaults": {}, "repo_overrides": {}}
    for row in rows:
        if int(row["sample_count"]) < min_samples:
            continue
        provider = str(row["provider"])
        if row.get("repo_key"):
            config["repo_overrides"].setdefault(row["repo_key"], {})[provider] = row["recommended"]
        elif row.get("env_type"):
            config["env_type_defaults"].setdefault(row["env_type"], {})[provider] = row["recommended"]
    return config


def markdown_report(rows: list[dict[str, Any]], observation_count: int, min_samples: int) -> str:
    lines = [
        "# Resource Observation Report",
        "",
        f"Generated: {iso_now()}",
        "",
        f"Observations: {observation_count}",
        f"Suggested config min samples: {min_samples}",
        "",
        "provider | scope | samples | passed | failures | p95 wall | p95 rss GB | p95 disk GB | recommended",
        "--- | --- | ---: | ---: | --- | ---: | ---: | ---: | ---",
    ]
    for row in rows:
        lines.append(
            " | ".join(
                [
                    str(row.get("provider") or "-"),
                    str(row.get("repo_key") or row.get("env_type") or "unknown"),
                    str(row["sample_count"]),
                    str(row["pass_count"]),
                    failure_summary(row["failure_counts"]),
                    format_number(row.get("p95_wall_seconds")),
                    format_number(row.get("p95_peak_rss_gb")),
                    format_number(row.get("p95_disk_gb")),
                    format_spec(row["recommended"]),
                ]
            )
        )
    return "\n".join(lines + [""])


def is_resource_observation(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("provider"), str)
        and isinstance(value.get("resource_policy"), str)
        and isinstance(value.get("requested"), dict)
        and isinstance(value.get("effective"), dict)
        and isinstance(value.get("usage"), dict)
        and isinstance(value.get("return_code"), int)
        and isinstance(value.get("passed"), bool)
        and isinstance(value.get("failure_class"), str)
    )


def number_at(value: dict[str, Any], key: str, nested_key: str) -> float | None:
    nested = value.get(key)
    item = nested.get(nested_key) if isinstance(nested, dict) else None
    return float(item) if is_finite_number(item) else None


def percentile(values: list[float | None], p: int) -> float | None:
    numbers = sorted(float(value) for value in values if is_finite_number(value))
    if not numbers:
        return None
    index = min(len(numbers) - 1, math.ceil((p / 100) * len(numbers)) - 1)
    return numbers[index]


def round_up_tier(value: float, tiers: list[int]) -> int:
    return next((tier for tier in tiers if tier >= value), tiers[-1] if tiers else math.ceil(value))


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def failure_summary(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}:{count}" for key, count in counts.items() if count > 0)


def format_spec(spec: dict[str, Any]) -> str:
    return f"{spec['cpu']} CPU / {spec['memoryGb']} GB / {spec['diskGb']} GB disk / {spec['timeoutSeconds']}s"


def format_number(value: Any) -> str:
    return "-" if not is_finite_number(value) else f"{float(value):.2f}"


def write_output(path: Path | None, content: str) -> None:
    if path is None:
        print(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    args = parse_args()
    observations = load_observations(args)
    rows = aggregate_observations(observations)
    config = suggested_config(rows, args.min_samples)
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "observation_count": len(observations),
        "group_count": len(rows),
        "min_samples": args.min_samples,
        "groups": rows,
        "suggested_config": config,
    }
    content = json.dumps(payload, indent=2) + "\n" if args.format == "json" else markdown_report(rows, len(observations), args.min_samples)
    write_output(args.output, content)
    if args.suggested_config_output:
        write_output(args.suggested_config_output, json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    main()
