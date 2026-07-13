# Experiment Paper Trails

Audit/paper-trail manuscripts for the hospital-navigation experiment line, kept
**alongside the other manuscripts** in `paper/`. Each paper trail proves its result
came from a controlled sequence of gates, not a loose run. The canonical evidence
lives under `assets/experiments/…`; the files here are the manuscript-level face and
index (no large data is duplicated).

## Manuscripts in this repo (context)
- `paper/fleetsafe_paper.tex`
- `paper/annual_review_2026.tex`
- `paper/icra_metric_provenance_stopping/` (main.tex + README)
- `paper/showcase/`
- `docs/paper/FleetSafe_VLN_Paper_Draft.md`
- `results/unified_benchmark_paper/unified_report.md`

## Experiment paper trails
| Experiment | Status | Manuscript face | Canonical package |
|---|---|---|---|
| **H6** hard-route-family coverage diagnostic | `DIAGNOSTIC_ONLY_NOT_PROMOTED` | [`h6_paper_trail.md`](h6_paper_trail.md) | `assets/experiments/hospital_h2_collection_20260709/h6_paper_trail.md` (+ 7 companion files) |
| H5 mixed-family replay | HOLD, not promoted (prior) | — | `assets/experiments/hospital_h2_collection_20260709/h5_*` |
| H4 NavGen diversity | positive diagnostic, not promoted (prior) | — | `assets/experiments/hospital_h2_collection_20260709/h4_*` |

## H6 canonical package (source of truth)
Under `assets/experiments/hospital_h2_collection_20260709/`:
`h6_paper_trail.md`, `h6_decision_log.md`, `h6_git_diff_summary.md`,
`h6_command_ledger.md`, `h6_claim_boundary.md`, `h6_repro_commands.md`,
`h6_artifact_manifest.csv`, `h6_artifact_manifest_sha256.txt` — plus the
professor report `h6_professor_report.md`, eval matrix, per-family table, governance
records, and collection reports.

> Attribution: Frank Asante Van Laarhoven only. Not committed until the paper trail
> is reviewed and approved.
