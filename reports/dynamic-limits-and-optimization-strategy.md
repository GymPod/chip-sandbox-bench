# Dynamic Limits And Optimization Strategy

Updated: 2026-06-24

## Executive Takeaway

Dynamic limits should be treated as a control loop, not a single heuristic:

```text
observe command/task behavior -> recommend a resource envelope -> enforce with bounded retries -> feed new evidence back
```

The current harness has useful timing and idle-gap traces, but it still chooses task resources mostly from command-line defaults plus a small set of static repo overrides. That is enough for benchmarking, but not enough for coding-agent cost control. For agents, we should learn a per-task or per-repo resource envelope from actual execution: memory high-water, disk growth, CPU saturation, phase duration, timeout reason, idle gaps, resume latency, and provider quota errors.

The first product version should run in `observe` mode when validating a new workload, where it records recommendations without changing behavior. This repo now ships a checked-in `data/resource_policy.json` and uses `adaptive` as the default benchmark policy so every task also has an adaptive price. Use `--resource-policy static` for fixed-resource provider comparisons.

## Current State In This Repo

- `bench.ts` starts with global defaults and then applies `taskEnv.resources` from the SWE-Smith manifest.
- `data/swesmith_env_manifests.json` has 66 repo entries; only 7 include resource overrides.
- The static overrides are coarse: two repos use 8 GB memory and 20 GB disk, four use 8 GB memory, and one uses 4 CPU, 8 GB memory, and 20 GB disk.
- `agent_trace` records command timing, labels, return codes, command hashes, inter-command idle gaps, and command usage when the provider can report it.
- `matrix.ts` has static provider concurrency caps. AWS caps by `AWS_MICROVM_ACCOUNT_MEMORY_GB / --memory-gb`; Daytona caps by assumed account CPU and memory.
- `report.ts` classifies some provider limit failures from stderr, mostly Daytona CPU/memory and rate-limit strings.
- AWS MicroVM is the best first place to add in-guest usage telemetry because this repo owns `ts/aws-microvm-runner/server.py`.
- `data/resource_policy.json` directly configures adaptive defaults: AWS MicroVMs use 1 GB by default, other remote providers use 2 GB, and known heavy SWE-Smith repos keep their higher resource tiers.

## Implemented Config

The checked-in adaptive config currently changes AWS MicroVM pricing/execution resources this way on the 100-task SWE-Smith smoke set:

resource change | task count
--- | ---:
2 GB -> 1 GB | 88
8 GB -> 4 GB | 5
8 GB -> 8 GB | 7

Using the current AWS MicroVM memory-derived vCPU formula, that lowers the per-second resource rate for this task set by 39.7% versus the static `--memory-gb 2` plus manifest-override baseline. The 8 GB -> 4 GB bucket covers memory-heavy repos that can retry upward on a clear memory signal; build-heavy repos such as Pandas, MONAI, and FVCore stay at 8 GB.

## Dynamic Resource Envelope

Each task run should produce an observation keyed by:

- provider, dataset, task id, env type, repo key, source id, runtime, image/snapshot id, and manifest hash;
- phase labels: start, upload, prepare, instruction write, solve, verify, stop;
- requested CPU, memory, disk, timeout, and concurrency;
- command outcome: return code, timeout, provider error class, resource error class;
- measured usage: wall seconds, user CPU seconds, system CPU seconds, peak RSS, workspace/cache disk bytes, stdout/stderr bytes;
- agent-session behavior: command idle gaps, suspend/resume count, resume latency, and termination reason.

The derived envelope should contain:

- `minCpu`, `recommendedCpu`, and `maxCpu`;
- `minMemoryGb`, `recommendedMemoryGb`, and `maxMemoryGb`;
- `minDiskGb`, `recommendedDiskGb`, and `maxDiskGb`;
- phase-specific timeout recommendations;
- confidence level and sample count;
- reason strings, such as `observed_peak_rss`, `oom_retry_passed`, `compile_cpu_bound`, `disk_high_water`, or `provider_quota`.

Do not auto-edit `data/swesmith_env_overrides.json` from a single run. Generate suggestions first, then promote stable recommendations after repeated evidence.

