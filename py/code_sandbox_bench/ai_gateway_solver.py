import json
import hashlib
import os
import pathlib
import re
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone


API_BASE = os.environ.get("AI_GATEWAY_BASE_URL", "https://ai-gateway.vercel.sh/v1").rstrip("/")
CHAT_URL = f"{API_BASE}/chat/completions"
MODELS_URL = f"{API_BASE}/models"
MODEL_PREFERENCES = [
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v3.2",
    "deepseek/deepseek-v3.1",
    "qwen/qwen3-coder",
    "google/gemini-3-flash",
    "anthropic/claude-haiku-4.5",
]
MAX_STEPS = int(os.environ.get("SOLVER_MAX_STEPS", "3"))
STEP_TIMEOUT = int(os.environ.get("SOLVER_STEP_TIMEOUT_SECONDS", "240"))
MAX_TOKENS = int(os.environ.get("SOLVER_MAX_TOKENS", "6000"))
TASK_WORKDIR = os.environ.get("BENCH_TASK_WORKDIR", "/workspace")
TASK_FILE = os.environ.get("BENCH_TASK_FILE", f"{TASK_WORKDIR}/TASK.md")
TASK_ENV_TYPE = os.environ.get("BENCH_TASK_ENV_TYPE", "terminalbench")
TASK_ID = os.environ.get("BENCH_TASK_ID", pathlib.Path(TASK_FILE).stem)
PROVIDER = os.environ.get("BENCH_PROVIDER", "unknown")
TRACE_PATH = pathlib.Path(os.environ.get("BENCH_SOLVER_TRACE_PATH", "/logs/solver/trace.json"))


def main() -> None:
    task = read_text(TASK_FILE, 40000)
    tests = "\n\n".join(
        [
            read_text("/tests/test.sh", 40000),
            read_text("/tests/test_outputs.py", 40000),
            read_text("/tests/test_state.py", 40000),
        ]
    )
    context = workspace_context()
    system_prompt = textwrap.dedent(
        """
        You are an autonomous benchmark task solver running inside a Linux sandbox.
        Work only in the task workdir unless the task or tests require another path.
        You may install packages, edit files, build code, and create outputs.
        The base image may only include Python. If the task needs R, Java, build tools,
        autotools, or another runtime, install it noninteractively before using it.
        Return only a bash script to execute. Do not include explanation outside the script.
        The script should be idempotent and should not modify /tests.
        """
    ).strip()
    user_prompt = (
        f"Task:\n{task}\n\n"
        f"Task env type: {TASK_ENV_TYPE}\n"
        f"Task workdir: {TASK_WORKDIR}\n\n"
        f"Verifier tests:\n{tests}\n\n"
        f"Initial workspace context:\n{context}\n\n"
        "Write a bash script that completes the task. The verifier is bash /tests/test.sh when present, "
        "otherwise pytest /tests/test_outputs.py."
    )
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    trace = {
        "schema_version": 1,
        "trace_id": str(uuid.uuid4()),
        "task_id": TASK_ID,
        "provider": PROVIDER,
        "solver": "ai-gateway",
        "status": "running",
        "started_at": iso_now(),
        "step_count": 0,
        "steps": [],
    }
    persist_trace(trace)
    last_verify = ""
    try:
        for step in range(1, MAX_STEPS + 1):
            print(f"ai_gateway solver step {step}/{MAX_STEPS}", flush=True)
            trace_step = {
                "index": step,
                "status": "running",
                "started_at": iso_now(),
                "request": {
                    "message_count": len(messages),
                    "prompt": str(messages[-1]["content"]),
                },
            }
            trace["steps"].append(trace_step)
            persist_trace(trace)

            response = chat(messages)
            content = response["content"]
            trace["model"] = response["model"]
            trace_step["response"] = response
            script = extract_script(content)
            trace_step["action"] = {
                "command": script,
                "command_sha256": hashlib.sha256(script.encode("utf-8")).hexdigest(),
            }
            persist_trace(trace)

            script_path = pathlib.Path(f"/tmp/ai_gateway_solver_step_{step}.sh")
            script_path.write_text(script)
            script_path.chmod(0o755)
            print(f"--- solver script {step} ---", flush=True)
            print(script[-12000:], flush=True)
            print(f"--- end solver script {step} ---", flush=True)
            print(f"executing {script_path}", flush=True)
            execution = run_captured(str(script_path), STEP_TIMEOUT)
            trace_step["execution"] = execution
            print(f"script rc={execution['return_code']}", flush=True)
            if execution["stdout"]:
                print(execution["stdout"][-4000:], flush=True)
            if execution["stderr"]:
                print(execution["stderr"][-4000:], file=sys.stderr, flush=True)

            verification = run_captured(
                'if [ -f /tests/test.sh ]; then PATH="$HOME/.local/bin:$PATH" bash /tests/test.sh; '
                'else PATH="$HOME/.local/bin:$PATH" '
                "pytest /tests/test_outputs.py -q; fi",
                STEP_TIMEOUT,
            )
            trace_step["verification"] = verification
            trace_step["status"] = "passed" if verification["return_code"] == 0 else "failed"
            trace_step["completed_at"] = iso_now()
            persist_trace(trace)
            print(f"verify rc={verification['return_code']}", flush=True)
            if verification["stdout"]:
                print(verification["stdout"][-4000:], flush=True)
            if verification["stderr"]:
                print(verification["stderr"][-4000:], file=sys.stderr, flush=True)
            if verification["return_code"] == 0:
                finish_trace(trace, "passed")
                return
            last_verify = (
                f"script rc={execution['return_code']}\nscript stdout:\n{execution['stdout']}\n"
                f"script stderr:\n{execution['stderr']}\nverify stdout:\n{verification['stdout']}\n"
                f"verify stderr:\n{verification['stderr']}"
            )
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The verifier still failed. Return a revised bash script only.\n\n"
                        f"Latest script/verifier output:\n{last_verify[-20000:]}"
                    ),
                }
            )
        finish_trace(trace, "failed")
        print(last_verify[-12000:], file=sys.stderr)
        raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as error:
        if trace["steps"]:
            current_step = trace["steps"][-1]
            if current_step["status"] == "running":
                current_step["status"] = "error"
                current_step["completed_at"] = iso_now()
                current_step["error"] = f"{type(error).__name__}: {error}"
        trace["error"] = f"{type(error).__name__}: {error}"
        finish_trace(trace, "error")
        raise


