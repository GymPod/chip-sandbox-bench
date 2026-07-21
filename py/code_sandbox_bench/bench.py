import argparse
import asyncio
import base64
import json
import os
import shlex
import time
import hashlib
from pathlib import Path
from typing import Any

from code_sandbox_bench.adaptive_concurrency import (
    DEFAULT_ADAPTIVE_CONCURRENCY_STATE_PATH,
    AdaptiveConcurrencyLimiter,
    static_worker_count,
)
from code_sandbox_bench.agent_trace import AgentTraceRecorder, TracedProvider, summarize_agent_traces
from code_sandbox_bench.cost_model import estimate_cost
from code_sandbox_bench.dataset import BenchTask, select_tasks
from code_sandbox_bench.providers import CommandResult, make_provider, write_text
from code_sandbox_bench.resource_policy import (
    build_resource_observation,
    load_resource_policy_config,
    recommend_adaptive_resources,
    resolve_resource_spec,
    resource_retry_decision,
    resource_spec,
)
from code_sandbox_bench.task_env import TaskEnv, resolve_task_env

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "data" / "terminalbench_2026_03_05_smoke16.jsonl"
ARCHIVE_PREPARE_COMMAND = """
set -eu
mkdir -p /tmp/tb /workspace /testbed /tests /solution /logs/verifier
python3 - <<'PY'
import base64
from pathlib import Path
Path("/tmp/task.tar.gz").write_bytes(base64.b64decode(Path("/tmp/task.tar.gz.b64").read_text()))
PY
tar --no-same-owner -xzf /tmp/task.tar.gz -C /tmp/tb
cp -a /tmp/tb/. /workspace/
cp -a /tmp/tb/. /testbed/
if [ -d /tmp/tb/tests ]; then cp -a /tmp/tb/tests/. /tests/; fi
if [ -d /tmp/tb/solution ]; then cp -a /tmp/tb/solution/. /solution/; fi
"""
PREPARE_COMMAND = ARCHIVE_PREPARE_COMMAND + """
python3 -m ensurepip --user >/tmp/ensurepip.log 2>&1 || true
PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --user pytest==8.4.1 >/tmp/pip-pytest.log 2>&1 || true
"""
CHIP_PREPARE_COMMAND = ARCHIVE_PREPARE_COMMAND + r"""
command -v gcc >/dev/null
command -v g++ >/dev/null
iverilog -V 2>&1 | grep -q 'Icarus Verilog version 12\.0'
yosys -V | grep -q 'Yosys 0\.59+0'
test "$(pkg-config --modversion systemc)" = "3.0.2"
python3 - <<'PY'
import pytest
import yaml
PY
"""
VERIFY_COMMAND = """
set +e
if [ -x /tests/test.sh ] || [ -f /tests/test.sh ]; then
  PATH="$HOME/.local/bin:$PATH" bash /tests/test.sh
else
  PATH="$HOME/.local/bin:$PATH" pytest /tests/test_outputs.py -rA
fi
code=$?
if [ "$code" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit "$code"
"""
RESOURCE_PROBE_COMMAND = """
set +e
for path in /workspace /testbed /tests /solution /tmp /root/.cache /home/agent/.cache /opt/testbed-venv /opt/verifier-venv; do
  if [ -e "$path" ]; then
    kb=$(du -sk "$path" 2>/dev/null | awk '{print $1}')
    printf '%s\\t%s\\n' "$path" "${kb:-0}"
  fi
done
exit 0
"""
GATEWAY_SOLVER_REMOTE_PATH = "/tmp/code_sandbox_bench_ai_gateway_solver.py"
DEFAULT_GATEWAY_FORWARD_ENV = [
    "AI_GATEWAY_API_KEY",
    "VERCEL_OIDC_TOKEN",
    "AI_GATEWAY_MODEL",
    "AI_GATEWAY_BASE_URL",
    "AI_GATEWAY_VALIDATE_MODEL",
    "SOLVER_MAX_STEPS",
    "SOLVER_STEP_TIMEOUT_SECONDS",
    "SOLVER_MAX_TOKENS",
    "SOLVER_TEMPERATURE",
]
FALLBACK_TESTBED_PIP_DEPS = [
    "pytest<9",
    "pytest-cov<7",
    "pytest-xdist",
    "pytest-timeout",
    "pytest-mock",
    "pytest-asyncio",
    "hypothesis",
    "mock",
]
APT_PACKAGE_NAMES = {"gcc-c++": "g++", "pkgconf-pkg-config": "pkg-config"}


MAX_TRANSIENT_TASK_ATTEMPTS = 5


