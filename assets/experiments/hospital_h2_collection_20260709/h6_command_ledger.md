# H6 — Command Ledger

Major commands / wrapper scripts actually run, with the interpreter each requires.
Three interpreters are involved (this is a real gotcha, recorded for repro):

- **Isaac / recording** — `~/miniforge3/envs/isaac/bin/python` (Isaac Sim 5.1, torch 2.7+cu128) + `source /opt/ros/humble/setup.bash`
- **Conversion** — `/usr/bin/python3.10` + `source /opt/ros/humble/setup.bash` (ROS 2 Humble ABI; numpy 2.x writes the pickles). Do **not** use `set -u` when sourcing ROS (`AMENT_TRACE_SETUP_FILES` is unbound → aborts).
- **Train / eval / governance** — `~/miniforge3/envs/gnm_train/bin/python` (torch 2.11+cu128, numpy 2.2.6 — reads the pickles; the isaac env's numpy 1.26 cannot).

All commands run from repo root `/home/favl/robotics/gnm-vlnverse-baseline`.

---

### Smoke test (per route, ~100 s)
```bash
source /opt/ros/humble/setup.bash
~/miniforge3/envs/isaac/bin/python -u scripts/robots/m3pro_ros2_bringup.py \
  --gnm-control --route-follow assets/experiments/hospital_h6_routes/h6_uturn_01.json \
  --holonomic-base --collision-report --episode --episode-name h6smoke_uturn01 \
  --goal-id h2_weave_J --steps 6000
```

### Precheck harness (light mode, no bags; 8/8)
```bash
~/miniforge3/envs/isaac/bin/python scripts/gnm/h6_precheck_verdicts.py
# single-family re-check after the chain_01 repair:
~/miniforge3/envs/isaac/bin/python scripts/gnm/h6_precheck_verdicts.py --family h6_chain_01
# -> h6_precheck_verdict_table.{json,csv}
```

### Recording harness (16 episodes, FULL mode rosbag ON, ~3.5 h)
```bash
~/miniforge3/envs/isaac/bin/python scripts/gnm/h6_record_collection.py
# gate: prechecks 8/8; per episode: timeout --signal=INT --kill-after=60 1500 ...
#   m3pro_ros2_bringup.py --gnm-control --route-follow <route> --holonomic-base
#   --collision-report --episode --episode-name h6rec_<rid>_<v> --goal-id h2_weave_J --steps 6000
# -> h6_recording_ledger.{json,csv}
```

### Collection reports (9 artifacts)
```bash
~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h6_collection_reports.py
```

### Conversion (16 episodes → GNM frames, stride 12)
```bash
bash scripts/gnm/h6_convert_all.sh          # sources ROS; loops the 16 traj dirs:
#   /usr/bin/python3.10 scripts/datasets/convert_hospital_rosbags_to_gnm.py <traj_dir> 12
# -> datasets/isaac_hospital_imagenav_v0/unassigned/h6rec_*/ ; h6_convert_ledger.jsonl
```

### Build dataset root + readiness reports
```bash
PYTHONPATH=$PWD ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/build_h6_dataset_root.py
# -> datasets/isaac_hospital_h6/{train,val,test_h6hard}; h6_dataset_readiness.json + 5 reports
```

### Diagnostic training (weights-only init from H1, fresh optimizer)
```bash
WANDB_MODE=offline PYTHONPATH=$PWD ~/miniforge3/envs/gnm_train/bin/python -u \
  scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_h6_hard_families.yaml
# -> checkpoints/h6_hard_families_finetune/{best.pt,latest.pt}  (best val action loss 0.0685)
```

### Evaluation (3 ckpts × 4 held-out sets = 12; `--data-root` forced)
```bash
WANDB_MODE=offline PYTHONPATH=$PWD ~/miniforge3/envs/gnm_train/bin/python \
  scripts/gnm/h6_evaluate_all.py         # wraps 06_evaluate.py per (model,split)
# per call: 06_evaluate.py --ckpt <ckpt> --data-root <root> --split <split> --track A ...
# -> h6_eval_matrix.{json,csv}; 12× h6_eval_{h1,h5,h6}_{set}.json
PYTHONPATH=$PWD ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h6_per_family_table.py
# -> h6_per_family_failure_table.{json,csv}   (uses --save-episodes)
```

### Governance / adjudication (DriftGuard + VerdictPlane run-card, DIAGNOSTIC_ONLY)
```bash
PYTHONPATH=$PWD ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h6_governance_adjudicate.py
# -> h6_driftguard_decision.json, h6_verdictplane_record.json,
#    h6_{candidate,incumbent,h5_reference}_card.json, h6_adjudication.json
```

### Paper-trail manifest (hashes + git intent)
```bash
~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h6_build_audit_manifest.py
# -> h6_artifact_manifest.csv, h6_artifact_manifest_sha256.txt
```
