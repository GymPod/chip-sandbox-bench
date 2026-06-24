# Per-Provider Report

Updated: 2026-06-24

This report summarizes current provider behavior on the 100-task SWE-Smith cold-gold runnability evidence set. Use [cross-vendor-comparison.md](cross-vendor-comparison.md) for the head-to-head rollup and [per-task-comparison.md](per-task-comparison.md) for task-level timings.

## Rollup

provider | passed | observed task seconds | mean seconds | median seconds | p95 seconds | estimated provider cost | estimated internal compute cost | % higher
--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---:
vercel | 100/100 | 14356.6 | 143.6 | 128.6 | 267.9 | $1.5458 | $0.3092 | 92%
modal | 100/100 | 17397.9 | 174.0 | 159.2 | 318.3 | $1.3200 | $1.3200 | 719%
daytona | 100/100 | 19006.8 | 190.1 | 189.8 | 288.9 | $0.9465 | $0.1893 | 17%
aws-microvm | 97/100 | 14390.0 | 143.9 | 127.4 | 230.2 | $0.8063 | $0.1613 | 0%

## Vercel

- Current evidence: 100/100 passing.
- Execution model: fallback runtime reconstruction from `data/swesmith_env_manifests.json`, because Vercel cannot directly consume each SWE-Smith task Docker image.
- Main cost driver: prepare and dependency reconstruction dominate relative to Modal and Daytona.
- Product fit: useful once manifests are complete, but timing comparisons should account for the fallback-runtime setup path.

## Modal

- Current evidence: 100/100 passing.
- Execution model: native task Docker image support for SWE-Smith task images.
- Recent fixes addressed deterministic solve application, transient provider transport retries, Dockerfile command handling, DSPy dependency/cache drift, Pandas/Tweepy focused reruns, and SQLFluff test command de-duplication.
- Product fit: strong fidelity for task-Docker workloads, with retry handling still useful for transient stream/setup failures.

## Daytona

- Current evidence: 100/100 passing.
- Execution model: native task Docker image support for SWE-Smith task images.
- Recent fixes addressed deterministic solve application, task image command fidelity, Pydantic uv pathing, Safety local DB/provider egress behavior, DSPy drift, and SQLFluff test command de-duplication.
- Product fit: lowest estimated cost among the native task-Docker providers in the current stitched cold-gold evidence set.

## AWS Lambda MicroVMs

- Current evidence: 97/100 passing from `results/ts-aws-microvm-cold-gold-all100-gym-platform-20260624.json`.
- Execution model: fresh per-task MicroVMs launched from the reused `code-sandbox-bench-runner-20260624-gym-platform-2` image, with manifest-driven SWE-Smith environment reconstruction inside each MicroVM.
- Recent run shape: `--task-limit 100`, `--concurrency 10`, `--memory-gb 2`, `--cpu 2`, and `scripts/gold_solver.sh`.
- Remaining failures: DVC hit an `RLIMIT_NOFILE` verifier setup issue, one Pandas row had two failing `read_stata` tests, and one Pandas row produced a green pytest log but returned `127` after the wrapper tried `/opt/verifier-venv/bin/pytest`.
- Product fit: AWS MicroVM startup is fast and the run parallelized cleanly, but SWE-Smith currently uses fallback environment reconstruction rather than native per-task Docker images.
- Cost note: AWS MicroVM estimated cost uses public US East (N. Virginia) ARM runtime rates: `$0.09969984` per vCPU-hour and `$0.01320012` per GB-hour. The revised compute-only estimate is about `$0.8063`, split into `$0.6375` memory-derived vCPU and `$0.1688` memory. This is a 23.2% reduction from the previous requested-CPU estimate of `$1.0501`; snapshot read/write/storage and data transfer are excluded.
- Internal cost note: estimated internal compute cost applies an 80% discount to Vercel, Daytona, and AWS MicroVM estimated provider cost; `% higher` compares that internal compute cost to AWS MicroVM.

