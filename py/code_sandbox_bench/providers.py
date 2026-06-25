import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    return_code: int


class Provider(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def run(self, command: str, cwd: str | None, timeout: int) -> CommandResult: ...

    @abstractmethod
    async def stop(self) -> None: ...

    def metadata(self) -> dict[str, object]:
        return {}


class LocalProvider(Provider):
    def __init__(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="code-sandbox-bench-local-"))

    async def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    async def run(self, command: str, cwd: str | None, timeout: int) -> CommandResult:
        workdir = self.root / cwd.lstrip("/") if cwd else self.root
        workdir.mkdir(parents=True, exist_ok=True)
        local_command = self._localize(command)
        env = os.environ.copy()
        env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
        if sys.prefix != sys.base_prefix:
            env["VIRTUAL_ENV"] = sys.prefix
        proc = await asyncio.create_subprocess_shell(
            local_command,
            cwd=workdir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return CommandResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"), 124)
        return CommandResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode or 0)

    async def stop(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _localize(self, command: str) -> str:
        command = re.sub(r"(?<![A-Za-z0-9_.-])/workspace\b", str(self.root / "workspace"), command)
        command = re.sub(r"(?<![A-Za-z0-9_.-])/testbed\b", str(self.root / "testbed"), command)
        command = re.sub(r"(?<![A-Za-z0-9_.-])/tests\b", str(self.root / "tests"), command)
        command = re.sub(r"(?<![A-Za-z0-9_.-])/solution\b", str(self.root / "solution"), command)
        command = re.sub(r"(?<![A-Za-z0-9_.-])/logs\b", str(self.root / "logs"), command)
        command = re.sub(r"(?<![A-Za-z0-9_.-])/tmp/", str(self.root / "tmp") + "/", command)
        return command


class VercelCliProvider(Provider):
    def __init__(self, runtime: str, timeout: str) -> None:
        self.runtime = runtime
        self.timeout = timeout
        self.sandbox_id: str | None = None

    async def start(self) -> None:
        result = subprocess.run(
            ["sandbox", "create", "--runtime", self.runtime, "--timeout", self.timeout],
            check=True,
            text=True,
            capture_output=True,
        )
        match = re.search(r"\b(sb_[A-Za-z0-9_-]+)\b", result.stdout + result.stderr)
        if match is None:
            raise RuntimeError(f"Could not parse Vercel sandbox id from output:\n{result.stdout}\n{result.stderr}")
        self.sandbox_id = match.group(1)

    async def run(self, command: str, cwd: str | None, timeout: int) -> CommandResult:
        if self.sandbox_id is None:
            raise RuntimeError("Vercel sandbox not started")
        args = ["sandbox", "exec"]
        if cwd is not None:
            args += ["--workdir", cwd]
        args += [self.sandbox_id, command]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return CommandResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"), 124)
        return CommandResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode or 0)

    async def stop(self) -> None:
        if self.sandbox_id is not None:
            subprocess.run(["sandbox", "stop", self.sandbox_id], text=True, capture_output=True, check=False)
            self.sandbox_id = None


