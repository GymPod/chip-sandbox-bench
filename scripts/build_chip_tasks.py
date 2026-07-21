#!/usr/bin/env python3
"""Build deterministic chip-design task archives from inspectable source trees."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = ROOT / "data" / "chip_tasks"
DEFAULT_DATASET = ROOT / "data" / "chip_design_50.jsonl"
DEFAULT_MANIFEST = ROOT / "data" / "chip_design_50.manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-root", type=Path, default=TASK_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if rebuilding would change the checked-in dataset or manifest.",
    )
    return parser.parse_args()


def git_head(repo: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def verify_source(source: dict[str, object]) -> None:
    repo = ROOT / str(source["repo"])
    expected_commit = str(source["commit"])
    actual_commit = git_head(repo)
    if actual_commit != expected_commit:
        raise ValueError(
            f"{repo.relative_to(ROOT)} is at {actual_commit}, expected {expected_commit}"
        )
    for raw_path in source.get("paths", []):
        path = repo / str(raw_path)
        if not path.exists():
            raise FileNotFoundError(path)


def task_files(task_dir: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for source_dir, prefix in (
        (task_dir / "workspace", ""),
        (task_dir / "tests", "tests/"),
        (task_dir / "solution", "solution/"),
    ):
        if not source_dir.is_dir():
            raise FileNotFoundError(source_dir)
        for path in sorted(item for item in source_dir.rglob("*") if item.is_file()):
            files.append((path, prefix + path.relative_to(source_dir).as_posix()))
    return files


def archive_task(task_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for path, archive_name in task_files(task_dir):
                data = path.read_bytes()
                info = tarfile.TarInfo(archive_name)
                info.size = len(data)
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mode = 0o755 if path.suffix == ".sh" else 0o644
                archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def build(task_root: Path) -> tuple[str, str]:
    rows: list[dict[str, object]] = []
    manifest_tasks: list[dict[str, object]] = []
    task_dirs = sorted(path.parent for path in task_root.glob("*/task.json"))
    if not task_dirs:
        raise ValueError(f"No tasks found under {task_root}")

    for task_dir in task_dirs:
        spec = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
        verify_source(spec["source"])
        archive = archive_task(task_dir)
        archive_sha256 = hashlib.sha256(archive).hexdigest()
        row = {
            "task_id": spec["task_id"],
            "prompt": spec["prompt"],
            "instruction": spec.get("instruction", spec["prompt"]),
            "task_files": {
                "encoding": "tar.gz+base64",
                "content": base64.b64encode(archive).decode("ascii"),
            },
            "data_source": spec["benchmark"],
            "env_type": "chip",
            "discipline": spec["discipline"],
            "benchmark": spec["benchmark"],
            "tools": spec["tools"],
            "source": spec["source"],
            "archive_sha256": archive_sha256,
        }
        rows.append(row)
        manifest_tasks.append(
            {
                key: value
                for key, value in row.items()
                if key not in {"task_files", "prompt", "instruction"}
            }
            | {
                "prompt": spec["prompt"],
                "archive_bytes": len(archive),
            }
        )

    disciplines: dict[str, int] = {}
    for row in rows:
        discipline = str(row["discipline"])
        disciplines[discipline] = disciplines.get(discipline, 0) + 1

    dataset_text = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows
    )
    manifest = {
        "schema_version": 1,
        "dataset": DEFAULT_DATASET.name,
        "task_count": len(rows),
        "discipline_counts": disciplines,
        "tasks": manifest_tasks,
    }
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return dataset_text, manifest_text


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        existing = path.read_text(encoding="utf-8")
        if existing != content:
            raise SystemExit(f"{path} is stale; run scripts/build_chip_tasks.py")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    dataset_text, manifest_text = build(args.task_root.resolve())
    write_or_check(args.output.resolve(), dataset_text, args.check)
    write_or_check(args.manifest.resolve(), manifest_text, args.check)
    action = "validated" if args.check else "wrote"
    print(f"{action} {args.output} and {args.manifest}")


if __name__ == "__main__":
    main()
