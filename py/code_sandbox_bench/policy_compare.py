import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from code_sandbox_bench.cost_model import estimate_cost
from code_sandbox_bench.dataset import BenchTask, select_tasks
from code_sandbox_bench.resource_policy import load_resource_policy_config, resolve_resource_spec, resource_spec
from code_sandbox_bench.task_env import resolve_task_env


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "data" / "terminalbench_2026_03_05_smoke16.jsonl"
DEFAULT_CONFIG = ROOT / "data" / "resource_policy.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", "--input", default="")
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--baseline-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--candidate-config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--resource-policy", choices=["static", "observe", "adaptive"], default="adaptive")
    parser.add_argument("--task-index", default="all")
    parser.add_argument("--task-limit", type=int)
    parser.add_argument("--cpu", type=int, default=2)
    parser.add_argument("--memory-gb", type=int)
    parser.add_argument("--disk-gb", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--runtime")
    return parser.parse_args()


def result_paths(args: argparse.Namespace) -> list[Path]:
    paths = [Path(item) for item in args.results.split(",") if item.strip()]
    if args.results_dir:
        paths.extend(path for path in args.results_dir.iterdir() if path.suffix == ".json")
    if not paths:
        raise ValueError("No result inputs. Use --results or --results-dir.")
    return [path.resolve() for path in paths]


def load_run(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Result input not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("provider") or not isinstance(data.get("results"), list):
        raise ValueError(f"Unsupported benchmark result file: {path}")
    return {"path": str(path), "data": data}


def task_map(args: argparse.Namespace) -> dict[str, BenchTask]:
    return {task.task_id: task for task in select_tasks(args.dataset, args.task_index, args.task_limit)}


def compare_run(
    run: dict[str, Any],
    tasks: dict[str, BenchTask],
    baseline_config: dict[str, Any],
    candidate_config: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    data = run["data"]
    rows = [row for row in data["results"] if isinstance(row, dict) and is_finite_number(row.get("elapsed_seconds"))]
    compared_tasks = [compare_task(data, row, tasks, baseline_config, candidate_config, args) for row in rows]
    baseline_cost = sum(float(task["baseline_cost_usd"]) for task in compared_tasks)
    candidate_cost = sum(float(task["candidate_cost_usd"]) for task in compared_tasks)
    return {
        "path": run["path"],
        "provider": data["provider"],
        **({"mode": data["mode"]} if data.get("mode") else {}),
        **({"kind": data["kind"]} if data.get("kind") else {}),
        "task_count": len(compared_tasks),
        **({"passed": data["passed"]} if isinstance(data.get("passed"), int) else {}),
        **({"input_estimated_cost_usd": data["estimated_cost_usd"]} if is_finite_number(data.get("estimated_cost_usd")) else {}),
        "baseline_cost_usd": baseline_cost,
        "candidate_cost_usd": candidate_cost,
        "reduction_usd": baseline_cost - candidate_cost,
        "reduction_pct": pct_reduction(baseline_cost, candidate_cost),
        "resource_change_counts": resource_change_counts(compared_tasks),
        "tasks": compared_tasks,
    }


def compare_task(
    run: dict[str, Any],
    row: dict[str, Any],
    tasks: dict[str, BenchTask],
    baseline_config: dict[str, Any],
    candidate_config: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    task_id = str(row["task_id"])
    task = tasks.get(task_id)
    if task is None:
        raise ValueError(f"Task {task_id} from result file was not found in dataset {args.dataset}")
    provider = str(run["provider"])
    runtime = str(run.get("runtime") or args.runtime or default_runtime(provider))
    task_env = resolve_task_env(task, runtime, provider)
    base = base_resource_spec(provider, args)
    baseline = resolve_resource_spec(provider, args.resource_policy, base, task_env, baseline_config)["effective"]
    candidate = resolve_resource_spec(provider, args.resource_policy, base, task_env, candidate_config)["effective"]
    elapsed = float(row["elapsed_seconds"])
    baseline_cost = estimate_cost(provider, elapsed, int(baseline["cpu"]), int(baseline["memoryGb"]), billable_disk_gb(provider, int(baseline["diskGb"])))
    candidate_cost = estimate_cost(provider, elapsed, int(candidate["cpu"]), int(candidate["memoryGb"]), billable_disk_gb(provider, int(candidate["diskGb"])))
    return {
        "task_id": task_id,
        **({"passed": row["passed"]} if isinstance(row.get("passed"), bool) else {}),
        "elapsed_seconds": elapsed,
        "baseline_cost_usd": baseline_cost,
        "candidate_cost_usd": candidate_cost,
        "reduction_pct": pct_reduction(baseline_cost, candidate_cost),
        "baseline_resources": baseline,
        "candidate_resources": candidate,
    }


def base_resource_spec(provider: str, args: argparse.Namespace) -> dict[str, int]:
    return resource_spec(
        args.cpu,
        args.memory_gb if args.memory_gb is not None else (2 if provider == "aws-microvm" else 4),
        args.disk_gb,
        args.timeout_seconds,
    )


def default_runtime(provider: str) -> str:
    return "python:3.13" if provider in {"modal", "daytona"} else "python3.13"


def billable_disk_gb(provider: str, disk_gb: int) -> int:
    return min(disk_gb, 10) if provider == "daytona" else disk_gb


def resource_change_counts(tasks: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        key = f"{format_spec(task['baseline_resources'])} -> {format_spec(task['candidate_resources'])}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def markdown_report(runs: list[dict[str, Any]], args: argparse.Namespace, baseline_config: dict[str, Any], candidate_config: dict[str, Any]) -> str:
    baseline = sum(float(run["baseline_cost_usd"]) for run in runs)
    candidate = sum(float(run["candidate_cost_usd"]) for run in runs)
    lines = [
        "# Resource Policy Cost Comparison",
        "",
        f"Generated: {iso_now()}",
        "",
        f"Dataset: `{display_path(args.dataset)}`",
        f"Baseline config: `{display_path(args.baseline_config)}`",
        f"Candidate config: `{display_path(args.candidate_config)}`",
        f"Resource policy: `{args.resource_policy}`",
        "",
        "This projection holds observed task elapsed seconds constant and replays each task through the same provider cost model used by Python bench.",
        "",
        "## Summary",
        "",
        "scope | runs | tasks | baseline cost | candidate cost | reduction",
        "--- | ---: | ---: | ---: | ---: | ---:",
        " | ".join(["total", str(len(runs)), str(sum(int(run["task_count"]) for run in runs)), fmt_money(baseline), fmt_money(candidate), fmt_pct(pct_reduction(baseline, candidate))]),
        "",
        "## Runs",
        "",
        "provider | mode | tasks | passed | input cost | baseline cost | candidate cost | reduction",
        "--- | --- | ---: | ---: | ---: | ---: | ---: | ---:",
    ]
    for run in runs:
        lines.append(
            " | ".join(
                [
                    str(run["provider"]),
                    str(run.get("mode") or "-"),
                    str(run["task_count"]),
                    str(run.get("passed", "-")),
                    fmt_money(run.get("input_estimated_cost_usd")),
                    fmt_money(run["baseline_cost_usd"]),
                    fmt_money(run["candidate_cost_usd"]),
                    fmt_pct(run.get("reduction_pct")),
                ]
            )
        )
    lines.extend(["", "## Resource Changes", ""])
    for run in runs:
        lines.extend([f"### {run['provider']}{' ' + run['mode'] if run.get('mode') else ''}", "", "change | tasks", "--- | ---:"])
        lines.extend(f"`{change}` | {count}" for change, count in run["resource_change_counts"].items())
        lines.append("")
    lines.extend(
        [
            "## Config Snapshot",
            "",
            f"Baseline provider defaults: `{json.dumps(baseline_config.get('provider_defaults') or {})}`",
            "",
            f"Candidate provider defaults: `{json.dumps(candidate_config.get('provider_defaults') or {})}`",
            "",
        ]
    )
    return "\n".join(lines)


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def pct_reduction(baseline: float, candidate: float) -> float | None:
    return ((baseline - candidate) / baseline) * 100 if baseline > 0 else None


def format_spec(spec: dict[str, Any]) -> str:
    return f"{spec['cpu']} CPU / {spec['memoryGb']} GB / {spec['diskGb']} GB / {spec['timeoutSeconds']}s"


def fmt_money(value: Any) -> str:
    return "-" if not is_finite_number(value) else f"${float(value):.4f}"


def fmt_pct(value: Any) -> str:
    return "-" if not is_finite_number(value) else f"{float(value):.1f}%"


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def write_output(path: Path | None, content: str) -> None:
    if path is None:
        print(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    args = parse_args()
    runs = [load_run(path) for path in result_paths(args)]
    baseline_config = load_resource_policy_config(args.baseline_config)
    candidate_config = load_resource_policy_config(args.candidate_config)
    tasks = task_map(args)
    comparisons = sorted(
        [compare_run(run, tasks, baseline_config, candidate_config, args) for run in runs],
        key=lambda run: (str(run.get("provider")), str(run.get("mode") or "")),
    )
    total_baseline = sum(float(run["baseline_cost_usd"]) for run in comparisons)
    total_candidate = sum(float(run["candidate_cost_usd"]) for run in comparisons)
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "dataset": str(args.dataset),
        "baseline_config": str(args.baseline_config),
        "candidate_config": str(args.candidate_config),
        "resource_policy": args.resource_policy,
        "total_baseline_cost_usd": total_baseline,
        "total_candidate_cost_usd": total_candidate,
        "total_reduction_pct": pct_reduction(total_baseline, total_candidate),
        "runs": comparisons,
    }
    content = json.dumps(payload, indent=2) + "\n" if args.format == "json" else markdown_report(comparisons, args, baseline_config, candidate_config)
    write_output(args.output, content)


if __name__ == "__main__":
    main()
