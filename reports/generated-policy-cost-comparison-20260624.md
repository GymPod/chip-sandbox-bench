# Resource Policy Cost Comparison

Generated: 2026-06-24T23:02:32.187Z

Dataset: `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/data/terminalbench_2026_03_05_smoke16.jsonl`
Baseline config: `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/data/resource_policy_before_cpu1_20260624.json`
Candidate config: `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/data/resource_policy.json`
Resource policy: `adaptive`

This projection holds observed task elapsed seconds constant and replays each task through the same provider cost model used by `bench.ts`.

## Summary

scope | runs | tasks | baseline cost | candidate cost | reduction
--- | ---: | ---: | ---: | ---: | ---:
total | 3 | 48 | $0.2457 | $0.1476 | 39.9%

## Runs

provider | mode | tasks | passed | input cost | baseline cost | candidate cost | reduction
--- | --- | ---: | ---: | ---: | ---: | ---: | ---:
daytona | - | 16 | 10 | $0.0713 | $0.0574 | $0.0357 | 37.7%
modal | - | 16 | 11 | $0.0960 | $0.0766 | $0.0480 | 37.3%
vercel | - | 16 | 9 | $0.1276 | $0.1118 | $0.0638 | 42.9%

## Resource Changes

### daytona

change | tasks
--- | ---:
`2 CPU / 2 GB / 10 GB / 180s -> 1 CPU / 2 GB / 10 GB / 180s` | 16

### modal

change | tasks
--- | ---:
`2 CPU / 2 GB / 10 GB / 180s -> 1 CPU / 2 GB / 10 GB / 180s` | 16

### vercel

change | tasks
--- | ---:
`2 CPU / 2 GB / 10 GB / 180s -> 1 CPU / 2 GB / 10 GB / 180s` | 16

## Config Snapshot

Baseline provider defaults: `{"local":{"cpu":2,"memoryGb":2,"diskGb":10},"vercel":{"cpu":2,"memoryGb":2,"diskGb":10},"modal":{"cpu":2,"memoryGb":2,"diskGb":10},"daytona":{"cpu":2,"memoryGb":2,"diskGb":10},"aws-microvm":{"cpu":2,"memoryGb":1,"diskGb":10}}`

Candidate provider defaults: `{"local":{"cpu":1,"memoryGb":2,"diskGb":10},"vercel":{"cpu":1,"memoryGb":2,"diskGb":10},"modal":{"cpu":1,"memoryGb":2,"diskGb":10},"daytona":{"cpu":1,"memoryGb":2,"diskGb":10},"aws-microvm":{"cpu":2,"memoryGb":1,"diskGb":10}}`