## Reasonable Starting Policies

### Memory

Use the adaptive config as the execution baseline: 1 GB for AWS MicroVMs, 2 GB for other remote providers, and checked-in higher tiers for known heavy repos. After observations exist:

```text
recommendedMemoryGb = round_up_tier(max(default, p95(peak_rss_gb) * 1.5))
tiers = 1, 2, 4, 8, 16 for AWS MicroVMs; 2, 4, 8, 16 for other providers
```

If a task fails with a strong memory signal, retry once at the next tier and record the retry. Strong signals include OOM killer messages, provider memory-limit errors, `MemoryError`, failed native builds with killed compiler processes, or peak RSS within 85% of the limit followed by failure.

For AWS MicroVMs, memory also determines billable vCPU in this harness, so increasing memory is both a memory and CPU-cost decision. Only promote an 8 GB envelope when the lower tier is unreliable or materially slower in a way that offsets the higher rate.

### CPU

Start low. Increase CPU only when the observation says the task is CPU-bound:

- CPU seconds divided by wall seconds is near the vCPU count for build/verify phases;
- timeout happens with high CPU utilization, not while waiting on network or package indexes;
- a higher-CPU retry improves wall time enough to offset the higher provider rate.

For AWS MicroVMs, treat `--cpu` as metadata unless the provider exposes a real independent CPU knob. The current cost model bills vCPU from memory, so CPU recommendations should be paired with memory-tier recommendations.

### Disk

Disk should be learned from high-water marks and error strings:

- keep the default at 10 GB for normal tasks;
- move to 20 GB when workspace plus package caches exceed 70% of the tier or when errors include `No space left on device`, pip wheel extraction failures, or compiler/linker temp-file failures;
- avoid large disk defaults for AWS until snapshot write/read cost is included in the estimate.

### Timeouts

Use phase-specific timeouts rather than one broad timeout:

```text
prepare_timeout = clamp(p95(prepare_seconds) * 1.5, 60, 900)
solve_timeout = agent/model policy, not provider policy
verify_timeout = clamp(p95(verify_seconds) * 2.0, 30, 600)
```

Timeout retries should be classified. A timeout with low CPU, recent network output, or package resolver logs is not the same as a timeout with high CPU and no output.

### Concurrency

Replace static concurrency caps with additive-increase/multiplicative-decrease per provider and account:

- increase concurrency slowly after clean runs;
- cut concurrency on quota, rate-limit, or provider transport errors;
- bin-pack tasks by recommended memory instead of treating all tasks as the default size;
- count AWS `SUSPENDED` MicroVMs against memory quota, because suspended MicroVMs still consume account capacity;
- prefer running smaller tasks while a high-memory task waits for capacity.

## Auto-Suspend Thresholds Should Also Be Dynamic

Auto-suspend should use expected-cost break-even, not a fixed "after every command" rule.

For a 2 GB / 1 billable-vCPU AWS MicroVM using the current example rates:

```text
running_rate = $0.0000350278/sec
write_cost = 2 GB * $0.0038 = $0.0076
read_cost = 2 GB * $0.00155 = $0.0031
```

If the session is likely to resume, suspend+resume break-even is:

```text
(write_cost + read_cost) / running_rate ~= 306 seconds
```

If the session is unlikely to resume, write-only break-even is about 217 seconds. A dynamic idle policy should estimate resume probability from agent traces:

```text
threshold = (write_cost + p_resume * read_cost) / running_rate
```

Then apply product latency constraints:

- if resume latency hurts UX, raise the threshold;
- if the user has gone inactive and resume probability drops, lower it;
- if command traces show frequent 10-60 second gaps, do not suspend after every command unless AWS snapshot IO is much cheaper than the current example rates;
- if traces show 5+ minute gaps, auto-suspend is usually worth it.

## Other Optimization Strategies

### 1. Observation-First Agent Tracing

`CommandResult` and `agent_trace.events[]` now include optional `command_usage`:

- wall seconds;
- user and system CPU seconds;
- peak RSS;
- stdout/stderr bytes;
- timeout and signal fields.

