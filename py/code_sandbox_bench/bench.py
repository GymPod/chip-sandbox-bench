import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from code_sandbox_bench.dataset import BenchTask, select_tasks
from code_sandbox_bench.providers import CommandResult, make_provider, write_text

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "data" / "terminalbench_2026_03_05_smoke16.parquet"
PREPARE_COMMAND = """
set -eu
mkdir -p /tmp/tb /workspace /tests /logs/verifier
python3 - <<'PY'
import base64
from pathlib import Path
Path("/tmp/task.tar.gz").write_bytes(base64.b64decode(Path("/tmp/task.tar.gz.b64").read_text()))
PY
tar -xzf /tmp/task.tar.gz -C /tmp/tb
cp -a /tmp/tb/. /workspace/
cp -a /tmp/tb/tests/. /tests/
python3 -m ensurepip --user >/tmp/ensurepip.log 2>&1 || true
python3 -m pip install --user pytest==8.4.1 >/tmp/pip-pytest.log 2>&1 || true
"""
VERIFY_COMMAND = """
set +e
PATH="$HOME/.local/bin:$PATH" pytest /tests/test_outputs.py -rA
code=$?
if [ "$code" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit "$code"
"""


def estimate_cost(provider: str, seconds: float, cpu: int, memory_gb: int, disk_gb: int) -> float:
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
    provider = make_provider(
        args.provider,
        args.runtime,
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
    try:
        await provider.start()
        await write_text(provider, "/tmp/task.tar.gz.b64", task.archive_b64, args.timeout_seconds)
        prepare = await provider.run(PREPARE_COMMAND, cwd=None, timeout=args.timeout_seconds)
        if prepare.return_code != 0:
            result = prepare
        else:
            result = await provider.run(VERIFY_COMMAND, cwd="/workspace", timeout=args.timeout_seconds)
    finally:
        await provider.stop()
    elapsed = time.monotonic() - started
    output = {
        "task_id": task.task_id,
        "passed": result.return_code == 0,
        "return_code": result.return_code,
        "elapsed_seconds": elapsed,
        "estimated_cost_usd": estimate_cost(args.provider, elapsed, args.cpu, args.memory_gb, args.disk_gb),
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }
    output.update(provider.metadata())
    return output


async def main_async(args: argparse.Namespace) -> None:
    load_dotenv(args.env_file)
    if args.runtime is None:
        args.runtime = "python3.13" if args.provider == "vercel" else "python:3.11-slim"
    tasks = select_tasks(args.dataset, args.task_index)
    results = []
    for task in tasks:
        print(f"running {task.task_id} on {args.provider}")
        results.append(await run_task(args, task))
    summary = {
        "provider": args.provider,
        "runtime": args.runtime,
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
    parser.add_argument("--provider", choices=["local", "vercel", "modal", "daytona", "aws-microvm"], required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--task-index", default="all")
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
    return parser.parse_args()


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
