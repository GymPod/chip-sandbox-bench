# AWS Lambda MicroVM Provider

## Configuration

Implementation:

- `AwsMicrovmProvider` in `ts/src/providers.ts`
- AWS SDK facade in `ts/src/aws_microvm_sdk.ts` (`AwsMicrovm`, `AwsMicrovmSandbox`)
- compatibility exports in `ts/src/aws_microvm.ts`
- runner image artifact in `ts/aws-microvm-runner/`

Required inputs:

- `AWS_REGION`, defaulting to `us-east-1`
- `AWS_MICROVM_IMAGE_ID` or `--aws-microvm-image-id`
- `AWS_MICROVM_IMAGE_VERSION` or `--aws-microvm-image-version`, optional but recommended for repeatability
- `AWS_MICROVM_BUILD_ROLE_ARN` for `bun run prewarm --provider aws-microvm`
- One MicroVM image artifact source for `bun run prewarm --provider aws-microvm`:
  - `AWS_MICROVM_CODE_ARTIFACT_URI` or `--aws-code-artifact-uri` for a prebuilt ECR image URI
  - `AWS_MICROVM_ARTIFACT_BUCKET` or `--aws-bucket` for the default S3 zip upload path

Useful runtime controls:

- `AWS_MICROVM_MAX_DURATION_SECONDS`, defaulting to `timeoutSeconds + 180` with a 3600s cap
- `AWS_MICROVM_START_TIMEOUT_SECONDS`, default `600`
- `AWS_MICROVM_QUOTA_RETRY_SECONDS`, default `15`
- `AWS_MICROVM_SESSION_MODE`, default `terminate`; supported values: `terminate`, `auto-suspend`, `explicit-suspend`
- `AWS_MICROVM_MAX_IDLE_DURATION_SECONDS`, default `120` in `terminate` mode and `300` in session modes
- `AWS_MICROVM_SUSPENDED_DURATION_SECONDS`, default `0` in `terminate` mode and `25200` in session modes
- `AWS_MICROVM_AUTO_RESUME`, default `false` in `terminate` / `explicit-suspend` and `true` in `auto-suspend`
- `AWS_MICROVM_FIRST_REQUEST_TIMEOUT_SECONDS`, default `15` in `terminate` mode and `60` in session modes
- `AWS_MICROVM_RESUME_TIMEOUT_SECONDS`, default `120`
- `AWS_MICROVM_RESUME_CHECK_AFTER_IDLE_SECONDS`, default `60`
- `AWS_MICROVM_ACCOUNT_MEMORY_GB`, default `4`
- `AWS_MICROVM_MAX_CONCURRENCY`, default `1` in `bench.ts`
- `AWS_MICROVM_INGRESS_CONNECTORS`, default `ALL_INGRESS`
- `AWS_MICROVM_EGRESS_CONNECTORS`, default `INTERNET_EGRESS`
- `AWS_MICROVM_ESTIMATE_VCPU_SECOND_USD`, `AWS_MICROVM_ESTIMATE_GB_SECOND_USD`, `AWS_MICROVM_ESTIMATE_SNAPSHOT_WRITE_GB_USD`, `AWS_MICROVM_ESTIMATE_SNAPSHOT_READ_GB_USD`, and `AWS_MICROVM_ESTIMATE_SNAPSHOT_STORAGE_GB_MONTH_USD` override lifecycle cost estimates.

The AWS MicroVM static `bench` default keeps `--memory-gb 2` for fixed-resource comparisons, but the checked-in adaptive resource config lowers the effective AWS default to 1 GB. The AWS `prewarm` command also defaults to 1 GB so newly built adaptive images do not bake in a 2 GB minimum. The AWS runtime estimate derives billable vCPU from memory at `memoryGb / 2`.

## Image Creation

Create the reusable runner image with the default S3 artifact path:

```bash
cd ts
bun run prewarm \
  --provider aws-microvm \
  --name code-sandbox-bench-runner-YYYYMMDD \
  --timeout-seconds 900 \
  --memory-gb 1 \
  --aws-region us-east-1 \
  --aws-bucket <artifact-bucket> \
  --aws-build-role-arn <build-role-arn> \
  --output ../results/prewarm-aws-microvm.json
```