async def run_task(args: argparse.Namespace, task: BenchTask, concurrency: int) -> dict[str, object]:
    retry_errors: list[str] = []
    total_elapsed_seconds = 0.0
    resource_config = load_resource_policy_config(args.resource_config)
    resource_retry: dict[str, Any] | None = None
    for attempt in range(1, MAX_TRANSIENT_TASK_ATTEMPTS + 1):
        result = await run_task_attempt(args, task, resource_config, concurrency, resource_retry.get("next") if resource_retry else None)
        total_elapsed_seconds += float(result.get("elapsed_seconds") or 0)
        if attempt > 1:
            result["task_attempts"] = attempt
        if retry_errors:
            result["transient_retry_errors"] = retry_errors
            result["elapsed_seconds"] = total_elapsed_seconds
        if not is_transient_task_failure(args, result) or attempt == MAX_TRANSIENT_TASK_ATTEMPTS:
            if args.resource_policy == "adaptive" and result.get("passed") is False and resource_retry is None:
                recommendation = result.get("adaptive_resource_recommendation")
                retry = resource_retry_decision(recommendation, 0) if isinstance(recommendation, dict) else None
                if retry is not None:
                    resource_retry = retry
                    retry_errors.append(f"resource retry: {retry['reason']}")
                    print(f"retrying {task.task_id} on {args.provider} with adaptive resources: {retry['reason']}", flush=True)
                    await asyncio.sleep(2)
                    continue
            return result
        retry_errors.append(str(result.get("stderr_tail") or ""))
        print(f"retrying {task.task_id} on {args.provider} after transient provider transport error", flush=True)
        await asyncio.sleep(attempt * 2)
    raise RuntimeError("unreachable retry state")


def is_transient_task_failure(args: argparse.Namespace, result: dict[str, object]) -> bool:
    stderr = str(result.get("stderr_tail") or "")
    if result.get("passed") is not False:
        return False
    if args.provider == "vercel":
        return any(
            token in stderr
            for token in [
                "StreamError: Stream ended before command finished",
                "Error: Unable to connect. Is the computer able to access the url?",
                "AbortError: The operation was aborted.",
                "TimeoutError: The operation timed out.",
                "Error: Status code 410 is not ok",
            ]
        )
    if args.provider == "modal":
        return any(
            token in stderr
            for token in [
                "Error: Deadline exceeded",
                "Failed to read exec stdio stream",
                "ImageJoinStreaming INTERNAL",
                "UNAVAILABLE",
                "Received RST_STREAM",
                "Name resolution failed",
                "ECONNREFUSED",
                "No connection established",
            ]
        )
    return False


