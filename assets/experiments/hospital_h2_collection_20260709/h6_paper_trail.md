# H6 — Paper Trail / Audit Ledger

**Experiment:** H6 hard-route-family coverage diagnostic on
**Isaac-Hospital-ImageNav-v0** (internal simulation).
**Repo:** `gnm-vlnverse-baseline` · **branch:** `h23-execfix` · **base commit:** `024033b`.
**Status:** `DIAGNOSTIC_ONLY_NOT_PROMOTED` — incumbent **H1 retained**, nothing
committed. This ledger proves the result came from a controlled sequence of gates,
not a loose run.

Companion files (this package): `h6_decision_log.md` (B), `h6_artifact_manifest.csv`
+ `h6_artifact_manifest_sha256.txt` (E), `h6_git_diff_summary.md` (F),
`h6_command_ledger.md` (G), `h6_claim_boundary.md` (I), `h6_repro_commands.md` (J).

---

## A. Timeline
All local time; dates from log filenames / ledger timestamps.

| # | When | Event | Primary evidence |
|---|---|---|---|
| 1 | 2026-07-12 | H6 route-planning decision: 8 families by **route type** (uturn/chain/ftL/sharpmulti/tightcorr/compound), 5 train / 1 val / 2 fresh held-out | `h6_plan.md`, `h6_route_family_approval_table.csv` |
| 2 | 2026-07-12 | 8-route precheck plan (light mode, no bags) authored | `scripts/gnm/h6_precheck_verdicts.py` |
| 3 | 2026-07-12 16:57–17:08 | Smoke test on `h6_uturn_01` (route_completed w/ `--steps 6000`) | `logs/h6_smoke_uturn01_*.log` |
| 4 | 2026-07-12 17:39 | Initial precheck: **7/8 PASS** | `logs/h6_precheck_harness_20260712_173959.log` |
| 5 | 2026-07-12 | **`h6_chain_01` FAIL** — `cl_stop_reason=left_xy_bounds` e-stop at wp 3/6 (route ran to x=−8.0, outside ±6 m control-authority box) | `h6_precheck_verdict_table.json`, `h6_excluded_routes.json` |
| 6 | 2026-07-12 | Preserve original out-of-bounds route as rejected evidence | `hospital_h6_routes/rejected/h6_chain_01__rejected.json` |
| 7 | 2026-07-12 | **Decider hardening**: `check_xy_bound` + `REJECT_XY_BOUND` (±6 m), enforced in `place()` + generator | `scripts/gnm/execution_feasibility_decider.py`, `scripts/datasets/hospital_h6_generate_hard_routes.py` |
| 8 | 2026-07-12 | Repaired `h6_chain_01` in-bounds (x∈[−3.5, 0.5]); 7 other routes byte-identical | `hospital_h6_routes/h6_chain_01.json` |
| 9 | 2026-07-12 18:35–18:40 | Re-precheck `h6_chain_01` → PASS ⇒ **8/8 PASS** (old route still REJECT_XY_BOUND) | `logs/h6_precheck_chain01_rerun_20260712_183541.log`, `h6_precheck_verdict_table.json` |
| 10 | 2026-07-12 19:51–23:27 | **16/16 recording** (8 families ×2), FULL mode rosbag ON | `logs/h6_record_collection_20260712_195121.log`, `h6_recording_ledger.json` |
| 11 | 2026-07-13 00:1x | Conversion 16/16 → GNM frames (stride 12) | `logs/h6_convert_batch.log`, `h6_convert_ledger.jsonl` |
| 12 | 2026-07-13 00:19–00:20 | Diagnostic fine-tune (weights-only init from H1, fresh optimizer) | `logs/h6_train.log`, `h6_professor_report.md` |
| 13 | 2026-07-13 00:2x | Evaluation 3 ckpts × 4 held-out sets = 12 evals | `logs/h6_evaluate_all.log`, `h6_eval_matrix.json` |
| 14 | 2026-07-13 | Governance (DriftGuard + VerdictPlane run-card) | `h6_driftguard_decision.json`, `h6_verdictplane_record.json`, `h6_adjudication.json` |
| 15 | 2026-07-13 | Professor report + this paper trail | `h6_professor_report.md`, `h6_paper_trail.md` |