The prewarm script packages `ts/aws-microvm-runner/`, uploads it to S3, calls `CreateMicrovmImage`, waits for `CREATED`, and emits:

```text
AWS_REGION=...
AWS_MICROVM_IMAGE_ID=...
AWS_MICROVM_IMAGE_VERSION=...
```

To use ECR as the MicroVM code artifact, first build and push the runner image:

```bash
AWS_ACCOUNT_ID=<account-id>
AWS_REGION=us-east-1
ECR_REPO=code-sandbox-bench-runner
ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO"

aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" || true
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
docker buildx build --platform linux/arm64 \
  -t "$ECR_URI:YYYYMMDD" \
  --push \
  ts/aws-microvm-runner
```

Then create the MicroVM image from that ECR artifact:

```bash
cd ts
bun run prewarm \
  --provider aws-microvm \
  --name code-sandbox-bench-runner-YYYYMMDD \
  --timeout-seconds 900 \
  --memory-gb 1 \
  --aws-region us-east-1 \
  --aws-code-artifact-uri <account-id>.dkr.ecr.us-east-1.amazonaws.com/code-sandbox-bench-runner:YYYYMMDD \
  --aws-build-role-arn <build-role-arn> \
  --output ../results/prewarm-aws-microvm.json
```

For repeatability, prefer an ECR digest URI after pushing:

```text
<account-id>.dkr.ecr.us-east-1.amazonaws.com/code-sandbox-bench-runner@sha256:<digest>
```

The command still calls `CreateMicrovmImage`, waits for `CREATED`, and emits:

```text
AWS_REGION=...
AWS_MICROVM_IMAGE_ID=...
AWS_MICROVM_IMAGE_VERSION=...
```

For private ECR repositories, the MicroVM build role must be able to pull the image:

```json
{
  "Effect": "Allow",
  "Action": [
    "ecr:GetAuthorizationToken",
    "ecr:BatchCheckLayerAvailability",
    "ecr:GetDownloadUrlForLayer",
    "ecr:BatchGetImage"
  ],
  "Resource": "*"
}
```

Lifecycle hooks are disabled by default for the MVP image. Set `AWS_MICROVM_ENABLE_HOOKS=1` to include `/ready`, `/validate`, `/run`, `/resume`, `/suspend`, and `/terminate` hooks exposed by the runner.

## Runtime Lifecycle

The AWS provider has three layers:

- `AwsMicrovmProvider` in `ts/src/providers.ts`, which adapts the benchmark `Provider` contract.
- `AwsMicrovm` / `AwsMicrovmSandbox` in `ts/src/aws_microvm_sdk.ts`, which bake AWS region, image, lifecycle, auth, connector, retry, and pricing defaults into a Daytona-shaped client/sandbox interface.
- A repo-owned Python command runner in `ts/aws-microvm-runner/server.py`, baked into the MicroVM image and listening on port `8080`.

Most benchmark commands do not call an AWS "exec" API. The local SDK facade starts and exposes the MicroVM; after that, command execution is an authenticated HTTPS request to `server.py` inside the MicroVM.

### Start

`bench.ts` creates the provider and times `activeProvider.start()`. For `aws-microvm`, this calls:

```text
bench.ts
  -> makeProvider("aws-microvm")
  -> AwsMicrovmProvider.start()
  -> AwsMicrovm.create(...)
  -> AwsMicrovmSandbox.start()
```

`AwsMicrovmSandbox.start()` then:

1. Calls `RunMicrovm` with the configured image id/version, optional execution role ARN, duration, idle policy, ingress connectors, egress connectors, logging, and a unique client token.
2. Retries `ServiceQuotaExceededException` until `AWS_MICROVM_START_TIMEOUT_SECONDS` expires. This handles the case where AWS still has memory quota reserved for a recently terminated MicroVM.
3. Stores the returned `microvmId` and HTTPS `endpoint`.
4. Calls `GetMicrovm` while waiting so the endpoint can be refreshed if AWS reports a newer value.
5. Creates a port-scoped token with `CreateMicrovmAuthToken` for port `8080`.
6. Polls `GET /health` through the MicroVM endpoint until `server.py` responds.

