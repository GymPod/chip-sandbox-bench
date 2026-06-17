# Cost Estimate Caveats

Updated: 2026-06-17

This page audits the cost estimates in the provider reports. The estimates are useful for directional comparison, but they should not be treated as provider bills.

## Bottom Line

The strongest current claim is runnability: Vercel, Modal, and Daytona each have 100/100 passing cold-gold evidence for `data/swesmith_v4_smoke100.jsonl`.

The weakest current claim is exact spend. The dollar figures are local harness estimates calculated from selected result JSONs, not reconciled billing data from provider invoices or usage exports.

## Data Used

The current report rollup uses stitched local artifacts:

provider | selected tasks | observed task seconds | estimated cost | selected source files
--- | ---: | ---: | ---: | ---:
Vercel | 100 | 14356.6 | $1.5458 | 56
Modal | 100 | 17397.9 | $1.3200 | 13
Daytona | 100 | 19006.8 | $0.9465 | 35

Selection rule:

1. Scan local `results/ts-<provider>-cold-gold*.json` files.
2. For each provider/task, select the newest passing result.
3. If no passing result exists, select the newest cold-gold result.

`results/*` is ignored by git, except `results/README.md`. A fresh clone does not contain the JSON files used to generate the current report numbers.

## Formula Used

The formulas live in `ts/src/bench.ts`.

provider | harness formula
--- | ---
Vercel | `(seconds / 3600) * (cpu * 0.128 + memoryGb * 0.0212) + 0.60 / 1_000_000`
Modal | `seconds * ((cpu / 2) * 0.00003942 + memoryGb * 0.00000672)`
Daytona | `seconds * (cpu * 0.000014 + memoryGb * 0.0000045 + max(0, diskGb - 5) * 0.00000003)`

## Reliability

claim | confidence | why
--- | --- | ---
100/100 runnability | High | The selected local result artifacts contain passing verifier results for all 100 tasks on all three providers.
Relative task-time shape | Medium-low | The data is stitched from full and focused reruns across different times and code states.
Exact dollar estimates | Low | The estimates are formula-based and are not reconciled to provider usage exports or invoices.
Provider cost ranking | Medium-low | The ranking is useful as a rough signal, but sensitive to billing details, cache state, and the stitched data selection.

## Known Flaws

- The report uses local ignored artifacts, so the exact underlying data is not reproducible from the repository alone.
- The rollup stitches full runs and focused reruns. It is not a single synchronized matrix.
- The selection rule prefers successful results and excludes failed attempts and debugging reruns, so it does not estimate the total spend required to get to green.
- Cold runs may still benefit from provider-side image, registry, package, or layer caches.
- Different selected artifacts were produced at different commits and times during the repair process.
- Provider setup phases do not necessarily map cleanly to provider billing dimensions.
- Model/API spend is excluded.
- Network egress, image build, snapshot storage, registry transfer, volume, and account minimums are not modeled unless they are implicitly included in elapsed sandbox time.

## Provider-Specific Caveats

### Vercel

- Public Sandbox pricing bills CPU as active CPU, while the harness charges CPU for full elapsed wall time. This likely overestimates Vercel for I/O-heavy tasks.
- The harness passes `vcpus` at sandbox creation, but the report formula uses recorded `memoryGb`; actual provisioned memory may differ from the recorded value.
- SWE-Smith on Vercel uses manifest-driven fallback environment reconstruction, not native per-task Docker images. Prepare time dominates many tasks and may not represent a future optimized snapshot path.
- Snapshot storage or snapshot creation costs are not included.

### Modal

- Modal Sandbox rates in the formula match the public sandbox CPU and memory rates at the time of this audit, but the harness ignores region multipliers, non-preemptible multipliers, discounts, and included credits.
- Modal bills CPU and memory based on whichever is higher: request or actual usage. The harness estimates from requested resources only.
- Modal disk requests can increase billable memory at a 20:1 ratio. The current formula does not account for that.
- Image build time and image caching behavior can materially affect cold runs.

### Daytona

- The Daytona formula is the least verified. Daytona docs describe pay-as-you-go billing based on sandbox resources, but this repo does not include a checked, official rate source for the hard-coded CPU, memory, and disk values.
- Daytona start time is a large portion of the selected elapsed time. Whether every part of that startup interval maps to billable sandbox resource time should be verified against billing exports.
- Disk is capped to 10 GB in `bench.ts` for task runs, so requested disk values in some artifacts are normalized before costing.

## What Would Make This Decision-Grade

1. Check in a deterministic report generator and an input manifest with artifact filenames, checksums, provider, task id, commit, and timestamp.
2. Run one fresh synchronized cold-gold matrix across all providers with the same commit, concurrency, resources, timeout, dataset, and solver command.
3. Capture provider run ids or sandbox ids in result JSONs.
4. Reconcile estimates against provider billing or usage exports.
5. Split cost reporting by sandbox runtime, image build, snapshot/storage, network, retries, and failed attempts.
6. For Vercel, use active CPU billing data rather than full wall-clock CPU.
7. For Daytona, replace the hard-coded rates with a documented source or org billing export.