async def run_task_attempt(
    args: argparse.Namespace,
    task: BenchTask,
    resource_config: dict[str, Any],
    concurrency: int,
    retry_resource_spec: dict[str, int] | None = None,
) -> dict[str, object]:
    task_env = resolve_task_env(task, args.runtime, args.provider)
    trace_recorder = AgentTraceRecorder(args.provider, task.task_id)
    started = time.monotonic()
    provider = None
    result = CommandResult("", "", 1)
    solve_result: CommandResult | None = None
    solve_elapsed: float | None = None
    provider_metadata: dict[str, object] = {}
    disk_usage: dict[str, object] | None = None
    phases: dict[str, float] = {}
    base_resource_spec = resource_spec(args.cpu, args.memory_gb, args.disk_gb, args.timeout_seconds)
    resolved_resource_spec = resolve_resource_spec(args.provider, args.resource_policy, base_resource_spec, task_env, resource_config)
    execution_spec = retry_resource_spec or resolved_resource_spec["effective"]
    requested_disk_gb = int(execution_spec["diskGb"])
    disk_gb = min(requested_disk_gb, 10) if args.provider == "daytona" else requested_disk_gb
    cpu = int(execution_spec["cpu"])
    memory_gb = int(execution_spec["memoryGb"])
    timeout_seconds = int(execution_spec["timeoutSeconds"])

    async def timed(name: str, action):
        phase_started = time.monotonic()
        try:
            return await action()
        finally:
            phases[f"{name}_seconds"] = time.monotonic() - phase_started

    try:
        base_provider = make_provider(
            args.provider,
            task_env.runtime or args.runtime,
            args.timeout_seconds,
            cpu,
            memory_gb,
            disk_gb,
            aws_microvm_image_id=args.aws_microvm_image_id,
            aws_microvm_image_version=args.aws_microvm_image_version,
            aws_microvm_execution_role_arn=args.aws_microvm_execution_role_arn,
        )
        provider = TracedProvider(base_provider, trace_recorder)
        await timed("start", provider.start)
        await timed(
            "upload",
            lambda: write_text(
                provider,
                "/tmp/task.tar.gz.b64",
                task.archive_b64,
                timeout_seconds,
                trace={"label": "upload_task_archive"},
            ),
        )
        prepare = await timed(
            "prepare",
            lambda: provider.run(prepare_command_for(task_env), cwd=None, timeout=timeout_seconds, trace={"label": "prepare"}),
        )
        if prepare.return_code != 0:
            result = prepare
        else:
            await timed("instruction_write", lambda: write_task_instructions(provider, task, task_env, timeout_seconds))
            solve_command = resolve_solve_command(args)
            if solve_command is not None:
                if args.solver == "ai-gateway":
                    await timed("solver_upload", lambda: upload_ai_gateway_solver(provider, timeout_seconds))
                solve_started = time.monotonic()
                solve_result = await timed(
                    "solve",
                    lambda: provider.run(
                            with_bench_env(with_forwarded_env(solve_command, resolve_forward_env(args)), task_env),
                            cwd=task_env.workdir,
                            timeout=args.solve_timeout_seconds,
                            trace={"label": "solve"},
                        ),
                )
                solve_elapsed = time.monotonic() - solve_started
            result = await timed(
                "verify",
                lambda: provider.run(
                    verify_command_for(task_env),
                    cwd=task_env.verifier_cwd,
                    timeout=timeout_seconds,
                    trace={"label": "verify"},
                ),
            )
    except Exception as error:
        result = CommandResult("", format_error(error), 1)
    finally:
        if provider is not None:
            try:
                probe = await timed(
                    "resource_probe",
                    lambda: provider.run(
                        RESOURCE_PROBE_COMMAND,
                        cwd=None,
                        timeout=min(30, timeout_seconds),
                        trace={"label": "resource_probe"},
                    ),
                )
                disk_usage = parse_disk_usage(probe.stdout)
            except Exception:
                disk_usage = None
            try:
                await timed("stop", provider.stop)
                provider_metadata = provider.metadata()
            except Exception as error:
                provider_metadata = provider.metadata()
                result = CommandResult(result.stdout, f"{result.stderr}\nstop failed:\n{format_error(error)}".strip(), result.return_code or 1)
    trace_recorder.finish()
    elapsed = time.monotonic() - started
    agent_trace = trace_recorder.snapshot()
    static_disk_gb = min(int(resolved_resource_spec["requested"]["diskGb"]), 10) if args.provider == "daytona" else int(resolved_resource_spec["requested"]["diskGb"])
    static_estimated_cost = estimate_cost(
        args.provider,
        elapsed,
        int(resolved_resource_spec["requested"]["cpu"]),
        int(resolved_resource_spec["requested"]["memoryGb"]),
        static_disk_gb,
    )
    estimated_cost = estimate_cost(args.provider, elapsed, cpu, memory_gb, disk_gb)
    adaptive_disk_gb = min(int(resolved_resource_spec["adaptive"]["diskGb"]), 10) if args.provider == "daytona" else int(resolved_resource_spec["adaptive"]["diskGb"])
    adaptive_estimated_cost = estimate_cost(
        args.provider,
        elapsed,
        int(resolved_resource_spec["adaptive"]["cpu"]),
        int(resolved_resource_spec["adaptive"]["memoryGb"]),
        adaptive_disk_gb,
    )
    resource_observation = build_resource_observation(
        args.provider,
        args.resource_policy,
        {
            "dataset": str(args.dataset),
            "task_id": task.task_id,
            "task_env": task_env,
            "runtime": task_env.runtime or args.runtime,
            "image_id": args.aws_microvm_image_id if args.provider == "aws-microvm" else None,
            "image_version": args.aws_microvm_image_version if args.provider == "aws-microvm" else None,
            "manifest_hash": hash_json(task_env.manifest),
            "requested": resolved_resource_spec["requested"],
            "adaptive": resolved_resource_spec["adaptive"],
            "effective": {"cpu": cpu, "memoryGb": memory_gb, "diskGb": disk_gb, "timeoutSeconds": timeout_seconds},
            "concurrency": concurrency,
            "resource_resolution_reasons": resolved_resource_spec["reasons"],
            "phase_seconds": phases,
            "disk_usage": disk_usage,
            "estimated_cost_usd": estimated_cost,
            "static_estimated_cost_usd": static_estimated_cost,
            "adaptive_estimated_cost_usd": adaptive_estimated_cost,
        },
        agent_trace,
        result.return_code,
        result.return_code == 0,
        result.stderr,
    )
    adaptive_recommendation = recommend_adaptive_resources(resource_observation)
    output = {
        "task_id": task.task_id,
        "task_repo": task_env.repo_key,
        "task_cpu": cpu,
        "task_memory_gb": memory_gb,
        "task_disk_gb": disk_gb,
        "env_type": task_env.env_type,
        "data_source": task_env.data_source,
        "discipline": task.discipline,
        "benchmark": task.benchmark,
        "tools": list(task.tools),
        "source": task.source,
        "archive_sha256": task.archive_sha256,
        "task_workdir": task_env.workdir,
        "task_runtime": task_env.runtime,
        "task_docker_image": task_env.docker_image,
        "passed": result.return_code == 0,
        "return_code": result.return_code,
        "elapsed_seconds": elapsed,
        "estimated_cost_usd": estimated_cost,
        "static_estimated_cost_usd": static_estimated_cost,
        "adaptive_estimated_cost_usd": adaptive_estimated_cost,
        "adaptive_cost_delta_usd": adaptive_estimated_cost - static_estimated_cost,
        "adaptive_cost_reduction_pct": (
            ((static_estimated_cost - adaptive_estimated_cost) / static_estimated_cost) * 100 if static_estimated_cost > 0 else None
        ),
        "resource_policy": args.resource_policy,
        "requested_resources": resolved_resource_spec["requested"],
        "adaptive_resources": resolved_resource_spec["adaptive"],
        "effective_resources": {"cpu": cpu, "memoryGb": memory_gb, "diskGb": disk_gb, "timeoutSeconds": timeout_seconds},
        "resource_resolution_reasons": resolved_resource_spec["reasons"],
        "resource_observation": resource_observation,
        "adaptive_resource_recommendation": adaptive_recommendation,
        **({"resource_retry": {"resources": retry_resource_spec}} if retry_resource_spec else {}),
        "phases": phases,
        "agent_trace": agent_trace,
        **provider_metadata,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }
    if solve_result is not None:
        output.update(
            {
                "solve_return_code": solve_result.return_code,
                "solve_elapsed_seconds": solve_elapsed,
                "solve_stdout_tail": solve_result.stdout[-2000:],
                "solve_stderr_tail": solve_result.stderr[-2000:],
            }
        )
    return output


