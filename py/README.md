# Python Runner

Python implementation of the benchmark runner and provider adapters.

The Python runner is the primary path for Python-only benchmark execution. It supports verifier-only runs, solver-enabled runs, and a built-in Vercel AI Gateway solver without invoking the TypeScript runner.

## Install

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[providers,env]"
```

The base package can run JSONL datasets without optional dependencies. Install `.[parquet]` only when reading parquet datasets.

## Run One Docker Task

```bash
python -m code_sandbox_bench.bench --provider docker --task-index 0 --output ../results/py-docker-one.json
```

Docker is the recommended local Linux executor for Python-only solver proof runs. The `local` provider is useful for narrow command-adapter smoke checks, but archived task scripts can contain absolute `/workspace`, `/tests`, and `/logs` paths that only behave like the benchmark environment inside a real Linux sandbox.

## Run AI Gateway Solver Proof

Set `AI_GATEWAY_API_KEY` or `VERCEL_OIDC_TOKEN`, plus `AI_GATEWAY_MODEL` when you want a specific model. The runner validates model availability through AI Gateway's OpenAI-compatible `/models` endpoint when `AI_GATEWAY_VALIDATE_MODEL=1`.

```bash
python -m code_sandbox_bench.bench \
  --provider docker \
  --dataset ../data/terminalbench_2026_03_05_smoke16.jsonl \
  --task-index all \
  --task-limit 16 \
  --stop-after-passes 10 \
  --solver ai-gateway \
  --timeout-seconds 900 \
  --solve-timeout-seconds 420 \
  --output ../results/py-docker-ai-gateway-10pass-terminalbench-smoke16.json
```

## Run A Provider

```bash
python -m code_sandbox_bench.bench --provider docker --task-index all --output ../results/py-docker-all.json
python -m code_sandbox_bench.bench --provider vercel --task-index all --output ../results/vercel-all.json
python -m code_sandbox_bench.bench --provider modal --task-index all --output ../results/modal-all.json
python -m code_sandbox_bench.bench --provider daytona --task-index all --output ../results/daytona-all.json
python -m code_sandbox_bench.bench --provider aws-microvm --task-index all --output ../results/aws-microvm-all.json
```

## Notes

- The Python runner supports `local`, `docker`, `vercel`, `modal`, `daytona`, and `aws-microvm`.
- Provider credentials are read from the environment.
- AWS MicroVM uses the persistent TypeScript bridge in `ts/src/aws_microvm_py_bridge.ts` so Python runs share the same MicroVM SDK implementation and telemetry path.
- The built-in `ai-gateway` solver is uploaded by the Python runner and uses only Python standard-library HTTP calls inside the sandbox.
- Resource policy defaults come from `data/resource_policy.json`; use `--resource-policy static` for fixed-resource comparisons and `--resource-observations-output` to write JSONL observations.

## Reports

The Python runner writes provider-level result JSON with the same dynamic-limit fields as the TypeScript runner: requested/adaptive/effective resources, static/adaptive cost estimates, resource observations, adaptive recommendations, retry metadata, adaptive concurrency summaries, agent traces, per-task phases, verifier tails, and solver tails when enabled.

Useful report commands:

```bash
python -m code_sandbox_bench.resource_report --input ../results/resource-observations.jsonl --format json
python -m code_sandbox_bench.matrix --providers aws-microvm --modes cold --task-limit 20 --solver gold
python -m code_sandbox_bench.policy_compare --results ../results/baseline.json --candidate-config ../data/resource_policy.json --format json
python -m code_sandbox_bench.canary_validate --baseline-results ../results/baseline.json --candidate-results ../results/candidate.json --format json
python -m code_sandbox_bench.cost_goal_audit --policy-comparison ../reports/policy.json --resource-report ../reports/resources.json --canary-validation ../reports/canary.json
python -m code_sandbox_bench.cost_canary_loop --providers vercel,modal,daytona --modes warm --baseline-results ../results/baseline.json
```
