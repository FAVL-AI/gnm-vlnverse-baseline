# H8-S1R Follow-up Clean-Commit Verification

## Verification target

Follow-up commit:

`0c9a7653567963b1bf3e510e03228b6b4cd57e83`

Parent commit:

`8706e322500e19b4a19db37849ee0cecdecc796c`

Commit subject:

`Fix H8 clean-checkout portability and isolation`

The original H8-S1R commit was not amended.

## Verification environment

The follow-up commit was checked out in a newly created detached Git worktree under `/tmp`.

The detached worktree contained committed files only and was clean before verification began.

This was a clean-checkout technical verification. It was not an independent human review.

## Commit identity

- Author: Frank Asante Van Laarhoven
- Author email: F.Van-Laarhoven2@newcastle.ac.uk
- Committer: Frank Asante Van Laarhoven
- Committer email: F.Van-Laarhoven2@newcastle.ac.uk
- Follow-up files committed: 5

## Checkout-portability verification

The following objects resolved inside the detached checkout:

- drive-validation module;
- recorded-mode module;
- drive-validation repository root;
- recorded-mode repository root;
- synthetic-fork scene asset;
- Yahboom robot asset.

No shared asset path resolved to the primary development checkout.

Result:

**PASS**

## Complete H8 regression

Pytest collected:

- 2992 total tests;
- 605 H8 tests selected;
- 2387 tests deselected.

Result:

- 605 passed;
- 0 failed;
- 2387 deselected.

Result:

**PASS**

## Import-isolation verification

The evidence-provider and evidence-schema tests retained their static forbidden-import scans.

Their runtime backstops executed through clean subprocess isolation and no longer depended on
process-global `sys.modules` state introduced by unrelated pytest collection.

Result:

**PASS**

## Compilation verification

The bounded implementation and test files passed Python compilation.

Result:

**PASS**

## Lint verification

The modified evidence-provider and evidence-schema tests passed Ruff.

For the two legacy files:

- `scripts/gnm/h8_synthetic_fork_drive_validate.py`;
- `tests/gnm/test_h8_synthetic_fork_recorded_mode.py`;

the committed changed-line audit reported zero Ruff findings.

Pre-existing whole-file findings outside the committed lines remain documented and out of scope:

- drive-validation module: 10;
- recorded-mode test module: 21.

Result:

**PASS WITH DOCUMENTED OUT-OF-SCOPE LEGACY FINDINGS**

## Commit-integrity verification

The follow-up commit contains exactly these files:

1. `docs/research/H8_S1R_CLEAN_CHECKOUT_FOLLOWUP.md`
2. `scripts/gnm/h8_synthetic_fork_drive_validate.py`
3. `tests/gnm/test_h8_evidence_provider.py`
4. `tests/gnm/test_h8_evidence_schema.py`
5. `tests/gnm/test_h8_synthetic_fork_recorded_mode.py`

`git show --check` passed.

The detached worktree remained clean after testing.

## Verification verdict

**H8 FOLLOW-UP CLEAN-COMMIT VERIFICATION: PASS**

The clean-checkout portability and import-isolation engineering defects are technically closed.

## Boundary and remaining gates

This verification does not constitute independent human review.

It does not authorise:

- Isaac Sim execution;
- ROS 2 execution;
- hospital route capture;
- dataset capture;
- model training;
- policy inference;
- pushing;
- tagging;
- Session A.

Before Session A can become eligible, the programme still requires:

1. independent closure verification;
2. written Prof. Bo Wei approval of the proposed success threshold, tau = 0.50 m;
3. storage recheck confirming at least 100 GB free;
4. explicit authorisation for Session A map extension only;
5. continued prohibition of route capture until separately authorised.

No push was performed.

No tag was created.

Session A remains **NOT ELIGIBLE**.
