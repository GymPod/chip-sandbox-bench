# Per-Provider Report

Updated: 2026-06-05

This page summarizes provider behavior on the current 20-task SWE-Smith evidence set. Use [cross-vendor-comparison.md](cross-vendor-comparison.md) for the strict apples-to-apples subset and [per-task-failure-audit.md](per-task-failure-audit.md) for detailed failed-task notes.

## Provider Rollup

provider | mode | passed | total seconds | estimated provider cost | notable caveat
--- | --- | ---: | ---: | ---: | ---
vercel | cold | 13/20 | 994.5 | $0.0942 | Fallback runtime, no direct task Docker image.
vercel | warm | 13/20 | 1023.5 | $0.0969 | Warm does not remove most SWE-Smith setup cost.
modal | cold | 17/20 | 1045.4 | $0.0693 | Strong image fidelity, but some patch rejects and real failures.
modal | warm | 17/20 | 968.4 | $0.0642 | Slightly faster than cold on this slice.
daytona | cold | 19/20 | 765.2 | $0.0353 | Best coverage here; fvcore still fails.
daytona | warm | 19/20 | 698.5 | $0.0322 | Fastest and lowest estimated provider cost in this slice.

## Vercel

Current result:

- 13/20 cold, 13/20 warm.
- On the 13-task comparable subset: 659.4s cold and 670.8s warm.

Strengths:

- Executes simple Python package tasks reliably after fallback verifier setup.
- Vercel-specific fixes now get `typeguard`, `cantools`, `starlette`, `soupsieve`, and `dask` past basic missing-dependency or pytest-config failures.
- Task startup is predictable in this slice.

Failure signatures:

- `_sqlite3` missing from Vercel `python3.13`, visible in `conan-io__conan.86f29e13.pr_11412`.
- Console-script/subprocess fidelity issues in `amueller__word_cloud.ec24191c.func_basic__b5q81acm`.
- Collection-time Conan autotools errors in `conan-io__conan.86f29e13.pr_15965`.
- Large real-test mismatch in `dask__dask.5f61e423.combine_module__dkp16syb`.
- Staticfiles permission test failures in both Starlette tasks.
- Missing PyTorch for fvcore in the matrix artifact; targeted PyTorch repair changes this to real test failures.

Trade-off:

Vercel needs a task-compatible runtime or snapshot path for SWE-Smith Docker-image tasks. Repo-specific dependency repair improves signal, but each repair adds setup time and can still miss pinned image details.

## Modal

Current result:

- 17/20 cold, 17/20 warm.
- On the 13-task comparable subset: 559.3s cold and 523.5s warm.

Strengths:

- Good Docker-image fidelity for SWE-Smith tasks.
- Passes Vercel-only hard cases such as wordcloud, Conan `pr_15965`, Dask, and fvcore.
- Warm mode is modestly faster than cold on the comparable subset.

Failure signatures:

- Conan `pr_11412` reaches real tests and fails `ConfigInstallTest::test_overwrite_read_only_file`; solver patch output also shows unreversed patch rejects.
- Both Starlette tasks show patch-application rejects in Modal and then fail with a mostly passing suite.
- Earlier high-concurrency runs exposed sandbox creation and shutdown rate issues, so task concurrency needs to track account limits.

Trade-off:

Modal is a strong fidelity provider for task-Docker workloads, but the current gold-solver patch application is not deterministic for all tasks. That can make a failure look provider-related when the patch script is the immediate problem.

## Daytona

Current result:

- 19/20 cold, 19/20 warm.
- On the 13-task comparable subset: 385.8s cold and 349.8s warm.

Strengths:

- Best pass count in the current 20-task evidence set.
- Lowest estimated provider cost and fastest elapsed time on the comparable subset.
- Passes the Vercel/Modal Starlette failures and the Vercel-only Dask/wordcloud/Conan failures.

Failure signatures:

- Fvcore fails in both cold and warm with `test_patch_resolved` reporting unresolved tests, even though the patch applies.
- Earlier high-concurrency experiments hit CPU and memory limits, so concurrency needs to be raised carefully despite improved limits.

Trade-off:

Daytona looks best on this slice, but its behavior depends on resource limits and task-image setup. The fvcore failure shows that high overall pass rate does not eliminate per-repo fidelity or solver correctness questions.

## Cross-Provider Takeaway

For price/performance, compare only tasks all providers can pass. For product fit, the excluded failures matter: they show where each provider needs image fidelity, dependency pinning, patch determinism, or concurrency tuning before larger SWE-Smith runs are interpretable.
