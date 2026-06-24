# Sandbox Provider Warm/Cold Price Report

Generated: 2026-06-24T23:02:32.181Z

## Scope

- Dataset: result files do not record dataset path.
- Task env mapping: result files do not record env counts.
- Solve runs cover cold and warm startup for Vercel, Modal, and Daytona using `scripts/openrouter_solver.sh` through OpenRouter.
- Verifier-only runs are intentionally excluded from this report.

## Task Environment Mapping

env type | workdir | provider runtime mapping | notes
--- | --- | --- | ---
`terminalbench` | `/workspace` | configured `--runtime` | Generic TerminalBench archive layout.
`harbor_swesmith` | `/testbed` | Modal/Daytona use task `environment/Dockerfile` base image; Vercel requires a prebuilt snapshot/runtime | SWE-Smith archives include `tests/test.sh`, `solution/*`, and task Docker context.

## Warm Vs Cold Price

provider | cold provider cost | warm provider cost | warm minus cold | warm/cold
--- | ---: | ---: | ---: | ---:
vercel | - | $0.1276 | - | -
modal | - | $0.0960 | - | -
daytona | - | $0.0713 | - | -
aws-microvm | - | - | - | -

## Solve Rollup

provider | mode | passed | total seconds | mean seconds | median seconds | p95 seconds | estimated provider cost | estimated internal compute cost | % higher
--- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---:
vercel | warm | 9/16 | 1348.16 | 84.26 | 76.79 | 165.87 | $0.1276 | $0.0255 | -
modal | warm | 11/16 | 1448.34 | 90.52 | 77.92 | 181.65 | $0.0960 | $0.0960 | -
daytona | warm | 10/16 | 1544.11 | 96.51 | 84.63 | 243.60 | $0.0713 | $0.0143 | -

## Mean Phase Seconds

provider | mode | start | upload | prepare | instruction write | solve | verify | stop
--- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---:
vercel | warm | 0.23 | 2.29 | 1.08 | 2.27 | 75.42 | 0.87 | 2.10
modal | warm | 0.66 | 1.66 | 2.67 | 1.52 | 82.89 | 0.87 | 0.25
daytona | warm | 0.87 | 0.29 | 1.44 | 0.78 | 92.20 | 0.80 | 0.13

## Failure Signals

provider | mode | signals
--- | --- | ---
vercel | warm | other: 7
modal | warm | other: 5
daytona | warm | other: 6

## Per Task

task | vercel warm | modal warm | daytona warm
--- | --- | --- | ---
R_package_dependency_missing_medium | fail 114.21s | pass 44.43s | pass 164.22s
Rscript_segfault_debugging_hard | pass 103.80s | pass 118.71s | pass 107.79s
Rscript_segfault_debugging_medium | pass 43.94s | pass 56.40s | pass 56.31s
a_b_testing_models_hard | pass 71.20s | pass 51.21s | pass 46.07s
a_b_testing_models_medium | pass 34.17s | pass 79.85s | pass 68.67s
a_star_pathfinding_hard | fail 152.02s | fail 75.98s | fail 127.99s
a_star_pathfinding_medium | fail 54.24s | pass 97.38s | pass 46.86s
aar_android_library_packaging_hard | fail 50.62s | fail 101.72s | fail 105.27s
aar_android_library_packaging_medium | fail 95.25s | fail 181.55s | fail 76.26s
abc_synthesis_optimization_hard | pass 37.53s | pass 30.14s | pass 19.25s
abc_synthesis_optimization_medium | fail 66.60s | fail 143.64s | fail 87.32s
abi_compliance_checker_tool_hard | pass 34.16s | pass 33.04s | pass 81.94s
abi_compliance_checker_tool_medium | pass 82.38s | pass 63.32s | fail 102.88s
acl2_induction_scheme_selection_hard | pass 93.55s | pass 148.35s | pass 243.60s
acl2_induction_scheme_selection_medium | pass 148.62s | pass 40.97s | pass 132.08s
aclocal_macro_not_found_hard | fail 165.87s | fail 181.65s | fail 77.61s

## Failed Tasks

- vercel warm: R_package_dependency_missing_medium, a_star_pathfinding_hard, a_star_pathfinding_medium, aar_android_library_packaging_hard, aar_android_library_packaging_medium, abc_synthesis_optimization_medium, aclocal_macro_not_found_hard
- modal warm: a_star_pathfinding_hard, aar_android_library_packaging_hard, aar_android_library_packaging_medium, abc_synthesis_optimization_medium, aclocal_macro_not_found_hard
- daytona warm: a_star_pathfinding_hard, aar_android_library_packaging_hard, aar_android_library_packaging_medium, abc_synthesis_optimization_medium, abi_compliance_checker_tool_medium, aclocal_macro_not_found_hard

## Raw Artifacts

- vercel warm: `../results/ts-vercel-warm-solve-all-20260528.json`
- modal warm: `../results/ts-modal-warm-solve-all-20260528.json`
- daytona warm: `../results/ts-daytona-warm-solve-all-20260528.json`
- missing vercel cold: `../results/ts-vercel-cold-solve-all.json`
- missing modal cold: `../results/ts-modal-cold-solve-all.json`
- missing daytona cold: `../results/ts-daytona-cold-solve-all.json`
- missing aws-microvm cold: `../results/ts-aws-microvm-cold-solve-all.json`
- missing aws-microvm warm: `../results/ts-aws-microvm-warm-solve-all.json`

## Notes

- Per-task rows intentionally omit per-task price; provider cost is reported only at run level.
- Estimated internal compute cost applies an 80% discount to Vercel, Daytona, and AWS MicroVM estimated provider cost; `% higher` compares that internal compute cost to AWS MicroVM for the same mode.
- The matrix runner caps Modal and Daytona task concurrency by default to avoid known provider rate, CPU, and memory limits while still running all provider/mode runs concurrently.
- For task-Docker datasets such as SWE-Smith, the matrix runner does not reuse generic Modal or Daytona warm artifacts because each task needs its own image.
- Vercel cannot consume the per-task Docker image directly; SWE-Smith Vercel runs require an equivalent task-compatible runtime or snapshot.
- Cost estimates are harness estimates based on configured provider rates and measured elapsed time; they do not include OpenRouter model spend.
- Cold and warm runs are only directly comparable when they use the same task set, solver command, model, resource settings, and concurrency.
