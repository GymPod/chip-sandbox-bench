# Cross-Vendor Comparison

Updated: 2026-06-17

This page compares Vercel, Modal, and Daytona on the full 100-task SWE-Smith smoke dataset using solver-independent cold gold runs. Every task has passing evidence on every provider, so the comparable subset is now the full dataset rather than a smaller passing slice.

## Inputs

- Dataset: `data/swesmith_v4_smoke100.jsonl` (100 SWE-Smith tasks).
- Evidence rule: for each provider/task, select the newest passing `ts-<provider>-cold-gold*.json` result; if no passing result exists, select the newest cold-gold result.
- Solver: `scripts/gold_solver.sh` semantics, either through `--solve-command 'bash /solution/solve.sh'` or equivalent gold-solver reruns.
- Timing caveat: the table sums selected per-task elapsed seconds across full and focused rerun artifacts. It is a runnability and relative task-time view, not a single synchronized matrix wall-clock measurement.

## Head-To-Head Rollup

provider | passed | observed task seconds | mean seconds | median seconds | p95 seconds | estimated provider cost
--- | ---: | ---: | ---: | ---: | ---: | ---:
vercel | 100/100 | 14356.6 | 143.6 | 128.6 | 267.9 | $1.5458
modal | 100/100 | 17397.9 | 174.0 | 159.2 | 318.3 | $1.3200
daytona | 100/100 | 19006.8 | 190.1 | 189.8 | 288.9 | $0.9465

## Interpretation

- All three providers now have 100/100 passing cold-gold evidence for the 100-task SWE-Smith smoke set.
- Vercel has the lowest observed task seconds in this stitched newest-passing evidence set.
- Daytona has the lowest estimated provider cost in this stitched newest-passing evidence set.
- Modal sits between Vercel and Daytona on estimated provider cost in this evidence set.
- Because this table stitches full and focused reruns, use it for runnability and rough head-to-head shape; run a fresh synchronized matrix before making strict speed claims.

## Mean Phase Seconds

provider | start | upload | prepare | instruction write | solve | verify | stop
--- | ---: | ---: | ---: | ---: | ---: | ---: | ---:
vercel | 0.3 | 4.7 | 114.4 | 4.0 | 0.5 | 17.1 | 2.6
modal | 0.7 | 2.7 | 128.6 | 1.7 | 0.3 | 24.3 | 0.4
daytona | 165.1 | 0.9 | 3.2 | 1.2 | 0.2 | 19.4 | 0.1

## Comparable Tasks

The comparable subset is all 100 tasks. See [per-task-comparison.md](per-task-comparison.md) for every task row and selected evidence file.