## Evidence Files

### Vercel

- `results/ts-vercel-cold-gold-extra-task73.json`
- `results/ts-vercel-cold-gold-extra-task74.json`
- `results/ts-vercel-cold-gold-extra-task76.json`
- `results/ts-vercel-cold-gold-extra-task77.json`
- `results/ts-vercel-cold-gold-extra-task82.json`
- `results/ts-vercel-cold-gold-extra-task83.json`
- `results/ts-vercel-cold-gold-extra-task84.json`
- `results/ts-vercel-cold-gold-extra-task85.json`
- `results/ts-vercel-cold-gold-extra-task86.json`
- `results/ts-vercel-cold-gold-extra-task87.json`
- `results/ts-vercel-cold-gold-extra-task90.json`
- `results/ts-vercel-cold-gold-extra-task91.json`
- `results/ts-vercel-cold-gold-extra-task93.json`
- `results/ts-vercel-cold-gold-extra-task94.json`
- `results/ts-vercel-cold-gold-extra-task95.json`
- `results/ts-vercel-cold-gold-extra-task96.json`
- `results/ts-vercel-cold-gold-extra-task99.json`
- `results/ts-vercel-cold-gold-rerun-task23.json`
- `results/ts-vercel-cold-gold-rerun-task4.json`
- `results/ts-vercel-cold-gold-rerun-task97.json`
- `results/ts-vercel-cold-gold-rerun11-task37.json`
- `results/ts-vercel-cold-gold-rerun12-task20.json`
- `results/ts-vercel-cold-gold-rerun12-task50.json`
- `results/ts-vercel-cold-gold-rerun12-task88.json`
- `results/ts-vercel-cold-gold-rerun12-task89.json`
- `results/ts-vercel-cold-gold-rerun12-task98.json`
- `results/ts-vercel-cold-gold-rerun14-task22.json`
- `results/ts-vercel-cold-gold-rerun14-task75.json`
- `results/ts-vercel-cold-gold-rerun17-task19.json`
- `results/ts-vercel-cold-gold-rerun2-task47.json`
- `results/ts-vercel-cold-gold-rerun2-task70.json`
- `results/ts-vercel-cold-gold-rerun2-task71.json`
- `results/ts-vercel-cold-gold-rerun2-task72.json`
- `results/ts-vercel-cold-gold-rerun2-task78.json`
- `results/ts-vercel-cold-gold-rerun2-task79.json`
- `results/ts-vercel-cold-gold-rerun2-task80.json`
- `results/ts-vercel-cold-gold-rerun2-task81.json`
- `results/ts-vercel-cold-gold-rerun4-task63.json`
- `results/ts-vercel-cold-gold-rerun4-task64.json`
- `results/ts-vercel-cold-gold-rerun4-task65.json`
- `results/ts-vercel-cold-gold-rerun5-task29.json`
- `results/ts-vercel-cold-gold-rerun5-task36.json`
- `results/ts-vercel-cold-gold-rerun5-task44.json`
- `results/ts-vercel-cold-gold-rerun5-task45.json`
- `results/ts-vercel-cold-gold-rerun5-task9.json`
- `results/ts-vercel-cold-gold-rerun5-task92.json`
- `results/ts-vercel-cold-gold-rerun7-task1.json`
- `results/ts-vercel-cold-gold-rerun7-task34.json`
- `results/ts-vercel-cold-gold-rerun8-task25.json`
- `results/ts-vercel-cold-gold-rerun9-task27.json`
- `results/ts-vercel-cold-gold-rerun9-task41.json`
- `results/ts-vercel-cold-gold-rerun9-task51.json`
- `results/ts-vercel-cold-gold-rerun9-task66.json`
- `results/ts-vercel-cold-gold-rerun9-task67.json`
- `results/ts-vercel-cold-gold-rerun9-task68.json`
- `results/ts-vercel-cold-gold-task70.json`

### Modal

