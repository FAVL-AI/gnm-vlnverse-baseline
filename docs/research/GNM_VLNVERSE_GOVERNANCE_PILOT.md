# GNM-VLNVerse Embodied-AI Governance Pilot

This pilot uses GNM-VLNVerse as a real embodied-AI workload to test
model promotion, incident localization, action governance, and MLOps
evidence tracking. It is not a full VLNVerse benchmark submission.

## Architecture (external JSON bridges only — repos are never merged)

    gnm-vlnverse-baseline (this repo)
        exports: assets/experiments/mlops_cards/*.json
                 (scripts/gnm/export_mlops_run_card.py — summaries,
                  hashes, paths, gates, claim boundaries only)

    mlops-production-pipeline          — evidence display
        src/mlops_pipeline/external_runs.py + tools/render_external_runs.py
        renders run identity, split, metrics, gates, lineage, claims
        (5 schema/claim-gate unit tests)

    DriftGuardAI                       — promotion judge
        examples/gnm_vlnverse_promotion_gate.py
        rule: promote only if SR and SPL improve or match and NE does
        not materially worsen on the SAME scene-held-out test;
        numeric offline CR = invalid provenance

    Sentinel-AIOPs                     — incident localization
        engine/examples/gnm_vlnverse_incident_adapter.py
        typed ActionProposals: leakage, CUDA loss, missing W&B,
        broken lineage, CR misuse, generalization regression

    VerdictPlane                       — action governance
        policies/gnm_vlnverse_model_promotion.yaml
        policies/gnm_vlnverse_live_isaac.yaml
        default-deny; robot deployment and publication require a human

## Measured pilot result (2026-07-08, real run cards)

| Stage | Tool | Outcome |
|---|---|---|
| Run cards | exporter | baseline SR 0.32 / EMA 0.999 SR 0.18 on kujiale_0271 (n=50), all gates PASS |
| Display | mlops dashboard | 2 cards rendered; schema tests 5/5 |
| Promotion | DriftGuard | **candidate rejected** (SR/SPL regressed, NE worsened) |
| Incidents | Sentinel | 1 incident: scene_holdout_generalization_failure ("recovery is not safety") |
| Governance | VerdictPlane | promote→deny, publish→require_human, isaac smoke→allow, robot→require_human |

The governance verdicts reproduce the pre-registered scientific decision
from the research pipeline, produced independently by the startup stack
from exported evidence alone. Checkpoints, rosbags, W&B raw directories
and videos never leave this repository.
