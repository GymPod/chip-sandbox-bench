# Cost Reduction Loop 2026-06-24

## Objective

Reduce benchmark costs by another 20% by running the resource observation and aggregation loop, applying adaptive resource and concurrency learnings, and validating the resulting cost reduction against the current benchmark baseline.

## Policy Change

`data/resource_policy.json` now promotes a CPU-1 default for:

- local
- Vercel
- Modal
- Daytona

AWS MicroVM stays at 2 configured CPU / 1 GB memory because the current harness cost model derives billable AWS vCPU from memory. The known heavy SWE-Smith CPU floors remain explicit:

- `pandas-dev__pandas.95280573`: 4 CPU / 8 GB / 20 GB disk
- `facebookresearch__fvcore.a491d5b9`: 2 CPU / 8 GB / 20 GB disk
- `Project-MONAI__MONAI.a09c1f08`: 2 CPU / 8 GB / 20 GB disk

## Cost Projection

Command:

```bash
npm run policy:compare -- --results ../results/ts-vercel-warm-solve-all-20260528.json,../results/ts-modal-warm-solve-all-20260528.json,../results/ts-daytona-warm-solve-all-20260528.json --dataset ../data/terminalbench_2026_03_05_smoke16.jsonl --baseline-config ../data/resource_policy_before_cpu1_20260624.json --candidate-config ../data/resource_policy.json --output ../reports/generated-policy-cost-comparison.md
```

Result:

provider | baseline cost | candidate cost | projected reduction
--- | ---: | ---: | ---:
Vercel | $0.1118 | $0.0638 | 42.9%
Modal | $0.0766 | $0.0480 | 37.3%
Daytona | $0.0574 | $0.0357 | 37.7%
Total | $0.2457 | $0.1476 | 39.9%

The comparison replays existing warm solve elapsed times through the shared `estimateCost` model. It is a cost projection, not a provider-side runtime guarantee.

## Observation Loop Sample

Command:

```bash
npm run bench -- --provider local --dataset ../data/terminalbench_2026_03_05_smoke16.jsonl --task-index all --task-limit 3 --timeout-seconds 90 --solve-timeout-seconds 30 --concurrency 2 --solve-command-file ../scripts/gold_solver.sh --output ../results/cost-loop-local-terminalbench-sample-20260624.json --resource-observations-output ../results/resource-observations/cost-loop-local-terminalbench-sample-20260624.jsonl --adaptive-concurrency-state ../results/adaptive_concurrency_state_cost_loop.json
```

Aggregation:

```bash
npm run resource:report -- --input ../results/resource-observations/cost-loop-local-terminalbench-sample-20260624.jsonl --min-samples 1 --output ../reports/generated-local-resource-observations-20260624.md --suggested-config-output ../results/generated-local-resource-policy-20260624.json
```

Observed loop behavior:

- 3 observations were written with effective resources of 1 CPU / 2 GB / 10 GB.
- The disk probe ran for every task and reported near-zero local disk usage for the extracted archives.
- Adaptive concurrency stayed at 2 because no provider quota, rate-limit, or transport pressure was observed.
- All 3 local TerminalBench tasks failed because the local archive pathing did not provide `/solution/solve.sh` or `/tests/test_outputs.py`; these failures are not provider resource failures and should not be treated as validation that CPU 1 passes on remote providers.

## Aggregation Down-Size Check

The aggregation loop was also validated with a synthetic clean observation containing CPU seconds, peak RSS, and disk high-water data. A 2 CPU / 4 GB / 20 GB observation with low measured usage now recommends:

```json
{"cpu":1,"memoryGb":2,"diskGb":10,"timeoutSeconds":180}
```

The emitted reasons were `observed_peak_rss`, `observed_cpu_seconds`, and `observed_disk_high_water`. This verifies that future provider observations can drive resources down as well as retrying upward on resource failures.

## Remaining Validation

The cost target is met by projection, but the goal should stay open until at least one remote canary run validates that CPU 1 does not erase the savings through materially slower wall time or lower pass rate. This workspace had no `.env` file and no provider credentials in the environment, so only the local observation loop could be run in this turn.

