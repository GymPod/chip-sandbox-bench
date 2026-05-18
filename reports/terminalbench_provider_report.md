# TerminalBench Provider Harness Report

## Scope

This report covers the lightweight dogfood terminal harness and the 16-row TerminalBench smoke benchmark added in PR 1705. The harness supports:

- `local` execution for toy terminal repair tasks.
- `vercel` / `vercel_sandbox` for toy tasks and TerminalBench smoke verifier runs.
- `modal` and `daytona` in the verifier-only cold vs prepared-snapshot benchmark CLI.

The benchmark is intentionally verifier-only. It prepares a task workspace and runs `bash /tests/test.sh`, but it does not run a solver/model edit step. A `0/16` pass count is therefore expected for the 16 TerminalBench runs.

## How The Tests Work

### Toy Harness Smoke

Command shape:

```bash
PYTHONPATH=$(pwd) python -m autonomy.dogfood.terminal_harness --provider vercel --runtime python --task-source toy --timeout-seconds 120
```

This runs a tiny terminal-style repair task through the OpenRouter-compatible agent path. The agent receives a shell tool backed by the selected provider. For Vercel, the harness starts a sandbox, runs the agent's tool calls inside it, and then executes the verifier in the same sandbox.

Observed result:

| Test | Provider | Result |
| --- | --- | --- |
| Toy Python repair | Vercel Sandbox | Passed |

### TerminalBench Smoke Benchmark

Command used for the completed 16-task Vercel run:

```bash
PYTHONPATH=$(pwd) python -m autonomy.dogfood.vercel_terminalbench_benchmark --task-index all --timeout-seconds 180 --output /tmp/vercel-terminalbench-benchmark-all16.json
```

For each selected TerminalBench row, the benchmark runs three phases:

| Phase | What It Does |
| --- | --- |
| Cold prepare + verifier | Starts a fresh provider sandbox, uploads the task workspace and tests, installs `pytest`, then runs `bash /tests/test.sh`. |
| Snapshot prepare | Starts or builds a prepared environment with the task workspace and tests, then snapshots it. |
| Warm verifier | Starts from the prepared snapshot and runs only `bash /tests/test.sh`. |

Provider-specific snapshot behavior:

| Provider | Snapshot Method |
| --- | --- |
| Vercel | Prepare a running Vercel sandbox, then call the Vercel snapshot API and restart from the returned snapshot ID. |
| Modal | Prepare a running Modal sandbox, then snapshot its filesystem as a Modal image and restart from that image ID. |
| Daytona | Build a named Daytona snapshot from an image spec that includes the task workspace, tests, and verifier dependencies. |

### Local Verification

The following local checks ran against the implementation:

| Check | Result | Notes |
| --- | --- | --- |
| `py_compile` on changed harness/provider/test files | Passed | Validates syntax/importability for the changed files. |
| Focused pytest suite | Passed | `39 passed, 6 skipped, 1 warning`; skipped tests are Daytona live-provider tests without credentials. |
| Pre-commit on changed files | Passed | Black, isort, ruff, autoflake, and repository file checks passed. |
| Benchmark CLI help smoke | Passed | Confirms `--provider {vercel,vercel_sandbox,modal,daytona}` is exposed. |
| Vercel one-task benchmark regression | Passed | Exercised the generalized provider benchmark path and cleaned up the Vercel snapshot. |
| `make typecheck` | Failed baseline | Repo-wide mypy backlog: `1719 errors in 182 files`. |
| `make test` | Failed baseline | Repo-wide failures: `48 failed, 1041 passed, 12 skipped, 192 errors`. |

Modal and Daytona live 16-task benchmark runs were not executed in this local environment because provider credentials were not configured:

- Modal: `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`
- Daytona: `DAYTONA_API_KEY`, `DAYTONA_API_URL`, and sometimes `DAYTONA_TARGET`

## Actual Vercel 16-Task Result

