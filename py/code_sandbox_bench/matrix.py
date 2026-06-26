import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from code_sandbox_bench.adaptive_concurrency import (
    DEFAULT_ADAPTIVE_CONCURRENCY_STATE_PATH,
    adaptive_limit_for_provider,
)
from code_sandbox_bench.resource_policy import load_resource_policy_config


ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ["vercel", "modal", "daytona", "aws-microvm"]
MODES = ["cold", "warm"]
DEFAULT_FORWARD_ENV = (
    "OPENROUTER_API_KEY,OPENROUTER_MODEL,AI_GATEWAY_API_KEY,AI_GATEWAY_MODEL,"
    "VERCEL_OIDC_TOKEN,SOLVER_MAX_STEPS,SOLVER_STEP_TIMEOUT_SECONDS"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--providers", default="all")
    parser.add_argument("--modes", default="cold,warm")
    parser.add_argument("--dataset", type=Path, default=ROOT / "data" / "swesmith_v4_smoke100.jsonl")
    parser.add_argument("--task-index", default="all")
    parser.add_argument("--task-limit", type=int)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--resource-observations-dir", type=Path)
    parser.add_argument("--suffix")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--solve-timeout-seconds", type=int, default=900)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--vercel-concurrency", type=int)
    parser.add_argument("--modal-concurrency", type=int)
    parser.add_argument("--daytona-concurrency", type=int)
    parser.add_argument("--aws-microvm-concurrency", type=int)
    parser.add_argument("--run-concurrency", type=int)
    parser.add_argument("--cpu", type=int, default=2)
    parser.add_argument("--memory-gb", type=int, default=4)
    parser.add_argument("--disk-gb", type=int, default=10)
    parser.add_argument("--resource-policy", choices=["static", "observe", "adaptive"])
    parser.add_argument(
        "--resource-config",
        type=Path,
        default=Path(os.environ["BENCH_RESOURCE_CONFIG"]) if os.environ.get("BENCH_RESOURCE_CONFIG") else None,
    )
    parser.add_argument("--adaptive-concurrency", default=os.environ.get("BENCH_ADAPTIVE_CONCURRENCY", "true"))
    parser.add_argument(
        "--adaptive-concurrency-state",
        type=Path,
        default=Path(os.environ.get("BENCH_ADAPTIVE_CONCURRENCY_STATE", str(DEFAULT_ADAPTIVE_CONCURRENCY_STATE_PATH))),
    )
    parser.add_argument("--solver", choices=["none", "ai-gateway", "gold"], default="none")
    parser.add_argument("--solve-command")
    parser.add_argument("--solve-command-file", type=Path, default=ROOT / "scripts" / "openrouter_solver.sh")
    parser.add_argument("--forward-env", default=DEFAULT_FORWARD_ENV)
    parser.add_argument("--vercel-runtime", default="python3.13")
    parser.add_argument("--modal-runtime", default="python:3.13")
    parser.add_argument("--daytona-runtime", default="python:3.13")
    parser.add_argument("--aws-microvm-runtime", default="python3.13")
    parser.add_argument("--aws-microvm-image-id", default=os.environ.get("AWS_MICROVM_IMAGE_ID"))
    parser.add_argument("--aws-microvm-image-version", default=os.environ.get("AWS_MICROVM_IMAGE_VERSION"))
    parser.add_argument("--aws-microvm-execution-role-arn", default=os.environ.get("AWS_MICROVM_EXECUTION_ROLE_ARN"))
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.providers = parse_list(args.providers, PROVIDERS)
    args.modes = parse_list(args.modes, MODES)
    args.dataset = args.dataset.resolve()
    args.output_dir = args.output_dir.resolve()
    args.resource_observations_dir = (args.resource_observations_dir or args.output_dir / "resource-observations").resolve()
    args.resource_config = args.resource_config.resolve() if args.resource_config else None
    args.solve_command_file = args.solve_command_file.resolve() if args.solve_command_file else None
    args.env_file = args.env_file.resolve()
    args.adaptive_concurrency_state = args.adaptive_concurrency_state.resolve()
    args.suffix = args.suffix or datetime.now().strftime("%Y%m%d")
    args.run_concurrency = args.run_concurrency or max(1, len(args.providers) * len(args.modes))
    args.adaptive_concurrency = parse_bool(str(args.adaptive_concurrency))
    resource_config = load_resource_policy_config(args.resource_config)
    args.resource_policy = args.resource_policy or os.environ.get("BENCH_RESOURCE_POLICY") or resource_config.get("default_policy") or "adaptive"
    return args


def parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value}")


def parse_list(value: str, allowed: list[str]) -> list[str]:
    items = allowed if value == "all" else [item.strip() for item in value.split(",") if item.strip()]
    unsupported = [item for item in items if item not in allowed]
    if unsupported:
        raise ValueError(f"Unsupported value: {unsupported[0]}")
    return items


def runtime_for(provider: str, args: argparse.Namespace) -> str:
    if provider == "vercel":
        return args.vercel_runtime
    if provider == "modal":
        return args.modal_runtime
    if provider == "aws-microvm":
        return args.aws_microvm_runtime
    return args.daytona_runtime


def build_run_specs(args: argparse.Namespace) -> list[dict[str, Any]]:
    specs = []
    for provider in args.providers:
        for mode in args.modes:
            runtime = runtime_for(provider, args)
            task_concurrency = task_concurrency_for(provider, args)
            output = args.output_dir / f"py-{provider}-{mode}-solve-all-{args.suffix}.json"
            observations = args.resource_observations_dir / f"py-{provider}-{mode}-solve-all-{args.suffix}.jsonl"
            argv = [
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
                "--runtime",
                runtime,
                "--timeout-seconds",
                str(args.timeout_seconds),
                "--solve-timeout-seconds",
                str(args.solve_timeout_seconds),
                "--concurrency",
                str(task_concurrency),
                "--cpu",
                str(args.cpu),
                "--memory-gb",
                str(args.memory_gb),
                "--disk-gb",
                str(args.disk_gb),
                "--resource-policy",
                args.resource_policy,
                "--resource-observations-output",
                str(observations),
                "--adaptive-concurrency",
                str(args.adaptive_concurrency).lower(),
                "--adaptive-concurrency-state",
                str(args.adaptive_concurrency_state),
                "--forward-env",
                args.forward_env,
                "--env-file",
                str(args.env_file),
                "--output",
                str(output),
            ]
            if args.task_limit is not None:
                argv.extend(["--task-limit", str(args.task_limit)])
            if args.resource_config is not None:
                argv.extend(["--resource-config", str(args.resource_config)])
            argv.extend(solver_args(args))
            argv.extend(aws_microvm_args(provider, args))
            specs.append(
                {
                    "provider": provider,
                    "mode": mode,
                    "runtime": runtime,
                    "task_concurrency": task_concurrency,
                    "output": output,
                    "resource_observations_output": observations,
                    "argv": argv,
                }
            )
    return specs


def solver_args(args: argparse.Namespace) -> list[str]:
    if args.solve_command:
        return ["--solve-command", args.solve_command]
    if args.solver != "none":
        return ["--solver", args.solver]
    if args.solve_command_file:
        return ["--solve-command-file", str(args.solve_command_file)]
    return []


