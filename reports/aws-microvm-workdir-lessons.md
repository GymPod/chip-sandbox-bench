# Lessons From Workdir For AWS Lambda MicroVM Strategy

Updated: 2026-06-24

Scope:

- Local AWS provider: `ts/src/aws_microvm.ts`, `ts/src/providers.ts`, `ts/aws-microvm-runner/server.py`, and `docs/providers/aws-microvm.md`.
- Reference project: `mv37-org/workdir` at commit `8bc295034a71aed08936ac3c68a926d336ac5803`.
- AWS docs checked on 2026-06-24: Lambda MicroVM idle policy, runtime lifecycle, and pricing.

## Executive Takeaway

Workdir's useful lesson is not just "pause the VM." It treats idle time as a product lifecycle:

```text
running -> standby -> auto-resume -> running
```

That lifecycle is tied to request-path resume, billing intervals, activity tracking, restart recovery, and explicit exclusions for secrets and long-running background work. Our AWS provider has the raw idle-policy knobs already, but the default is effectively "terminate, do not suspend":

```text
AWS_MICROVM_SUSPENDED_DURATION_SECONDS=0
AWS_MICROVM_AUTO_RESUME=false
```

For benchmark jobs, that default is still reasonable. For interactive agent sessions, we should add a separate session strategy that keeps the MicroVM identity alive across commands and lets AWS suspend it between command bursts.

## Current Local Strategy

The current AWS provider launches one MicroVM from a prebuilt image, talks to a repo-owned HTTP runner inside the VM, and terminates after the task.

- `AwsMicrovmSandbox.start()` calls `RunMicrovm`, stores `microvmId` and `endpoint`, creates a port-scoped auth token, and polls `/health`.
- `run(command)` posts to `/commands`, then polls `/commands/<jobId>`.
- `stop()` always calls `TerminateMicrovm`.
- "Warm" means image reuse, not stateful MicroVM reuse.
- Cost estimates for AWS are placeholder-rate based and do not split running compute, suspended snapshot storage, snapshot read/write, or data transfer.

The provider does pass an `idlePolicy`, but local docs intentionally prefer `suspendedDurationSeconds=0` for benchmark tasks. That means there is currently no pause/resume cost saving for command gaps.

## Workdir Lessons Worth Copying

### 1. Make standby a first-class state, not a flag

Workdir has both explicit user pause and automatic standby:

- `stopped`: user-requested pause, explicit resume required.
- `standby`: automatic idle eviction, next request transparently resumes.

The important behaviors:

- close billing before the runtime standby/pause call;
- use compare-and-set state transitions to avoid double resume, double billing, and stale writers;
- auto-resume in every request path that touches live state;
- touch activity before and after exec, preview, PTY, and file operations;
- persist enough runtime metadata to survive control-plane restart;
- never snapshot resident secrets.

For AWS, the runtime side is managed by Lambda MicroVMs, but we still need the product state machine locally if these sessions are user-facing.

### 2. Let AWS auto-resume handle the common case

AWS idle policy measures inbound traffic through the MicroVM proxy endpoint. With:

```json
{
  "autoResumeEnabled": true,
  "maxIdleDurationSeconds": 300,
  "suspendedDurationSeconds": 25200
}
```

the next HTTP request to the endpoint resumes the VM and is held until resume completes. That maps naturally onto our command runner: the next `POST /commands` can be the wake request.

Implementation implication:

- keep `TerminateMicrovm` for job/task mode;
- add a session mode that does not call `stop()` after every command;
- set auto-resume in session mode;
- increase first-command-after-idle timeout and retry a transient 502/timeout after refreshing endpoint/token;
- record "resume latency" separately from command runtime.

### 3. Choose idle thresholds from break-even math

AWS pricing says running MicroVMs incur compute charges, suspended MicroVMs incur snapshot storage but not compute, and suspend/resume adds snapshot write/read charges.

Using the published us-east-1 example rates:

- vCPU: `$0.0000276944` per vCPU-second
- memory: `$0.0000036667` per GB-second
- snapshot write: `$0.0038` per GB
- snapshot read: `$0.00155` per GB

