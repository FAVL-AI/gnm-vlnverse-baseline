# Paper Claim-to-Evidence Map

Every quantitative claim in the ICRA paper maps to a specific evidence file.
A claim without an evidence file is not permitted in the paper.

## Main result table

| Paper claim | Recomputed value | Evidence file | Verifier script | Status |
|---|---|---|---|---|
| Baseline GNM SR = 20.0% | 3/15 = 20.0% | `results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv` | `verify_tracka_all_methods_metric_provenance.py` | **PASS** |
| Baseline GNM OSR = 46.7% | 7/15 = 46.7% | same | same | **PASS** |
| Baseline GNM NE = 6.51 m | 6.51 m | same | same | **PASS** |
| Hand-tuned waypoint gate SR = 26.7% | 4/15 = 26.7% | same | same | **PASS** |
| Hand-tuned waypoint gate OSR = 26.7% | 4/15 = 26.7% | same | same | **PASS** |
| Hand-tuned waypoint gate NE = 5.34 m | 5.34 m | same | same | **PASS** |
| Logistic stop head SR = 20.0% | 3/15 = 20.0% | same | same | **PASS** |
| Logistic stop head OSR = 46.7% | 7/15 = 46.7% | same | same | **PASS** |
| Logistic stop head NE = 6.51 m | 6.51 m | same | same | **PASS** |
| Temporal neural stop head SR = 33.3% | 5/15 = 33.3% | same | same | **PASS** |
| Temporal neural stop head OSR = 33.3% | 5/15 = 33.3% | same | same | **PASS** |
| Temporal neural stop head NE = 4.47 m | 4.47 m | same | same | **PASS** |
| Geometry-aware oracle SR = 46.7% | 7/15 = 46.7% | same | same | **PASS** |
| Geometry-aware oracle OSR = 46.7% | 7/15 = 46.7% | same | same | **PASS** |
| Geometry-aware oracle NE = 3.79 m | 3.79 m | same | same | **PASS** |

## Dataset claims

| Paper claim | Evidence file | Status |
|---|---|---|
| 15 validation episodes | `results/research_audit/tracka_validation_split_lock.json` | **PASS** |
| 238 training trajectories | `results/dataset_manifest.md` | REPORTED |
| 4 Kujiale scenes | `results/scene_manifest.md` | REPORTED |
| Success radius = 3.0 m | `results/research_audit/tracka_validation_split_lock.json` | **PASS** |

## Methodological claims

| Paper claim | Evidence file | Status |
|---|---|---|
| Temporal stop head uses only runtime GNM signals | `results/research_audit/stop_policy_feature_audit.md` | **PASS** |
| Temporal stop head does not use oracle goal geometry | `results/research_audit/stop_policy_feature_audit.md` | **PASS** |
| Geometry-aware oracle is diagnostic upper bound only | `results/research_audit/stop_policy_feature_audit.md` | **PASS** |
| All methods evaluated on the same 15 episodes | `results/research_audit/tracka_validation_split_lock.json` | **PASS** |
| SR–OSR gap proves stopping failure (not path failure) | `results/research_audit/tracka_all_methods_metric_provenance_report.md` | **PASS** |

## Blocked claims (must not appear in paper)

| Claim | Reason blocked | Evidence ledger |
|---|---|---|
| Yahboom episode_001 rosbag2 recorded | No rosbag2 file exists | `results/research_audit/research_claim_validation_ledger.md` |
| Yahboom data converted to GNM format | No conversion output | same |
| GNM fine-tuned on Yahboom data | No fine-tuning checkpoint | same |
| FleetSafe-GNM closed-loop physical deployment | No physical robot evidence | same |
| Track B language-grounding completed | No Track B eval results | same |
| Global superiority over GNM, ViNT, NoMaD, SaferPath | No matched comparative benchmark | same |

## How to regenerate all provenance

```bash
python3 scripts/gnm/generate_all_methods_provenance.py
python3 scripts/gnm/verify_tracka_all_methods_metric_provenance.py
python3 scripts/gnm/verify_tracka_metric_provenance.py
python3 scripts/gnm/check_research_claim_gates.py
```

Or use the single pack script:

```bash
bash scripts/gnm/run_tracka_metric_provenance_pack.sh
```
