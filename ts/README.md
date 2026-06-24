# Bun / TypeScript Runner

Primary runner for current benchmark matrices and reports.

## Install

```bash
npm install
```

## Commands

- `bun run bench`: run one provider/mode.
- `bun run matrix`: run several provider/mode combinations concurrently.
- `bun run prewarm`: create or test warm artifacts where supported.
- `bun run report`: generate a raw markdown report from result JSON files.
- `bun run resource:report`: aggregate resource observation JSONL/result JSON into resource suggestions.
- `bun run policy:compare`: replay result timings through two resource policy configs and project cost deltas.
- `bun run canary:validate`: compare candidate canary results against baseline results with cost, pass-rate, and wall-time guardrails.
- `bun run cost:goal-audit`: audit whether projection, observations, and canary validation prove the active cost-reduction goal.
- `bun run cost:canary-loop`: dry-run or execute the full candidate matrix, resource aggregation, canary validation, and goal audit sequence.
- `bun run triage`: classify failed tasks from result JSON files into provider-transport, environment-fidelity, patch-application, timeout, and real-test-failure buckets.

## Local Smoke

```bash
bun run bench --provider local --task-index 0 --output ../results/ts-local-one.json
```

## Solve-Enabled Provider Run

```bash
bun --env-file=../.env src/bench.ts --provider modal --mode cold --dataset ../data/swesmith_v4_smoke100.jsonl --task-index all --task-limit 20 --concurrency 2 --timeout-seconds 900 --solve-timeout-seconds 300 --forward-env OPENROUTER_API_KEY,OPENROUTER_MODEL,SOLVER_MAX_STEPS,SOLVER_STEP_TIMEOUT_SECONDS --solve-command-file ../scripts/openrouter_solver.sh --output ../results/ts-modal-cold-task20.json
```

## Matrix Run

```bash
bun --env-file=../.env src/matrix.ts --providers all --modes cold,warm --task-index all --task-limit 20 --concurrency 2 --run-concurrency 6 --timeout-seconds 900 --solve-timeout-seconds 300 --solve-command-file ../scripts/openrouter_solver.sh --output ../results/solve-price-matrix-task20.json
```

The matrix runner starts provider/mode runs concurrently. It also applies provider-specific task concurrency caps unless overridden with `--vercel-concurrency`, `--modal-concurrency`, `--daytona-concurrency`, or `--aws-microvm-concurrency`. Task concurrency is seeded from `--adaptive-concurrency-state` and benchmark runs update that state when provider quota, rate-limit, or transport pressure appears.

## Report Generation

```bash
bun run report --results-dir ../results --output ../reports/generated-provider-report.md
```

Generated reports are raw summaries. Curated analysis lives in `../reports/`.

## Resource Observation Reports

```bash
bun run resource:report --results-dir ../results/resource-observations --output ../reports/generated-resource-observations.md --suggested-config-output ../results/generated-resource-policy.json
```

`src/bench.ts` records keyed resource observations when `--resource-observations-output` is set. `src/matrix.ts` writes those files under `--resource-observations-dir` by default. The report command also accepts benchmark result JSON files and extracts embedded `resource_observation` rows.

When observations include CPU seconds, peak RSS, or disk high-water marks, `resource:report` can recommend smaller CPU, memory, and disk envelopes for cleanly passing tasks. Resource failures still recommend upward retry tiers.

## Resource Policy Cost Comparison

```bash
bun run policy:compare -- --results ../results/ts-vercel-warm-solve-all-20260528.json,../results/ts-modal-warm-solve-all-20260528.json,../results/ts-daytona-warm-solve-all-20260528.json --dataset ../data/terminalbench_2026_03_05_smoke16.jsonl --baseline-config ../data/resource_policy_before_cpu1_20260624.json --candidate-config ../data/resource_policy.json --output ../reports/generated-policy-cost-comparison.md
```

`src/policy_compare.ts` holds observed task elapsed seconds constant, resolves each task under the baseline and candidate resource configs, and replays both envelopes through the same provider cost model used by `src/bench.ts`. Use it before promoting generated resource suggestions so every policy change has an explicit projected cost delta.

## Canary Validation

After running a candidate provider canary with the proposed resource policy, compare it to the matching baseline results:

```bash
bun run canary:validate -- --baseline-results ../results/ts-vercel-warm-solve-all-20260528.json --candidate-results ../results/ts-vercel-warm-solve-all-cpu1-canary.json --min-reduction-pct 20 --max-pass-drop 0 --max-wall-ratio 1.2 --output ../reports/generated-canary-validation.md
```

`src/canary_validate.ts` compares overlapping task IDs, so a small candidate canary can be checked against a larger baseline run. It fails nonzero when the actual candidate result misses the cost-reduction target, loses too many passing tasks, or gets too slow.

## Goal Audit

After generating policy comparison, resource report, and canary validation JSON files, run:

```bash
bun run cost:goal-audit -- --policy-comparison ../reports/generated-policy-cost-comparison-20260624.json --resource-report ../reports/generated-local-resource-observations-20260624.json --canary-validation ../reports/generated-canary-validation.json --min-reduction-pct 20 --min-observations 1 --output ../reports/generated-cost-goal-audit.md
```