The `/health` handler lives in `server.py` and returns `{"ok": true}`. This is the first point where the harness proves that the in-VM runner, not just the AWS resource, is ready.

### Harness Commands

Every harness phase after start goes through the common `Provider.run(command, cwd, timeoutSeconds)` contract:

```text
upload task archive
prepare environment
write task instructions
solve
verify
```

For AWS MicroVMs, `AwsMicrovmProvider.run()` delegates to `AwsMicrovmSandbox.process.executeCommand(...)`, which sends the command to `server.py`:

1. Ensure `microvmId` and endpoint are present.
2. Create or reuse a cached `CreateMicrovmAuthToken` value.
3. `POST /commands` to the MicroVM endpoint with:

```json
{
  "command": "<shell command>",
  "cwd": "/workspace",
  "timeoutSeconds": 300
}
```

4. `server.py` validates that `command` is non-empty and that `cwd`, when provided, is an absolute path.
5. `server.py` creates a job id, records job metadata in memory, creates stdout/stderr file paths under `/tmp/code-sandbox-bench-jobs`, and starts a daemon thread.
6. The daemon thread runs:

```text
/bin/sh -lc <command>
```

with `cwd` or `/`, the MicroVM environment, and the requested subprocess timeout.

7. stdout and stderr are written directly to job files instead of being retained in request memory.
8. The TypeScript provider polls `GET /commands/<jobId>` until `status == "completed"`.
9. `server.py` reads the tail of the stdout/stderr files, capped by `AWS_MICROVM_RUNNER_MAX_OUTPUT_BYTES`, and returns `{ stdout, stderr, returnCode }`.

The async job shape avoids holding one HTTPS request open for long dependency installs. It also lets the TypeScript side survive retryable proxy and service errors while polling: HTTP 5xx, 408, 409, 429, and network timeouts are retried until the command timeout budget is exhausted.

`server.py` still contains a synchronous `POST /run-command` endpoint, but the benchmark provider uses `/commands` plus `/commands/<jobId>` for normal task execution.

### Agent Trace Logging

Every benchmark result now includes per-task `agent_trace` data and a top-level `agent_trace_summary`. This is the primary local evidence for tuning AWS MicroVM session idle policy.

The trace records:

- lifecycle events for `start` and `stop`;
- command events for upload chunks, prepare, instruction writes, solve, and verify;
- wall-clock start/end timestamps, duration, `idle_gap_seconds` between all events, and `command_idle_gap_seconds` between provider commands;
- command cwd, timeout, return code, length, and SHA-256.

Raw command text is intentionally not stored because solver commands can contain forwarded environment values. Use the idle-gap buckets in `agent_trace_summary` (`over_10s`, `over_60s`, `over_300s`) when evaluating whether auto-suspend thresholds are worthwhile for coding-agent traffic.

### Session Modes

`AWS_MICROVM_SESSION_MODE=terminate` preserves existing benchmark behavior: `stop()` calls `TerminateMicrovm`, releases quota, and leaves no suspended session behind.

`AWS_MICROVM_SESSION_MODE=auto-suspend` keeps the MicroVM identity alive across calls to `stop()` by explicitly suspending instead of terminating. Its idle policy enables AWS auto-resume, so the next request to the endpoint can wake the MicroVM. The provider uses a longer first-request timeout in this mode and retries one transient first-request failure after refreshing state, endpoint, and auth token.

`AWS_MICROVM_SESSION_MODE=explicit-suspend` also suspends on `stop()`, but it resumes through `ResumeMicrovm` before the next command when the state is `SUSPENDED`. This is useful for product paths that know they are parking a session and want resume latency measured separately from command runtime.

Both session modes emit an `aws_microvm` object in each benchmark row with lifecycle events, state, suspend/resume counts, and estimated lifecycle cost buckets.

### Lifecycle Hooks

Lifecycle hooks are separate from benchmark command execution. When `AWS_MICROVM_ENABLE_HOOKS=1` is set during image creation, `CreateMicrovmImage` includes `/ready`, `/validate`, `/run`, `/resume`, `/suspend`, and `/terminate` hooks under the AWS Lambda MicroVM runtime prefix:

```text
/aws/lambda-microvms/runtime/v1/<hook>
```

