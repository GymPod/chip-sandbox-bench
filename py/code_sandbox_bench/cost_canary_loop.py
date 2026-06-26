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
    parser.add_argument("--run-concurrency", type=int, default=1)
    parser.add_argument("--resource-policy", default="adaptive")
    parser.add_argument("--resource-config", type=Path)
    parser.add_argument("--solver", choices=["none", "ai-gateway", "gold"], default="none")
    parser.add_argument("--solve-command")
    parser.add_argument("--solve-command-file", type=Path, default=ROOT / "scripts" / "openrouter_solver.sh")
    parser.add_argument("--forward-env", default="")
    parser.add_argument("--aws-microvm-image-id", default=os.environ.get("AWS_MICROVM_IMAGE_ID"))
    parser.add_argument("--aws-microvm-image-version", default=os.environ.get("AWS_MICROVM_IMAGE_VERSION"))
    parser.add_argument("--aws-microvm-execution-role-arn", default=os.environ.get("AWS_MICROVM_EXECUTION_ROLE_ARN"))
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
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
    args.dataset = args.dataset.resolve()
    args.output_dir = args.output_dir.resolve()
    args.reports_dir = args.reports_dir.resolve()
    args.resource_observations_dir = (args.resource_observations_dir or args.output_dir / "resource-observations").resolve()
    args.resource_config = args.resource_config.resolve() if args.resource_config else None
    args.solve_command_file = args.solve_command_file.resolve() if args.solve_command_file else None
    args.env_file = args.env_file.resolve()
    args.baseline_config = args.baseline_config.resolve() if args.baseline_config else None
    args.candidate_config = args.candidate_config.resolve()
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
    matrix = matrix_output(args)
    steps: list[dict[str, Any]] = [
        {
            "name": "candidate_matrix",
            "argv": [
                sys.executable,
                "-m",
                "code_sandbox_bench.matrix",
                "--providers",
                ",".join(args.providers),
                "--modes",
                ",".join(args.modes),
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
                "--run-concurrency",
                str(args.run_concurrency),
                "--resource-policy",
                args.resource_policy,
                "--resource-config",
                str(args.resource_config or args.candidate_config),
                "--solver",
                args.solver,
                "--forward-env",
                args.forward_env,
                "--env-file",
                str(args.env_file),
                "--output-dir",
                str(args.output_dir),
                "--resource-observations-dir",
                str(args.resource_observations_dir),
                "--suffix",
                args.suffix,
                "--output",
                str(matrix),
            ],
            "output": str(matrix),
            "allow_failure": True,
        }
    ]
    if args.solve_command:
        steps[0]["argv"].extend(["--solve-command", args.solve_command])
    elif args.solver == "none":
        steps[0]["argv"].extend(["--solve-command-file", str(args.solve_command_file)])
    if args.aws_microvm_image_id:
        steps[0]["argv"].extend(["--aws-microvm-image-id", args.aws_microvm_image_id])
    if args.aws_microvm_image_version:
        steps[0]["argv"].extend(["--aws-microvm-image-version", args.aws_microvm_image_version])
    if args.aws_microvm_execution_role_arn:
        steps[0]["argv"].extend(["--aws-microvm-execution-role-arn", args.aws_microvm_execution_role_arn])
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
    checks = [provider_preflight(provider, args) for provider in args.providers]
    checks.extend(solver_preflight(args))
    return {"enabled": True, "passed": all(check["passed"] for check in checks), "checks": checks}


def matrix_output(args: argparse.Namespace) -> Path:
    return args.output_dir / f"py-cost-canary-matrix-{args.suffix}.json"


def provider_preflight(provider: str, args: argparse.Namespace) -> dict[str, Any]:
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
    has_image = bool(args.aws_microvm_image_id) or env_present("AWS_MICROVM_IMAGE_ID") or env_present("AWS_MICROVM_IMAGE_ARN")
    has_auth = env_present("AWS_PROFILE") or (env_present("AWS_ACCESS_KEY_ID") and env_present("AWS_SECRET_ACCESS_KEY")) or env_present("AWS_WEB_IDENTITY_TOKEN_FILE")
    missing = ([] if has_image else ["AWS_MICROVM_IMAGE_ID or AWS_MICROVM_IMAGE_ARN"]) + (
        [] if has_auth else ["AWS_PROFILE or AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY or AWS_WEB_IDENTITY_TOKEN_FILE"]
    )
    return {"name": "aws-microvm", "passed": not missing, "missing": missing}


def solver_preflight(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.solver == "ai-gateway" or uses_ai_gateway_solver(args.solve_command_file):
        has_auth = env_present("AI_GATEWAY_API_KEY") or env_present("VERCEL_OIDC_TOKEN")
        return [
            {
                "name": "ai-gateway-solver",
                "passed": has_auth,
                "missing": [] if has_auth else ["AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN"],
            }
        ]
    if args.solver == "none" and uses_openrouter_solver(args.solve_command_file):
        missing = [name for name in ["OPENROUTER_API_KEY", "OPENROUTER_MODEL"] if not env_present(name)]
        return [{"name": "openrouter-solver", "passed": not missing, "missing": missing}]
    return []


def uses_openrouter_solver(path: Path) -> bool:
    return path.name == "openrouter_solver.sh"


def uses_ai_gateway_solver(path: Path) -> bool:
    return path.name == "ai_gateway_solver.sh"


def env_present(name: str) -> bool:
    return bool(os.environ.get(name))


def run_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for step in steps:
        print(f"running step {step['name']}", flush=True)
        completed = subprocess.run(
            step["argv"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=python_subprocess_env(),
        )
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


def python_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    package_path = str(ROOT / "py")
    env["PYTHONPATH"] = package_path if not env.get("PYTHONPATH") else f"{package_path}{os.pathsep}{env['PYTHONPATH']}"
    return env


def validate_args(args: argparse.Namespace) -> None:
    if not csv(args.baseline_results):
        raise ValueError("--baseline-results is required")
    if not args.baseline_config:
        raise ValueError("--baseline-config is required so the loop can produce projection evidence")


def main() -> None:
    args = parse_args()
    validate_args(args)
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
