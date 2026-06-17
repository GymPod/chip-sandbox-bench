# Vercel Provider

## Configuration

Implementation: `VercelSdkProvider` in `ts/src/providers.ts`.

Required credentials are read from the environment when any Vercel credential variable is present:

- `VERCEL_TOKEN`, `VERCEL_ACCESS_TOKEN`, or `VERCEL_API_KEY`
- `VERCEL_TEAM_ID`
- `VERCEL_PROJECT_ID`

If none of those variables are present, the SDK is called without explicit credentials and relies on ambient auth. The provider also wraps `fetch` to force `accept-encoding: identity`, which avoids compressed response handling issues in the SDK path.

## Sandbox Creation

Cold start:

```ts
VercelSandbox.create({
  runtime,
  timeout,
  resources: { vcpus: cpu }
})
```

Warm start:

```ts
VercelSandbox.create({
  source: { type: "snapshot", snapshotId },
  timeout,
  resources: { vcpus: cpu }
})
```

The runtime defaults to `python3.13` in `bench.ts` and `matrix.ts`, unless overridden with `--runtime` or `--vercel-runtime`.

Vercel currently receives CPU only through the SDK `resources` object. The harness still records memory and disk in result metadata for consistent reporting, but Vercel sandbox creation does not use those values here.

## Command Invocation

Commands are invoked with:

```ts
sandbox.runCommand({
  cmd: "/bin/sh",
  args: ["-lc", command],
  cwd,
  sudo: true,
  detached: true
})
```

The harness polls the detached process until it exits or the command timeout expires. It then reads stdout/stderr separately. On timeout, it sends `SIGTERM` and records exit code `124`.

Transient Vercel failures are retried at the task level when stderr contains stream aborts, connection errors, timeout errors, or `410` status responses.

## Environment Setup

### TerminalBench

TerminalBench tasks run in `/workspace`.

Prepare flow:

1. Decode `/tmp/task.tar.gz.b64` into `/tmp/task.tar.gz`.
2. Extract into `/tmp/tb`.
3. Copy task contents into `/workspace`.
4. Copy task `tests/` into `/tests`.
5. Copy task `solution/` into `/solution`.
6. Install `pytest==8.4.1` with user pip as a best-effort baseline.

When a TerminalBench prewarm profile is used, `ts/src/prewarm.ts` creates a Vercel sandbox, runs `TERMINALBENCH_VERCEL_PREWARM_COMMAND`, snapshots it, and emits:

```text
VERCEL_SNAPSHOT_ID=<snapshot-id>
```

Later warm runs pass that value through `--vercel-snapshot-id` or the `VERCEL_SNAPSHOT_ID` environment variable.

### SWE-Smith

Vercel cannot directly consume each SWE-Smith task Docker image in this harness, so SWE-Smith tasks use manifest-driven reconstruction in `/testbed`.

The manifest entry is loaded from `data/swesmith_env_manifests.json` by repo key. It contains:

- SWE-Smith mirror repo.
- Source branch/commit id.
- Python version.
- Profile install commands.
- Extra pip pins.
- System packages.
- Optional pre-verify commands.
- Optional resource overrides.

Prepare flow after archive extraction:

1. Install base system packages with `dnf`, `yum`, or `apt-get` when available.
2. Install or locate `uv`.
3. Install the manifest Python version under `/opt/uv-python`.
4. Create `/opt/testbed-venv`.
5. Clone the SWE-Smith mirror into `/testbed` at `source_id`.
6. Run the manifest install commands inside `/opt/testbed-venv`.
7. Install verifier dependencies in `/opt/verifier-venv`.
8. Create `/opt/miniconda3/bin/activate` and a no-op `conda` shim when the task expects conda.
9. Create an `agent` user when missing.
10. Rewrite `/solution/solve.sh` into the deterministic gold-solver form when gold patches are present.

The setup writes `/opt/bench-fallback-env-key`, a hash of repo, source id, Python version, install commands, pins, system packages, and pre-verify commands. If that key changes between tasks, the harness deletes `/opt/testbed-venv`, `/testbed`, and verifier state before rebuilding.

Verification exports:

```bash
PYTHONPATH=/testbed/src:${PYTHONPATH:-}
```

Then it runs `/tests/test.sh` when present. Otherwise it runs `pytest /tests/test_outputs.py -rA`.

## Cold And Warm Behavior

Cold Vercel runs create a fresh sandbox from `runtime`.

Warm Vercel runs create from `VERCEL_SNAPSHOT_ID` or `--vercel-snapshot-id`. This is mainly useful for TerminalBench-style generic runtimes.

For SWE-Smith, a Vercel snapshot can reduce generic setup, but each task still needs `/testbed` to match its repo manifest. The fallback setup invalidates stale `/testbed` state when the manifest key changes.

`matrix.ts` does not automatically omit Vercel warm args for SWE-Smith, but strict timing comparisons should treat Vercel SWE-Smith warm runs as manifest-reconstruction runs unless the snapshot was built for the same repo/env key.

## Cost Estimate

The harness estimates Vercel cost as:

```text
(seconds / 3600) * (cpu * 0.128 + memoryGb * 0.0212) + 0.60 / 1_000_000
```

This is a local reporting estimate and excludes model spend.