`server.py` handles those hook POSTs by ensuring runtime directories exist, validating basic runner readiness, persisting job metadata under `/tmp/code-sandbox-bench-jobs/jobs.json`, and flushing filesystem buffers on `/suspend` and `/terminate`. The harness does not depend on the hooks for task upload, prepare, solve, verify, or cleanup, but session-mode images should enable them.

### Stop

After each task, `bench.ts` calls the provider cleanup path. For AWS MicroVMs:

```text
AwsMicrovmProvider.stop()
  -> AwsMicrovm.delete(sandbox)
  -> AwsMicrovmSandbox.stop()
  -> TerminateMicrovm
```

In `terminate` mode, the provider clears its endpoint and cached auth token before sending `TerminateMicrovm`. `ResourceNotFound` during termination is ignored because the desired final state is already reached. In session modes, `stop()` suspends instead of terminating; use the reaper or direct `terminate()` cleanup path for abandoned sessions.

## Comparison With SDK-Managed Providers

AWS MicroVMs expose a lower-level lifecycle than the other SDKs used by this harness. The harness owns more of the command execution protocol.

| Provider | Start path | Command path | Stop path | Harness-owned runner? |
| --- | --- | --- | --- | --- |
| AWS MicroVM | `AwsMicrovm.create(...)`, backed by `RunMicrovm`, then `GetMicrovm`, `CreateMicrovmAuthToken`, `GET /health` | `sandbox.process.executeCommand(command, cwd, undefined, timeoutSeconds)`, backed by authenticated HTTPS to `server.py`: `POST /commands`, poll `GET /commands/<jobId>` | `AwsMicrovm.delete(sandbox)`, backed by `TerminateMicrovm` or session-mode suspend | Yes. `server.py` validates commands, spawns `/bin/sh -lc`, stores output files, and reports job status. |
| Daytona | `client.create(...)` from image or snapshot | `sandbox.process.executeCommand(command, cwd, undefined, timeoutSeconds)` | `client.delete(sandbox)` and client dispose | No. The Daytona SDK/service owns process execution and output transport. |
| Modal | `client.sandboxes.create(...)` after app/image setup | `sandbox.exec(["/bin/sh", "-lc", command], ...)` and SDK stream reads | `sandbox.terminate()` | No. The Modal SDK/service owns process execution and stream handling. |
| Vercel | `VercelSandbox.create(...)` from runtime or snapshot | `sandbox.runCommand(...)`, wait, then read SDK stdout/stderr | `sandbox.stop({ blocking: true })` | No. The Vercel SDK/service owns process execution and stream handling. |

The important distinction is where `run(command)` lands. Daytona, Modal, and Vercel provide command execution as SDK primitives. AWS Lambda MicroVMs provide MicroVM lifecycle, endpoint access, and proxy auth; this repo supplies the in-VM command API with `server.py`.

## Task Environments

TerminalBench tasks run in `/workspace`. The shared harness extracts the task archive, copies tests to `/tests`, and runs the verifier.

SWE-Smith tasks currently use the Vercel-style manifest reconstruction path because the AWS MicroVM provider does not consume each task Docker image directly.

## Cold And Warm Behavior

AWS MicroVMs always launch a fresh MicroVM per task from a prebuilt MicroVM image. In this harness:

- `cold` means a new MicroVM instance from the configured image.
- `warm` reuses the same `AWS_MICROVM_IMAGE_ID` / version artifact across runs, but still launches isolated per-task MicroVMs.

This shape parallelizes cleanly once the AWS account quota allows it: build one image, then run N task MicroVMs with the same environment config and bounded `AWS_MICROVM_MAX_CONCURRENCY`. The harness also caps AWS MicroVM task concurrency by `AWS_MICROVM_ACCOUNT_MEMORY_GB / --memory-gb`; in the current account, the 2 GB AWS default permits more parallelism than the repo-wide 4 GB default.

## MVP Evidence

The first passing proof used:

