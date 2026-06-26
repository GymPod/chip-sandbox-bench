import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ["vercel", "modal", "daytona", "aws-microvm"]
MODES = ["cold", "warm"]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="false")
    parser.add_argument("--providers", default="vercel,modal,daytona")
    parser.add_argument("--modes", default="warm")
    parser.add_argument("--baseline-results", "--baseline", default="")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "terminalbench_2026_03_05_smoke16.jsonl")
    parser.add_argument("--task-index", default="all")
    parser.add_argument("--task-limit", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--resource-observations-dir", type=Path)
    parser.add_argument("--suffix")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--solve-timeout-seconds", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--resource-policy", default="adaptive")
    parser.add_argument("--resource-config", type=Path)
    parser.add_argument("--solve-command-file", type=Path, default=ROOT / "scripts" / "openrouter_solver.sh")
    parser.add_argument("--baseline-config", type=Path)
    parser.add_argument("--candidate-config", type=Path, default=ROOT / "data" / "resource_policy.json")
    parser.add_argument("--min-reduction-pct", type=float, default=20.0)
    parser.add_argument("--max-pass-drop", type=int, default=0)
    parser.add_argument("--max-wall-ratio", type=float, default=1.2)
    parser.add_argument("--preflight", default="true")
    parser.add_argument("--skip-preflight", default="false")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.run = parse_bool(args.run)
    args.preflight = parse_bool(args.preflight) and not parse_bool(args.skip_preflight)
    args.providers = parse_list(args.providers, PROVIDERS)
    args.modes = parse_list(args.modes, MODES)
    args.resource_observations_dir = args.resource_observations_dir or args.output_dir / "resource-observations"
    args.suffix = args.suffix or f"cpu1-canary-{datetime.now().strftime('%Y%m%d')}"
    return args


def parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Unsupported boolean: {value}")


def parse_list(value: str, allowed: list[str]) -> list[str]:
    items = allowed if value == "all" else [item.strip() for item in value.split(",") if item.strip()]
    unsupported = [item for item in items if item not in allowed]
    if unsupported:
        raise ValueError(f"Unsupported value: {unsupported[0]}")
    return items


def csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def candidate_results(args: argparse.Namespace) -> list[Path]:
    return [
        args.output_dir / f"py-{provider}-{mode}-solve-all-{args.suffix}.json"
        for provider in args.providers
        for mode in args.modes
    ]


def candidate_observations(args: argparse.Namespace) -> list[Path]:
    return [
        args.resource_observations_dir / f"py-{provider}-{mode}-solve-all-{args.suffix}.jsonl"
        for provider in args.providers
        for mode in args.modes
    ]


def resource_report_output(args: argparse.Namespace) -> Path:
    return args.reports_dir / f"generated-py-resource-observations-{args.suffix}.json"


def suggested_config_output(args: argparse.Namespace) -> Path:
    return args.output_dir / f"generated-py-resource-policy-{args.suffix}.json"


def policy_comparison_output(args: argparse.Namespace) -> Path:
    return args.reports_dir / f"generated-py-policy-cost-comparison-{args.suffix}.json"


def canary_validation_output(args: argparse.Namespace) -> Path:
    return args.reports_dir / f"generated-py-canary-validation-{args.suffix}.json"


def goal_audit_output(args: argparse.Namespace) -> Path:
    return args.reports_dir / f"generated-py-cost-goal-audit-{args.suffix}.json"


