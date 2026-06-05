# Per-Task Failure Audit

Updated: 2026-06-05

This audit covers the seven tasks excluded from the 13-task cross-vendor comparable subset. It uses the current task20 evidence set listed in [terminalbench_provider_report.md](terminalbench_provider_report.md), plus the targeted Vercel fvcore/PyTorch probe.

## Summary

task | failed modes | classification | next action
--- | --- | --- | ---
`amueller__word_cloud.ec24191c.func_basic__b5q81acm` | Vercel cold/warm | Vercel CLI execution fidelity | Inspect generated console script/PATH and Vercel subprocess executable behavior.
`conan-io__conan.86f29e13.pr_11412` | Vercel cold/warm, Modal cold/warm | Mixed: Vercel `_sqlite3`; Modal real tests plus patch rejects | Add Conan to Vercel sqlite interpreter mapping; separately inspect gold patch idempotency on Modal.
`conan-io__conan.86f29e13.pr_15965` | Vercel cold/warm | Vercel collection failure | Capture full traceback; likely another repo-specific Vercel dependency/runtime gap.
`dask__dask.5f61e423.combine_module__dkp16syb` | Vercel cold/warm | Real test failures under Vercel dependency/runtime set | Version-pin pandas/pyarrow/numpy stack closer to task image or use task-compatible snapshot.
`encode__starlette.db5063c2.combine_file__hrjivx2s` | Vercel cold/warm, Modal cold/warm | Staticfiles permission tests; Modal also patch rejects | Investigate filesystem permission semantics and gold patch idempotency.
`encode__starlette.db5063c2.func_basic__vehyiaux` | Vercel cold/warm, Modal cold/warm | Staticfiles permission tests; Modal also patch rejects | Same as Starlette combine task.
`facebookresearch__fvcore.a491d5b9.lm_rewrite__yldgp998` | Vercel cold/warm, Daytona cold/warm | PyTorch/image fidelity; remaining real test failures after PyTorch repair | Prefer exact task image or snapshot; pin torch/image dependency versions if staying with fallback runtime.

## `amueller__word_cloud.ec24191c.func_basic__b5q81acm`

Observed status:

- Vercel cold: failed in 42.5s.
- Vercel warm: failed in 49.7s.
- Modal and Daytona: passed in both modes.

Vercel reached the real test suite: `73 passed, 7 warnings, 3 errors`. The three errors are all CLI executable cases:

- `test_cli_as_executable[wordcloud_cli --help-usage: wordcloud_cli-0]`
- `test_cli_as_executable[/vercel/runtimes/python/bin/python3 -m wordcloud --help-usage: __main__-0]`
- `test_cli_as_executable[/vercel/runtimes/python/bin/python3 /testbed/test/../wordcloud/wordcloud_cli.py --help-To execute the CLI-1]`

This is not a missing-testbed failure. The patch applied and most tests passed. The likely gap is Vercel's fallback Python install/executable layout, PATH, or subprocess behavior for console entrypoints.

## `conan-io__conan.86f29e13.pr_11412`

Observed status:

- Vercel cold/warm: failed quickly during import.
- Modal cold/warm: failed after running hundreds of tests.
- Daytona cold/warm: passed.

Vercel failure:

- Importing Conan reaches `conan/internal/cache/db/cache_database.py`.
- That imports `sqlite3`.
- Vercel `python3.13` fails with `ModuleNotFoundError: No module named '_sqlite3'`.

This is the same class of fidelity gap that required a repo-specific interpreter switch for `cantools`. Conan probably needs the same sqlite-aware interpreter mapping on Vercel, but that must be checked against Conan's Python-version requirements.

Modal failure:

- `2 failed, 277 passed, 8 warnings`.
- Both failures are `ConfigInstallTest::test_overwrite_read_only_file`.
- `solve_return_code=1`; the gold patch script also reports unreversed patch rejects in `conan/api/subapi/download.py` and `conans/client/rest/rest_client_v2.py`.