def read_text(path: str, limit: int = 20000) -> str:
    try:
        text = pathlib.Path(path).read_text(errors="replace")
    except FileNotFoundError:
        return f"{path} not found"
    if len(text) > limit:
        return text[:limit] + "\n...[truncated]..."
    return text


def run(command: str, timeout: int) -> tuple[int, str, str]:
    result = run_captured(command, timeout)
    return int(result["return_code"]), str(result["stdout"]), str(result["stderr"])


def run_captured(command: str, timeout: int) -> dict[str, object]:
    started = time.monotonic()
    try:
        process = subprocess.run(
            ["/bin/bash", "-lc", command],
            cwd=TASK_WORKDIR,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "return_code": process.returncode,
            "stdout": process.stdout[-12000:],
            "stderr": process.stderr[-12000:],
            "duration_seconds": time.monotonic() - started,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "return_code": 124,
            "stdout": decode_timeout_output(error.stdout)[-12000:],
            "stderr": decode_timeout_output(error.stderr)[-12000:],
            "duration_seconds": time.monotonic() - started,
            "timed_out": True,
        }


def decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def persist_trace(trace: dict[str, object]) -> None:
    trace["step_count"] = len(trace["steps"])
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = TRACE_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    temporary.replace(TRACE_PATH)


def finish_trace(trace: dict[str, object], status: str) -> None:
    trace["status"] = status
    trace["completed_at"] = iso_now()
    persist_trace(trace)


def workspace_context() -> str:
    _, stdout, stderr = run(
        f"find {TASK_WORKDIR} -maxdepth 4 -type f "
        "-not -path '*/.git/*' -not -path '*/node_modules/*' "
        "-printf '%p\\n' | sort | head -200",
        30,
    )
    paths = [line.strip() for line in stdout.splitlines() if line.strip()]
    chunks = [f"Workspace files:\n{stdout or stderr}"]
    total = sum(len(chunk) for chunk in chunks)
    for path in paths:
        if total > 70000:
            break
        try:
            file_path = pathlib.Path(path)
            if file_path.stat().st_size > 60000:
                continue
            data = file_path.read_bytes()
            if b"\x00" in data[:4096]:
                continue
            text = data.decode("utf-8", errors="replace")
        except OSError:
            continue
        snippet = f"\n--- {path} ---\n{text[:12000]}"
        chunks.append(snippet)
        total += len(snippet)
    return "\n".join(chunks)


