# Bun / TypeScript Runner

Install:

```bash
bun install
```

Run one local verifier:

```bash
bun run bench --provider local --task-index 0 --output ../results/ts-local-one.json
```

Run all tasks with the Vercel Sandbox CLI:

```bash
bun run bench --provider vercel --task-index all --output ../results/ts-vercel-all.json
```

The TypeScript runner reads `../data/terminalbench_2026_03_05_smoke16.jsonl`. The Python runner is the canonical path for Modal and Daytona because their Python SDKs expose the required sandbox APIs directly.