def task_concurrency_for(provider: str, args: argparse.Namespace) -> int:
    mode_count = max(1, len(args.modes))
    if provider == "vercel":
        static_limit = args.vercel_concurrency or (1 if uses_task_docker_dataset(args.dataset) else args.concurrency)
    elif provider == "modal":
        static_limit = args.modal_concurrency or (
            1 if uses_task_docker_dataset(args.dataset) else min(args.concurrency, max(1, 5 // mode_count))
        )
    elif provider == "aws-microvm":
        account_memory_gb = float(os.environ.get("AWS_MICROVM_ACCOUNT_MEMORY_GB", "4"))
        memory_cap = max(1, int(account_memory_gb // concurrency_memory_gb(provider, args) // mode_count))
        static_limit = args.aws_microvm_concurrency or min(args.concurrency, memory_cap)
    else:
        cpu_cap = 10 // max(1, args.cpu) // mode_count
        memory_cap = 10 // max(1, concurrency_memory_gb(provider, args)) // mode_count
        static_limit = args.daytona_concurrency or min(args.concurrency, max(1, min(cpu_cap, memory_cap)))
    return adaptive_limit_for_provider(
        provider,
        args.concurrency,
        static_limit,
        args.adaptive_concurrency_state,
        args.adaptive_concurrency,
    )


def concurrency_memory_gb(provider: str, args: argparse.Namespace) -> int:
    if args.resource_policy != "adaptive":
        return args.memory_gb
    config = load_resource_policy_config(args.resource_config)
    provider_default = config.get("provider_defaults", {}).get(provider, {})
    return int(provider_default.get("memoryGb") or args.memory_gb)


def uses_task_docker_dataset(dataset: Path) -> bool:
    if dataset.suffix != ".jsonl":
        return False
    try:
        first_line = next(line for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip())
    except (OSError, StopIteration):
        return False
    task = json.loads(first_line)
    return task.get("env_type") == "harbor_swesmith" or task.get("data_source") == "harbor_swesmith"


def aws_microvm_args(provider: str, args: argparse.Namespace) -> list[str]:
    if provider != "aws-microvm":
        return []
    result = []
    if args.aws_microvm_image_id:
        result.extend(["--aws-microvm-image-id", args.aws_microvm_image_id])
    if args.aws_microvm_image_version:
        result.extend(["--aws-microvm-image-version", args.aws_microvm_image_version])
    if args.aws_microvm_execution_role_arn:
        result.extend(["--aws-microvm-execution-role-arn", args.aws_microvm_execution_role_arn])
    return result


async def run_spec(spec: dict[str, Any]) -> dict[str, Any]:
    spec["output"].parent.mkdir(parents=True, exist_ok=True)
    spec["resource_observations_output"].parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    print(f"starting {spec['provider']} {spec['mode']}: {spec['output']}", flush=True)
    proc = await asyncio.create_subprocess_exec(*spec["argv"], cwd=ROOT, env=python_subprocess_env())
    exit_code = await proc.wait()
    elapsed = time.monotonic() - started
    summary = read_bench_summary(spec["output"])
    print(f"finished {spec['provider']} {spec['mode']}: exit {exit_code}, {elapsed:.2f}s", flush=True)
    return {
        "provider": spec["provider"],
        "mode": spec["mode"],
        "runtime": spec["runtime"],
        "task_concurrency": spec["task_concurrency"],
        "output": str(spec["output"]),
        "resource_observations_output": str(spec["resource_observations_output"]),
        "exit_code": exit_code,
        **({"passed": summary["passed"], "task_count": summary["task_count"], "all_passed": summary["passed"] == summary["task_count"]} if summary else {}),
        "elapsed_seconds": elapsed,
    }


def read_bench_summary(output: Path) -> dict[str, int] | None:
    try:
        parsed = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(parsed.get("passed"), int) and isinstance(parsed.get("task_count"), int):
        return {"passed": parsed["passed"], "task_count": parsed["task_count"]}
    return None


def python_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    package_path = str(ROOT / "py")
    env["PYTHONPATH"] = package_path if not env.get("PYTHONPATH") else f"{package_path}{os.pathsep}{env['PYTHONPATH']}"
    return env


async def run_with_concurrency(specs: list[dict[str, Any]], concurrency: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any] | None] = [None] * len(specs)
    next_index = 0

    async def worker() -> None:
        nonlocal next_index
        while True:
            index = next_index
            next_index += 1
            if index >= len(specs):
                return
            results[index] = await run_spec(specs[index])

    worker_count = max(1, min(concurrency, len(specs)))
    await asyncio.gather(*(worker() for _ in range(worker_count)))
    return [result for result in results if result is not None]


async def main_async(args: argparse.Namespace) -> None:
    specs = build_run_specs(args)
    results = await run_with_concurrency(specs, args.run_concurrency)
    summary = {
        "generated_at": datetime.now().isoformat(),
        "requested_task_concurrency_per_run": args.concurrency,
        "effective_task_concurrency_per_run": {
            f"{spec['provider']}-{spec['mode']}": spec["task_concurrency"] for spec in specs
        },
        "adaptive_concurrency_state": str(args.adaptive_concurrency_state),
        "resource_observations_dir": str(args.resource_observations_dir),
        "run_concurrency": args.run_concurrency,
        "results": results,
    }
    output = json.dumps(summary, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output)
    if any(result["exit_code"] != 0 or result.get("all_passed") is False for result in results):
        raise SystemExit(1)


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
