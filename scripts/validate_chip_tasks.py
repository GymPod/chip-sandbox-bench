#!/usr/bin/env python3
"""Apply gold solutions and run every chip-task verifier in an isolated host."""

from __future__ import annotations

import argparse
import base64
import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path


DEFAULT_DATASET = (
    Path(__file__).resolve().parents[1] / "data" / "chip_design_50.jsonl"
)
SANDBOX_PATHS = (Path("/workspace"), Path("/tests"), Path("/solution"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    return parser.parse_args()


def reset_sandbox() -> None:
    for path in SANDBOX_PATHS:
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True)


def extract_archive(encoded: str) -> None:
    archive_bytes = base64.b64decode(encoded, validate=True)
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            destination = (Path("/workspace") / member.name).resolve()
            if not destination.is_relative_to(Path("/workspace")):
                raise ValueError(f"Unsafe archive path: {member.name}")
        archive.extractall("/workspace", filter="data")

    for name in ("tests", "solution"):
        source = Path("/workspace") / name
        destination = Path("/") / name
        if not source.is_dir():
            raise FileNotFoundError(source)
        shutil.copytree(source, destination, dirs_exist_ok=True)
        shutil.rmtree(source)


def run(command: list[str], task_id: str) -> None:
    print(f"[{task_id}] {' '.join(command)}", flush=True)
    subprocess.run(command, check=True, cwd="/workspace")


def main() -> None:
    args = parse_args()
    rows = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for row in rows:
        task_id = row["task_id"]
        reset_sandbox()
        extract_archive(row["task_files"]["content"])
        run(["bash", "/solution/solve.sh"], task_id)
        test_script = Path("/tests/test.sh")
        if test_script.exists():
            run(["bash", str(test_script)], task_id)
        else:
            run(["python3", "-m", "pytest", "-q", "/tests/test_outputs.py"], task_id)
    print(f"validated {len(rows)} chip tasks", flush=True)


if __name__ == "__main__":
    main()
