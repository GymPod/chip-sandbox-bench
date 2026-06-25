import argparse
import asyncio
import json
import os
import shlex
import time
from pathlib import Path

from code_sandbox_bench.dataset import BenchTask, select_tasks
from code_sandbox_bench.providers import CommandResult, make_provider, write_text
from code_sandbox_bench.task_env import TaskEnv, resolve_task_env

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "data" / "terminalbench_2026_03_05_smoke16.jsonl"
PREPARE_COMMAND = """
set -eu
mkdir -p /tmp/tb /workspace /tests /solution /logs/verifier
python3 - <<'PY'
import base64
from pathlib import Path
Path("/tmp/task.tar.gz").write_bytes(base64.b64decode(Path("/tmp/task.tar.gz.b64").read_text()))
PY
tar --no-same-owner -xzf /tmp/task.tar.gz -C /tmp/tb
cp -a /tmp/tb/. /workspace/
if [ -d /tmp/tb/tests ]; then cp -a /tmp/tb/tests/. /tests/; fi
if [ -d /tmp/tb/solution ]; then cp -a /tmp/tb/solution/. /solution/; fi
python3 -m ensurepip --user >/tmp/ensurepip.log 2>&1 || true
PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --user pytest==8.4.1 >/tmp/pip-pytest.log 2>&1 || true
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


def estimate_cost(provider: str, seconds: float, cpu: int, memory_gb: int, disk_gb: int) -> float:
    if provider in {"local", "docker"}:
        return 0.0
    if provider == "vercel":
        return (seconds / 3600.0) * ((cpu * 0.128) + (memory_gb * 0.0212)) + 0.60 / 1_000_000
    if provider == "modal":
        return seconds * ((cpu / 2.0) * 0.00003942 + memory_gb * 0.00000672)
    if provider == "daytona":
        billable_storage_gb = max(0, disk_gb - 5)
        return seconds * (cpu * 0.00001400 + memory_gb * 0.00000450 + billable_storage_gb * 0.00000003)
    if provider == "aws-microvm":
        vcpu_second_usd = float(os.environ.get("AWS_MICROVM_ESTIMATE_VCPU_SECOND_USD", "0.0000276944"))
        gb_second_usd = float(os.environ.get("AWS_MICROVM_ESTIMATE_GB_SECOND_USD", "0.0000036667"))
        return seconds * ((memory_gb / 2.0) * vcpu_second_usd + memory_gb * gb_second_usd)
    return 0.0


async def run_task(args: argparse.Namespace, task: BenchTask) -> dict[str, object]:
    task_env = resolve_task_env(task, args.runtime, args.provider)
    provider = make_provider(
        args.provider,
        task_env.runtime or args.runtime,
        args.timeout_seconds,
        args.cpu,
        args.memory_gb,
        args.disk_gb,
        aws_microvm_image_id=args.aws_microvm_image_id,
        aws_microvm_image_version=args.aws_microvm_image_version,
        aws_microvm_execution_role_arn=args.aws_microvm_execution_role_arn,
    )
    started = time.monotonic()
    result = CommandResult("", "", 1)
    solve_result: CommandResult | None = None
    solve_elapsed: float | None = None
    phases: dict[str, float] = {}

    async def timed(name: str, action):
        phase_started = time.monotonic()
        try:
            return await action()
        finally:
            phases[f"{name}_seconds"] = time.monotonic() - phase_started

    try:
        await timed("start", provider.start)
        await timed("upload", lambda: write_text(provider, "/tmp/task.tar.gz.b64", task.archive_b64, args.timeout_seconds))
        prepare = await timed(
            "prepare",
            lambda: provider.run(prepare_command_for(task_env), cwd=None, timeout=args.timeout_seconds),
        )
        if prepare.return_code != 0:
            result = prepare
        else:
            await timed("instruction_write", lambda: write_task_instructions(provider, task, task_env, args.timeout_seconds))
            solve_command = resolve_solve_command(args)
            if solve_command is not None:
                if args.solver == "ai-gateway":
                    await timed("solver_upload", lambda: upload_ai_gateway_solver(provider, args.timeout_seconds))
                solve_started = time.monotonic()
                solve_result = await timed(
                    "solve",
                    lambda: provider.run(
                        with_bench_env(with_forwarded_env(solve_command, resolve_forward_env(args)), task_env),
                        cwd=task_env.workdir,
                        timeout=args.solve_timeout_seconds,
                    ),
                )
                solve_elapsed = time.monotonic() - solve_started
            result = await timed(
                "verify",
                lambda: provider.run(verify_command_for(task_env), cwd=task_env.verifier_cwd, timeout=args.timeout_seconds),
            )
    finally:
        try:
            await timed("stop", provider.stop)
        except Exception as error:
            result = CommandResult(result.stdout, f"{result.stderr}\nstop failed: {error}".strip(), result.return_code or 1)
    elapsed = time.monotonic() - started
    output = {
        "task_id": task.task_id,
        "env_type": task_env.env_type,
        "data_source": task_env.data_source,
        "task_workdir": task_env.workdir,
        "task_runtime": task_env.runtime,
        "task_docker_image": task_env.docker_image,
        "passed": result.return_code == 0,
        "return_code": result.return_code,
        "elapsed_seconds": elapsed,
        "estimated_cost_usd": estimate_cost(args.provider, elapsed, args.cpu, args.memory_gb, args.disk_gb),
        "phases": phases,
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
    output.update(provider.metadata())
    return output


async def main_async(args: argparse.Namespace) -> None:
    load_env_file(args.env_file)
    if args.runtime is None:
        args.runtime = "python3.13" if args.provider == "vercel" else "python:3.11-slim"
    if args.ai_gateway_model:
        os.environ["AI_GATEWAY_MODEL"] = args.ai_gateway_model
    tasks = select_tasks(args.dataset, args.task_index, args.task_limit)
    results = []
    for task in tasks:
        print(f"running {task.task_id} on {args.provider}", flush=True)
        results.append(await run_task(args, task))
        if args.stop_after_passes is not None:
            passed = sum(1 for item in results if item["passed"])
            if passed >= args.stop_after_passes:
                print(f"stopping after {passed} passing tasks", flush=True)
                break
    summary = {
        "provider": args.provider,
        "mode": args.mode,
        "kind": "solve" if resolve_solve_command(args) else "verifier",
        "dataset": str(args.dataset),
        "runtime": args.runtime,
        "solve_enabled": resolve_solve_command(args) is not None,
        "solver": args.solver,
        "task_count": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "estimated_cost_usd": sum(float(item["estimated_cost_usd"]) for item in results),
        "results": results,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


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
    parser.add_argument("--runtime")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--cpu", type=int, default=2)
    parser.add_argument("--memory-gb", type=int, default=4)
    parser.add_argument("--disk-gb", type=int, default=10)
    parser.add_argument("--aws-microvm-image-id", default=os.environ.get("AWS_MICROVM_IMAGE_ID"))
    parser.add_argument("--aws-microvm-image-version", default=os.environ.get("AWS_MICROVM_IMAGE_VERSION"))
    parser.add_argument("--aws-microvm-execution-role-arn", default=os.environ.get("AWS_MICROVM_EXECUTION_ROLE_ARN"))
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.solve_timeout_seconds is None:
        args.solve_timeout_seconds = args.timeout_seconds
    return args


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
    if task_env.env_type != "harbor_swesmith":
        return PREPARE_COMMAND
    return PREPARE_COMMAND + deterministic_solve_rewrite()


def verify_command_for(task_env: TaskEnv) -> str:
    if task_env.env_type != "harbor_swesmith":
        return VERIFY_COMMAND
    pre_verify = "\n".join(f"{{ {command} ; }} || true" for command in manifest_list(task_env, "pre_verify_cmds"))
    return f"""
set +e
ulimit -n 65535 2>/dev/null || ulimit -n 4096 2>/dev/null || true
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
bash /tmp/bench-verify.sh
code=$?
if [ "$code" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit "$code"
"""


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
    await write_text(provider, "/tmp/task_prompt.md", prompt, timeout)
    await write_text(provider, "/tmp/task_instruction.md", instruction, timeout)
    await write_text(provider, "/workspace/TASK.md", task_markdown, timeout)
    if task_env.workdir != "/workspace":
        await write_text(provider, f"{task_env.workdir}/TASK.md", task_markdown, timeout)


async def upload_ai_gateway_solver(provider, timeout: int) -> None:
    source = (Path(__file__).with_name("ai_gateway_solver.py")).read_text(encoding="utf-8")
    await write_text(provider, GATEWAY_SOLVER_REMOTE_PATH, source, timeout)


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