For a 2 GB / 1 vCPU baseline, suspend+resume snapshot IO is:

```text
2 GB * ($0.0038 + $0.00155) = $0.0107
```

Running compute is:

```text
$0.0000276944 + 2 * $0.0000036667 = $0.0000350278/sec
```

Break-even for a suspend/resume cycle is about:

```text
$0.0107 / $0.0000350278 ~= 306 seconds
```

So a 60 second idle timeout may be too aggressive for chatty agent loops. A practical starting point is `maxIdleDurationSeconds=300`, then tune from observed inter-command gaps. If the session is likely to terminate instead of resume, write-only break-even is lower, but most interactive sessions resume.

### 4. Suspended saves compute cost but not AWS memory quota

AWS docs state account capacity covers MicroVMs in `RUNNING` or `SUSPENDED` state. This is a major difference from Workdir's self-hosted standby, which kills Firecracker and frees host RAM.

Implications:

- pause/resume lowers billable compute, not account concurrency pressure;
- we still need a suspended-session reaper using `suspendedDurationSeconds` and explicit termination;
- the scheduler/accounting layer should count suspended sessions against AWS memory quota;
- quota retries should consider terminating abandoned suspended sessions, not only waiting.

### 5. Model AWS cost with lifecycle buckets

The current AWS estimate formula charges only elapsed seconds times optional vCPU/GB-hour env vars. It cannot evaluate pause/resume.

Add these fields to result/session telemetry:

- `runningSeconds`
- `suspendedSeconds`
- `suspendCount`
- `resumeCount`
- `imageSnapshotGb`
- `suspendSnapshotWriteGb`
- `resumeSnapshotReadGb`
- `dataTransferBytes`
- `terminationReason`

Then estimate:

```text
running compute
+ peak over-baseline compute, if we can observe it
+ snapshot read/write on launch/suspend/resume
+ suspended snapshot storage
+ data transfer
```

This is necessary before deciding whether auto-suspend is actually cheaper for our command distribution.

### 6. Use lifecycle hooks for real readiness and resume hygiene

Our image hook support is currently disabled by default, and the runner only ACKs lifecycle hooks.

For session mode, hooks should become real:

- `/ready`: prove the runner is accepting commands.
- `/validate`: run a representative cheap command so AWS samples/prefetches useful image paths.
- `/run`: accept per-MicroVM config via `runHookPayload`.
- `/suspend`: flush runner job metadata/output files and close external connections.
- `/resume`: refresh expiring credentials, recreate external connections, and validate the runner.
- `/terminate`: final cleanup/log flush.

The runner already stores stdout/stderr on disk, which is good for suspend. It should also make job metadata recoverable enough that a resumed session can report what happened before suspension.

### 7. Avoid auto-suspend for background-only work

AWS idle detection is based on inbound endpoint traffic, not guest CPU activity. Our foreground command path polls every two seconds, so it keeps endpoint traffic active while a command runs.

Risks:

- a detached/background command with no polling can be suspended mid-work;
- a dev server with no preview traffic can be treated as idle;
- a long-running in-guest process may need explicit keepalive traffic or a disabled idle policy.

Session mode should distinguish:

- foreground command sessions: auto-suspend safe;
- interactive preview/browser sessions: activity must be preview/PTY/WebSocket aware;
- background jobs: disable auto-suspend or run a host-side keepalive while work is intended to continue.

### 8. Label boot and wake paths honestly

Workdir reports boot path instead of hiding cold starts behind warm numbers. We should mirror that in benchmark JSON:

- `aws_image_launch`
- `aws_auto_resume`
- `aws_explicit_resume`
- `aws_fresh_run`
- `aws_terminated_relaunch`

For every command, record whether it hit a suspended VM and how long the first request took. This keeps "warm" from mixing image reuse, state reuse, and auto-resume.

### 9. Keep image reuse and session reuse separate

There are two different wins:

- Image reuse: our current `CreateMicrovmImage` artifact avoids rebuilding task environments.
- Session reuse: keeping the same MicroVM alive across user/agent turns preserves filesystem, package caches, process state, and shell context.