- `results/ts-modal-cold-gold-all100-current.json`
- `results/ts-modal-cold-gold-focus-edited-clusters-current.json`
- `results/ts-modal-cold-gold-rerun-current-task20.json`
- `results/ts-modal-cold-gold-rerun-current-task46.json`
- `results/ts-modal-cold-gold-rerun-current-task48.json`
- `results/ts-modal-cold-gold-rerun-current-task49.json`
- `results/ts-modal-cold-gold-rerun-current-task50.json`
- `results/ts-modal-cold-gold-rerun-current-task97.json`
- `results/ts-modal-cold-gold-rerun-task87-sqlfluff-dedupe-python-test.json`
- `results/ts-modal-cold-gold-rerun-task88-dspy-request-shim.json`
- `results/ts-modal-cold-gold-rerun-task89-dspy-request-shim.json`
- `results/ts-modal-cold-gold-rerun-task99-modal-dockerfilecommands-retry.json`
- `results/ts-modal-cold-gold-rerun-tasks47-50-97-current.json`

### Daytona

- `results/ts-daytona-cold-gold-all100-current.json`
- `results/ts-daytona-cold-gold-focus-patch-retry-current.json`
- `results/ts-daytona-cold-gold-focus-pydantic-tornado-retry-current.json`
- `results/ts-daytona-cold-gold-remaining-47-99-current.json`
- `results/ts-daytona-cold-gold-rerun-current-task18.json`
- `results/ts-daytona-cold-gold-rerun-current-task46.json`
- `results/ts-daytona-cold-gold-rerun-seq-task13.json`
- `results/ts-daytona-cold-gold-rerun-seq-task20.json`
- `results/ts-daytona-cold-gold-rerun-seq-task21.json`
- `results/ts-daytona-cold-gold-rerun-seq-task26.json`
- `results/ts-daytona-cold-gold-rerun-seq-task27.json`
- `results/ts-daytona-cold-gold-rerun-seq-task28.json`
- `results/ts-daytona-cold-gold-rerun-seq-task29.json`
- `results/ts-daytona-cold-gold-rerun-seq-task30.json`
- `results/ts-daytona-cold-gold-rerun-seq-task31.json`
- `results/ts-daytona-cold-gold-rerun-seq-task32.json`
- `results/ts-daytona-cold-gold-rerun-seq-task33.json`
- `results/ts-daytona-cold-gold-rerun-seq-task34.json`
- `results/ts-daytona-cold-gold-rerun-seq-task35.json`
- `results/ts-daytona-cold-gold-rerun-seq-task36.json`
- `results/ts-daytona-cold-gold-rerun-seq-task37.json`
- `results/ts-daytona-cold-gold-rerun-seq-task38.json`
- `results/ts-daytona-cold-gold-rerun-seq-task39.json`
- `results/ts-daytona-cold-gold-rerun-seq-task40.json`
- `results/ts-daytona-cold-gold-rerun-seq-task41.json`
- `results/ts-daytona-cold-gold-rerun-seq-task42.json`
- `results/ts-daytona-cold-gold-rerun-seq-task43.json`
- `results/ts-daytona-cold-gold-rerun-seq-task44.json`
- `results/ts-daytona-cold-gold-rerun-seq-task45.json`
- `results/ts-daytona-cold-gold-rerun-task57-pydantic-usrlocal-uv.json`
- `results/ts-daytona-cold-gold-rerun-task58-pydantic-usrlocal-uv.json`
- `results/ts-daytona-cold-gold-rerun-task75-safety-local-db-shim-empty-license.json`
- `results/ts-daytona-cold-gold-rerun-task87-sqlfluff-dedupe-python-test.json`
- `results/ts-daytona-cold-gold-rerun-task88-dspy-request-shim.json`
- `results/ts-daytona-cold-gold-rerun-task89-dspy-request-shim.json`

### AWS Lambda MicroVMs

- `results/ts-aws-microvm-cold-gold-all100-gym-platform-20260624.json`