`src/cost_goal_audit.ts` fails nonzero until all required evidence is present. It is intentionally stricter than the projection report: projected savings alone are not enough to complete the goal without passing remote canary validation.

## Canary Loop

To generate the exact command sequence without spending provider budget:

```bash
bun run cost:canary-loop -- --baseline-results ../results/ts-vercel-warm-solve-all-20260528.json,../results/ts-modal-warm-solve-all-20260528.json,../results/ts-daytona-warm-solve-all-20260528.json --baseline-config ../data/resource_policy_before_cpu1_20260624.json --providers vercel,modal,daytona --modes warm --task-limit 3 --output ../reports/generated-cost-canary-loop-dry-run.md
```

The dry-run report includes provider credential preflight by default. To execute it after provider credentials are loaded, add `--run true`. If preflight fails in run mode, the loop writes a JSON artifact and exits nonzero before launching the candidate matrix. Use `--preflight false` only when intentionally validating outside the built-in credential checks.

The loop defaults to `scripts/openrouter_solver.sh` because the current solve baselines were produced through the OpenRouter solver. It also infers OpenRouter baselines from existing result tails and fails preflight if the candidate solver does not match. In run mode it performs a live, one-token OpenRouter check before launching provider sandboxes so expired, blocked, or budget-exceeded keys do not spend provider budget. Override `--solve-command-file` only when the baseline and candidate results should intentionally use a different solver contract.

The preflight checks the providers selected for the loop:

- Vercel: `VERCEL_TOKEN` or `VERCEL_ACCESS_TOKEN` or `VERCEL_API_KEY`, plus `VERCEL_TEAM_ID` and `VERCEL_PROJECT_ID`.
- Modal: `MODAL_TOKEN_ID` plus `MODAL_TOKEN_SECRET`, or a local Modal config at `~/.modal.toml`.
- Daytona: `DAYTONA_API_KEY`.
- AWS MicroVM: `AWS_MICROVM_IMAGE_ID` or `AWS_MICROVM_IMAGE_ARN`, plus an AWS credential source such as `AWS_PROFILE`, static key envs, or web identity envs.
- OpenRouter solver: `OPENROUTER_API_KEY` when `scripts/openrouter_solver.sh` is selected.

When preflight passes, the loop runs `matrix`, aggregates only that canary's observation JSONL files, runs `policy:compare`, validates actual candidate result files, and then runs `cost:goal-audit`.

How it works:

- `src/report.ts` scans `--results-dir` for the newest `ts-<provider>-<mode>-solve-all*.json` file for each provider (vercel, modal, daytona) and mode (cold, warm), preferring date-suffixed files. Missing provider/mode combinations are noted rather than failing the run.
- For each discovered run it computes pass counts, total/mean/median/p95 elapsed seconds, harness cost estimates, mean per-phase timings (`start`, `upload`, `prepare`, `instruction write`, `solve`, `verify`, `stop`), and per-task tables.
- The input JSONs come from `src/bench.ts` (single provider/mode runs) or `src/matrix.ts` (concurrent matrices). Warm runs depend on artifacts created by `src/prewarm.ts` (Vercel snapshot, Modal image, or Daytona prewarm profile).

## Task Runtime Mapping

- `terminalbench` tasks run from `/workspace` on the configured runtime.
- `harbor_swesmith` tasks run from `/testbed`.
- Modal and Daytona can use task Docker images or Dockerfile-derived setup.
- Vercel (and local) reconstruct the task environment from the per-repo manifest in `../data/swesmith_env_manifests.json`: the exact Python version is provisioned with uv into `/opt/testbed-venv`, the SWE-Smith mirror repo is cloned at the task branch, and the profile's install commands run inside the venv. The verifier venv matches the task image's (pytest/swebench/swesmith), so grading uses the task's real FAIL_TO_PASS/PASS_TO_PASS lists. Per-repo overrides live in `../data/swesmith_env_overrides.json`; regenerate the manifest with `python3 ../scripts/build_env_manifests.py`.

For SWE-Smith tasks the prepare step also rewrites `/solution/solve.sh` into a deterministic, idempotent form (reverse-applies the gold patch only while it is still present), and the verifier runs as the unprivileged `agent` user when possible so permission-sensitive test suites behave like they do in the task Docker image. Per-repo resource overrides (`resources` in the manifest) raise cpu/memory/disk for heavy repos such as pandas and MONAI.

## Gold Runnability Check

To verify that every task environment can apply the reference solution and pass its verifier on a provider (no LLM involved):

```bash
bun --env-file=../.env src/bench.ts --provider vercel --mode cold --task-index all --task-limit 100 --timeout-seconds 900 --solve-timeout-seconds 300 --solve-command-file ../scripts/gold_solver.sh --output ../results/ts-vercel-cold-gold-all.json
```

## Failure Triage

```bash
bun run triage ../results/ts-vercel-cold-solve-all-*.json --output ../reports/generated-triage.md
```

## Validation

```bash
bun run typecheck
bun run test:playwright
```

Live AWS MicroVM and Daytona SDK contract checks are skipped by default. Run them with `SDK_CONTRACT_LIVE=1` plus the provider credentials and image settings required by `tests/live_sdk_contract.spec.ts`.
