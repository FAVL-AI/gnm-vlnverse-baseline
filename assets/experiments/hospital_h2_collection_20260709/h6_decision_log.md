# H6 — Decision Log (gate-by-gate)

Each gate: name · result · evidence file · decision · what was allowed next ·
what remained blocked. Human approver: Frank Asante Van Laarhoven. Every phase was
explicitly gated; no phase auto-advanced past a blocked gate.

---

### Gate 1 — Route-authoring feasibility
- **Result:** 7/8 PASS initially → **8/8 PASS** after repair.
- **Evidence:** `h6_precheck_verdict_table.json`, `h6_route_family_approval_table.csv`, `h6_excluded_routes.json`.
- **Finding:** `h6_chain_01` placement drove to x=−8.0, outside the ±6 m runtime XY control-authority box → `left_xy_bounds` e-stop (a route-placement defect, not controller infeasibility: 0 collisions, 8.18 m driven cleanly first).
- **Decision:** do **not** widen the safety bound ("the route was wrong; the envelope was right"); harden the decider with `REJECT_XY_BOUND` (±6 m), re-author `h6_chain_01` in-bounds, preserve the original as rejected evidence.
- **Allowed next:** recording (once 8/8). **Blocked:** the original out-of-bounds route (permanently rejected, retained as evidence).

### Gate 2 — Smoke test
- **Result:** PASS (route_completed=True with `--steps 6000`; the 480-step / 8 s default was too short).
- **Evidence:** `logs/h6_smoke_uturn01_*.log`.
- **Decision:** adopt `--steps 6000` (~100 s, H4-equivalent) as the standard episode length.
- **Allowed next:** full 8-family precheck. **Blocked:** nothing.

### Gate 3 — 8-family precheck (light mode, no bags)
- **Result:** **8/8 PASS** (route_completed, 0 contacts, clean DDS/proc teardown).
- **Evidence:** `h6_precheck_verdict_table.{json,csv}`, `logs/h6_precheck_chain01_rerun_20260712_183541.log`.
- **Decision:** controller-feasibility confirmed for all 8 families → proceed to recording.
- **Allowed next:** 16-episode FULL-mode recording. **Blocked:** training (pending recording + review).

### Gate 4 — Raw recording quality
- **Result:** **16/16 RECORDED_OK** — route_completed=True, 0 collisions, max streak 0, clean teardown, ~1.96 GB/bag; no STOP condition tripped.
- **Evidence:** `h6_recording_ledger.{json,csv}`, `h6_recording_quality_table.csv`, `h6_artifact_completeness_report.json`, `h6_cleanup_dds_report.json`, `h6_disk_report.json`, `h6_leakage_report.json`.
- **Decision:** raw collection gate PASSES.
- **Allowed next:** conversion + diagnostic fast-track (explicitly approved as diagnostic). **Blocked:** promotion, tag, push, commit.

### Gate 5 — Conversion / leakage
- **Result:** **PASS** — 16/16 converted (2,841 frames, stride 12); `artifacts_all_complete=True`; `leakage_clean=True` (episode- and family-disjoint); single fixed goal `h2_weave_J`.
- **Evidence:** `h6_dataset_readiness.json`, `h6_conversion_leakage_report.json`, `h6_converted_dataset_summary.json`, `h6_converted_split_counts.{json,csv}`, `h6_goal_claimboundary.json`, `h6_convert_ledger.jsonl`.
- **Decision:** dataset root `datasets/isaac_hospital_h6` built (train 10 / val 2 / test_h6hard 4).
- **Allowed next:** one diagnostic fine-tune. **Blocked:** anything on a leakage/incomplete failure (would have stopped here with a dataset-readiness report — did not trigger).

### Gate 6 — Diagnostic training
- **Result:** PASS — weights-only init from H1 (fresh optimizer confirmed in log), best val action loss **0.0685**, select-on-val.
- **Evidence:** `logs/h6_train.log`, `configs/gnm/gnm_h6_hard_families.yaml`, `checkpoints/h6_hard_families_finetune/best.pt`.
- **Decision:** produce a single diagnostic checkpoint; no promotion.
- **Allowed next:** evaluation. **Blocked:** promotion, SOTA/real-robot/goal-conditioning claims.

### Gate 7 — Evaluation
- **Result:** 12/12 complete (H1/H5/H6 × test_h4/test_h6hard/test_prior/test_combined), `--data-root` forced on every call.
- **Evidence:** `h6_eval_matrix.{json,csv}`, 12× `h6_eval_*.json`, `h6_per_family_failure_table.{json,csv}`.
- **Decision:** record the full comparison including the negative hard-held-out result.
- **Allowed next:** governance. **Blocked:** promotion.

### Gate 8 — DriftGuard / VerdictPlane governance
- **Result:** DriftGuard dual-guard `net_gate=promote` — **but the hard-held-out improvement guard passes only on an SR tie at 0 + NE gain, not a success gain**; VerdictPlane `verdict=deny`.
- **Evidence:** `h6_driftguard_decision.json`, `h6_verdictplane_record.json`, `h6_{candidate,incumbent,h5_reference}_card.json`.
- **Decision:** administratively block promotion regardless of the computed gate; stamp `DIAGNOSTIC_ONLY_NOT_PROMOTED`.
- **Allowed next:** diagnostic archival + professor report. **Blocked:** promotion (deny).
- *Note:* the governance uses the same **inline** DriftGuard/VerdictPlane run-card contract H4/H5 used; the external `/home/favl/driftguard` and `/home/favl/verdictplane` repos are **not** invoked (consistent with H4/H5).

### Gate 9 — Final adjudication
- **Result:** `DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent H1 retained, H6 retained as diagnostic evidence.
- **Evidence:** `h6_adjudication.json`, `h6_professor_report.md`, `h6_paper_trail.md`.
- **Decision:** accept H6 as diagnostic; do not promote. Coverage hypothesis refined, not confirmed.
- **Allowed next:** paper-trail review, then (only on approval) a narrow H6-scoped commit. **Blocked:** commit / push / promote / tag until the paper trail is reviewed.
