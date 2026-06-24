# Results

Checked-in benchmark metadata and ignored local benchmark artifacts.

## Naming

Common result names use:

```text
ts-<provider>-<mode>-solve-all-<suffix>.json
ts-<provider>-cold-gold-<suffix>.json
solve-price-matrix-<suffix>.json
```

Provider files contain per-task results. Matrix files summarize a set of provider/mode runs.

## Current Report Inputs

The curated reports now use cold-gold SWE-Smith evidence for all 100 tasks in `data/swesmith_v4_smoke100.jsonl`.

Evidence selection rule:

- Scan local ignored `results/ts-<provider>-cold-gold*.json` files.
- For each provider/task, select the newest passing result.
- If no passing result exists, select the newest cold-gold result.

The current report generation found 100/100 passing evidence for Vercel, Modal, and Daytona. The latest task-87 SQLFluff confirmation files are:

- `ts-daytona-cold-gold-rerun-task87-sqlfluff-dedupe-python-test.json`
- `ts-modal-cold-gold-rerun-task87-sqlfluff-dedupe-python-test.json`

See `../reports/terminalbench_provider_report.md` for the report index.

## Artifact Types

- `prewarm-*`: warm artifact creation or inspection output.
- `*-verifier-*`: verifier-only checks. Daytona verifier artifacts live under `verifier/`.
- `*-solve-*`: solver-enabled runs.
- `*-cold-gold-*`: solver-independent gold-patch runnability checks.
- `*-env-*`, `*-probe*`, `*-trace*`: provider or task-environment investigations.

## Agent Trace Fields

Benchmark result JSON includes a top-level `agent_trace_summary` and a per-task `agent_trace`.
The trace records lifecycle and command timing so idle gaps between commands can be analyzed without CloudWatch:

- `started_at`, `completed_at`, and `duration_seconds` for each lifecycle or command event.
- `idle_gap_seconds`, measured from the prior event completion to the next event start in the same task attempt.
- `command_idle_gap_seconds`, measured from the prior command completion to the next command start.
- `label`, `cwd`, `timeout_seconds`, and `return_code` for command events.
- `command_length` and `command_sha256` instead of raw command text.

The summary buckets command-to-command idle gaps with `over_10s`, `over_60s`, and `over_300s` counters for auto-suspend threshold analysis.

Result JSON may include output tails from task logs. Do not store secrets in task output or forwarded environment values.