| Mode | Passed | Estimated Upper-Bound Cost |
| --- | ---: | ---: |
| Cold prepare + verifier | 0/16 | $0.023947 |
| Warm verifier from prepared snapshots | 0/16 | $0.009132 |
| Snapshot prepare + warm verifier | 0/16 | $0.041493 |

Interpretation:

- Warm-only was cheaper than cold by about `$0.014815` for this run.
- Including snapshot preparation made the one-shot warm path more expensive than cold by about `$0.017546`.
- The run left no active Vercel sandboxes or retained Vercel snapshots after cleanup.

## Vendor Pricing Model

Pricing was checked against public vendor pages on May 18, 2026.

| Provider | Rates Used In Benchmark |
| --- | --- |
| Vercel Sandbox | Active CPU `$0.128/vCPU-hour`, memory `$0.0212/GB-hour`, creation `$0.60/1M`, storage `$0.08/GB-month` from [Vercel pricing](https://vercel.com/pricing). |
| Modal Sandbox + Notebooks | CPU `$0.00003942/physical-core-second`, memory `$0.00000672/GiB-second`; Modal states one physical core is 2 vCPU equivalent on [Modal pricing](https://modal.com/pricing). |
| Daytona | CPU `$0.00001400/vCPU-second`, memory `$0.00000450/GiB-second`, storage `$0.00000003/GiB-second` after 5 GB free from [Daytona pricing](https://www.daytona.io/pricing). |

Important assumptions:

- The harness records wall-clock phase duration and treats it as an upper bound for active CPU.
- Vercel bills active CPU separately from provisioned memory; the benchmark cannot see exact active CPU seconds from the CLI.
- Modal uses physical cores. The comparison maps `2 vCPU` to `1 physical core`.
- Daytona storage estimate assumes `10 GiB` disk with `5 GiB` billable after the free allowance.
- Network, snapshot storage retention beyond the run, provider credits, region multipliers, and volume discounts are excluded.

## Side-By-Side Cost Comparison

The table below applies the measured Vercel phase durations to each vendor's public rates. This is a normalized model, not a substitute for live Modal/Daytona benchmark data.

Measured aggregate phase durations inferred from the completed Vercel benchmark:

| Phase | Total Seconds | Avg Seconds / Task |
| --- | ---: | ---: |
| Cold prepare + verifier | 252.86 | 15.80 |
| Warm verifier | 96.36 | 6.02 |
| Snapshot prepare | 341.74 | 21.36 |

Normalized cost estimate for all 16 tasks:

| Provider | Cold | Warm Only | Snapshot Prepare | Snapshot Prepare + Warm |
| --- | ---: | ---: | ---: | ---: |
| Vercel Sandbox | $0.023947 | $0.009132 | $0.032361 | $0.041493 |
| Modal | $0.016765 | $0.006389 | $0.022657 | $0.029046 |
| Daytona | $0.011669 | $0.004447 | $0.015771 | $0.020218 |

Takeaways:

- On this verifier-only workload, warm starts are materially cheaper than cold runs if snapshots already exist.
- Snapshot preparation dominates one-shot warm cost. Reusing snapshots across multiple verifier or solver attempts is where warm starts become useful.
- The normalized model suggests Daytona has the lowest raw compute/storage cost for this workload, followed by Modal, then Vercel. That conclusion should be rechecked with live Modal/Daytona runs because startup latency, snapshot creation time, SDK behavior, and provider-specific billing details can move the totals.

## Next Live Benchmark Commands

After credentials are configured, run:

```bash
PYTHONPATH=$(pwd) python -m autonomy.dogfood.vercel_terminalbench_benchmark --provider modal --task-index all --timeout-seconds 180 --output /tmp/modal-terminalbench-benchmark-all16.json
```

```bash
PYTHONPATH=$(pwd) python -m autonomy.dogfood.vercel_terminalbench_benchmark --provider daytona --task-index all --timeout-seconds 180 --output /tmp/daytona-terminalbench-benchmark-all16.json
```

Those outputs should replace the normalized Modal/Daytona estimates with measured cold, snapshot-prepare, and warm timings.
