# Modal Provider

## Configuration

Implementation: `ModalProvider` in `ts/src/providers.ts`.

The provider uses the Modal SDK default credential discovery through:

```ts
new ModalClient()
```

The harness creates or reuses a Modal app named:

```text
code-sandbox-bench
```

Useful inputs:

- `--runtime` or `--modal-runtime`: base image name, defaulting to `python:3.13` in `matrix.ts`.
- `--modal-image-id` or `MODAL_IMAGE_ID`: prebuilt image id for warm TerminalBench runs.
- `--cpu`, `--memory-gb`, `--timeout-seconds`: sandbox resources and command timeout.

## Sandbox Creation

Modal starts from either a prebuilt image id or a registry image:

```ts
const image = modalImageId
  ? await client.images.fromId(modalImageId)
  : client.images.fromRegistry(runtimeOrTaskImage)
```

When no prebuilt image id is provided and Dockerfile commands exist, the harness builds:

```ts
image.dockerfileCommands(commands).build(app)
```

Then it creates a long-lived command sandbox:

```ts
client.sandboxes.create(app, image, {
  command: ["sleep", "infinity"],
  timeoutMs,
  cpu: cpu / 2,
  memoryMiB: memoryGb * 1024
})
```

Modal CPU is passed as `cpu / 2`, so the default harness `--cpu 2` becomes Modal `cpu: 1`.

## Command Invocation

Commands are invoked with:

```ts
sandbox.exec(["/bin/sh", "-lc", command], {
  workdir: cwd,
  timeoutMs,
  mode: "text"
})
```

The harness reads stdout, stderr, and the process exit code, wrapped in a local timeout of `timeoutSeconds + 30`.

Transient Modal failures are retried at the task level when stderr includes deadline, stream, image join, unavailable, reset, DNS, refused connection, or missing connection messages.

## Environment Setup

### TerminalBench

TerminalBench tasks run in `/workspace`.

Prepare flow:

1. Decode and extract the task archive.
2. Copy task files to `/workspace`.
3. Copy tests to `/tests`.
4. Copy solution files to `/solution`.
5. Install `pytest==8.4.1` with user pip as a best-effort baseline.

For TerminalBench warm images, `ts/src/prewarm.ts` builds a Modal image from the requested runtime plus `TERMINALBENCH_DEBIAN_PREWARM_COMMANDS`. It emits:

```text
MODAL_IMAGE_ID=<image-id>
```

Warm runs pass that with `--modal-image-id` or the `MODAL_IMAGE_ID` environment variable.

### SWE-Smith

Modal supports Docker-image task runtimes in this harness, so SWE-Smith tasks do not use the Vercel fallback runtime as the primary environment.

For each SWE-Smith task:

1. `resolveTaskEnv()` reads `environment/Dockerfile` from the task archive.
2. It parses the `FROM` image as the runtime.
3. It converts the remaining Dockerfile instructions into Modal Dockerfile commands.
4. It inlines `environment/hackblock/*` files because provider builds do not have the original archive filesystem.
5. It appends:

```dockerfile
USER root
ENV HOME=/root
WORKDIR /testbed
```

The root user override lets the harness prepare `/tests`, `/solution`, `/logs`, and deterministic solve scripts consistently even when the original task image ended as the unprivileged `agent` user.

The common prepare script still extracts the task archive, copies tests and solution files, and rewrites `/solution/solve.sh` into an idempotent deterministic gold-solver form when gold patches are present.

Verification for SWE-Smith:

1. Runs repo-specific `pre_verify_cmds` from `data/swesmith_env_manifests.json`.
2. Writes `/tmp/bench-verify.sh`.
3. Exports `PYTHONPATH=/testbed/src`.
4. Runs `/tests/test.sh` when present.
5. Runs as user `agent` when root and an `agent` user exists, matching SWE-Smith image semantics.
6. Writes `/logs/verifier/reward.txt`.

Repo-specific manifest overrides still matter for Modal because `pre_verify_cmds`, resource overrides, and task-specific verifier repairs are consumed even though Modal uses task Docker images.

## Cold And Warm Behavior

Cold Modal runs create from the task/runtime image and build any Dockerfile commands needed for that task.

Warm Modal TerminalBench runs can use `MODAL_IMAGE_ID`.

For SWE-Smith, `matrix.ts` intentionally does not pass generic warm artifacts to Modal. Each task can require a different SWE-Smith image and Dockerfile command set, so a single prebuilt image is not a safe shared warm artifact.

## Concurrency

For task-Docker datasets such as SWE-Smith, `matrix.ts` defaults Modal task concurrency to `1` unless overridden with `--modal-concurrency`.

The single-provider `bench.ts` runner accepts `--concurrency`, but provider transport and image build pressure make lower concurrency safer for SWE-Smith.

## Cost Estimate

The harness estimates Modal cost as:

```text
seconds * ((cpu / 2) * 0.00003942 + memoryGb * 0.00000672)
```

This is a local reporting estimate and excludes model spend.

