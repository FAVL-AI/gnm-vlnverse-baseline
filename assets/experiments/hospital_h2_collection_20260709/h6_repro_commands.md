# H6 — Reproduction & Verification Commands

Run from repo root `/home/favl/robotics/gnm-vlnverse-baseline`.
`GT=~/miniforge3/envs/gnm_train/bin/python`.

---

## 1. Verify artifact hashes (run from repo root — paths are repo-root-relative)
```bash
sha256sum -c assets/experiments/hospital_h2_collection_20260709/h6_artifact_manifest_sha256.txt
# every git=yes evidence file must say "OK" (75 files, 0 failed)
```

## 2. Check dataset counts (splits + leakage)
```bash
for s in train val test_h6hard; do
  echo "$s: $(ls -1 datasets/isaac_hospital_h6/$s | wc -l)"; done   # expect 10 / 2 / 4
$GT -c "import json;d=json.load(open('datasets/isaac_hospital_h6/split_manifest.json'));print(d['counts'])"
$GT -c "import json;print('leakage_clean=',json.load(open('assets/experiments/hospital_h2_collection_20260709/h6_conversion_leakage_report.json'))['leakage_clean'])"
# raw collection: expect 16 RECORDED_OK
$GT -c "import json;r=json.load(open('assets/experiments/hospital_h2_collection_20260709/h6_recording_ledger.json'));print('RECORDED_OK',sum(x['status']=='RECORDED_OK' for x in r),'/',len(r))"
```

## 3. Re-run evaluation from the saved checkpoints (no retraining)
```bash
WANDB_MODE=offline PYTHONPATH=$PWD $GT scripts/gnm/h6_evaluate_all.py
WANDB_MODE=offline PYTHONPATH=$PWD $GT scripts/gnm/h6_per_family_table.py
# then re-adjudicate:
PYTHONPATH=$PWD $GT scripts/gnm/h6_governance_adjudicate.py
# checkpoints used (must exist):
#   checkpoints/hospital_front_rgb_finetune/best.pt   (H1 incumbent)
#   checkpoints/h5_mixed_replay_finetune/best.pt      (H5 reference)
#   checkpoints/h6_hard_families_finetune/best.pt     (H6 diagnostic)
```

## 4. Regenerate the professor report inputs
```bash
# the report h6_professor_report.md is written from h6_eval_matrix.json +
# h6_per_family_failure_table.json; regenerate those two, then diff the numbers:
$GT -c "import json;m=json.load(open('assets/experiments/hospital_h2_collection_20260709/h6_eval_matrix.json'));\
print('h6 combined SR',m['h6']['test_combined']['SR'],'| h6hard OSR',m['h6']['test_h6hard']['OSR'])"
# expect: h6 combined SR 0.25 | h6hard OSR 0.0
```

## 5. Re-fine-tune from scratch (optional; reproduces best.pt bit-for-bit only if env matches)
```bash
rm -rf checkpoints/h6_hard_families_finetune          # ensure no latest.pt (else it resumes)
WANDB_MODE=offline PYTHONPATH=$PWD $GT scripts/gnm/04_train_gnm.py \
  --cfg configs/gnm/gnm_h6_hard_families.yaml         # seed 42, init from H1
```

## 6. Verify NO unrelated files enter a future commit
```bash
# the intended H6 commit set — nothing else:
git add -n -- \
  scripts/gnm/execution_feasibility_decider.py \
  scripts/datasets/hospital_h6_generate_hard_routes.py \
  assets/experiments/hospital_h6_routes/h6_chain_01.json \
  assets/experiments/hospital_h6_routes/rejected/h6_chain_01__rejected.json \
  assets/experiments/hospital_h2_collection_20260709/h6_route_family_approval_table.csv \
  scripts/gnm/h6_precheck_verdicts.py scripts/gnm/h6_record_collection.py \
  scripts/gnm/h6_collection_reports.py scripts/gnm/h6_convert_all.sh \
  scripts/gnm/build_h6_dataset_root.py scripts/gnm/h6_evaluate_all.py \
  scripts/gnm/h6_governance_adjudicate.py scripts/gnm/h6_per_family_table.py \
  scripts/gnm/h6_build_audit_manifest.py configs/gnm/gnm_h6_hard_families.yaml \
  assets/experiments/hospital_h2_collection_20260709/h6_*.json \
  assets/experiments/hospital_h2_collection_20260709/h6_*.csv \
  assets/experiments/hospital_h2_collection_20260709/h6_*.md \
  assets/experiments/hospital_h2_collection_20260709/h6_*.txt \
  assets/experiments/hospital_h2_collection_20260709/h6_*.jsonl

# assert the 5 unrelated tracked-modified files are NOT staged:
for f in scripts/datasets/convert_hospital_rosbags_to_gnm.py scripts/gnm/06_evaluate.py \
         scripts/datasets/hospital_navgen_sample_routes.py \
         assets/experiments/hospital_h2_collection_20260709/collection_discipline_notes.md \
         assets/experiments/hospital_h2_collection_20260709/runtime_degradation_events.json; do
  git diff --cached --name-only | grep -qx "$f" && echo "LEAK: $f staged!" || echo "ok excluded: $f"
done

# assert no large binaries staged:
git diff --cached --name-only | grep -E 'rosbags/|/trajectories/|isaac_hospital_h6/|isaac_hospital_imagenav_v0/|checkpoints/|\.db3$|\.pt$|\.jpg$|\.png$' \
  && echo "LEAK: large artifact staged!" || echo "ok: no large artifacts staged"
```
> `git add -n` is a **dry run** (prints what would be added, stages nothing). Do the
> real `git add` only after Frank approves the paper trail.
