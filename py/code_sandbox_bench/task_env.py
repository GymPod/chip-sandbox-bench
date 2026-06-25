import base64
import io
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import Path

from code_sandbox_bench.dataset import BenchTask


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_MANIFESTS_PATH = ROOT / "data" / "swesmith_env_manifests.json"


@dataclass(frozen=True)
class TaskEnv:
    env_type: str
    workdir: str
    verifier_cwd: str
    data_source: str | None = None
    runtime: str | None = None
    docker_image: str | None = None
    repo_key: str | None = None
    source_id: str | None = None
    manifest: dict[str, object] | None = None


def resolve_task_env(task: BenchTask, default_runtime: str, provider: str) -> TaskEnv:
    if task.env_type == "harbor_swesmith":
        dockerfile = read_archive_text(task, "environment/Dockerfile")
        task_toml = read_archive_text(task, "task.toml")
        repo_key = None
        source_id = None
        if task_toml:
            repository = parse_toml_value(task_toml, "repository")
            repo_key = repository.split("/", 1)[1] if repository and "/" in repository else repository
            source_id = parse_toml_value(task_toml, "source_id")
        manifest = load_env_manifests().get(repo_key or "")
        docker_image = parse_dockerfile_from(dockerfile) if dockerfile else None
        return TaskEnv(
            env_type=task.env_type,
            data_source=task.data_source,
            workdir="/testbed",
            verifier_cwd="/testbed",
            runtime=docker_image if provider in {"modal", "daytona"} else default_runtime,
            docker_image=docker_image,
            repo_key=repo_key,
            source_id=source_id,
            manifest=manifest,
        )
    return TaskEnv(
        env_type=task.env_type or "terminalbench",
        data_source=task.data_source,
        workdir="/workspace",
        verifier_cwd="/workspace",
        runtime=default_runtime,
    )


def load_env_manifests(path: Path = DEFAULT_ENV_MANIFESTS_PATH) -> dict[str, dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    repos = payload.get("repos", {})
    return repos if isinstance(repos, dict) else {}


def read_archive_text(task: BenchTask, member_path: str) -> str | None:
    if task.task_files_encoding != "tar.gz+base64":
        return None
    try:
        archive = base64.b64decode(task.archive_b64)
    except ValueError:
        return None
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        try:
            member = tar.getmember(member_path)
        except KeyError:
            return None
        extracted = tar.extractfile(member)
        if extracted is None:
            return None
        return extracted.read().decode("utf-8", errors="replace")


def parse_toml_value(toml: str, key: str) -> str | None:
    match = re.search(rf'^{re.escape(key)} = "([^"]+)"', toml, flags=re.MULTILINE)
    return match.group(1) if match else None


def parse_dockerfile_from(dockerfile: str | None) -> str | None:
    if not dockerfile:
        return None
    for line in dockerfile.splitlines():
        stripped = line.strip()
        if stripped.startswith("FROM "):
            parts = stripped.split()
            return parts[1] if len(parts) > 1 else None
    return None