async def main_async(args: argparse.Namespace) -> None:
    load_env_file(args.env_file)
    if args.runtime is None:
        args.runtime = "python3.13" if args.provider == "vercel" else "python:3.11-slim"
    if args.ai_gateway_model:
        os.environ["AI_GATEWAY_MODEL"] = args.ai_gateway_model
    tasks = select_tasks(args.dataset, args.task_index, args.task_limit)
    if args.stop_after_passes is not None:
        results = []
        for task in tasks:
            print(f"running {task.task_id} on {args.provider}", flush=True)
            results.append(await run_task(args, task, 1))
            if args.stop_after_passes is not None:
                passed = sum(1 for item in results if item["passed"])
                if passed >= args.stop_after_passes:
                    print(f"stopping after {passed} passing tasks", flush=True)
                    break
        adaptive_concurrency = {
            "enabled": args.adaptive_concurrency,
            "provider": args.provider,
            "requested_limit": args.concurrency,
            "static_limit": 1,
            "initial_limit": 1,
            "final_limit": 1,
            **({"state_path": str(args.adaptive_concurrency_state)} if args.adaptive_concurrency_state else {}),
            "events": [],
        }
    else:
        run = await run_with_concurrency(tasks, args)
        results = run["results"]
        adaptive_concurrency = run["adaptive_concurrency"]
    static_cost = sum(float(item.get("static_estimated_cost_usd") or 0) for item in results)
    adaptive_cost = sum(float(item.get("adaptive_estimated_cost_usd") or 0) for item in results)
    summary = {
        "provider": args.provider,
        "mode": args.mode,
        "kind": "solve" if resolve_solve_command(args) else "verifier",
        "dataset": str(args.dataset),
        "runtime": args.runtime,
        "resource_policy": args.resource_policy,
        "resource_config": str(args.resource_config or "data/resource_policy.json"),
        "task_env_counts": task_env_counts(tasks),
        "solve_enabled": resolve_solve_command(args) is not None,
        "solver": args.solver,
        "task_count": len(results),
        "passed": sum(1 for item in results if item.get("passed")),
        "estimated_cost_usd": sum(float(item.get("estimated_cost_usd") or 0) for item in results),
        "static_estimated_cost_usd": static_cost,
        "adaptive_estimated_cost_usd": adaptive_cost,
        "adaptive_cost_reduction_pct": ((static_cost - adaptive_cost) / static_cost) * 100 if static_cost > 0 else None,
        "aws_microvm_lifecycle_cost_usd": aws_microvm_lifecycle_cost(results),
        "adaptive_concurrency": adaptive_concurrency,
        "agent_trace_summary": summarize_agent_traces(
            [item["agent_trace"] for item in results if isinstance(item.get("agent_trace"), dict)]
        ),
        "results": results,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if args.resource_observations_output is not None:
        write_resource_observations(args.resource_observations_output, results)
    print(json.dumps(summary, indent=2))
    if summary["passed"] != summary["task_count"]:
        raise SystemExit(1)


async def run_with_concurrency(tasks: list[BenchTask], args: argparse.Namespace) -> dict[str, object]:
    if not tasks:
        return {
            "results": [],
            "adaptive_concurrency": {
                "enabled": args.adaptive_concurrency,
                "provider": args.provider,
                "requested_limit": args.concurrency,
                "static_limit": 1,
                "initial_limit": 1,
                "final_limit": 1,
                **({"state_path": str(args.adaptive_concurrency_state)} if args.adaptive_concurrency_state else {}),
                "events": [],
            },
        }
    results: list[dict[str, object] | None] = [None] * len(tasks)
    next_index = 0
    active_count = 0
    completed_count = 0
    done = asyncio.Event()
    env_types = [task.env_type or "terminalbench" for task in tasks]
    static_limit = static_worker_count(args.provider, env_types, args.concurrency, len(tasks), args.memory_gb)
    limiter = AdaptiveConcurrencyLimiter(
        args.provider,
        args.concurrency,
        static_limit,
        args.adaptive_concurrency,
        args.adaptive_concurrency_state,
    )

    def launch() -> None:
        nonlocal next_index, active_count
        while active_count < limiter.current_limit() and next_index < len(tasks):
            index = next_index
            next_index += 1
            active_count += 1
            task = tasks[index]
            concurrency = limiter.current_limit()
            print(f"running {task.task_id} on {args.provider} (concurrency {concurrency})", flush=True)
            asyncio.create_task(worker(index, task, concurrency))

    async def worker(index: int, task: BenchTask, concurrency: int) -> None:
        nonlocal active_count, completed_count
        try:
            result = await run_task(args, task, concurrency)
        except Exception as error:
            result = {"task_id": task.task_id, "passed": False, "return_code": 1, "stderr_tail": format_error(error)}
        results[index] = result
        event = limiter.record_result(result)
        if event["pressure_class"] != "none" and event["next_limit"] != event["previous_limit"]:
            print(
                f"adaptive concurrency {args.provider}: {event['previous_limit']} -> {event['next_limit']} "
                f"after {event['pressure_class']} ({event['reason']})",
                flush=True,
            )
        active_count -= 1
        completed_count += 1
        if completed_count >= len(tasks):
            done.set()
            return
        launch()

    launch()
    await done.wait()
    return {"results": [item for item in results if item is not None], "adaptive_concurrency": limiter.summary()}


def task_env_counts(tasks: list[BenchTask]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        key = task.env_type or "terminalbench"
        counts[key] = counts.get(key, 0) + 1
    return counts


def write_resource_observations(path: Path, results: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item["resource_observation"]) for item in results if item.get("resource_observation")]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def aws_microvm_lifecycle_cost(results: list[dict[str, object]]) -> float | None:
    total = 0.0
    found = False
    for item in results:
        aws = item.get("aws_microvm")
        lifecycle_cost = aws.get("lifecycle_cost") if isinstance(aws, dict) else None
        value = lifecycle_cost.get("total_usd") if isinstance(lifecycle_cost, dict) else None
        if isinstance(value, (int, float)):
            total += float(value)
            found = True
    return total if found else None


def parse_disk_usage(stdout: str) -> dict[str, object] | None:
    paths: dict[str, dict[str, float]] = {}
    for line in stdout.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        try:
            kb = int(parts[1])
        except ValueError:
            continue
        paths[parts[0]] = {"kb": kb, "gb": kb / 1024 / 1024}
    if not paths:
        return None
    total_kb = sum(int(item["kb"]) for item in paths.values())
    cache_kb = sum(int(item["kb"]) for path, item in paths.items() if ".cache" in path)
    usage: dict[str, object] = {
        "paths": paths,
        "total_kb": total_kb,
        "total_gb": total_kb / 1024 / 1024,
    }
    if "/workspace" in paths:
        usage["workspace_kb"] = paths["/workspace"]["kb"]
        usage["workspace_gb"] = paths["/workspace"]["gb"]
    if "/testbed" in paths:
        usage["testbed_kb"] = paths["/testbed"]["kb"]
        usage["testbed_gb"] = paths["/testbed"]["gb"]
    if cache_kb > 0:
        usage["cache_kb"] = cache_kb
        usage["cache_gb"] = cache_kb / 1024 / 1024
    return usage


def hash_json(value: object) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def format_error(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["local", "docker", "vercel", "modal", "daytona", "aws-microvm"], required=True)
    parser.add_argument("--mode", choices=["cold", "warm"], default="cold")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--task-index", default="all")
    parser.add_argument("--task-limit", type=int)
    parser.add_argument("--stop-after-passes", type=int)
    parser.add_argument("--solver", choices=["none", "ai-gateway", "gold"], default="none")
    parser.add_argument("--solve-command")
    parser.add_argument("--solve-command-file", type=Path)
    parser.add_argument("--solve-timeout-seconds", type=int)
    parser.add_argument("--forward-env", default="")
    parser.add_argument("--ai-gateway-model")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--runtime")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--cpu", type=int, default=2)
    parser.add_argument("--memory-gb", type=int)
    parser.add_argument("--disk-gb", type=int, default=10)
    parser.add_argument("--resource-policy", choices=["static", "observe", "adaptive"], default=os.environ.get("BENCH_RESOURCE_POLICY"))
    parser.add_argument(
        "--resource-config",
        type=Path,
        default=Path(os.environ["BENCH_RESOURCE_CONFIG"]) if os.environ.get("BENCH_RESOURCE_CONFIG") else None,
    )
    parser.add_argument("--resource-observations-output", type=Path)
    parser.add_argument("--adaptive-concurrency", default=os.environ.get("BENCH_ADAPTIVE_CONCURRENCY", "true"))
    parser.add_argument(
        "--adaptive-concurrency-state",
        type=Path,
        default=Path(os.environ.get("BENCH_ADAPTIVE_CONCURRENCY_STATE", str(DEFAULT_ADAPTIVE_CONCURRENCY_STATE_PATH))),
    )
    parser.add_argument("--aws-microvm-image-id", default=os.environ.get("AWS_MICROVM_IMAGE_ID"))
    parser.add_argument("--aws-microvm-image-version", default=os.environ.get("AWS_MICROVM_IMAGE_VERSION"))
    parser.add_argument("--aws-microvm-execution-role-arn", default=os.environ.get("AWS_MICROVM_EXECUTION_ROLE_ARN"))
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    resource_config = load_resource_policy_config(args.resource_config)
    if args.resource_policy is None:
        args.resource_policy = resource_config.get("default_policy") or "adaptive"
    if args.memory_gb is None:
        args.memory_gb = 2 if args.provider == "aws-microvm" else 4
    args.adaptive_concurrency = parse_bool(str(args.adaptive_concurrency))
    if args.solve_timeout_seconds is None:
        args.solve_timeout_seconds = args.timeout_seconds
    return args


def parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value}")


def load_env_file(path: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        load_dotenv = None
    if load_dotenv is not None:
        load_dotenv(path)
        return
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("'\""))


def prepare_command_for(task_env: TaskEnv) -> str:
    if task_env.env_type == "chip":
        return CHIP_PREPARE_COMMAND
    if task_env.env_type != "harbor_swesmith":
        return PREPARE_COMMAND
    return PREPARE_COMMAND + fallback_env_setup(task_env) + deterministic_solve_rewrite()


def verify_command_for(task_env: TaskEnv) -> str:
    if task_env.env_type != "harbor_swesmith":
        return VERIFY_COMMAND
    pre_verify = "\n".join(f"{{ {command} ; }} || true" for command in manifest_list(task_env, "pre_verify_cmds"))
    return f"""
set +e
ulimit -n 65535 2>/dev/null || ulimit -n 4096 2>/dev/null || true
if [ ! -x /opt/verifier-venv/bin/pytest ] && [ -x /opt/testbed-venv/bin/pytest ]; then
  mkdir -p /opt/verifier-venv/bin
  ln -sf /opt/testbed-venv/bin/pytest /opt/verifier-venv/bin/pytest
fi
{pre_verify}
cat > /tmp/bench-verify.sh <<'BENCH_EOF_VERIFY'
ulimit -n 65535 2>/dev/null || ulimit -n 4096 2>/dev/null || true
export PYTHONPATH=/testbed/src:${{PYTHONPATH:-}}
if [ -x /tests/test.sh ] || [ -f /tests/test.sh ]; then
  PATH="$HOME/.local/bin:$PATH" bash /tests/test.sh
else
  PATH="$HOME/.local/bin:$PATH" pytest /tests/test_outputs.py -rA
fi
BENCH_EOF_VERIFY
chmod 755 /tmp/bench-verify.sh
if [ "$(id -u)" -eq 0 ] && id agent >/dev/null 2>&1; then
  chown -R agent /testbed /tests /solution /logs 2>/dev/null || true
  if command -v runuser >/dev/null 2>&1; then
    cd /testbed && runuser -u agent -- bash /tmp/bench-verify.sh
  else
    cd /testbed && su -s /bin/bash agent -c 'bash /tmp/bench-verify.sh'
  fi
else
  bash /tmp/bench-verify.sh
fi
code=$?
if [ "$code" -ne 0 ] && [ -f /logs/test_output.log ] && grep -Eq '====+ [0-9]+ passed(, [^=]+)* in ' /logs/test_output.log; then
  code=0
fi
if [ "$code" -ne 0 ] && [ -f /logs/test_output.log ] && grep -Eq '^OK( \\([^)]*\\))?$' /logs/test_output.log; then
  code=0
fi
if [ "$code" -ne 0 ] && [ -f /logs/test_output.log ]; then
  echo "===== /logs/test_output.log head ====="
  head -120 /logs/test_output.log
  echo "===== /logs/test_output.log tail ====="
  tail -200 /logs/test_output.log
fi
if [ "$code" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit "$code"
"""


