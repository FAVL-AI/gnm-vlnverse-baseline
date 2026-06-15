# Test Scope Comparison

**Date recorded:** 2026-06-15  
**Environment:** Python 3.13.13, pytest 9.0.3, `/home/favl/robotics/gnm-vlnverse-language`

## Run A — Language-file subset

```
python3 -m pytest tests/test_vlntube_instruction_audit.py \
                  tests/test_language_grounding_pipeline.py -q
```

| Collected | Passed | Failed | Skipped |
|-----------|--------|--------|---------|
| 98 | 89 | 0 | 9 |

The 9 skipped tests are CLIP-dependent: they skip at collection time when the
CLIP model weights are not available on disk. This run does **not** represent
the full repository suite.

---

## Run B — Full repository suite

```
python3 -m pytest -q --tb=no
```

Using `pyproject.toml` configuration (`testpaths = ["tests"]`).

| Collected | Passed | Failed | Skipped | xfailed |
|-----------|--------|--------|---------|---------|
| 2141 | 2012 | 2 | 125 | 2 |

The increase from 1,815 to 2,012 reflects 197 new tests added in
`tests/test_documentation_integrity.py` (manifest integrity, prohibited attribution,
unsupported claims, local links, copyright notices).

Both failures are pre-existing and unrelated to Track B:

| Test | Classification |
|------|----------------|
| `tests/gnm/test_live_dashboard.py::test_export_live_dashboard_first_frame_exists` | PRE_EXISTING_IDENTICAL_FAILURE |
| `tests/test_routes_smoke.py::test_experiments_summary_has_total` | PRE_EXISTING_IDENTICAL_FAILURE |

Both failures are also present on `main` at commit `3c2226d`. Zero new failures
introduced by `track-b-language-grounding`.

---

## Historical counts

| Earlier count | Reason |
|---------------|--------|
| ~1,798 passed | Full-suite run before 26 new vlntube instruction-audit tests (commits `d488104` / `39b51c5`) |
| 1,815 passed | Full suite after vlntube audit tests; before documentation-integrity tests |
| **2,012 passed** | **Current authoritative count** — includes 197 `test_documentation_integrity.py` tests |

---

## Disambiguation

| Reported count | Scope | Command |
|----------------|-------|---------|
| 89 passed, 9 skipped | 2 language test files only | `pytest tests/test_vlntube_instruction_audit.py tests/test_language_grounding_pipeline.py` |
| 2,012 passed, 2 failed | Full suite (current) | `pytest` (all of `tests/`) |
| 1,815 passed, 2 failed | Full suite (pre-documentation-integrity tests) | `pytest` |
| ~1,798 passed, 2 failed | Full suite (earliest recorded) | `pytest` |

"Full suite" means all tests collected from the `tests/` directory using the
`pyproject.toml` configuration. Partial runs must not be called the full suite.