The next run should use `canary:validate` against fresh Vercel, Modal, and Daytona result JSONs after a small canary matrix:

```bash
npm run canary:validate -- --baseline-results ../results/ts-vercel-warm-solve-all-20260528.json,../results/ts-modal-warm-solve-all-20260528.json,../results/ts-daytona-warm-solve-all-20260528.json --candidate-results ../results/ts-vercel-warm-solve-all-cpu1-canary.json,../results/ts-modal-warm-solve-all-cpu1-canary.json,../results/ts-daytona-warm-solve-all-cpu1-canary.json --min-reduction-pct 20 --max-pass-drop 0 --max-wall-ratio 1.2 --output ../reports/generated-canary-validation.md
```

This validator compares overlapping task IDs, so the canary can be smaller than the baseline while still enforcing actual cost, pass-rate, and wall-time guardrails.

After `policy:compare`, `resource:report`, and `canary:validate` have written JSON artifacts, run the goal audit:

```bash
npm run cost:goal-audit -- --policy-comparison ../reports/generated-policy-cost-comparison-20260624.json --resource-report ../reports/generated-local-resource-observations-20260624.json --canary-validation ../reports/generated-canary-validation.json --min-reduction-pct 20 --min-observations 1 --output ../reports/generated-cost-goal-audit.md
```

The audit intentionally fails until remote canary validation is present and passing.

The full sequence can be generated without spending provider budget:

```bash
npm run cost:canary-loop -- --baseline-results ../results/ts-vercel-warm-solve-all-20260528.json,../results/ts-modal-warm-solve-all-20260528.json,../results/ts-daytona-warm-solve-all-20260528.json --baseline-config ../data/resource_policy_before_cpu1_20260624.json --providers vercel,modal,daytona --modes warm --task-limit 3 --output ../reports/generated-cost-canary-loop-dry-run.md
```

The generated dry run now includes provider credential preflight. In this workspace, preflight currently reports:

provider | status | missing
--- | --- | ---
Vercel | fail | `VERCEL_TOKEN`/`VERCEL_ACCESS_TOKEN`/`VERCEL_API_KEY`, `VERCEL_TEAM_ID`, `VERCEL_PROJECT_ID`
Modal | pass | none (`~/.modal.toml` is present)
Daytona | fail | `DAYTONA_API_KEY`

With `--run true`, the loop writes `reports/generated-cost-canary-loop-preflight-20260624.json` and exits nonzero before launching the candidate matrix while those checks fail.

A one-task Modal-only canary was attempted because Modal auth is available through `~/.modal.toml`. The first sandboxed attempt failed on DNS resolution for `api.modal.com`; rerunning with network access reached Modal and produced `results/ts-modal-warm-solve-all-modal-cpu1-canary-20260624.json`, but failed validation because the loop was using `scripts/gold_solver.sh`. That solver is not comparable to the existing OpenRouter solve baseline for this TerminalBench dataset, and `/solution/solve.sh` is not staged in the task archive. The loop now defaults to `scripts/openrouter_solver.sh` and infers OpenRouter baselines from existing result tails, so future canaries either use the same solver contract as the baseline or fail preflight before provider work starts.

Add `--run true` when provider and OpenRouter credentials are available. The loop executes the canary matrix, aggregates only the canary observation JSONL files, runs projected policy comparison, validates actual canary results, and runs the final goal audit.

## OpenRouter Budget Blocker

The OpenRouter and provider credentials were later loaded from `~/src/autonomy/code-sandbox-bench/.env` after the originally requested `~/src/autonomy/circuit/.env` path was not present. Preflight passed and the three-provider canary reached Vercel, Modal, and Daytona, but every solver call failed before task solving with:

```text
OpenRouter HTTP 403: Workspace monthly budget exceeded.
```

The loop wrote `reports/generated-canary-validation-cpu1-canary-20260624.json`, but the canary validation fails because the candidate pass count is zero. The loop now performs a live OpenRouter check before launching provider sandboxes so this budget/auth failure is caught before provider spend on future runs.
