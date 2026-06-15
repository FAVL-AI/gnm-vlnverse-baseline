# Regression Comparison — Gate A vs Base Commit

**Date:** 2026-06-15  
**Purpose:** Demonstrate that two test failures present after commit `27ad5cb` were already present at the branch base `3c2226d` and are therefore not regressions introduced by Gate A work.

## Environment

| Field | Value |
|-------|-------|
| Python executable | `/home/favl/miniforge3/bin/python3` |
| Python version | 3.13.13 |
| pytest version | 9.0.3 |
| Base commit | `3c2226d6e519a66206f4ea7317f552604526b83a` |
| Current commit | `27ad5cb` |
| Base worktree | `/tmp/gnm-track-b-baseline-check` (detached, `git worktree add --detach`) |
| Current worktree | `/home/favl/robotics/gnm-vlnverse-language` |

## Test Results

### `tests/gnm/test_live_dashboard.py::test_export_live_dashboard_first_frame_exists`

| | Base (`3c2226d`) | Current (`27ad5cb`) |
|-|------------------|---------------------|
| Return code | 1 (FAILED) | 1 (FAILED) |
| Error | `AssertionError: dashboard_000000.png (frame 0) missing` | `AssertionError: dashboard_000000.png (frame 0) missing` |
| Classification | **PRE_EXISTING_IDENTICAL_FAILURE** | — |

**Root cause:** The test checks for a pre-generated file
`results/bo_reviewer_packet/live_dashboard/dashboard_000000.png`
that is not present in this CI environment. The file must be created by running
`--export-live-dashboard` on a machine with the full rendered dataset.
The failure message is identical on both commits; only the absolute worktree path differs.

### `tests/test_routes_smoke.py::test_experiments_summary_has_total`

| | Base (`3c2226d`) | Current (`27ad5cb`) |
|-|------------------|---------------------|
| Return code | 1 (FAILED) | 1 (FAILED) |
| Error | `assert 0 > 0` | `assert 0 > 0` |
| Classification | **PRE_EXISTING_IDENTICAL_FAILURE** | — |

**Root cause:** The test asserts `body["total_runs"] > 0` against an in-memory
experiment database. No experiment runs have been recorded in this environment,
so `total_runs=0` on both commits. The assertion and failure message are
byte-for-byte identical.

## Classification Summary

| Classification | Count |
|----------------|-------|
| PRE_EXISTING_IDENTICAL_FAILURE | **2** |
| PRE_EXISTING_DIFFERENT_FAILURE | 0 |
| NEW_REGRESSION | **0** |
| ENVIRONMENT_MISMATCH | 0 |
| PASSES_ON_BOTH | 0 |

## Conclusion

**Zero regressions introduced by commit `27ad5cb`.**

Both failures existed identically at `3c2226d` (the merge-base of this feature
branch with `origin/main`). The Gate A changes (`evaluate_track_b.py`, +10 tests,
regenerated result artefacts) did not cause either failure.
