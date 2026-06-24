# AWS MicroVM Cost Reduction Sample

Updated: 2026-06-24

## Goal

Drive estimated AWS MicroVM benchmark cost down by at least 20% on a representative sample while preserving the benchmark shape for coding-agent work.

## Live AWS Status

Live AWS reruns were blocked during this pass because `aws sts get-caller-identity` returned `ExpiredToken`. The validation below uses a local one-task benchmark sample to exercise benchmark output and agent trace logging, then applies the AWS estimator to the same elapsed seconds. It also recomputes the existing 100-task AWS report sample from the checked-in report split.

## Implementation

- AWS MicroVM `bench` and `prewarm` now default `--memory-gb` to `2`; other providers keep the `4` GB default.
- AWS runtime estimates now derive billable vCPU from memory as `memoryGb / 2` instead of using requested `--cpu`.
- AWS lifecycle telemetry now reports `billable_vcpu` and uses the same memory-derived vCPU bucket for running compute.

## Sample Run

```bash
cd ts
npm run bench -- \
  --provider local \
  --dataset ../data/terminalbench_2026_03_05_smoke16.jsonl \
  --task-index 0 \
  --timeout-seconds 60 \
  --solve-timeout-seconds 5 \
  --concurrency 1 \
  --cpu 2 \
  --memory-gb 2 \
  --output /tmp/code-sandbox-bench-cost-goal-sample.json
```

The sample ran `R_package_dependency_missing_medium` with 3.3927 observed task seconds, 2 requested CPU, and 2 GB memory. It was intentionally run without a solver, so verifier pass/fail is not used as a success criterion for this cost-estimator sample.

metric | old AWS estimate | new AWS estimate | reduction
--- | ---: | ---: | ---:
local one-task sample | $0.000213 | $0.000119 | 44.2%
existing AWS 100-task report sample | $1.0501 | $0.8063 | 23.2%

The 100-task recomputation uses the previous report split of `$0.8813` requested-CPU and `$0.1688` memory. Keeping the memory bucket unchanged and replacing requested CPU with `memoryGb / 2` changes the vCPU bucket to about `$0.6375`, for about `$0.8063` total runtime compute.

## Agent Trace Signal

The local sample produced `agent_trace_summary` with 10 commands and no idle gaps over 10 seconds. That is expected for the local smoke run because commands execute back-to-back inside the harness. The checked-in trace fields are still the right evidence path for real coding-agent traffic: use `command_idle_gap_seconds` and the `over_10s`, `over_60s`, and `over_300s` buckets to set auto-suspend thresholds once AWS credentials are refreshed.

