# Failure Modes And Trade-Offs

Updated: 2026-06-17

The 100-task cold-gold runnability pass is now green across all three providers. The remaining interpretation work is about how to compare timings fairly, not about unresolved task executability.

## Current State

provider | runnable tasks | main execution path | remaining comparison caveat
--- | ---: | --- | ---
Vercel | 100/100 | Manifest-driven fallback runtime reconstruction | Not native per-task Docker; prepare time includes environment reconstruction.
Modal | 100/100 | Native SWE-Smith task Docker images | Stitched evidence includes focused reruns, so use a fresh matrix for strict wall-clock comparisons.
Daytona | 100/100 | Native SWE-Smith task Docker images | Stitched evidence includes focused reruns, so use a fresh matrix for strict wall-clock comparisons.

## Resolved Failure Clusters

cluster | examples | fix character
--- | --- | ---
Dependency pins | SoupSieve, Webargs, Nikola, Astroid, Safety | Repo-specific `swesmith_env_overrides.json` pins and pre-verify setup.
Provider image/runtime fidelity | Pydantic, Modal task Docker commands | Provider-specific command and path normalization.
Network or external fixture drift | Safety, DSPy | Local response/cache shims where task tests depend on remote fixtures.
Heavy suite verification | Pandas, Tweepy, Tornado | Focused provider reruns and narrow pre-verify adjustments.
SQLFluff verifier instability | task 87 | De-duplicated repeated `python_test.py` invocation in generated verifier command.

## Trade-Offs

- The current reports use newest passing cold-gold evidence per provider/task. That is the right view for "can every task run?".
- For strict speed and price comparisons, run a fresh single matrix with the same concurrency, timeouts, resources, and solver command across providers.
- Vercel's SWE-Smith path is intentionally different from Modal/Daytona because it reconstructs task environments from manifests instead of running task Docker images directly.
- Cost estimates are harness estimates from measured elapsed time and configured provider rates; they exclude model spend.
