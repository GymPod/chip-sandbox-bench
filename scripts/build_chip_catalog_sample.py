#!/usr/bin/env python3
"""Materialize a stratified execution-calibration sample from the chip catalog."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import tarfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "viewer" / ".convex-import" / "tasks.json"
DEFAULT_OUTPUT = ROOT / "data" / "chip_catalog_sample100.jsonl"
DEFAULT_MANIFEST = ROOT / "data" / "chip_catalog_sample100.manifest.json"

DISCIPLINES = (
    "Architecture & Microarchitecture",
    "Architecture Modeling",
    "RTL Design",
    "Verification (DV/FV)",
    "Software Development",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--per-discipline", type=int, default=20)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def local_source(task: dict[str, Any]) -> list[Path] | None:
    benchmark_id = task.get("benchmarkId")
    source = task.get("source") or {}
    paths = source.get("paths") or []
    if not isinstance(benchmark_id, str) or not isinstance(paths, list):
        return None
    root = ROOT / "benchmarks" / benchmark_id
    resolved = []
    for value in paths:
        if not isinstance(value, str):
            return None
        candidate = root / PurePosixPath(value)
        if not candidate.is_file():
            return None
        resolved.append(candidate)
    return resolved or None


def is_software_candidate(task: dict[str, Any]) -> bool:
    if task.get("discipline") == "Software Development":
        return True
    if task.get("benchmarkId") not in {"opentitan", "zephyr"}:
        return False
    return any(str(path).endswith((".c", ".cc", ".cpp", ".h")) for path in (task.get("source") or {}).get("paths", []))


def eligible(task: dict[str, Any], discipline: str) -> bool:
    if task.get("dataset") != "Native benchmark corpus":
        return False
    if discipline == "Software Development":
        return is_software_candidate(task)
    return task.get("discipline") == discipline


def select_tasks(catalog: list[dict[str, Any]], per_discipline: int) -> dict[str, list[dict[str, Any]]]:
    selected: dict[str, list[dict[str, Any]]] = {}
    for discipline in DISCIPLINES:
        candidates = [
            task
            for task in catalog
            if eligible(task, discipline) and local_source(task) is not None
        ]
        candidates.sort(key=lambda task: (str(task.get("benchmarkId")), str(task.get("taskId"))))

        # Round-robin benchmarks so a large repository cannot dominate the sample.
        by_benchmark: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for task in candidates:
            by_benchmark[str(task["benchmarkId"])].append(task)
        groups = [by_benchmark[key] for key in sorted(by_benchmark)]
        rows: list[dict[str, Any]] = []
        index = 0
        while groups and len(rows) < per_discipline:
            group = groups[index % len(groups)]
            rows.append(group.pop(0))
            if not group:
                groups.remove(group)
                index = 0
            else:
                index += 1
        if len(rows) != per_discipline:
            raise ValueError(f"Only found {len(rows)} materializable {discipline} tasks")
        selected[discipline] = rows
    return selected


def add_file(archive: tarfile.TarFile, name: str, content: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = mode
    archive.addfile(info, io.BytesIO(content))


def execution_test(task_id: str, source_hash: str) -> str:
    return f"""import json
from pathlib import Path

def test_execution_evidence():
    report = json.loads(Path("/workspace/execution_report.json").read_text())
    assert report["task_id"] == {task_id!r}
    assert report["source_sha256"] == {source_hash!r}
    assert report["status"] == "completed"
    assert isinstance(report["commands"], list) and report["commands"]
    assert isinstance(report["findings"], list) and report["findings"]
"""


def gold_solution(task_id: str, source_hash: str) -> str:
    return f"""#!/bin/sh
set -eu
cat > /workspace/execution_report.json <<'JSON'
{{"task_id": {json.dumps(task_id)}, "source_sha256": {json.dumps(source_hash)}, "status": "completed", "commands": ["find /workspace/sources -type f -maxdepth 8 -print"], "findings": ["Materialized source inventory recorded."]}}
JSON
"""


def archive_task(task: dict[str, Any], discipline: str) -> tuple[bytes, str]:
    source_files = local_source(task)
    if source_files is None:
        raise ValueError(task["taskId"])
    digest = hashlib.sha256()
    for path in source_files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    source_hash = digest.hexdigest()
    task_id = f"catalog-{task['taskId']}"
    metadata = {
        "schema_version": 1,
        "task_id": task_id,
        "catalog_task_id": task["taskId"],
        "discipline": discipline,
        "benchmark": task["benchmark"],
        "benchmark_id": task["benchmarkId"],
        "source": task["source"],
        "verification_kind": "execution-evidence",
        "source_sha256": source_hash,
    }
    with io.BytesIO() as buffer:
        with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in source_files:
                    relative = path.relative_to(ROOT).as_posix()
                    add_file(archive, f"sources/{relative}", path.read_bytes())
                add_file(archive, "task_metadata.json", json.dumps(metadata, sort_keys=True, indent=2).encode() + b"\n")
                add_file(archive, "tests/test_outputs.py", execution_test(task_id, source_hash).encode())
                add_file(archive, "solution/solve.sh", gold_solution(task_id, source_hash).encode(), 0o755)
        return buffer.getvalue(), source_hash


def build(catalog: list[dict[str, Any]], per_discipline: int) -> tuple[str, str]:
    selected = select_tasks(catalog, per_discipline)
    rows: list[dict[str, Any]] = []
    manifest_tasks: list[dict[str, Any]] = []
    for discipline in DISCIPLINES:
        for task in selected[discipline]:
            archive, source_hash = archive_task(task, discipline)
            task_id = f"catalog-{task['taskId']}"
            prompt = (
                f"Execute and inspect the materialized {task['benchmark']} source task. "
                "Use the available command-line tools to perform the most relevant feasible "
                "check, then write /workspace/execution_report.json with status \"completed\", "
                "the provided task_id and source_sha256 from /workspace/task_metadata.json, "
                "the commands you ran, and concrete findings."
            )
            row = {
                "task_id": task_id,
                "prompt": prompt,
                "instruction": prompt,
                "task_files": {"encoding": "tar.gz+base64", "content": base64.b64encode(archive).decode("ascii")},
                "data_source": task["benchmark"],
                "env_type": "chip",
                "discipline": discipline,
                "benchmark": task["benchmark"],
                "tools": task.get("tools") or [],
                "source": task["source"],
                "verification_kind": "execution-evidence",
                "archive_sha256": hashlib.sha256(archive).hexdigest(),
                "source_sha256": source_hash,
            }
            rows.append(row)
            manifest_tasks.append(
                {
                    "task_id": task_id,
                    "catalog_task_id": task["taskId"],
                    "discipline": discipline,
                    "benchmark": task["benchmark"],
                    "benchmark_id": task["benchmarkId"],
                    "verification_kind": "execution-evidence",
                    "source_sha256": source_hash,
                }
            )
    dataset = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    manifest = json.dumps(
        {
            "schema_version": 1,
            "dataset": DEFAULT_OUTPUT.name,
            "task_count": len(rows),
            "per_discipline": per_discipline,
            "verification_kind": "execution-evidence",
            "tasks": manifest_tasks,
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    return dataset, manifest


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        if path.read_text(encoding="utf-8") != content:
            raise SystemExit(f"{path} is stale; rerun {Path(__file__).name}")
        return
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    dataset, manifest = build(catalog, args.per_discipline)
    write_or_check(args.output, dataset, args.check)
    write_or_check(args.manifest, manifest, args.check)
    print(f"Wrote {args.output} and {args.manifest}")


if __name__ == "__main__":
    main()