---

## B. Decisions & gates
Full detail in `h6_decision_log.md`. Summary — every gate, pass/fail, what it unlocked, what stayed blocked:

| Gate | Result | Evidence | Unlocked | Stayed blocked |
|---|---|---|---|---|
| Route-authoring | 7/8→**8/8** after repair | `h6_precheck_verdict_table.json`, `h6_excluded_routes.json` | recording | out-of-bounds chain_01 (rejected) |
| Smoke-test | PASS | `logs/h6_smoke_*` | precheck | — |
| 8-precheck | **8/8 PASS** | `h6_precheck_verdict_table.json` | 16-ep recording | — |
| Raw recording | **16/16 RECORDED_OK** | `h6_recording_ledger.json`, `h6_recording_quality_table.csv` | conversion | training (until approved) |
| Conversion/leakage | **PASS** (16/16, leakage-clean) | `h6_dataset_readiness.json`, `h6_conversion_leakage_report.json` | diagnostic training | — |
| Diagnostic training | PASS (val loss 0.0685) | `logs/h6_train.log` | evaluation | promotion |
| Evaluation | 12/12 complete | `h6_eval_matrix.json` | governance | promotion |
| DriftGuard/VerdictPlane | net_gate=promote **but** VerdictPlane **deny** | `h6_driftguard_decision.json`, `h6_verdictplane_record.json` | — | **promotion (deny)** |
| Final adjudication | `DIAGNOSTIC_ONLY_NOT_PROMOTED` | `h6_adjudication.json` | diagnostic archival | promote / tag / push / commit |

---

## C. Inputs
| Input | Path / source |
|---|---|
| H6 route files (8) | `assets/experiments/hospital_h6_routes/h6_{uturn_01,uturn_02,chain_01,chain_02,ftL_01,sharpmulti_01,tightcorr_01,compound_01}.json` |
| Repaired `h6_chain_01` | `assets/experiments/hospital_h6_routes/h6_chain_01.json` (in-bounds x∈[−3.5,0.5]) |
| Rejected original `h6_chain_01` | `assets/experiments/hospital_h6_routes/rejected/h6_chain_01__rejected.json` |
| H6 raw bags (16) | `assets/experiments/rosbags/h6rec_*` (30 GB) |
| H6 trajectories (16) | `assets/experiments/trajectories/h6rec_*` (205 MB) |
| H6 converted root | `datasets/isaac_hospital_h6/{train,val,test_h6hard}` (built from `datasets/isaac_hospital_imagenav_v0/unassigned/h6rec_*`) |
| Training config | `configs/gnm/gnm_h6_hard_families.yaml` |
| **H1 incumbent** (init + eval baseline) | `checkpoints/hospital_front_rgb_finetune/best.pt` (sha256 `d269a0fb…`) |
| **H5 reference** | `checkpoints/h5_mixed_replay_finetune/best.pt` (sha256 `39acd488…`) |
| Eval splits | `datasets/isaac_hospital_h5/{test_h4,test_prior,test_combined}`; `datasets/isaac_hospital_h6/test_h6hard` |

