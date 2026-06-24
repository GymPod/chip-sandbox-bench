# Failure Modes And Trade-Offs

Updated: 2026-06-24

The 100-task cold-gold runnability pass is green across Vercel, Modal, and Daytona. AWS Lambda MicroVMs have a fresh all-100 run using the reused shared runner image, with 97/100 tasks passing and three verifier/environment gaps still open.

## Current State

provider | runnable tasks | main execution path | remaining comparison caveat
--- | ---: | --- | ---
Vercel | 100/100 | Manifest-driven fallback runtime reconstruction | Not native per-task Docker; prepare time includes environment reconstruction.
Modal | 100/100 | Native SWE-Smith task Docker images | Stitched evidence includes focused reruns, so use a fresh matrix for strict wall-clock comparisons.
Daytona | 100/100 | Native SWE-Smith task Docker images | Stitched evidence includes focused reruns, so use a fresh matrix for strict wall-clock comparisons.
AWS Lambda MicroVMs | 97/100 | Reused MicroVM runner image plus manifest-driven fallback runtime reconstruction | Compute-only AWS estimate excludes snapshot/data-transfer charges; three tasks need focused verifier/environment repair.

## Resolved Failure Clusters

cluster | examples | fix character
--- | --- | ---
Dependency pins | SoupSieve, Webargs, Nikola, Astroid, Safety | Repo-specific `swesmith_env_overrides.json` pins and pre-verify setup.
Provider image/runtime fidelity | Pydantic, Modal task Docker commands | Provider-specific command and path normalization.
Network or external fixture drift | Safety, DSPy | Local response/cache shims where task tests depend on remote fixtures.
Heavy suite verification | Pandas, Tweepy, Tornado | Focused provider reruns and narrow pre-verify adjustments.
SQLFluff verifier instability | task 87 | De-duplicated repeated `python_test.py` invocation in generated verifier command.
AWS MicroVM verifier gaps | DVC, Pandas | DVC needs an inherited `RLIMIT_NOFILE` setup adjustment; one Pandas row had `read_stata` failures; one Pandas row likely needs broader green-log detection for a `127` wrapper exit.

## Trade-Offs

- The current reports use newest passing cold-gold evidence per provider/task. That is the right view for "can every task run?".
- For strict speed and price comparisons, run a fresh single matrix with the same concurrency, timeouts, resources, and solver command across providers.
- Vercel's SWE-Smith path is intentionally different from Modal/Daytona because it reconstructs task environments from manifests instead of running task Docker images directly.
- AWS MicroVMs currently share Vercel's fallback reconstruction model for SWE-Smith, while reusing one prebuilt MicroVM runner image across tasks.
- Cost estimates are harness estimates from measured elapsed time and configured provider rates; they exclude model spend.
