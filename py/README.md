# Python Runner

Install:

```bash
uv venv && source .venv/bin/activate && uv pip install -e ".[providers]"
```

Run one local verifier:

```bash
python -m code_sandbox_bench.bench --provider local --task-index 0 --output ../results/local-one.json
```

Run all tasks on a provider:

```bash
python -m code_sandbox_bench.bench --provider vercel --task-index all --output ../results/vercel-all.json
python -m code_sandbox_bench.bench --provider modal --task-index all --output ../results/modal-all.json
python -m code_sandbox_bench.bench --provider daytona --task-index all --output ../results/daytona-all.json
```

