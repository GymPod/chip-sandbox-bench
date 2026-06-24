# Cost Canary Loop Dry Run

Generated: 2026-06-24T23:36:23.516Z

Providers: vercel, modal, daytona
Modes: warm
Suffix: cpu1-canary-20260624
Run enabled: false
Preflight enabled: true
Preflight passed: true

## Preflight

check | status | present | missing
--- | --- | --- | ---
vercel | pass | `VERCEL_TOKEN`, `VERCEL_TEAM_ID`, `VERCEL_PROJECT_ID` | none
modal | pass | `~/.modal.toml` | none
daytona | pass | `DAYTONA_API_KEY` | none
solver-contract | pass | `baseline:openrouter`, `candidate:openrouter_solver.sh` | none
openrouter-solver | pass | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | none



## Candidate Results

- `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/ts-vercel-warm-solve-all-cpu1-canary-20260624.json`
- `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/ts-modal-warm-solve-all-cpu1-canary-20260624.json`
- `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/ts-daytona-warm-solve-all-cpu1-canary-20260624.json`

## Candidate Observations

- `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/resource-observations/ts-vercel-warm-solve-all-cpu1-canary-20260624.jsonl`
- `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/resource-observations/ts-modal-warm-solve-all-cpu1-canary-20260624.jsonl`
- `/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/resource-observations/ts-daytona-warm-solve-all-cpu1-canary-20260624.jsonl`

## Steps

1. candidate_matrix

```bash
bun src/matrix.ts --providers vercel,modal,daytona --modes warm --dataset /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/data/terminalbench_2026_03_05_smoke16.jsonl --task-index all --task-limit 3 --timeout-seconds 900 --solve-timeout-seconds 300 --concurrency 2 --run-concurrency 1 --resource-policy adaptive --resource-config /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/data/resource_policy.json --solve-command-file /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/scripts/openrouter_solver.sh --output-dir /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results --resource-observations-dir /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/resource-observations --suffix cpu1-canary-20260624 --output /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/cost-canary-matrix-cpu1-canary-20260624.json
```

2. resource_report

```bash
bun src/resource_report.ts --input /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/resource-observations/ts-vercel-warm-solve-all-cpu1-canary-20260624.jsonl,/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/resource-observations/ts-modal-warm-solve-all-cpu1-canary-20260624.jsonl,/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/resource-observations/ts-daytona-warm-solve-all-cpu1-canary-20260624.jsonl --min-samples 1 --format json --output /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/reports/generated-resource-observations-cpu1-canary-20260624.json --suggested-config-output /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/generated-resource-policy-cpu1-canary-20260624.json
```

3. policy_compare

```bash
bun src/policy_compare.ts --results ../results/ts-vercel-warm-solve-all-20260528.json,../results/ts-modal-warm-solve-all-20260528.json,../results/ts-daytona-warm-solve-all-20260528.json --dataset /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/data/terminalbench_2026_03_05_smoke16.jsonl --baseline-config ../data/resource_policy_before_cpu1_20260624.json --candidate-config /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/data/resource_policy.json --format json --output /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/reports/generated-policy-cost-comparison-cpu1-canary-20260624.json
```

4. canary_validate

```bash
bun src/canary_validate.ts --baseline-results ../results/ts-vercel-warm-solve-all-20260528.json,../results/ts-modal-warm-solve-all-20260528.json,../results/ts-daytona-warm-solve-all-20260528.json --candidate-results /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/ts-vercel-warm-solve-all-cpu1-canary-20260624.json,/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/ts-modal-warm-solve-all-cpu1-canary-20260624.json,/Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/results/ts-daytona-warm-solve-all-cpu1-canary-20260624.json --min-reduction-pct 20 --max-pass-drop 0 --max-wall-ratio 1.2 --format json --output /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/reports/generated-canary-validation-cpu1-canary-20260624.json
```

5. goal_audit

```bash
bun src/cost_goal_audit.ts --policy-comparison /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/reports/generated-policy-cost-comparison-cpu1-canary-20260624.json --resource-report /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/reports/generated-resource-observations-cpu1-canary-20260624.json --canary-validation /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/reports/generated-canary-validation-cpu1-canary-20260624.json --min-reduction-pct 20 --min-observations 1 --format json --output /Users/jaylast/.codex/worktrees/9a85/code-sandbox-bench/reports/generated-cost-goal-audit-cpu1-canary-20260624.json
```
