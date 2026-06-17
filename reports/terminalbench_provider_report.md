# Sandbox Provider Report

Updated: 2026-06-17

This report set now tracks the 100-task SWE-Smith cold-gold runnability comparison across Vercel, Modal, and Daytona.

## Summary

All three providers have passing evidence for all 100 tasks in `data/swesmith_v4_smoke100.jsonl`.

provider | passed | observed task seconds | mean seconds | median seconds | p95 seconds | estimated provider cost
--- | ---: | ---: | ---: | ---: | ---: | ---:
vercel | 100/100 | 14356.6 | 143.6 | 128.6 | 267.9 | $1.5458
modal | 100/100 | 17397.9 | 174.0 | 159.2 | 318.3 | $1.3200
daytona | 100/100 | 19006.8 | 190.1 | 189.8 | 288.9 | $0.9465

## Report Index

- [Cross-vendor comparison](cross-vendor-comparison.md): head-to-head rollup for the full 100-task comparable set.
- [Per-task comparison](per-task-comparison.md): every task across Vercel, Modal, and Daytona.
- [Per-provider report](per-provider-report.md): provider-by-provider execution notes and evidence files.
- [Failure modes and trade-offs](failure-modes-tradeoffs.md): resolved clusters and remaining comparison caveats.
- [Per-task failure audit](per-task-failure-audit.md): current no-failure state plus historical cluster summary.
- [Cost estimate caveats](cost-estimate-caveats.md): reliability audit for the dollar estimates and underlying result data.

## Notes

- The comparison is solver-independent cold-gold runnability evidence.
- The timing rollups are stitched from full and focused reruns. Use a fresh synchronized matrix before making strict wall-clock claims.
- The dollar figures are harness estimates, not reconciled provider billing data. See [cost estimate caveats](cost-estimate-caveats.md).
- Vercel uses manifest-driven fallback environment reconstruction for SWE-Smith tasks; Modal and Daytona use native task Docker images.
