# Modal/Daytona Cost Inversion

Updated: 2026-06-24

This note explains why Modal can have lower elapsed task time than Daytona while still showing a higher estimated provider cost in the current SWE-Smith cold-gold report.

AWS Lambda MicroVMs are not included in the Modal/Daytona inversion calculation below because this note focuses on those two native task-Docker providers. The latest AWS all-100 run now has a compute-only estimate of about `$0.8063`; snapshot read/write/storage and data transfer are excluded.

## Bottom Line

The inversion is expected from the harness math. Modal is faster in the stitched evidence set, but the benchmark is charging Modal at a higher all-in sandbox resource rate than Daytona.

Modal is about 8.5% faster by observed task seconds, but its effective estimated cost per sandbox-hour is about 52.4% higher. That rate difference is large enough for Modal's total estimated cost to remain higher.

## Rollup With Effective Rate

Effective rate is calculated from the existing report values:

```text
effective $/sandbox-hour = estimated provider cost / observed task seconds * 3600
```

provider | observed task seconds | estimated provider cost | effective $/sandbox-hour
--- | ---: | ---: | ---:
vercel | 14356.6 | $1.5458 | $0.3876
modal | 17397.9 | $1.3200 | $0.2731
daytona | 19006.8 | $0.9465 | $0.1793

## Why Modal Costs More Here

The cost formulas in `ts/src/bench.ts` are provider-specific:

provider | harness formula
--- | ---
Modal | `seconds * ((cpu / 2) * 0.00003942 + memoryGb * 0.00000672)`
Daytona | `seconds * (cpu * 0.000014 + memoryGb * 0.0000045 + max(0, diskGb - 5) * 0.00000003)`

Converted to comparable hourly units:

resource | Modal | Daytona
--- | ---: | ---:
CPU | $0.0710 / vCPU-hour | $0.0504 / vCPU-hour
Memory | $0.0242 / GiB-hour | $0.0162 / GiB-hour

The benchmark also includes task-specific resource overrides. Several heavier rows request more CPU and/or memory, and those rows are not timing-neutral. Daytona is much faster on a few expensive rows, including MONAI, Pandas, FVCore, DSPy, and Tornado reruns. Those rows reduce Daytona's total estimated spend disproportionately.

## Interpretation

This is not evidence of a spreadsheet typo by itself. It is a rate-and-weighting artifact:

- Mean seconds is an unweighted timing statistic.
- Estimated provider cost is a weighted sum over each task's elapsed seconds and requested resources.
- Modal's sandbox CPU and memory rates in the harness are higher than Daytona's hard-coded rates.
- The current report is stitched from local full and focused rerun artifacts, not one synchronized matrix run.

For decision-grade pricing, rerun a fresh synchronized matrix and reconcile the harness estimates against provider billing exports.

The latest AWS MicroVM run is useful for timing shape and compute-only cost shape: it passed 97/100 tasks with 14390.0 observed task seconds and an estimated runtime compute cost of about `$0.8063`.

## Related Docs

- [Cross-vendor comparison](cross-vendor-comparison.md)
- [Cost estimate caveats](cost-estimate-caveats.md)
- [Per-task comparison](per-task-comparison.md)