## D. Outputs (generated evidence)
Recording quality `h6_recording_quality_table.csv` · split manifest `h6_split_manifest.json` ·
leakage `h6_leakage_report.json` + `h6_conversion_leakage_report.json` ·
excluded `h6_excluded_routes.json` + `h6_excluded_episode_report.json` ·
claim boundary `h6_claim_boundary.md` + `h6_goal_claimboundary.json` ·
conversion `h6_converted_dataset_summary.json` + `h6_converted_split_counts.{json,csv}` + `h6_dataset_readiness.json` + `h6_convert_ledger.jsonl` ·
training `configs/gnm/gnm_h6_hard_families.yaml` + `logs/h6_train.log` ·
eval `h6_eval_matrix.{json,csv}` + 12× `h6_eval_{h1,h5,h6}_{set}.json` ·
per-family `h6_per_family_failure_table.{json,csv}` ·
governance `h6_driftguard_decision.json` + `h6_verdictplane_record.json` ·
adjudication `h6_adjudication.json` + cards `h6_{candidate,incumbent,h5_reference}_card.json` ·
report `h6_professor_report.md`.

## E. File manifest
See `h6_artifact_manifest.csv` (path · type · size · sha256 · for-git · reason) and
`h6_artifact_manifest_sha256.txt` (verifiable with `sha256sum -c`). Large artifacts
(raw bags, converted frames, dataset root, checkpoints, logs) are marked **not for git**.

## F. Git diff summary
See `h6_git_diff_summary.md` — modified vs new H6-scoped files, the unrelated dirty
files to exclude, and the proposed commit boundary.

## G. Command ledger
See `h6_command_ledger.md` — the major commands / wrapper scripts actually run.

## H. Results summary (Track A, offline; `--data-root` forced)
| Set (n) | Model | SR | OSR | SPL | NE↓ (m) | nDTW↑ | TL (m) |
|---|---|---|---|---|---|---|---|
| test_h4 (6) | H1 | 0.000 | 1.000 | 0.000 | 14.04 | 0.167 | 14.46 |
| | H5 | 0.333 | 1.000 | 0.333 | 5.02 | 0.382 | 4.40 |
| | **H6** | 0.333 | 1.000 | 0.301 | 6.15 | 0.378 | 6.48 |
| **test_h6hard (4)** | H1 | 0.000 | 0.000 | 0.000 | 21.36 | 0.021 | 18.28 |
| *fresh hard* | H5 | 0.000 | 0.000 | 0.000 | 8.25 | 0.159 | 4.81 |
| | **H6** | 0.000 | 0.000 | 0.000 | 10.58 | 0.111 | 7.25 |
| test_prior (6) | H1 | 0.167 | 0.667 | 0.167 | 12.76 | 0.276 | 13.45 |
| | H5 | 0.000 | 0.333 | 0.000 | 7.19 | 0.290 | 4.42 |
| | **H6** | 0.167 | 0.500 | 0.167 | 7.73 | 0.325 | 6.35 |
| test_combined (12) | H1 | 0.083 | 0.833 | 0.083 | 13.40 | 0.222 | 13.95 |
| | H5 | 0.167 | 0.667 | 0.167 | 6.10 | 0.336 | 4.41 |
| | **H6** | 0.250 | 0.750 | 0.234 | 6.94 | 0.351 | 6.41 |

**Governance:** DriftGuard `net_gate=promote` (passes only on an SR **tie at 0** +
NE gain on the hard set — *not* a hard-family success gain) · VerdictPlane
`verdict=deny` · **Final adjudication `DIAGNOSTIC_ONLY_NOT_PROMOTED`**, H1 retained.

**One-line result:** H6 has the best combined SR (0.25) and nDTW, preserves the H4
gain, and fixes H5's prior-family regression — **but no model achieves SR>0 or
OSR>0 on the fresh hard held-out families**; the coverage hypothesis is refined,
not confirmed.

## I. Limitations
See `h6_claim_boundary.md`. In brief: **fixed placeholder goal image** (⇒ NOT
goal-conditioning evidence); scripted-expert demonstrations; simulation-only;
offline Track-A metrics; small n (4/6/12); one seed; deterministic a/b variants;
not real-robot; not a public benchmark; **not promoted**; no SOTA claim.

## J. Repro
See `h6_repro_commands.md` — verify hashes, check dataset counts, re-run evaluation
from saved checkpoints, regenerate the professor report, and verify no unrelated
files enter the future commit.