def fallback_env_setup(task_env: TaskEnv) -> str:
    manifest = task_env.manifest or {}
    python_version = str(manifest.get("python_version") or "3.10")
    mirror = str(manifest.get("mirror") or (f"swesmith/{task_env.repo_key}" if task_env.repo_key else ""))
    source_id = task_env.source_id or ""
    env_key_payload = {
        "repoKey": task_env.repo_key,
        "sourceId": source_id,
        "pythonVersion": python_version,
        "installCmds": manifest_list(task_env, "install_cmds"),
        "preInstallPip": manifest_list(task_env, "pre_install_pip"),
        "extraPip": manifest_list(task_env, "extra_pip"),
        "systemPackages": manifest_list(task_env, "system_packages"),
        "preVerifyCmds": manifest_list(task_env, "pre_verify_cmds"),
    }
    env_key = base64.b64encode(json.dumps(env_key_payload, sort_keys=True).encode()).decode()
    system_packages = sorted({"git", "patch", "tar", "gzip", "gcc", "gcc-c++", "make", *manifest_list(task_env, "system_packages")})
    pip_install_lines = [
        f"python -m pip install {quote_specs(FALLBACK_TESTBED_PIP_DEPS)} || true",
        *[
            f"python -m pip install {quote_specs([spec])} || echo {shlex.quote(f'bench-install-cmd-failed: pip install {spec}')}"
            for spec in manifest_list(task_env, "pre_install_pip")
        ],
    ]
    extra_pip = manifest_list(task_env, "extra_pip")
    if extra_pip:
        pip_install_lines.append(f"python -m pip install {quote_specs(extra_pip)} || echo 'bench-install-cmd-failed: extra pip deps'")
    post_install_pin_lines = [
        f"python -m pip install {quote_specs([spec])} || echo {shlex.quote(f'bench-install-cmd-failed: post install pip {spec}')}"
        for spec in manifest_list(task_env, "pre_install_pip")
    ]
    install_cmd_lines = []
    for command in manifest_list(task_env, "install_cmds") or ["python -m pip install -e ."]:
        guarded = f"if command -v apt-get >/dev/null 2>&1; then {command}; fi" if command.startswith("apt-get") else command
        install_cmd_lines.append(f"{{ {guarded} ; }} || echo {shlex.quote(f'bench-install-cmd-failed: {command}')}")
    return f"""
BENCH_REPO={shlex.quote(task_env.repo_key or "")}
BENCH_ENV_KEY={shlex.quote(env_key)}
if [ -f /opt/bench-fallback-repo ] && [ "$(cat /opt/bench-fallback-repo)" != "$BENCH_REPO" ]; then
  rm -rf /opt/testbed-venv /testbed /opt/bench-fallback-repo /opt/bench-fallback-env-key
  rm -f /opt/verifier-venv/bin/pytest
fi
if [ -f /opt/bench-fallback-env-key ] && [ "$(cat /opt/bench-fallback-env-key)" != "$BENCH_ENV_KEY" ]; then
  rm -rf /opt/testbed-venv /testbed /opt/bench-fallback-repo /opt/bench-fallback-env-key
  rm -f /opt/verifier-venv/bin/pytest
fi
if [ -f /opt/bench-fallback-repo ] && [ ! -f /opt/bench-fallback-env-key ]; then
  rm -rf /opt/testbed-venv /testbed /opt/bench-fallback-repo /opt/bench-fallback-env-key
  rm -f /opt/verifier-venv/bin/pytest
fi
if [ ! -x /opt/verifier-venv/bin/pytest ]; then
  {system_package_install(system_packages)}
  python3 -m ensurepip --user >/tmp/bench-ensurepip.log 2>&1 || true
  PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --user --upgrade pip uv >/tmp/bench-pip-uv.log 2>&1 || true
  BENCH_UV=$(command -v uv || printf '%s' "$HOME/.local/bin/uv")
  export UV_PYTHON_INSTALL_DIR=/opt/uv-python
  "$BENCH_UV" python install {shlex.quote(python_version)}
  "$BENCH_UV" venv --python {shlex.quote(python_version)} --seed /opt/testbed-venv
  chmod -R a+rX /opt/uv-python /opt/testbed-venv
  export PIP_INDEX_URL=https://pypi.org/simple
  if [ ! -e /testbed/pyproject.toml ] && [ ! -e /testbed/setup.py ] && [ ! -e /testbed/setup.cfg ]; then
    rm -rf /testbed
    git clone --depth 1 --branch {shlex.quote(source_id)} {shlex.quote(f'https://github.com/{mirror}.git')} /testbed || {{
      git clone {shlex.quote(f'https://github.com/{mirror}.git')} /testbed
      git -C /testbed checkout {shlex.quote(source_id)}
    }}
  fi
  cat > /tmp/bench-testbed-install.sh <<'BENCH_EOF_INSTALL'
set -x
cd /testbed
{chr(10).join(pip_install_lines)}
{chr(10).join(install_cmd_lines)}
python -m pip install 'pytest<9' 'pytest-cov<7' || true
{chr(10).join(post_install_pin_lines)}
BENCH_EOF_INSTALL
  PATH=/opt/testbed-venv/bin:$PATH bash /tmp/bench-testbed-install.sh >/tmp/bench-testbed-install.log 2>&1 || true
  grep -E 'bench-install-cmd-failed' /tmp/bench-testbed-install.log || true
  tail -30 /tmp/bench-testbed-install.log
  PATH=/opt/testbed-venv/bin:$PATH python - <<'BENCH_EOF_VERSIONS' || true
import importlib.metadata as md
for name in ["beautifulsoup4", "html5lib", "lxml", "cryptography", "paramiko", "pytest", "pyarrow", "requests"]:
    try:
        print(f"bench-package-version: {{name}}=={{md.version(name)}}")
    except md.PackageNotFoundError:
        pass
BENCH_EOF_VERSIONS
  rm -rf /opt/verifier-venv
  "$BENCH_UV" venv --python 3.11 --seed /opt/verifier-venv
  /opt/verifier-venv/bin/python -m pip install pytest==8.4.1 swebench==4.0.3 datasets==2.16.1 swesmith==0.0.6 >/tmp/bench-pip-verifier.log 2>&1 || tail -5 /tmp/bench-pip-verifier.log
  chmod -R a+rX /opt/verifier-venv
  mkdir -p /usr/local/bin
  ln -sf /opt/testbed-venv/bin/pytest /usr/local/bin/pytest
  printf '%s' "$BENCH_REPO" > /opt/bench-fallback-repo
  printf '%s' "$BENCH_ENV_KEY" > /opt/bench-fallback-env-key
  if [ ! -e /opt/miniconda3/bin/conda ]; then
    mkdir -p /opt/miniconda3/bin
    cat > /opt/miniconda3/bin/activate <<'BENCH_EOF_ACTIVATE'
export PATH=/opt/testbed-venv/bin:/opt/miniconda3/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
return 0
BENCH_EOF_ACTIVATE
    printf '#!/bin/sh\\nexit 0\\n' > /opt/miniconda3/bin/conda
    chmod +x /opt/miniconda3/bin/conda
  fi
  if ! id agent >/dev/null 2>&1; then
    useradd -m -u 1001 agent 2>/dev/null || useradd -m agent || true
  fi
fi
if [ -f /opt/bench-fallback-repo ]; then
  sed -i 's#/root/.local/bin/uv run ##g' /tests/test.sh 2>/dev/null || true
fi
if ! command -v patch >/dev/null 2>&1; then
  {system_package_install(["patch"])}
fi
"""


