# Chip Task Viewer

The viewer is a Vite frontend backed by Convex. Convex stores task metadata and
the inspectable workspace, test, and solution files from `../data/chip_tasks`.

## Local development

```bash
npm install
npx convex dev
npm run dev
```

## Backfill

Generate import files and replace the production tables:

```bash
python3 scripts/build_import.py
npx convex import --prod --table tasks --replace .convex-import/tasks.json
npx convex import --prod --table taskFiles --replace .convex-import/taskFiles.json
```

Import solver traces from one or more benchmark result files:

```bash
python3 scripts/build_trace_import.py ../results/chip-run.json
npx convex import --prod --table traceRuns --replace .convex-import/traceRuns.json
npx convex import --prod --table traceSteps --replace .convex-import/traceSteps.json
```

Imported runs appear under the task's **Traces** tab. Each step shows its model
prompt and response, extracted shell action, execution output, verifier output,
timing, and status.

Vercel runs `npm run vercel-build`, which deploys the Convex functions and
injects `VITE_CONVEX_URL` into the Vite build.
