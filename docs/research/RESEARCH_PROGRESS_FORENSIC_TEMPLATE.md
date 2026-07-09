# Research Progress Forensic Template (canonical)

Standing evidence checklist for research decks, annual reviews, weekly
updates, paper write-ups, and experiment reports. Not slide filler — a
COVERAGE CHECKLIST: every claim in any output must be traceable through
the fields below. Applies alongside the professor/reviewer research
review gate; companion structure to the Good/Bad/Ugly manuscript
sections and `docs/research/CAMERA_TASK_CONVENTIONS.md`.

## Per-claim evidence chain (all fields required)
1. **Hypothesis** — what we believed before the experiment, stated
   before results existed (pre-registered where possible).
2. **Setup** — data, split, scenes, camera convention, model, seed,
   config, commands; exact enough to re-run.
3. **Result** — raw numbers with n, from result JSONs (never retyped
   from memory); one-shot held-out evaluations labelled as such.
4. **Interpretation** — what the numbers mean, separated from the
   numbers; saturated or low-n metrics treated cautiously and said so.
5. **Failures / challenges** — what broke, stalled, or misled during
   the work (recorded as degradation/incident events where applicable).
6. **Limitation** — what cannot be claimed from this evidence.
7. **Decision** — keep / reject / promote / human_review, with the
   pre-registered rule that produced it.
8. **Mitigation** — what changed to control the failure or gap.
9. **Next evidence gate** — the exact next experiment and its
   acceptance condition.

## Standing cross-checks before any output is final
- Claim boundaries present (not full benchmark; not real-robot unless
  physical; CR only from Isaac PhysX contact evidence; no superiority
  claims over GNM/ViNT/NoMaD without matched protocol).
- Camera/task regime named per CAMERA_TASK_CONVENTIONS.md; no
  top-down/front-RGB mixing without a declared adaptation experiment.
- Split integrity: route/goal/scene-level only; no frame-level splits;
  held-out sets untouched before their single evaluation.
- Data roles separated: competent vs imperfect/failure trajectories;
  `recording_integrity` and `training_eligible` columns present in
  dataset tables; partial recordings excluded or re-recorded, never
  silently included.
- Governance evidence attached where a promotion decision exists
  (DriftGuard decision, VerdictPlane record, Sentinel incidents).
- Provenance: commit hash, checkpoint SHA-256, W&B run, validator
  outputs, artifact hygiene (no heavy binaries tracked).
- Negative results reported with the same prominence as positive ones.