def quote_specs(specs: list[str]) -> str:
    return " ".join(shlex.quote(token) for spec in specs for token in spec.split())


def system_package_install(dnf_packages: list[str]) -> str:
    apt_packages = [APT_PACKAGE_NAMES.get(name, name) for name in dnf_packages]
    return f"""if command -v dnf >/dev/null 2>&1; then
    dnf install -y {" ".join(dnf_packages)} >>/tmp/bench-system-deps.log 2>&1 || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y {" ".join(dnf_packages)} >>/tmp/bench-system-deps.log 2>&1 || true
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update >>/tmp/bench-system-deps.log 2>&1 || true
    apt-get install -y --no-install-recommends {" ".join(apt_packages)} >>/tmp/bench-system-deps.log 2>&1 || true
  fi"""


def deterministic_solve_rewrite() -> str:
    return r"""
for bench_sol_dir in /solution /workspace/solution; do
  if [ -f "$bench_sol_dir/gold.patch" ] && [ -f "$bench_sol_dir/restore-tests.patch" ]; then
    cat > "$bench_sol_dir/solve.sh" <<'BENCH_EOF_SOLVE'
#!/bin/bash
set -uo pipefail
cd /testbed
sol_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
patch -p1 --forward --reject-file=/dev/null < "$sol_dir/restore-tests.patch" || true
if patch -R -p1 --dry-run --force < "$sol_dir/gold.patch" >/dev/null 2>&1; then
  patch -R -p1 --force < "$sol_dir/gold.patch" || exit 1
fi
patch -p1 --dry-run --force < "$sol_dir/gold.patch" >/dev/null 2>&1 || exit 1
exit 0
BENCH_EOF_SOLVE
    chmod +x "$bench_sol_dir/solve.sh"
  fi
done
"""


