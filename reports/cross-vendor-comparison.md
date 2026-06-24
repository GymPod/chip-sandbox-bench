# Cross-Vendor Comparison

Updated: 2026-06-24

This page compares Vercel, Modal, Daytona, and AWS Lambda MicroVMs on the full 100-task SWE-Smith smoke dataset using solver-independent cold gold runs. Vercel, Modal, and Daytona have passing evidence for every task. The latest AWS MicroVM run used the reused `code-sandbox-bench-runner-20260624-gym-platform-2` image and passed 97/100 tasks.

## Inputs

- Dataset: `data/swesmith_v4_smoke100.jsonl` (100 SWE-Smith tasks).
- Evidence rule for Vercel, Modal, and Daytona: for each provider/task, select the newest passing `ts-<provider>-cold-gold*.json` result; if no passing result exists, select the newest cold-gold result.
- AWS MicroVM evidence: `results/ts-aws-microvm-cold-gold-all100-gym-platform-20260624.json`, a single 100-task run with concurrency 10 and a reused MicroVM image.
- Solver: `scripts/gold_solver.sh` semantics, either through `--solve-command 'bash /solution/solve.sh'` or equivalent gold-solver reruns.
- Timing caveat: the table sums selected per-task elapsed seconds across full and focused rerun artifacts. It is a runnability and relative task-time view, not a single synchronized matrix wall-clock measurement.

## Head-To-Head Rollup

provider | passed | observed task seconds | mean seconds | median seconds | p95 seconds | estimated provider cost
--- | ---: | ---: | ---: | ---: | ---: | ---:
vercel | 100/100 | 14356.6 | 143.6 | 128.6 | 267.9 | $1.5458
modal | 100/100 | 17397.9 | 174.0 | 159.2 | 318.3 | $1.3200
daytona | 100/100 | 19006.8 | 190.1 | 189.8 | 288.9 | $0.9465
aws-microvm | 97/100 | 14390.0 | 143.9 | 127.4 | 230.2 | $1.0501

## Interpretation

- Vercel, Modal, and Daytona have 100/100 passing cold-gold evidence for the 100-task SWE-Smith smoke set.
- AWS MicroVMs reached 97/100 on the first all-100 run with the shared runner image. The failures were one DVC verifier environment issue, one Pandas real test failure, and one Pandas likely false negative where the test log was green but the wrapper returned `127`.
- Vercel has the lowest observed task seconds in this stitched newest-passing evidence set.
- Daytona has the lowest estimated provider cost in this stitched newest-passing evidence set.
- Modal sits between Vercel and Daytona on estimated provider cost in this evidence set.
- AWS MicroVM observed task seconds are close to Vercel's in this run. The AWS MicroVM estimate uses public runtime compute rates only; snapshot read/write/storage and data transfer are excluded.
- Because this table stitches full and focused reruns, use it for runnability and rough head-to-head shape; run a fresh synchronized matrix before making strict speed claims.
- Treat estimated provider cost as directional only. See [cost estimate caveats](cost-estimate-caveats.md).

## Mean Phase Seconds

provider | start | upload | prepare | instruction write | solve | verify | stop
--- | ---: | ---: | ---: | ---: | ---: | ---: | ---:
vercel | 0.3 | 4.7 | 114.4 | 4.0 | 0.5 | 17.1 | 2.6
modal | 0.7 | 2.7 | 128.6 | 1.7 | 0.3 | 24.3 | 0.4
daytona | 165.1 | 0.9 | 3.2 | 1.2 | 0.2 | 19.4 | 0.1
aws-microvm | 3.4 | 1.0 | 122.1 | 1.3 | 2.1 | 13.8 | 0.2

## Comparable Tasks

The comparable subset for Vercel, Modal, and Daytona is all 100 tasks. AWS MicroVM currently has 97 passing tasks from the all-100 run. See [per-task-comparison.md](per-task-comparison.md) for the existing Vercel/Modal/Daytona task rows and selected evidence files.