The Modal result is therefore mixed: the environment is strong enough to run the test suite, but the gold patch application is not clean and the remaining failures are real tests.

## `conan-io__conan.86f29e13.pr_15965`

Observed status:

- Vercel cold/warm: failed.
- Modal and Daytona: passed in both modes.

Vercel collected zero items and hit two collection errors in `test/unittests/client/toolchain/autotools/autotools_toolchain_test.py`. The result tail does not include the full traceback, so this needs a targeted rerun with a larger log capture before assigning a precise root cause.

The useful distinction is that this is Vercel-only and collection-time. It is probably another fallback-runtime dependency or interpreter mismatch, not a general solver failure.

## `dask__dask.5f61e423.combine_module__dkp16syb`

Observed status:

- Vercel cold/warm: failed.
- Modal and Daytona: passed in both modes.

Vercel reached the real suite and ran for roughly 100 seconds in verify:

- cold: `35 failed, 5846 passed, 20 skipped, 8 xfailed`.
- warm: `35 failed, 5846 passed, 20 skipped, 8 xfailed`.

The visible failures concentrate in dataframe expression collection, quantile, datetime shift/frequency behavior, and `test_from_dask_array_index_dtype`. Earlier Vercel fixes moved this task past missing deps and pytest configuration into real test behavior. The remaining gap is likely dependency/version fidelity for the pandas/pyarrow/numpy/dask stack or Python-runtime differences versus the task image.

## `encode__starlette.db5063c2.combine_file__hrjivx2s`

Observed status:

- Vercel cold/warm: failed.
- Modal cold/warm: failed.
- Daytona cold/warm: passed.

Vercel reached the real suite:

- cold: `2 failed, 865 passed, 2 xfailed`.
- warm: `2 failed, 865 passed, 2 xfailed`.
- Both visible failures are `test_staticfiles_with_invalid_dir_permissions_returns_401` for `asyncio` and `trio`.

Modal also failed, but the solver patch application was not clean:

- `solve_return_code=1`.
- Patch output includes `Unreversed patch detected` and rejects for `starlette/middleware/base.py`.
- Verifier still shows two failing tests in a mostly passing suite.

This task should not be used for vendor speed/cost comparison until patch application is made deterministic and filesystem permission semantics are understood.

## `encode__starlette.db5063c2.func_basic__vehyiaux`

Observed status:

- Vercel cold/warm: failed.
- Modal cold/warm: failed.
- Daytona cold/warm: passed.

The failure shape mirrors the Starlette combine task:

- Vercel reaches `2 failed, 865 passed, 2 xfailed`.
- The visible failures are the same invalid-directory-permission staticfiles tests.
- Modal solver output shows patch idempotency/reversal problems before verification.

Treat this as the same failure family as `encode__starlette.db5063c2.combine_file__hrjivx2s`.

## `facebookresearch__fvcore.a491d5b9.lm_rewrite__yldgp998`

Observed status:

- Vercel cold/warm matrix artifact: failed with 14 collection errors because PyTorch was absent.
- Vercel targeted run after repo-specific PyTorch install: collection fixed, then `3 failed, 155 passed, 2 skipped`.
- Modal cold/warm: passed.
- Daytona cold/warm: failed with the verifier reporting unresolved tests.

The targeted Vercel run installed `torch` from `https://download.pytorch.org/whl/cpu` only for `facebookresearch__fvcore*`. That moved the failure from environment collection to real tests:

- `test_focal_loss_star_equals_ce_loss_multi_class`
- `test_model_stats_table`
- `test_crop_invalid_polygons`

Docker metadata for the task image shows Ubuntu 22.04, Miniconda Python 3.12, and a repo-specific `/root/setup_env.sh`; the manifest includes a 6.6 GB layer. That makes exact image matching costly, but it is the most credible route to full fidelity.