class DockerProvider(Provider):
    def __init__(self, image: str, timeout: int, cpu: int, memory_gb: int) -> None:
        self.image = image
        self.timeout = timeout
        self.cpu = cpu
        self.memory_gb = memory_gb
        self.container_name = f"code-sandbox-bench-py-{uuid.uuid4().hex[:12]}"

    async def start(self) -> None:
        args = [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            self.container_name,
            "--cpus",
            str(self.cpu),
            "--memory",
            f"{self.memory_gb}g",
            self.image,
            "sleep",
            "infinity",
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError((stderr or stdout).decode(errors="replace"))

    async def run(self, command: str, cwd: str | None, timeout: int) -> CommandResult:
        args = ["docker", "exec"]
        if cwd is not None:
            args += ["-w", cwd]
        args += [self.container_name, "/bin/sh", "-lc", command]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            stdout, stderr = await proc.communicate()
            return CommandResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"), 124)
        return CommandResult(stdout.decode(errors="replace"), stderr.decode(errors="replace"), proc.returncode or 0)

    async def stop(self) -> None:
        subprocess.run(["docker", "rm", "-f", self.container_name], text=True, capture_output=True, check=False)


class ModalProvider(Provider):
    def __init__(self, image: str, timeout: int, cpu: float, memory_mb: int) -> None:
        self.image = image
        self.timeout = timeout
        self.cpu = cpu
        self.memory_mb = memory_mb
        self.app = None
        self.sandbox = None

    async def start(self) -> None:
        import modal

        modal_image = modal.Image.from_registry(self.image)
        self.app = await modal.App.lookup.aio("code-sandbox-bench", create_if_missing=True)
        self.sandbox = await modal.Sandbox.create.aio(
            "sleep",
            "infinity",
            app=self.app,
            image=modal_image,
            timeout=self.timeout,
            cpu=self.cpu,
            memory=self.memory_mb,
        )

    async def run(self, command: str, cwd: str | None, timeout: int) -> CommandResult:
        if self.sandbox is None:
            raise RuntimeError("Modal sandbox not started")
        proc = await self.sandbox.exec.aio("/bin/sh", "-lc", command, workdir=cwd, timeout=timeout, text=False)
        stdout_parts: list[bytes] = []
        stderr_parts: list[bytes] = []
        async for chunk in proc.stdout:
            stdout_parts.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        async for chunk in proc.stderr:
            stderr_parts.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        await proc.wait.aio()
        return CommandResult(
            b"".join(stdout_parts).decode(errors="replace"),
            b"".join(stderr_parts).decode(errors="replace"),
            proc.returncode or 0,
        )

    async def stop(self) -> None:
        if self.sandbox is not None:
            await self.sandbox.terminate.aio()
            self.sandbox = None


class DaytonaProvider(Provider):
    def __init__(self, image: str, timeout: int, cpu: int, memory_gb: int, disk_gb: int) -> None:
        self.image = image
        self.timeout = timeout
        self.cpu = cpu
        self.memory_gb = memory_gb
        self.disk_gb = disk_gb
        self.client = None
        self.sandbox = None

    async def start(self) -> None:
        from daytona_sdk import AsyncDaytona, CreateSandboxFromImageParams, DaytonaConfig, Image, Resources

        self.client = AsyncDaytona(
            DaytonaConfig(
                api_key=os.environ.get("DAYTONA_API_KEY", ""),
                api_url=os.environ.get("DAYTONA_API_URL", ""),
                target=os.environ.get("DAYTONA_TARGET") or None,
            )
        )
        self.sandbox = await self.client.create(
            params=CreateSandboxFromImageParams(
                image=Image.base(self.image),
                resources=Resources(cpu=self.cpu, memory=self.memory_gb, disk=self.disk_gb),
                auto_stop_interval=0,
                auto_delete_interval=0,
            ),
            timeout=self.timeout,
        )

    async def run(self, command: str, cwd: str | None, timeout: int) -> CommandResult:
        if self.sandbox is None:
            raise RuntimeError("Daytona sandbox not started")
        response = await self.sandbox.process.exec(command=command, cwd=cwd, timeout=timeout)
        stdout = response.artifacts.stdout if response.artifacts else ""
        return CommandResult(stdout or response.result or "", "", response.exit_code or 0)

    async def stop(self) -> None:
        if self.client is not None and self.sandbox is not None:
            await self.client.remove(self.sandbox)
        if self.client is not None:
            await self.client.close()
        self.client = None
        self.sandbox = None


class AwsMicrovmProvider(Provider):
    def __init__(
        self,
        image_id: str | None,
        image_version: str | None,
        execution_role_arn: str | None,
        timeout: int,
        cpu: int,
        memory_gb: int,
    ) -> None:
        self.image_id = image_id or os.environ.get("AWS_MICROVM_IMAGE_ID") or os.environ.get("AWS_MICROVM_IMAGE_ARN")
        self.image_version = image_version or os.environ.get("AWS_MICROVM_IMAGE_VERSION")
        self.execution_role_arn = execution_role_arn or os.environ.get("AWS_MICROVM_EXECUTION_ROLE_ARN")
        self.timeout = timeout
        self.cpu = cpu
        self.memory_gb = memory_gb
        self.proc: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._metadata: dict[str, object] = {}

    async def start(self) -> None:
        if not self.image_id:
            raise RuntimeError("AWS_MICROVM_IMAGE_ID or --aws-microvm-image-id is required")
        repo_root = Path(__file__).resolve().parents[2]
        self.proc = await asyncio.create_subprocess_exec(
            "bun",
            "ts/src/aws_microvm_py_bridge.ts",
            cwd=repo_root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._request(
            "start",
            {
                "imageIdentifier": self.image_id,
                "imageVersion": self.image_version,
                "executionRoleArn": self.execution_role_arn,
                "timeoutSeconds": self.timeout,
                "cpu": self.cpu,
                "memoryGb": self.memory_gb,
            },
            timeout=self.timeout + 30,
        )

    async def run(self, command: str, cwd: str | None, timeout: int) -> CommandResult:
        response = await self._request(
            "run",
            {"command": command, "cwd": cwd, "timeoutSeconds": timeout},
            timeout=timeout + 30,
        )
        data = response.get("result") or {}
        return CommandResult(
            str(data.get("stdout") or ""),
            str(data.get("stderr") or ""),
            int(data.get("returnCode") or 0),
        )

    async def stop(self) -> None:
        if self.proc is None:
            return
        try:
            await self._request("stop", {}, timeout=60)
        finally:
            if self.proc.returncode is None:
                self.proc.terminate()
                await self.proc.wait()
            self.proc = None

    def metadata(self) -> dict[str, object]:
        return self._metadata

    async def _request(self, op: str, payload: dict[str, object], timeout: int) -> dict[str, object]:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("AWS MicroVM bridge is not running")
        self._request_id += 1
        request = {"id": self._request_id, "op": op, **payload}
        self.proc.stdin.write((json.dumps(request) + "\n").encode())
        await self.proc.stdin.drain()
        try:
            line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=timeout)
        except TimeoutError as exc:
            raise RuntimeError(f"AWS MicroVM bridge timed out during {op}") from exc
        if not line:
            stderr = ""
            if self.proc.stderr is not None:
                stderr = (await self.proc.stderr.read()).decode(errors="replace")
            raise RuntimeError(f"AWS MicroVM bridge exited during {op}: {stderr}")
        response = json.loads(line.decode())
        if response.get("id") != self._request_id:
            raise RuntimeError(f"AWS MicroVM bridge returned mismatched response: {response}")
        if isinstance(response.get("metadata"), dict):
            self._metadata = response["metadata"]
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error") or "AWS MicroVM bridge request failed"))
        return response


def make_provider(
    name: str,
    runtime: str,
    timeout: int,
    cpu: int,
    memory_gb: int,
    disk_gb: int,
    aws_microvm_image_id: str | None = None,
    aws_microvm_image_version: str | None = None,
    aws_microvm_execution_role_arn: str | None = None,
) -> Provider:
    if name == "local":
        return LocalProvider()
    if name == "vercel":
        return VercelCliProvider(runtime=runtime, timeout=f"{timeout}s")
    if name == "docker":
        return DockerProvider(image=runtime, timeout=timeout, cpu=cpu, memory_gb=memory_gb)
    if name == "modal":
        return ModalProvider(image=runtime, timeout=timeout, cpu=float(cpu), memory_mb=memory_gb * 1024)
    if name == "daytona":
        return DaytonaProvider(image=runtime, timeout=timeout, cpu=cpu, memory_gb=memory_gb, disk_gb=disk_gb)
    if name == "aws-microvm":
        return AwsMicrovmProvider(
            image_id=aws_microvm_image_id,
            image_version=aws_microvm_image_version,
            execution_role_arn=aws_microvm_execution_role_arn,
            timeout=timeout,
            cpu=cpu,
            memory_gb=memory_gb,
        )
    raise ValueError(f"Unsupported provider: {name}")


async def write_text(provider: Provider, remote_path: str, content: str, timeout: int) -> None:
    quoted_path = shlex.quote(remote_path)
    await provider.run(f"mkdir -p $(dirname {quoted_path}) && : > {quoted_path}", cwd=None, timeout=timeout)
    for offset in range(0, len(content), 30000):
        chunk = shlex.quote(content[offset : offset + 30000])
        result = await provider.run(f"printf %s {chunk} >> {quoted_path}", cwd=None, timeout=timeout)
        if result.return_code != 0:
            raise RuntimeError(result.stderr or result.stdout)
