#!/usr/bin/env python3
"""Build Convex JSON imports from the repository's chip task fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LANGUAGES = {
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".json": "JSON",
    ".md": "Markdown",
    ".py": "Python",
    ".sh": "Shell",
    ".sv": "SystemVerilog",
    ".v": "Verilog",
    ".yaml": "YAML",
    ".yml": "YAML",
}


def build_import(data_root: Path) -> tuple[list[dict], list[dict]]:
    tasks = []
    files = []

    for task_file in sorted(data_root.glob("*/task.json")):
        metadata = json.loads(task_file.read_text(encoding="utf-8"))
        task_id = metadata.pop("task_id")
        tasks.append({"taskId": task_id, **metadata})

        for path in sorted(task_file.parent.rglob("*")):
            if not path.is_file() or path == task_file:
                continue
            relative = path.relative_to(task_file.parent).as_posix()
            files.append(
                {
                    "taskId": task_id,
                    "path": relative,
                    "name": path.name,
                    "group": relative.split("/", 1)[0],
                    "size": path.stat().st_size,
                    "language": LANGUAGES.get(path.suffix.lower(), "Text"),
                    "content": path.read_text(encoding="utf-8"),
                }
            )

    return tasks, files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("../data/chip_tasks"))
    parser.add_argument("--output-dir", type=Path, default=Path(".convex-import"))
    args = parser.parse_args()

    tasks, files = build_import(args.data_root.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "tasks.json").write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "taskFiles.json").write_text(json.dumps(files, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(tasks)} tasks and {len(files)} files to {args.output_dir}")


if __name__ == "__main__":
    main()
