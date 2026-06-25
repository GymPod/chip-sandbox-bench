import argparse
import asyncio
import base64
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
    if args.stop_after_passes is not None or args.concurrency <= 1:
        results = []
        for task in tasks:
            print(f"running {task.task_id} on {args.provider}", flush=True)
            results.append(await run_task(args, task))
            if args.stop_after_passes is not None:
                passed = sum(1 for item in results if item["passed"])
                if passed >= args.stop_after_passes:
                    print(f"stopping after {passed} passing tasks", flush=True)
                    break
    else:
        semaphore = asyncio.Semaphore(args.concurrency)

        async def guarded(task: BenchTask) -> dict[str, object]:
            async with semaphore:
                print(f"running {task.task_id} on {args.provider}", flush=True)
                return await run_task(args, task)

        results = await asyncio.gather(*(guarded(task) for task in tasks))
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
    parser.add_argument("--concurrency", type=int, default=1)
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
