# H6 — Git Diff Summary & Proposed Commit Boundary

**Branch:** `h23-execfix` · **base commit:** `024033b` · **repo tree state at audit:**
9 tracked-modified + 321 untracked (the vast majority are unrelated pre-existing
H2/H4/H5/H21 artifacts). **Nothing is staged. Nothing will be committed until the
paper trail is approved.**

---

## 1. H6-scoped MODIFIED (tracked) — belong in the commit
| File | +add | −del | Why |
|---|---|---|---|
| `scripts/gnm/execution_feasibility_decider.py` | 28 | 6 | `check_xy_bound` + `REJECT_XY_BOUND` (±6 m runtime control-authority bound) |
| `scripts/datasets/hospital_h6_generate_hard_routes.py` | 86 | 25 | enforce XY bound in `place()`; preserve valid routes + re-author only broken ones; emit rejected evidence |
| `assets/experiments/hospital_h6_routes/h6_chain_01.json` | 17 | 17 | repaired route, in-bounds (x∈[−3.5, 0.5]) |
| `assets/experiments/hospital_h2_collection_20260709/h6_route_family_approval_table.csv` | 9 | 9 | added `xy_bound_feasibility` column + repaired-route row |

## 2. H6-scoped NEW (untracked) — belong in the commit
**Code / config (13):**
`scripts/gnm/h6_precheck_verdicts.py`, `h6_record_collection.py`,
`h6_collection_reports.py`, `h6_convert_all.sh`, `build_h6_dataset_root.py`,
`h6_evaluate_all.py`, `h6_governance_adjudicate.py`, `h6_per_family_table.py`,
`h6_build_audit_manifest.py`; `configs/gnm/gnm_h6_hard_families.yaml`;
`assets/experiments/hospital_h6_routes/rejected/h6_chain_01__rejected.json`;
`paper/experiment_paper_trails/README.md`, `paper/experiment_paper_trails/h6_paper_trail.md`
(manuscript-level registration alongside the other `paper/` manuscripts).

**Evidence (small JSON/CSV/MD/txt/jsonl, under `…/hospital_h2_collection_20260709/`):**
all `h6_*` reports, ledgers, eval matrix + 12 eval JSONs, per-family table,
governance decision/record/cards, adjudication, professor report, and this
paper-trail package (`h6_paper_trail.md`, `h6_decision_log.md`,
`h6_git_diff_summary.md`, `h6_command_ledger.md`, `h6_claim_boundary.md`,
`h6_repro_commands.md`, `h6_artifact_manifest.csv`, `h6_artifact_manifest_sha256.txt`).
Exact per-file list + hashes in `h6_artifact_manifest.csv`.

*Already committed at `024033b` (baseline, not part of this commit):* `h6_plan.md`,
`h6_coverage_table.csv`, and the 7 unchanged H6 route files.

## 3. UNRELATED dirty files — MUST be excluded
**Tracked-modified (5) — used but not H6-owned, or unrelated pre-existing:**
| File | Note |
|---|---|
| `scripts/datasets/convert_hospital_rosbags_to_gnm.py` | ≤Jul-11 checksum self-exclude fix; **used** for conversion, not H6-owned |
| `scripts/gnm/06_evaluate.py` | Jul-11 `--data-root` methodology lock; **used** for eval, not H6-owned |
| `scripts/datasets/hospital_navgen_sample_routes.py` | unrelated |
| `assets/experiments/hospital_h2_collection_20260709/collection_discipline_notes.md` | +33 lines, no H6 marker; **ambiguous → excluded** pending Frank's classification |
| `assets/experiments/hospital_h2_collection_20260709/runtime_degradation_events.json` | +21 lines, no H6 marker; **ambiguous → excluded** |

**Untracked (unrelated):** all H2/H4/H5/H21 artifacts and scripts — e.g.
`build_h4_dataset_root.py`, `build_h5_split_manifest.py`,
`h4/h5_governance_adjudicate.py`, `assets/experiments/goals/*`,
`assets/experiments/hospital_h22_routes/*`, `assets/experiments/data_expansion/*`,
`h4_*`/`h5_*` evidence, `execfix_val_*`/`h21_*` trajectories, and the raw
`assets/experiments/rosbags/` / `assets/experiments/trajectories/` non-`h6rec_*`
contents. None enter the H6 commit.

## 4. Large H6 artifacts — NOT for git (local + pCloud cold-storage candidates)
| Artifact | Size | Reason |
|---|---|---|
| `assets/experiments/rosbags/h6rec_*` (16) | 30 GB | raw sensor recording |
| `assets/experiments/trajectories/h6rec_*` (16) | 205 MB | raw per-step trajectory |
| `datasets/isaac_hospital_imagenav_v0/unassigned/h6rec_*` (16) | 38 MB | converted image frames |
| `datasets/isaac_hospital_h6/` | 38 MB | built dataset root (copy of the above) |
| `checkpoints/h6_hard_families_finetune/` | 149 MB | model weights (best.pt + latest.pt) |
| `logs/h6_*.log` (8) | small | run logs |

## 5. Proposed future commit boundary (narrow, H6-scoped)
```
# tracked-modified (4)
scripts/gnm/execution_feasibility_decider.py
scripts/datasets/hospital_h6_generate_hard_routes.py
assets/experiments/hospital_h6_routes/h6_chain_01.json
assets/experiments/hospital_h2_collection_20260709/h6_route_family_approval_table.csv
# new code/config (11)
scripts/gnm/h6_precheck_verdicts.py
scripts/gnm/h6_record_collection.py
scripts/gnm/h6_collection_reports.py
scripts/gnm/h6_convert_all.sh
scripts/gnm/build_h6_dataset_root.py
scripts/gnm/h6_evaluate_all.py
scripts/gnm/h6_governance_adjudicate.py
scripts/gnm/h6_per_family_table.py
scripts/gnm/h6_build_audit_manifest.py
configs/gnm/gnm_h6_hard_families.yaml
assets/experiments/hospital_h6_routes/rejected/h6_chain_01__rejected.json
# new evidence (all h6_* under the collection dir; see manifest git=yes rows)
assets/experiments/hospital_h2_collection_20260709/h6_*.{json,csv,md,txt,jsonl}
```
**Excluded from commit:** the 5 unrelated tracked-modified files, all unrelated
untracked artifacts, and every large binary artifact in §4. Attribution: commit
shows Frank Asante Van Laarhoven only; no co-author/vendor/AI trailers.