def build_steps(args: argparse.Namespace) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for provider in args.providers:
        for mode in args.modes:
            result_path = args.output_dir / f"py-{provider}-{mode}-solve-all-{args.suffix}.json"
            observation_path = args.resource_observations_dir / f"py-{provider}-{mode}-solve-all-{args.suffix}.jsonl"
            steps.append(
                {
                    "name": f"candidate_{provider}_{mode}",
                    "argv": [
                        sys.executable,
                        "-m",
                        "code_sandbox_bench.bench",
                        "--provider",
                        provider,
                        "--mode",
                        mode,
                        "--dataset",
                        str(args.dataset),
                        "--task-index",
                        args.task_index,
                        "--task-limit",
                        str(args.task_limit),
                        "--timeout-seconds",
                        str(args.timeout_seconds),
                        "--solve-timeout-seconds",
                        str(args.solve_timeout_seconds),
                        "--concurrency",
                        str(args.concurrency),
                        "--resource-policy",
                        args.resource_policy,
                        "--resource-config",
                        str(args.resource_config or args.candidate_config),
                        "--solve-command-file",
                        str(args.solve_command_file),
                        "--resource-observations-output",
                        str(observation_path),
                        "--output",
                        str(result_path),
                    ],
                    "output": str(result_path),
                    "allow_failure": True,
                }
            )
    resource_report = resource_report_output(args)
    steps.append(
        {
            "name": "resource_report",
            "argv": [
                sys.executable,
                "-m",
                "code_sandbox_bench.resource_report",
                "--input",
                ",".join(str(path) for path in candidate_observations(args)),
                "--min-samples",
                "1",
                "--format",
                "json",
                "--output",
                str(resource_report),
                "--suggested-config-output",
                str(suggested_config_output(args)),
            ],
            "output": str(resource_report),
        }
    )
    baselines = csv(args.baseline_results)
    if args.baseline_config and baselines:
        policy_comparison = policy_comparison_output(args)
        steps.append(
            {
                "name": "policy_compare",
                "argv": [
                    sys.executable,
                    "-m",
                    "code_sandbox_bench.policy_compare",
                    "--results",
                    ",".join(baselines),
                    "--dataset",
                    str(args.dataset),
                    "--baseline-config",
                    str(args.baseline_config),
                    "--candidate-config",
                    str(args.candidate_config),
                    "--format",
                    "json",
                    "--output",
                    str(policy_comparison),
                ],
                "output": str(policy_comparison),
            }
        )
    canary_validation = canary_validation_output(args)
    steps.append(
        {
            "name": "canary_validate",
            "argv": [
                sys.executable,
                "-m",
                "code_sandbox_bench.canary_validate",
                "--baseline-results",
                ",".join(baselines),
                "--candidate-results",
                ",".join(str(path) for path in candidate_results(args)),
                "--min-reduction-pct",
                str(args.min_reduction_pct),
                "--max-pass-drop",
                str(args.max_pass_drop),
                "--max-wall-ratio",
                str(args.max_wall_ratio),
                "--format",
                "json",
                "--output",
                str(canary_validation),
            ],
            "output": str(canary_validation),
        }
    )
    goal_audit = goal_audit_output(args)
    steps.append(
        {
            "name": "goal_audit",
            "argv": [
                sys.executable,
                "-m",
                "code_sandbox_bench.cost_goal_audit",
                "--policy-comparison",
                str(policy_comparison_output(args)),
                "--resource-report",
                str(resource_report),
                "--canary-validation",
                str(canary_validation),
                "--min-reduction-pct",
                str(args.min_reduction_pct),
                "--min-observations",
                "1",
                "--format",
                "json",
                "--output",
                str(goal_audit),
            ],
            "output": str(goal_audit),
        }
    )
    return steps


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    if not args.preflight:
        return {"enabled": False, "passed": True, "checks": []}
    checks = [provider_preflight(provider) for provider in args.providers]
    return {"enabled": True, "passed": all(check["passed"] for check in checks), "checks": checks}


def provider_preflight(provider: str) -> dict[str, Any]:
    if provider == "vercel":
        token_present = any(env_present(name) for name in ["VERCEL_TOKEN", "VERCEL_ACCESS_TOKEN", "VERCEL_API_KEY"])
        missing = ([] if token_present else ["VERCEL_TOKEN or VERCEL_ACCESS_TOKEN or VERCEL_API_KEY"]) + [
            name for name in ["VERCEL_TEAM_ID", "VERCEL_PROJECT_ID"] if not env_present(name)
        ]
        return {"name": "vercel", "passed": not missing, "missing": missing}
    if provider == "modal":
        has_pair = env_present("MODAL_TOKEN_ID") and env_present("MODAL_TOKEN_SECRET")
        has_config = Path(os.environ.get("MODAL_CONFIG_PATH", str(Path.home() / ".modal.toml"))).exists()
        return {"name": "modal", "passed": has_pair or has_config, "missing": [] if has_pair or has_config else ["MODAL_TOKEN_ID + MODAL_TOKEN_SECRET or ~/.modal.toml"]}
    if provider == "daytona":
        missing = [name for name in ["DAYTONA_API_KEY"] if not env_present(name)]
        return {"name": "daytona", "passed": not missing, "missing": missing}
    has_image = env_present("AWS_MICROVM_IMAGE_ID") or env_present("AWS_MICROVM_IMAGE_ARN")
    has_auth = env_present("AWS_PROFILE") or (env_present("AWS_ACCESS_KEY_ID") and env_present("AWS_SECRET_ACCESS_KEY")) or env_present("AWS_WEB_IDENTITY_TOKEN_FILE")
    missing = ([] if has_image else ["AWS_MICROVM_IMAGE_ID or AWS_MICROVM_IMAGE_ARN"]) + (
        [] if has_auth else ["AWS_PROFILE or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY or AWS_WEB_IDENTITY_TOKEN_FILE"]
    )
    return {"name": "aws-microvm", "passed": not missing, "missing": missing}


def env_present(name: str) -> bool:
    return bool(os.environ.get(name))


def run_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for step in steps:
        print(f"running step {step['name']}", flush=True)
        completed = subprocess.run(step["argv"], cwd=ROOT, text=True, capture_output=True, check=False)
        results.append(
            {
                "name": step["name"],
                "return_code": completed.returncode,
                "output": step.get("output"),
                "stdout_tail": completed.stdout[-2000:],
                "stderr_tail": completed.stderr[-2000:],
            }
        )
        if completed.returncode != 0 and not step.get("allow_failure"):
            break
    return results


def write_output(path: Path | None, content: str) -> None:
    if path is None:
        print(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    args.resource_observations_dir.mkdir(parents=True, exist_ok=True)
    steps = build_steps(args)
    preflight_result = preflight(args)
    step_results = run_steps(steps) if args.run and preflight_result["passed"] else []
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "run": args.run,
        "preflight": preflight_result,
        "steps": steps,
        "step_results": step_results,
    }
    write_output(args.output, json.dumps(payload, indent=2) + "\n")
    if args.run and (not preflight_result["passed"] or any(result["return_code"] != 0 for result in step_results if not next(step for step in steps if step["name"] == result["name"]).get("allow_failure"))):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