Do not overload `--mode warm` to mean both. Add a distinct mode or provider option such as:

```text
AWS_MICROVM_SESSION_MODE=terminate|auto-suspend|explicit-suspend
```

Benchmark mode should remain `terminate` unless the benchmark is explicitly measuring multi-turn agents.

## Suggested Implementation Sequence

1. Add session-mode config.
   - Keep current benchmark defaults.
   - Add `auto-suspend` defaults: `autoResumeEnabled=true`, `maxIdleDurationSeconds=300`, `suspendedDurationSeconds` bounded by product session TTL, `maximumDurationInSeconds<=28800`.

2. Make `AwsMicrovmSandbox` state-aware.
   - Track `lastCommandAt`, `lastKnownState`, `resumeAttempts`, and first-request latency.
   - On timeout/502 after an idle gap, call `GetMicrovm`, refresh endpoint/token, and retry once with a longer timeout.

3. Expand lifecycle hook support.
   - Enable hooks for session images.
   - Add `/suspend` if supported by the current AWS SDK version.
   - Make `/run`, `/resume`, `/suspend`, and `/terminate` operational instead of ACK-only.

4. Split cost accounting.
   - Keep elapsed wall-clock for benchmark comparability.
   - Add AWS-specific estimated running compute, suspended storage, and snapshot read/write.
   - Reconcile against AWS billing exports once real session traffic exists.

5. Add a small session benchmark.
   - Run `echo 1`, sleep past idle threshold, run `echo 2`.
   - Assert filesystem state survives.
   - Record auto-resume latency and charged lifecycle buckets.
   - Repeat with a background process to validate the "no auto-suspend for background work" rule.

6. Add cleanup/reaper tooling.
   - Periodically list MicroVMs for the image/version.
   - Terminate abandoned `SUSPENDED` sessions past product TTL.
   - Surface quota pressure from both `RUNNING` and `SUSPENDED`.

## Default Policy Recommendation

Use two profiles:

### Benchmark/task profile

```json
{
  "autoResumeEnabled": false,
  "maxIdleDurationSeconds": 120,
  "suspendedDurationSeconds": 0
}
```

Keep terminating after task cleanup. This avoids snapshot churn, releases quota, and preserves current benchmark semantics.

### Interactive agent profile

```json
{
  "autoResumeEnabled": true,
  "maxIdleDurationSeconds": 300,
  "suspendedDurationSeconds": 25200
}
```

Use this only when a MicroVM represents a user/agent session across multiple commands. Tune `maxIdleDurationSeconds` from observed inter-command gaps and snapshot charges.

## Sources

- Workdir README: https://github.com/mv37-org/workdir/blob/8bc295034a71aed08936ac3c68a926d336ac5803/README.md
- Workdir architecture: https://github.com/mv37-org/workdir/blob/8bc295034a71aed08936ac3c68a926d336ac5803/docs/ARCHITECTURE.md
- Workdir API lifecycle: https://github.com/mv37-org/workdir/blob/8bc295034a71aed08936ac3c68a926d336ac5803/docs/API.md
- Workdir roadmap/performance notes: https://github.com/mv37-org/workdir/blob/8bc295034a71aed08936ac3c68a926d336ac5803/roadmap.md
- Workdir lifecycle implementation: https://github.com/mv37-org/workdir/blob/8bc295034a71aed08936ac3c68a926d336ac5803/crates/sandboxd/src/service.rs
- Workdir Firecracker runtime: https://github.com/mv37-org/workdir/blob/8bc295034a71aed08936ac3c68a926d336ac5803/crates/sandboxd/src/runtime/firecracker.rs
- AWS Lambda MicroVM idle policy: https://docs.aws.amazon.com/lambda/latest/microvm-api/API_IdlePolicy.html
- AWS Lambda MicroVM runtime lifecycle: https://docs.aws.amazon.com/lambda/latest/dg/microvms-launching.html
- AWS Lambda pricing: https://aws.amazon.com/lambda/pricing/
