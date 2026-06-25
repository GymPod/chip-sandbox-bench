import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchTask:
    task_id: str
    prompt: str
    instruction: str
    archive_b64: str
    task_files_encoding: str = "tar.gz+base64"
    data_source: str | None = None
    env_type: str | None = None


def iter_tasks(path: Path) -> Iterator[BenchTask]:
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                task_files = row["task_files"]
                yield BenchTask(
                    task_id=row["task_id"],
                    prompt=row["prompt"],
                    instruction=row["instruction"],
                    archive_b64=task_files["content"],
                    task_files_encoding=task_files.get("encoding", "tar.gz+base64"),
                    data_source=row.get("data_source"),
                    env_type=row.get("env_type"),
                )
        return

    import pyarrow.parquet as pq

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
                task_files_encoding=task_files.get("encoding", "tar.gz+base64"),
                data_source=instance.get("data_source") or row.get("data_source"),
                env_type=instance.get("env_type") or row.get("env_type"),
            )


def select_tasks(path: Path, task_index: str, task_limit: int | None = None) -> list[BenchTask]:
    tasks = list(iter_tasks(path))
    if task_index == "all":
        return tasks if task_limit is None else tasks[:task_limit]
    selected = [tasks[int(task_index)]]
    return selected if task_limit is None else selected[:task_limit]
