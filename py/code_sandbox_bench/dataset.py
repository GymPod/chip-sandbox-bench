import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq


@dataclass(frozen=True)
class BenchTask:
    task_id: str
    prompt: str
    instruction: str
    archive_b64: str


def iter_tasks(path: Path) -> Iterator[BenchTask]:
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                yield BenchTask(
                    task_id=row["task_id"],
                    prompt=row["prompt"],
                    instruction=row["instruction"],
                    archive_b64=row["task_files"]["content"],
                )
        return

    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=8):
        for row in batch.to_pylist():
            instance = row["metadata"]["instance"]
            task_files = json.loads(instance["task_files"])
            yield BenchTask(
                task_id=instance["task_id"],
                prompt=row["prompt"],
                instruction=instance["instruction"],
                archive_b64=task_files["content"],
            )


def select_tasks(path: Path, task_index: str) -> list[BenchTask]:
    tasks = list(iter_tasks(path))
    if task_index == "all":
        return tasks
    return [tasks[int(task_index)]]

