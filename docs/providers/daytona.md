# Daytona Provider

## Configuration

Implementation: `DaytonaProvider` in `ts/src/providers.ts`.

The Daytona client is created with:

```ts
new Daytona({
  apiKey: process.env.DAYTONA_API_KEY,
  apiUrl: process.env.DAYTONA_API_URL,
  target: process.env.DAYTONA_TARGET || undefined
})
```

Useful inputs:

- `DAYTONA_API_KEY`
- `DAYTONA_API_URL`
- `DAYTONA_TARGET`
- `--runtime` or `--daytona-runtime`, defaulting to `python:3.13` in `matrix.ts`
- `--daytona-snapshot` or `DAYTONA_SNAPSHOT`
- `--cpu`, `--memory-gb`, `--disk-gb`, `--timeout-seconds`

## Sandbox Creation

Daytona creates a unique sandbox name:

```text
code-sandbox-bench-<timestamp>-<random>
```

The sandbox is labeled:

```json
{ "app": "code-sandbox-bench" }
```

Resources are passed as:

```ts
resources: {
  cpu,
  memory: memoryGb,
  disk: diskGb
}
```

`bench.ts` caps Daytona disk to `10 GB` for task runs:

```ts
diskGb = provider === "daytona" ? Math.min(requestedDiskGb, 10) : requestedDiskGb
```

Cold start from an image:

```ts
client.create({
  image: commands.length > 0
    ? DaytonaImage.base(image).dockerfileCommands(commands)
    : image,
  resources,
  autoStopInterval: 0,
  autoDeleteInterval: 0
})
```

Warm start from a snapshot:

```ts
client.create({
  snapshot: daytonaSnapshot,
  resources,
  autoStopInterval: 0,
  autoDeleteInterval: 0
})
```

Sandbox creation is retried up to three times for retryable startup errors such as `502 Bad Gateway`, duplicate sandbox name, rate limits, `RESOURCE_EXHAUSTED`, `ECONNRESET`, and `ETIMEDOUT`.

## Command Invocation

Commands are invoked with:

```ts
sandbox.process.executeCommand(command, cwd, undefined, timeoutSeconds)
```

The provider returns stdout from `response.artifacts.stdout` or `response.result`. Stderr is not surfaced separately by this adapter, so result JSONs typically have empty `stderr_tail` for Daytona command failures unless the command itself writes diagnostic output into stdout.

The harness wraps command execution in a local timeout of `timeoutSeconds + 30`.

## Environment Setup

### TerminalBench

TerminalBench tasks run in `/workspace`.

Prepare flow:

1. Decode and extract the task archive.
2. Copy task files to `/workspace`.
3. Copy tests to `/tests`.
4. Copy solution files to `/solution`.
5. Install `pytest==8.4.1` with user pip as a best-effort baseline.

Daytona supports two TerminalBench warm paths:

- `DAYTONA_SNAPSHOT` / `--daytona-snapshot`: create from a saved Daytona snapshot.
- `--prewarm-profile terminalbench-smoke`: build from `TERMINALBENCH_DEBIAN_PREWARM_COMMANDS` when no snapshot is passed.

`ts/src/prewarm.ts` can create a named Daytona snapshot from the runtime plus profile commands and emits:

```text
DAYTONA_SNAPSHOT=<snapshot-name>
```

### SWE-Smith

Daytona supports Docker-image task runtimes in this harness, so SWE-Smith tasks use the task Docker image/Dockerfile setup rather than Vercel-style manifest reconstruction.

For each SWE-Smith task:

1. `resolveTaskEnv()` reads `environment/Dockerfile`.
2. It parses the `FROM` image as the runtime.
3. It converts the rest of the Dockerfile into Daytona Dockerfile commands.
4. It inlines `environment/hackblock/*`.
5. It appends:

```dockerfile
USER root
ENV HOME=/root
WORKDIR /testbed
```

The common prepare script extracts the task archive, copies tests and solution files, and rewrites `/solution/solve.sh` into the deterministic gold-solver form when gold patches are present.

Verification for SWE-Smith:

1. Runs repo-specific `pre_verify_cmds` from the manifest.
2. Exports `PYTHONPATH=/testbed/src`.
3. Runs `/tests/test.sh` when present.
4. Runs as `agent` when root and the image has that user.
5. Writes `/logs/verifier/reward.txt`.

Although Daytona uses task images directly, `data/swesmith_env_manifests.json` is still read for resource overrides and `pre_verify_cmds`.

## Cold And Warm Behavior

Cold Daytona runs create from the task/runtime image and apply any Dockerfile commands for that task.

Warm Daytona TerminalBench runs can create from `DAYTONA_SNAPSHOT`, or use the TerminalBench prewarm profile when the dataset path includes `terminalbench`.

For SWE-Smith, `matrix.ts` intentionally does not pass `--daytona-snapshot` or generic prewarm profile args. Each task can require a different image and Dockerfile setup, so a single warm artifact is not a safe shared task-Docker environment.

## Concurrency

`bench.ts` forces Daytona task-Docker datasets to one worker:

```ts
if (provider === "daytona" && tasks.some((task) => task.env_type === "harbor_swesmith")) {
  return 1;
}
```

`matrix.ts` also caps Daytona concurrency from resource limits:

```text
min(requested concurrency, floor(10 / cpu / modeCount), floor(10 / memoryGb / modeCount))
```

This keeps total requested CPU and memory under the account-level assumptions encoded in the harness.

## Cleanup

After a task, the provider deletes the sandbox and disposes the Daytona client:

```ts
client.delete(sandbox)
client[Symbol.asyncDispose]()
```

## Cost Estimate

The harness estimates Daytona cost as:

```text
seconds * (cpu * 0.000014 + memoryGb * 0.0000045 + max(0, diskGb - 5) * 0.00000003)
```

This is a local reporting estimate and excludes model spend.

