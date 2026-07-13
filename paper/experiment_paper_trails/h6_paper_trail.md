# H6 — Hard-Route-Family Coverage Diagnostic (Paper-Trail Manuscript)

**Frank Asante Van Laarhoven** · Isaac-Hospital-ImageNav-v0 (internal simulation) ·
branch `h23-execfix` · status **`DIAGNOSTIC_ONLY_NOT_PROMOTED`**.

> Manuscript-level face of the H6 paper trail, registered alongside the other
> manuscripts in `paper/`. The **canonical, hash-verified package** is
> `assets/experiments/hospital_h2_collection_20260709/h6_paper_trail.md` and its 7
> companion files — this wrapper points to it and does not duplicate the data.

## Abstract
H6 tests whether adding *clean hard-route families* (uturn/chain/ftL/sharpmulti/
tightcorr) to **training** fixes the failure mode H5 exposed: no success on hard
held-out route families. Sixteen scripted-expert demonstrations were recorded
(16/16 clean, 0 collisions, leakage-clean), converted, and used to fine-tune a
MobileNetV2-GNM diagnostically (weights-only init from the retained H1 incumbent,
fresh optimizer, selection on a compound-turn validation split). Three checkpoints
(H1, H5, H6) were evaluated on four held-out sets. **Result:** H6 attains the best
combined SR (0.25) and nDTW, preserves the H4 held-out gain, and removes H5's
prior-family regression — **but no model reaches SR>0 or OSR>0 on the fresh hard
held-out families.** The coverage hypothesis is **refined, not confirmed**.
Governance denies promotion (`DIAGNOSTIC_ONLY_NOT_PROMOTED`); H1 retained.

## Claim boundary (hard limits)
Fixed placeholder goal ⇒ **not goal-conditioning evidence**; scripted-expert;
simulation-only; offline Track-A; small n (4/6/12); one seed; deterministic a/b
variants; not real-robot; not a public benchmark; **not promoted**; no SOTA claim.

## Canonical package (verify + read there)
`assets/experiments/hospital_h2_collection_20260709/`:
- `h6_paper_trail.md` — full timeline / gates / inputs / outputs / results
- `h6_decision_log.md` — 9 gates, pass/fail, unlocked/blocked
- `h6_git_diff_summary.md` — commit boundary + excluded files
- `h6_command_ledger.md` — exact commands / interpreters
- `h6_claim_boundary.md` — canonical limitations
- `h6_repro_commands.md` — verify hashes / re-run eval / regenerate report
- `h6_artifact_manifest.csv` + `h6_artifact_manifest_sha256.txt` — file hashes
- `h6_professor_report.md` — professor-facing writeup

Verify integrity from repo root:
```bash
sha256sum -c assets/experiments/hospital_h2_collection_20260709/h6_artifact_manifest_sha256.txt
```
