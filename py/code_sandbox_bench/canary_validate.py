import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-results", "--baseline", default="")
    parser.add_argument("--candidate-results", "--candidate", default="")
    parser.add_argument("--baseline-results-dir", type=Path)
    parser.add_argument("--candidate-results-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--min-reduction-pct", type=float, default=20.0)
    parser.add_argument("--max-pass-drop", type=int, default=0)
    parser.add_argument("--max-wall-ratio", type=float, default=1.2)
    return parser.parse_args()


def result_paths(paths_text: str, directory: Path | None) -> list[Path]:
    paths = [Path(item) for item in paths_text.split(",") if item.strip()]
    if directory:
        paths.extend(path for path in directory.iterdir() if path.suffix == ".json")
    if not paths:
        raise ValueError("No results provided.")
    return [path.resolve() for path in paths]


def load_run(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Result input not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("provider") or not isinstance(data.get("results"), list):
        raise ValueError(f"Unsupported benchmark result file: {path}")
    return {"path": str(path), "data": data}


def run_key(data: dict[str, Any]) -> str:
    return "|".join([str(data.get("provider")), str(data.get("mode") or "unknown-mode"), str(data.get("kind") or "unknown-kind")])


def validate_run(candidate: dict[str, Any], baselines: dict[str, dict[str, Any]], args: argparse.Namespace) -> dict[str, Any]:
    data = candidate["data"]
    key = run_key(data)
    baseline = baselines.get(key) or baselines.get("|".join([str(data.get("provider")), "unknown-mode", "unknown-kind"]))
    if baseline is None:
        raise ValueError(f"No baseline result found for candidate {candidate['path']} ({key})")
    baseline_rows = {
        row["task_id"]: row
        for row in baseline["data"]["results"]
        if isinstance(row, dict) and isinstance(row.get("task_id"), str)
    }
    matched = [
        {"baseline": baseline_rows[row["task_id"]], "candidate": row}
        for row in data["results"]
        if isinstance(row, dict) and isinstance(row.get("task_id"), str) and row["task_id"] in baseline_rows
    ]
    if not matched:
        raise ValueError(f"No overlapping task IDs between {baseline['path']} and {candidate['path']}")
    baseline_cost = sum(row_cost(pair["baseline"], baseline["data"]) for pair in matched)
    candidate_cost = sum(row_cost(pair["candidate"], data) for pair in matched)
    baseline_elapsed = sum(finite_number(pair["baseline"].get("elapsed_seconds")) or 0 for pair in matched)
    candidate_elapsed = sum(finite_number(pair["candidate"].get("elapsed_seconds")) or 0 for pair in matched)
    baseline_passed = sum(1 for pair in matched if pair["baseline"].get("passed") is True)
    candidate_passed = sum(1 for pair in matched if pair["candidate"].get("passed") is True)
    pass_drop = baseline_passed - candidate_passed
    reduction = pct_reduction(baseline_cost, candidate_cost)
    wall_ratio = candidate_elapsed / baseline_elapsed if baseline_elapsed > 0 else None
    failures = []
    if reduction is None or reduction < args.min_reduction_pct:
        failures.append(f"cost reduction {format_pct(reduction)} below {args.min_reduction_pct:.1f}%")
    if pass_drop > args.max_pass_drop:
        failures.append(f"pass drop {pass_drop} above {args.max_pass_drop}")
    if wall_ratio is not None and wall_ratio > args.max_wall_ratio:
        failures.append(f"wall ratio {wall_ratio:.2f} above {args.max_wall_ratio:.2f}")
    return {
        "key": key,
        "baseline_path": baseline["path"],
        "candidate_path": candidate["path"],
        "provider": data["provider"],
        **({"mode": data["mode"]} if data.get("mode") else {}),
        **({"kind": data["kind"]} if data.get("kind") else {}),
        "matched_tasks": len(matched),
        "baseline_passed": baseline_passed,
        "candidate_passed": candidate_passed,
        "pass_drop": pass_drop,
        "baseline_elapsed_seconds": baseline_elapsed,
        "candidate_elapsed_seconds": candidate_elapsed,
        **({"wall_ratio": wall_ratio} if wall_ratio is not None else {}),
        "baseline_cost_usd": baseline_cost,
        "candidate_cost_usd": candidate_cost,
        **({"reduction_pct": reduction} if reduction is not None else {}),
        "candidate_observations": sum(1 for pair in matched if pair["candidate"].get("resource_observation") is not None),
        "passed": not failures,
        "failures": failures,
    }


def row_cost(row: dict[str, Any], run: dict[str, Any]) -> float:
    direct = finite_number(row.get("estimated_cost_usd"))
    if direct is not None:
        return direct
    run_cost = finite_number(run.get("estimated_cost_usd"))
    if run_cost is None:
        return 0.0
    elapsed = finite_number(row.get("elapsed_seconds")) or 0.0
    total_elapsed = sum(finite_number(item.get("elapsed_seconds")) or 0.0 for item in run.get("results", []) if isinstance(item, dict))
    return run_cost * (elapsed / total_elapsed) if total_elapsed > 0 else 0.0


def markdown_report(validations: list[dict[str, Any]], args: argparse.Namespace) -> str:
    baseline_cost = sum(float(item["baseline_cost_usd"]) for item in validations)
    candidate_cost = sum(float(item["candidate_cost_usd"]) for item in validations)
    baseline_elapsed = sum(float(item["baseline_elapsed_seconds"]) for item in validations)
    candidate_elapsed = sum(float(item["candidate_elapsed_seconds"]) for item in validations)
    baseline_passed = sum(int(item["baseline_passed"]) for item in validations)
    candidate_passed = sum(int(item["candidate_passed"]) for item in validations)
    lines = [
        "# Canary Cost Validation",
        "",
        f"Generated: {iso_now()}",
        "",
        f"Minimum reduction: {args.min_reduction_pct:.1f}%",
        f"Maximum pass drop: {args.max_pass_drop}",
        f"Maximum wall ratio: {args.max_wall_ratio:.2f}",
        "",
        "## Summary",
        "",
        "baseline cost | candidate cost | reduction | baseline passed | candidate passed | wall ratio | status",
        "---: | ---: | ---: | ---: | ---: | ---: | ---",
        " | ".join(
            [
                format_money(baseline_cost),
                format_money(candidate_cost),
                format_pct(pct_reduction(baseline_cost, candidate_cost)),
                str(baseline_passed),
                str(candidate_passed),
                f"{candidate_elapsed / baseline_elapsed:.2f}" if baseline_elapsed > 0 else "-",
                "pass" if all(item["passed"] for item in validations) else "fail",
            ]
        ),
        "",
        "## Runs",
        "",
        "provider | mode | tasks | cost reduction | pass drop | wall ratio | observations | status | failures",
        "--- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---",
    ]
    for item in validations:
        lines.append(
            " | ".join(
                [
                    str(item["provider"]),
                    str(item.get("mode") or "-"),
                    str(item["matched_tasks"]),
                    format_pct(item.get("reduction_pct")),
                    str(item["pass_drop"]),
                    f"{item['wall_ratio']:.2f}" if finite_number(item.get("wall_ratio")) else "-",
                    str(item["candidate_observations"]),
                    "pass" if item["passed"] else "fail",
                    "; ".join(item["failures"]) or "-",
                ]
            )
        )
    return "\n".join(lines + [""])


def finite_number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def pct_reduction(baseline: float, candidate: float) -> float | None:
    return ((baseline - candidate) / baseline) * 100 if baseline > 0 else None


def format_money(value: Any) -> str:
    return "-" if finite_number(value) is None else f"${float(value):.4f}"


def format_pct(value: Any) -> str:
    return "-" if finite_number(value) is None else f"{float(value):.1f}%"


def write_output(path: Path | None, content: str) -> None:
    if path is None:
        print(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    args = parse_args()
    baseline_runs = [load_run(path) for path in result_paths(args.baseline_results, args.baseline_results_dir)]
    candidate_runs = [load_run(path) for path in result_paths(args.candidate_results, args.candidate_results_dir)]
    baselines = {run_key(run["data"]): run for run in baseline_runs}
    validations = sorted(
        [validate_run(run, baselines, args) for run in candidate_runs],
        key=lambda item: (str(item["provider"]), str(item.get("mode") or "")),
    )
    total_baseline = sum(float(item["baseline_cost_usd"]) for item in validations)
    total_candidate = sum(float(item["candidate_cost_usd"]) for item in validations)
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "min_reduction_pct": args.min_reduction_pct,
        "max_pass_drop": args.max_pass_drop,
        "max_wall_ratio": args.max_wall_ratio,
        "passed": all(item["passed"] for item in validations),
        "total_baseline_cost_usd": total_baseline,
        "total_candidate_cost_usd": total_candidate,
        "total_reduction_pct": pct_reduction(total_baseline, total_candidate),
        "validations": validations,
    }
    content = json.dumps(payload, indent=2) + "\n" if args.format == "json" else markdown_report(validations, args)
    write_output(args.output, content)
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
