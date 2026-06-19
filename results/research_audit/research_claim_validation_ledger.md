# Research Claim Validation Ledger

This file separates validated claims from blocked claims.

| Claim ID | Status | Claim | Missing evidence | Notes |
|---|---|---|---|---|
| `tracka_aggregate_results_reported` | **REPORTED** | Track A aggregate stop-policy results are reported. | None | Aggregate results exist. Full per-episode provenance must also pass for audit-ready status. |
| `tracka_baseline_per_episode_provenance` | **VALIDATED_IF_REPORT_PASSES** | Baseline GNM per-episode provenance exists and regenerates SR, OSR, and NE. | None | Currently validates baseline_gnm from 15 per-episode rows. All-method provenance is tracked separately. |
| `tracka_all_methods_per_episode_provenance` | **VALIDATED_IF_REPORT_PASSES** | Per-episode provenance exists for all Track A stop-policy methods. | None | Must include baseline_gnm, hand_tuned_waypoint_gate, logistic_stop_head, temporal_neural_stop_head, and geometry_aware_oracle. |
| `tracka_validation_split_locked` | **VALIDATED** | The 15-episode Track A validation split is locked so all methods use the same episodes. | None | Split lock records the canonical 15 episode IDs and success radius. |
| `stop_policy_feature_audit_complete` | **VALIDATED** | A feature audit confirms which stop-policy methods use oracle geometry and which are deployable. | None | Audit must cover all five methods and confirm temporal stop head does not use oracle geometry. |
| `paper_claim_to_evidence_map_complete` | **VALIDATED** | Every quantitative paper claim maps to a specific evidence file. | None | Map must list source file and verifier script for every table entry. |
| `tracka_per_scene_breakdown_complete` | **VALIDATED** | Per-scene SR/OSR/NE breakdown exists for all 5 Track A methods across all 4 Kujiale scenes. | None | 20-row CSV (5 methods × 4 scenes). Used for robustness inspection; per-scene CIs are wide for n ≤ 3. |
| `tracka_paired_comparison_complete` | **VALIDATED** | Paired Wilcoxon signed-rank and sign test comparing baseline_gnm vs temporal_neural_stop_head on 15 val episodes. | None | Wilcoxon T+=95, p≈0.047. Sign test p=0.119. Small-sample caution stated. |
| `tracka_robustness_summary_complete` | **VALIDATED** | A robustness summary documents data availability, per-scene findings, paired comparison, and honest claim boundaries. | None | Summary explicitly states no additional held-out data exists and documents train-split contamination reason. |
| `tracka_expanded_253ep_provenance_complete` | **VALIDATED** | Expanded 253-episode provenance for baseline_gnm and geometry_aware_oracle across all 4 Kujiale scenes with CI report. | None | 506-row CSV (253 ep × 2 methods). Only baseline and oracle expanded; waypoint/logistic/temporal remain at 15-ep val. Stopping-gap confirmed at N=253: baseline OSR−SR = 13 pp, CI width narrows from ±20 pp (val) to ±6 pp (expanded). |
| `yahboom_episode_001_rosbag2` | **BLOCKED** | A valid Yahboom episode_001 rosbag2 recording exists. | datasets/gnm_fleetsafe_rosbags/episode_001/episode_metadata.json<br>results/gnm_fleetsafe_v2_4/episode_001_validation.json | The validation JSON must confirm all five canonical topics have message_count > 0 and duration >= 30s. |
| `yahboom_rosbag_to_gnm_conversion` | **BLOCKED** | Yahboom rosbag2 has been converted to GNM dataset format. | datasets/gnm_fleetsafe_converted/episode_001/manifest.json<br>results/gnm_fleetsafe_v2_5/conversion_report.json | Only valid after episode_001 rosbag2 validation passes. |
| `gnm_finetune_on_yahboom` | **BLOCKED** | GNM has been fine-tuned on validated Yahboom data. | results/gnm_fleetsafe_v2_6/yahboom_finetune_report.json<br>models/yahboom_finetuned_gnm/manifest.json | Requires converted dataset, training command, checkpoint, and held-out evaluation. |
| `fleetsafe_gnm_closed_loop_physical` | **BLOCKED** | FleetSafe-GNM closed-loop deployment has been validated on the physical Yahboom robot. | results/physical_yahboom/fleetsafe_closed_loop_certificate.json<br>results/physical_yahboom/episode_summary.json | Requires real robot evidence, safety certificate, and no dry-run-only claim. |
| `trackb_language_grounding_completed` | **BLOCKED** | Track B language-grounding results are complete. | results/track_b_language_grounding/eval_summary.json<br>results/track_b_language_grounding/per_episode_language_grounding.csv | Requires held-out language-grounding evaluation, not only prepared gates. |
| `global_superiority_over_gnm_vint_nomad_saferpath` | **BLOCKED** | Global superiority over GNM, ViNT, NoMaD, or SaferPath is proven. | results/comparative_benchmark_gnm_vint_nomad_saferpath/protocol.md<br>results/comparative_benchmark_gnm_vint_nomad_saferpath/per_episode_results.csv<br>results/comparative_benchmark_gnm_vint_nomad_saferpath/statistical_report.json | Do not claim this unless matched baselines, identical splits/seeds, enough episodes, and statistical tests exist. |

## Rule

A blocked claim must not be used in the paper, README, release notes, slides, or abstract as completed evidence.