def manifest_list(task_env: TaskEnv, key: str) -> list[str]:
    value = (task_env.manifest or {}).get(key)
    return [str(item) for item in value] if isinstance(value, list) else []


async def write_task_instructions(provider, task: BenchTask, task_env: TaskEnv, timeout: int) -> None:
    prompt = task.prompt or task.instruction
    instruction = task.instruction or task.prompt
    task_markdown = "\n".join(
        [
            f"# {task.task_id}",
            "",
            "## Prompt",
            prompt.strip(),
            "",
            "## Instruction",
            instruction.strip(),
            "",
            f"Work in `{task_env.workdir}`. The verifier will run after your command exits.",
        ]
    )
    await write_text(provider, "/tmp/task_prompt.md", prompt, timeout, trace={"label": "write_task_prompt"})
    await write_text(provider, "/tmp/task_instruction.md", instruction, timeout, trace={"label": "write_task_instruction"})
    await write_text(provider, "/workspace/TASK.md", task_markdown, timeout, trace={"label": "write_workspace_task"})
    if task_env.workdir != "/workspace":
        await write_text(provider, f"{task_env.workdir}/TASK.md", task_markdown, timeout, trace={"label": "write_workdir_task"})


async def upload_ai_gateway_solver(provider, timeout: int) -> None:
    source = (Path(__file__).with_name("ai_gateway_solver.py")).read_text(encoding="utf-8")
    await write_text(provider, GATEWAY_SOLVER_REMOTE_PATH, source, timeout, trace={"label": "upload_ai_gateway_solver"})


def resolve_solve_command(args: argparse.Namespace) -> str | None:
    if args.solve_command_file is not None:
        return args.solve_command_file.read_text(encoding="utf-8")
    if args.solve_command is not None:
        return args.solve_command
    if args.solver == "ai-gateway":
        return f"python3 {shlex.quote(GATEWAY_SOLVER_REMOTE_PATH)}"
    if args.solver == "gold":
        return "bash /solution/solve.sh"
    return None


def resolve_forward_env(args: argparse.Namespace) -> list[str]:
    names = [name.strip() for name in args.forward_env.split(",") if name.strip()]
    if args.solver == "ai-gateway":
        names.extend(DEFAULT_GATEWAY_FORWARD_ENV)
    return sorted(set(names))


def with_forwarded_env(command: str, names: list[str]) -> str:
    exports = []
    for name in names:
        value = os.environ.get(name)
        if value:
            exports.append(f"export {name}={shlex.quote(value)}")
    return command if not exports else "\n".join(exports + [command])


def with_bench_env(command: str, task_env: TaskEnv) -> str:
    exports = [
        f"export BENCH_TASK_ENV_TYPE={shlex.quote(task_env.env_type)}",
        f"export BENCH_TASK_WORKDIR={shlex.quote(task_env.workdir)}",
        f"export BENCH_TASK_FILE={shlex.quote(f'{task_env.workdir}/TASK.md')}",
        f"export BENCH_TASK_DOCKER_IMAGE={shlex.quote(task_env.docker_image or '')}",
    ]
    return "\n".join(exports + [command])


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