AWS MicroVM collects this inside `server.py`; local, Vercel, Modal, and Daytona collect wall/output usage in the provider wrapper. Providers can add richer CPU/RSS metrics as their SDKs expose them.

### 2. Bounded Resource Retry Ladder

When a task fails with a resource-class signal:

```text
1 GB -> 2 GB -> 4 GB -> 8 GB on AWS MicroVMs; 2 GB -> 4 GB -> 8 GB elsewhere
10 GB disk -> 20 GB disk
base timeout -> observed p95 timeout tier
```

Use at most one automatic retry in normal benchmark mode so results do not hide instability. For product agent sessions, retry can be more permissive if the user experience is preserved.

### 3. Phase-Aware Caching

The current cost is dominated by prepare/environment reconstruction for fallback providers. Cache at the phase that repeats:

- common system packages in the base image;
- Python wheels and package-manager caches in the image;
- per-repo prepared images for repeated SWE-Smith repos;
- task archive extraction and verifier dependencies when dataset identity is stable.

Do not collapse all repos into one giant image. Promote caches by frequency and cost contribution.

### 4. Per-Repo Image Promotion

Use observations to decide which repos deserve specialized images:

- high prepare time;
- repeated task count;
- stable dependency set;
- high package/network variance;
- high failure rate from dependency reconstruction.

This is likely a larger win than small CPU tuning for AWS/Vercel fallback paths.

### 5. Command Batching

`writeText` currently produces multiple provider commands for task prompt, instruction, and workspace files. For agent sessions, each command is a possible wake/resume boundary. Batch small setup writes into one command when the provider is remote and the data size is below a safe threshold.

### 6. Solver-Aware Limits

Separate provider task limits from model/agent limits:

- provider command timeout;
- solver step timeout;
- max solver steps;
- verification timeout;
- total task wall-clock budget.

This keeps dynamic provider resources from masking model-loop failures.

### 7. Failure Taxonomy

Normalize failure classes across providers:

- memory limit or OOM;
- disk full;
- CPU/account quota;
- sandbox create/start rate limit;
- command timeout;
- network/package index failure;
- verifier false negative;
- provider transport retry exhausted.

Dynamic limits should only react to the first three and some command timeouts. The rest need caching, retry, or harness fixes.

### 8. Cost-Aware Scheduling

Schedule by expected marginal cost:

- run cheap/small tasks first to keep workers busy;
- avoid launching high-memory AWS MicroVMs when they reduce concurrency for many small tasks;
- terminate abandoned suspended sessions before waiting on quota;
- delay expensive retries until cheaper retry classes are exhausted.

### 9. Dataset-Specific Profiles

Keep separate resource policies for:

- SWE-Smith fallback reconstruction;
- SWE-Smith native task Docker;
- TerminalBench smoke;
- interactive coding-agent sessions.

One global resource policy will overfit one workload and hurt another.

## Implementation Sequence

1. Add optional `command_usage` telemetry to command results and agent traces. Done.
2. Store per-task observations as JSONL, keyed by task/repo/provider/runtime/image. Partially done through `--resource-observations-output`.
3. Add `bun src/resource_report.ts` to aggregate observations into resource suggestions.
4. Add `--resource-policy static|observe|adaptive`, defaulting to `adaptive`. Done.
5. In `observe`, emit recommended envelopes and adaptive prices without changing resources. Done for pricing; execution remains static outside `adaptive`.
6. In `adaptive`, apply checked-in config recommendations with caps and one bounded resource retry on clear resource failures. Done.
7. Replace provider concurrency constants with an adaptive limiter that records quota/rate-limit feedback.
8. Make AWS auto-suspend thresholds derive from observed idle gaps, resume probability, snapshot IO cost, and measured resume latency.
9. Promote stable recommendations into checked-in manifests only after repeated samples.

## Guardrails

- Always record requested and effective resources in result JSON.
- Always record retry count and retry reason.
- Keep a fixed-resource benchmark mode for fair provider comparisons.
- Never store raw command text or forwarded environment values in observations.
- Do not suspend background-only sessions unless there is explicit keepalive or the user has accepted pause semantics.
- Treat recommendations as stale when image, runtime, dataset, or manifest hash changes.
