#!/usr/bin/env python3
"""
Research claim gate checker.

This script separates validated claims from blocked claims. It prevents the repo
from accidentally claiming Yahboom rosbag conversion, real robot deployment,
Track B completion, or global superiority before the required evidence exists.
"""

from __future__ import annotations

import json
from pathlib import Path


CLAIMS = [
    {
        "id": "tracka_aggregate_results_reported",
        "claim": "Track A aggregate stop-policy results are reported.",
        "required_files": [
            "README.md",
            "results/ablations.md",
            "results/eval_episode_breakdown_tracka.md",
        ],
        "status_if_present": "reported",
        "notes": "Aggregate results exist. Full per-episode provenance must also pass for audit-ready status.",
    },
    {
        "id": "tracka_per_episode_provenance",
        "claim": "Full per-episode provenance CSV exists for Track A methods.",
        "required_files": [
            "results/research_audit/tracka_per_episode_metric_provenance.csv",
            "results/research_audit/tracka_metric_provenance_report.json",
        ],
        "status_if_present": "validated_if_report_passes",
        "notes": "Must be generated from evaluator output, not manually invented.",
    },
    {
        "id": "yahboom_episode_001_rosbag2",
        "claim": "A valid Yahboom episode_001 rosbag2 recording exists.",
        "required_files": [
            "datasets/gnm_fleetsafe_rosbags/episode_001/episode_metadata.json",
            "results/gnm_fleetsafe_v2_4/episode_001_validation.json",
        ],
        "status_if_present": "candidate_requires_json_pass",
        "notes": "The validation JSON must confirm all five canonical topics have message_count > 0 and duration >= 30s.",
    },
    {
        "id": "yahboom_rosbag_to_gnm_conversion",
        "claim": "Yahboom rosbag2 has been converted to GNM dataset format.",
        "required_files": [
            "datasets/gnm_fleetsafe_converted/episode_001/manifest.json",
            "results/gnm_fleetsafe_v2_5/conversion_report.json",
        ],
        "status_if_present": "candidate_requires_json_pass",
        "notes": "Only valid after episode_001 rosbag2 validation passes.",
    },
    {
        "id": "gnm_finetune_on_yahboom",
        "claim": "GNM has been fine-tuned on validated Yahboom data.",
        "required_files": [
            "results/gnm_fleetsafe_v2_6/yahboom_finetune_report.json",
            "models/yahboom_finetuned_gnm/manifest.json",
        ],
        "status_if_present": "candidate_requires_training_report",
        "notes": "Requires converted dataset, training command, checkpoint, and held-out evaluation.",
    },
    {
        "id": "fleetsafe_gnm_closed_loop_physical",
        "claim": "FleetSafe-GNM closed-loop deployment has been validated on the physical Yahboom robot.",
        "required_files": [
            "results/physical_yahboom/fleetsafe_closed_loop_certificate.json",
            "results/physical_yahboom/episode_summary.json",
        ],
        "status_if_present": "candidate_requires_safety_certificate",
        "notes": "Requires real robot evidence, safety certificate, and no dry-run-only claim.",
    },
    {
        "id": "trackb_language_grounding_completed",
        "claim": "Track B language-grounding results are complete.",
        "required_files": [
            "results/track_b_language_grounding/eval_summary.json",
            "results/track_b_language_grounding/per_episode_language_grounding.csv",
        ],
        "status_if_present": "candidate_requires_trackb_eval",
        "notes": "Requires held-out language-grounding evaluation, not only prepared gates.",
    },
    {
        "id": "global_superiority_over_gnm_vint_nomad_saferpath",
        "claim": "Global superiority over GNM, ViNT, NoMaD, or SaferPath is proven.",
        "required_files": [
            "results/comparative_benchmark_gnm_vint_nomad_saferpath/protocol.md",
            "results/comparative_benchmark_gnm_vint_nomad_saferpath/per_episode_results.csv",
            "results/comparative_benchmark_gnm_vint_nomad_saferpath/statistical_report.json",
        ],
        "status_if_present": "candidate_requires_statistical_benchmark",
        "notes": "Do not claim this unless matched baselines, identical splits/seeds, enough episodes, and statistical tests exist.",
    },
]


def file_exists(path: str) -> bool:
    return Path(path).exists()


def main() -> int:
    out_dir = Path("results/research_audit")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    any_blocked = False

    for item in CLAIMS:
        missing = [p for p in item["required_files"] if not file_exists(p)]
        if missing:
            status = "BLOCKED"
            any_blocked = True
        else:
            status = item["status_if_present"].upper()

        rows.append(
            {
                "id": item["id"],
                "claim": item["claim"],
                "status": status,
                "missing": missing,
                "notes": item["notes"],
            }
        )

    md = [
        "# Research Claim Validation Ledger",
        "",
        "This file separates validated claims from blocked claims.",
        "",
        "| Claim ID | Status | Claim | Missing evidence | Notes |",
        "|---|---|---|---|---|",
    ]

    for row in rows:
        missing = "<br>".join(row["missing"]) if row["missing"] else "None"
        md.append(
            f"| `{row['id']}` | **{row['status']}** | {row['claim']} | {missing} | {row['notes']} |"
        )

    md.append("")
    md.append("## Rule")
    md.append("")
    md.append(
        "A blocked claim must not be used in the paper, README, release notes, slides, or abstract as completed evidence."
    )

    (out_dir / "research_claim_validation_ledger.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8"
    )
    (out_dir / "research_claim_validation_ledger.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )

    print("[OK] Wrote results/research_audit/research_claim_validation_ledger.md")
    print("[OK] Wrote results/research_audit/research_claim_validation_ledger.json")

    if any_blocked:
        print("[INFO] Some claims are blocked. This is expected until evidence exists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
