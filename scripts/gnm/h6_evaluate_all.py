#!/usr/bin/env python3
"""H6 diagnostic evaluation driver: score 3 checkpoints x 4 held-out sets = 12
offline Track-A evaluations, with --data-root FORCED on every call (methodology
lock: checkpoint-embedded data_root is ignored for cross-corpus comparison).

Models:
  h1 = retained H1 hospital incumbent (checkpoints/hospital_front_rgb_finetune)
  h5 = H5 mixed-replay diagnostic (checkpoints/h5_mixed_replay_finetune)
  h6 = H6 hard-family diagnostic  (checkpoints/h6_hard_families_finetune)

Eval sets (all preserved / held-out; none trained on by the model that owns them):
  test_h4       datasets/isaac_hospital_h5   (H4 held-out families 008/012/016, n=6)
  test_prior    datasets/isaac_hospital_h5   (prior held-out uturn/chain/ftL, n=6)
  test_combined datasets/isaac_hospital_h5   (union, n=12)
  test_h6hard   datasets/isaac_hospital_h6   (H6 fresh hard held-out uturn_02/chain_02, n=4)

Copies each run's metrics_summary.json -> E/h6_eval_<model>_<split>.json and
writes a combined h6_eval_matrix.{json,csv}. No promotion; diagnostic only.
"""
import csv, json, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E = REPO / "assets/experiments/hospital_h2_collection_20260709"
PY = sys.executable  # run under the same (gnm_train) interpreter
EVAL = REPO / "scripts/gnm/06_evaluate.py"

MODELS = {
    "h1": "checkpoints/hospital_front_rgb_finetune/best.pt",
    "h5": "checkpoints/h5_mixed_replay_finetune/best.pt",
    "h6": "checkpoints/h6_hard_families_finetune/best.pt",
}
SPLITS = [
    ("test_h4",       "datasets/isaac_hospital_h5"),
    ("test_prior",    "datasets/isaac_hospital_h5"),
    ("test_combined", "datasets/isaac_hospital_h5"),
    ("test_h6hard",   "datasets/isaac_hospital_h6"),
]
KEYS = ["SR", "OSR", "SPL", "NE", "TL", "nDTW", "CLS", "CR", "SRn", "n_episodes"]


def run_one(model, ckpt, split, data_root):
    outdir = REPO / f"checkpoints/_h6cmp_eval/{model}__{split}"
    outdir.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(EVAL), "--ckpt", str(REPO / ckpt),
           "--data-root", str(REPO / data_root), "--split", split,
           "--track", "A", "--output-dir", str(outdir), "--device", "cuda"]
    env = {"PYTHONPATH": str(REPO)}
    import os
    env = {**os.environ, **env}
    p = subprocess.run(cmd, cwd=str(REPO), env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ms = outdir / "metrics_summary.json"
    if p.returncode != 0 or not ms.exists():
        print(f"[h6-eval] FAIL {model}/{split} rc={p.returncode}\n{p.stdout[-1500:]}")
        return None
    dst = E / f"h6_eval_{model}_{split}.json"
    shutil.copyfile(ms, dst)
    d = json.loads(ms.read_text())
    print(f"[h6-eval] {model}/{split}: SR={d.get('SR')} SPL={d.get('SPL')} "
          f"NE={d.get('NE')} nDTW={d.get('nDTW')} n={d.get('n_episodes')}")
    return d


def main():
    matrix = {}
    ok = 0
    for model, ckpt in MODELS.items():
        if not (REPO / ckpt).exists():
            print(f"[h6-eval] SKIP {model}: checkpoint missing {ckpt}")
            continue
        matrix[model] = {}
        for split, dr in SPLITS:
            d = run_one(model, ckpt, split, dr)
            if d is not None:
                ok += 1
                matrix[model][split] = {k: d.get(k) for k in KEYS}
    (E / "h6_eval_matrix.json").write_text(json.dumps(matrix, indent=2))
    with open(E / "h6_eval_matrix.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "split"] + KEYS)
        for model in matrix:
            for split in matrix[model]:
                r = matrix[model][split]
                w.writerow([model, split] + [r.get(k) for k in KEYS])
    print(f"[h6-eval] DONE {ok}/{len(MODELS)*len(SPLITS)} evals -> h6_eval_matrix.json")
    return 0 if ok == len(MODELS) * len(SPLITS) else 5


if __name__ == "__main__":
    sys.exit(main())
