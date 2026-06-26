import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from code_sandbox_bench.providers import CommandResult


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AgentTraceRecorder:
    def __init__(self, provider: str, task_id: str) -> None:
        self.trace_id = str(uuid.uuid4())
        self.provider = provider
        self.task_id = task_id
        self.started_at = iso_now()
        self.completed_at: str | None = None
        self.events: list[dict[str, Any]] = []
        self._last_completed_wall: float | None = None
        self._last_completed_command_wall: float | None = None

    async def lifecycle(self, label: str, action: Callable[[], Awaitable[Any]]) -> Any:
        return await self._record("lifecycle", label, None, action)

    async def command(
        self,
        label: str,
        command: str,
        cwd: str | None,
        timeout_seconds: int,
        action: Callable[[], Awaitable[CommandResult]],
    ) -> CommandResult:
        metadata = {
            "cwd": cwd,
            "timeout_seconds": timeout_seconds,
            "command_length": len(command),
            "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        }
        return await self._record("command", label, metadata, action)

    def finish(self) -> None:
        self.completed_at = iso_now()

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "trace_id": self.trace_id,
            "provider": self.provider,
            "task_id": self.task_id,
            "started_at": self.started_at,
            **({"completed_at": self.completed_at} if self.completed_at else {}),
            "event_count": len(self.events),
            "command_count": sum(1 for event in self.events if event.get("type") == "command"),
            "idle_gap_summary": summarize_idle_gaps(self.events),
            "events": self.events,
        }

    async def _record(
        self,
        event_type: str,
        label: str,
        metadata: dict[str, Any] | None,
        action: Callable[[], Awaitable[Any]],
    ) -> Any:
        started_wall = time.time()
        started_mono = time.monotonic()
        started_at = iso_now()
        idle_gap = None if self._last_completed_wall is None else max(0.0, started_wall - self._last_completed_wall)
        command_idle_gap = (
            None
            if event_type != "command" or self._last_completed_command_wall is None
            else max(0.0, started_wall - self._last_completed_command_wall)
        )
        try:
            result = await action()
            completed_wall = time.time()
            event: dict[str, Any] = {
                "index": len(self.events),
                "type": event_type,
                "label": label,
                "status": "completed",
                "started_at": started_at,
                "completed_at": iso_now(),
                "duration_seconds": time.monotonic() - started_mono,
                **({} if idle_gap is None else {"idle_gap_seconds": idle_gap}),
                **({} if command_idle_gap is None else {"command_idle_gap_seconds": command_idle_gap}),
                **(metadata or {}),
            }
            if isinstance(result, CommandResult):
                event["return_code"] = result.return_code
                if result.usage:
                    event["command_usage"] = result.usage
            self.events.append(event)
            self._last_completed_wall = completed_wall
            if event_type == "command":
                self._last_completed_command_wall = completed_wall
            return result
        except Exception as error:
            completed_wall = time.time()
            self.events.append(
                {
                    "index": len(self.events),
                    "type": event_type,
                    "label": label,
                    "status": "failed",
                    "started_at": started_at,
                    "completed_at": iso_now(),
                    "duration_seconds": time.monotonic() - started_mono,
                    **({} if idle_gap is None else {"idle_gap_seconds": idle_gap}),
                    **({} if command_idle_gap is None else {"command_idle_gap_seconds": command_idle_gap}),
                    **(metadata or {}),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            self._last_completed_wall = completed_wall
            if event_type == "command":
                self._last_completed_command_wall = completed_wall
            raise


class TracedProvider:
    def __init__(self, provider: Any, recorder: AgentTraceRecorder) -> None:
        self.provider = provider
        self.recorder = recorder

    async def start(self) -> None:
        await self.recorder.lifecycle("start", self.provider.start)

    async def run(
        self,
        command: str,
        cwd: str | None,
        timeout: int,
        trace: dict[str, Any] | None = None,
    ) -> CommandResult:
        label = str((trace or {}).get("label") or "command")
        return await self.recorder.command(label, command, cwd, timeout, lambda: self.provider.run(command, cwd, timeout, trace))

    async def stop(self) -> None:
        await self.recorder.lifecycle("stop", self.provider.stop)

    def metadata(self) -> dict[str, Any]:
        metadata = getattr(self.provider, "metadata", None)
        return metadata() if callable(metadata) else {}


def summarize_agent_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = [
        float(event["command_idle_gap_seconds"])
        for trace in traces
        for event in trace.get("events", [])
        if isinstance(event, dict) and isinstance(event.get("command_idle_gap_seconds"), (int, float))
    ]
    return {
        "trace_count": len(traces),
        "command_count": sum(int(trace.get("command_count") or 0) for trace in traces),
        **summarize_idle_gap_values(gaps),
    }


def summarize_idle_gaps(events: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_idle_gap_values(
        [
            float(event["command_idle_gap_seconds"])
            for event in events
            if isinstance(event.get("command_idle_gap_seconds"), (int, float))
        ]
    )


def summarize_idle_gap_values(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "max_seconds": max(values) if values else 0,
        "over_10s": sum(1 for value in values if value >= 10),
        "over_60s": sum(1 for value in values if value >= 60),
        "over_300s": sum(1 for value in values if value >= 300),
    }