```bash
AWS_REGION=us-east-1 AWS_MICROVM_MAX_DURATION_SECONDS=600 \
bun src/bench.ts \
  --provider aws-microvm \
  --mode cold \
  --dataset ../data/terminalbench_2026_03_05_smoke16.jsonl \
  --task-index 4 \
  --timeout-seconds 300 \
  --solve-timeout-seconds 120 \
  --concurrency 1 \
  --memory-gb 2 \
  --cpu 2 \
  --aws-microvm-image-id arn:aws:lambda:us-east-1:172630973301:microvm-image:code-sandbox-bench-runner-20260624 \
  --aws-microvm-image-version 1.0 \
  --solve-command '<deterministic task-4 results.json writer>' \
  --output ../results/ts-aws-microvm-cold-terminalbench-task4.json
```

Result:

- task `a_b_testing_models_medium`
- passed `1/1`
- elapsed `36.08s`
- start `2.83s`
- prepare `20.22s`
- solve `2.22s`
- verify `2.42s`
- stop `0.15s`

After the run, `ListMicrovms` showed all proof MicroVMs in `TERMINATED` state and the reusable image in `CREATED` state.

## SWE-Smith Smoke Evidence

The first SWE-Smith failure mode was a MicroVM proxy `502` during the long `prepare` phase. The provider now survives that path by polling async command jobs with retryable 5xx handling and file-backed command output. The first task then passed:

- result file: `results/ts-aws-microvm-cold-gold-task0-retry.json`
- task: `adrienverge__yamllint.8513d9b9.combine_file__26dq3p0r`
- passed: `1/1`
- elapsed: `176.25s`

A follow-up run covered tasks 1-9:

- result file: `results/ts-aws-microvm-cold-gold-tasks1-9-sequential.json`
- passed: `9/9` by harness result
- one row, `bottlepy__bottle.a8dfef30.func_basic__a0p07t6t`, had a suspicious verifier tail containing `FAILED`, so an additional task was run for cleaner evidence.

Additional clean task:

- result file: `results/ts-aws-microvm-cold-gold-task10.json`
- task: `conan-io__conan.86f29e13.combine_file__7tlw062n`
- passed: `1/1`
- elapsed: `160.61s`

Clean-pass count excluding the suspicious bottlepy row: `10`.

## Session Smoke And Reaper

Use the session smoke script to validate suspend/resume behavior and state preservation for a session image:

```bash
cd ts
AWS_MICROVM_SESSION_MODE=explicit-suspend \
bun run aws:session-smoke \
  --aws-microvm-image-id "$AWS_MICROVM_IMAGE_ID" \
  --aws-microvm-image-version "$AWS_MICROVM_IMAGE_VERSION" \
  --memory-gb 2 \
  --output ../results/aws-session-smoke.json
```

The smoke writes a file in `/workspace`, suspends/resumes, verifies the file survives, emits `aws_microvm.lifecycle_events`, and terminates by default. Add `--keep-session` only when intentionally inspecting a suspended MicroVM.

Use the reaper to inspect or terminate abandoned sessions for an image:

```bash
cd ts
bun run aws:reaper --image-id "$AWS_MICROVM_IMAGE_ID"
bun run aws:reaper --image-id "$AWS_MICROVM_IMAGE_ID" --max-suspended-age-seconds 25200 --execute
```

The reaper defaults to dry-run. It uses `startedAt` as the available age signal because the list API does not expose `suspendedAt`.

## Cost Guardrails

The provider sets short task-level maximum duration and immediate termination in `stop()` unless `AWS_MICROVM_SESSION_MODE` opts into session behavior. For live sweeps:

- Keep `AWS_MICROVM_MAX_CONCURRENCY` low until account quotas and pricing are confirmed.
- The current account showed a 4 GB base allocated memory limit. With `--memory-gb 4`, run sequentially or request a quota increase.
- Use one prebuilt image for a whole run instead of rebuilding per task.
- Prefer `AWS_MICROVM_SUSPENDED_DURATION_SECONDS=0` for benchmark tasks so idle MicroVMs terminate rather than persist.
- Benchmark rows include `aws_microvm.lifecycle_cost` with billable vCPU, running compute, launch snapshot read, suspend snapshot write, resume snapshot read, suspended storage, and total estimates. Runtime compute uses `memoryGb / 2` for the billable-vCPU bucket; `--cpu` remains task-resource metadata for cross-provider reporting. Override the default US East example rates with the `AWS_MICROVM_ESTIMATE_*` variables when using another region or negotiated pricing.