def extract_script(content: str) -> str:
    match = re.search(r"```(?:bash|sh|shell)?\s*\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
    if match:
        script = match.group(1)
    else:
        tag_match = re.search(r"<(?:bash|sh|shell)>\s*(.*?)</(?:bash|sh|shell)>", content, re.DOTALL | re.IGNORECASE)
        script = tag_match.group(1) if tag_match else content
    script = re.sub(r"</?(?:bash|sh|shell|thought|analysis|code)>\s*", "", script, flags=re.IGNORECASE)
    return prelude() + "\n" + script.strip() + "\n"


def prelude() -> str:
    return r"""
if [ "$(id -u)" -eq 0 ] || ! command -v sudo >/dev/null 2>&1 || ! sudo -n true >/dev/null 2>&1; then
  sudo() {
    command "$@"
  }
fi
export DEBIAN_FRONTEND=noninteractive
if ! command -v apt-get >/dev/null 2>&1 && command -v dnf >/dev/null 2>&1; then
  apt-get() {
    if [ "${1:-}" = "update" ]; then
      return 0
    fi
    if [ "${1:-}" = "install" ]; then
      shift
      packages=()
      for package in "$@"; do
        case "$package" in
          -*) ;;
          build-essential) packages+=(gcc gcc-c++ make) ;;
          default-jdk) packages+=(java-21-amazon-corretto-devel) ;;
          gfortran) packages+=(gcc-gfortran) ;;
          libcurl4-openssl-dev) packages+=(libcurl-devel) ;;
          libssl-dev) packages+=(openssl-devel) ;;
          libxml2-dev) packages+=(libxml2-devel) ;;
          pkg-config) packages+=(pkgconf-pkg-config) ;;
          r-base|r-base-dev) packages+=(R R-devel) ;;
          *) packages+=("$package") ;;
        esac
      done
      if [ "${#packages[@]}" -eq 0 ]; then
        return 0
      fi
      dnf install -y "${packages[@]}"
      return $?
    fi
    dnf "$@"
  }
fi
"""


def chat(messages: list[dict[str, str]]) -> dict[str, object]:
    key = gateway_key()
    model = resolve_model(key)
    body: dict[str, object] = {
        "model": model,
        "messages": messages,
        "temperature": float(os.environ.get("SOLVER_TEMPERATURE", "0.2")),
        "max_tokens": MAX_TOKENS,
    }
    payload = gateway_request(CHAT_URL, key, body)
    try:
        return {
            "model": str(payload.get("model") or model),
            "content": str(payload["choices"][0]["message"]["content"]),
            **({"usage": payload["usage"]} if isinstance(payload.get("usage"), dict) else {}),
        }
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected AI Gateway response: {json.dumps(payload)[:2000]}") from exc


def resolve_model(key: str) -> str:
    configured = os.environ.get("AI_GATEWAY_MODEL", "").strip()
    if configured:
        if os.environ.get("AI_GATEWAY_VALIDATE_MODEL", "0").lower() in {"1", "true", "yes", "on"}:
            validate_model(key, configured)
        return configured
    models = list_models(key)
    for preferred in MODEL_PREFERENCES:
        if preferred in models:
            return preferred
    for model in models:
        lowered = model.lower()
        if any(marker in lowered for marker in ("deepseek", "qwen", "coder", "flash", "mini", "haiku")):
            return model
    if models:
        return models[0]
    return MODEL_PREFERENCES[0]


def validate_model(key: str, model: str) -> None:
    models = list_models(key)
    if models and model not in models:
        raise RuntimeError(f"AI Gateway model {model!r} was not returned by /models")


def list_models(key: str) -> list[str]:
    request = urllib.request.Request(MODELS_URL, headers={"Authorization": f"Bearer {key}"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return []
    data = payload.get("data", [])
    return [str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")]


def gateway_request(url: str, key: str, body: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI Gateway HTTP {exc.code}: {details}") from exc


def gateway_key() -> str:
    key = os.environ.get("AI_GATEWAY_API_KEY") or os.environ.get("VERCEL_OIDC_TOKEN")
    if not key:
        print("AI_GATEWAY_API_KEY or VERCEL_OIDC_TOKEN is not set", file=sys.stderr)
        sys.exit(2)
    return key


if __name__ == "__main__":
    main()
