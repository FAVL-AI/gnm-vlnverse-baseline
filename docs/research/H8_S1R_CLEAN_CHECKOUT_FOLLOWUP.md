# H8-S1R Clean-Checkout Follow-up

## Scope

This report records the clean detached-worktree verification after commit
`8706e322500e19b4a19db37849ee0cecdecc796c`.

The original commit is not amended. The corrections belong to a separate follow-up commit.

## Initial clean-checkout result

- 594 passed
- 10 failed
- 2387 deselected

The clean checkout exposed two defects.

## Defect 1: import-isolation tests

Two tests inspected process-global `sys.modules`, so unrelated pytest collection could cause false
failures when `rclpy` or another forbidden module was already present.

The tests now retain their static source scans and use
`h8_import_isolation.forbidden_modules_introduced_by()` in a clean subprocess to determine whether
the target module itself introduced forbidden imports.

## Defect 2: hardcoded repository root

The drive-validation module used a checkout-specific path.

It now derives the active repository root with:

`REPO = Path(__file__).resolve().parents[2]`

A regression test verifies that drive-validation and recorded-mode asset paths remain inside the
active checkout.

## Verification

- Portability regression: 1 passed
- Focused follow-up suite: 84 passed
- Complete H8 regression: 605 passed, 0 failed, 2387 deselected
- Python compilation: passed
- Modified evidence tests: Ruff passed
- Changed-line Ruff findings: 0
- `git diff --check`: passed

Legacy whole-file Ruff findings remain outside this bounded correction:

- drive-validation module: 10
- recorded-mode test module: 21

## Follow-up files

1. `scripts/gnm/h8_synthetic_fork_drive_validate.py`
2. `tests/gnm/test_h8_evidence_provider.py`
3. `tests/gnm/test_h8_evidence_schema.py`
4. `tests/gnm/test_h8_synthetic_fork_recorded_mode.py`
5. `docs/research/H8_S1R_CLEAN_CHECKOUT_FOLLOWUP.md`

## Evidence boundary

This does not authorise Isaac Sim, ROS 2, capture, dataset creation, training, inference, pushing,
tagging or Session A.

**BOUNDED FOLLOW-UP IMPLEMENTATION: PASS**

**CLEAN-COMMIT FOLLOW-UP VERIFICATION: PENDING**

Session A remains **NOT ELIGIBLE**.
