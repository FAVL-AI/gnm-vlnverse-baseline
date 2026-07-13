#!/usr/bin/env python3
"""Per-family failure table for the H6 diagnostic comparison.

Re-runs Track-A eval with --save-episodes for H1/H5/H6 on the three
family-diagnostic held-out sets, reads each episode_result.json, and groups
per-episode success/NE by ROUTE FAMILY. Emits h6_per_family_failure_table.
{json,csv}. Diagnostic only; --data-root forced on every call.
"""
import csv, json, os, re, shutil, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E = REPO / "assets/experiments/hospital_h2_collection_20260709"
PY = sys.executable
EVAL = REPO / "scripts/gnm/06_evaluate.py"
MODELS = {"h1": "checkpoints/hospital_front_rgb_finetune/best.pt",
          "h5": "checkpoints/h5_mixed_replay_finetune/best.pt",
          "h6": "checkpoints/h6_hard_families_finetune/best.pt"}
SETS = [("test_h6hard", "datasets/isaac_hospital_h6"),
        ("test_prior", "datasets/isaac_hospital_h5"),
        ("test_h4", "datasets/isaac_hospital_h5")]


def family(name, split):
    n = name.lower()
    if split == "test_h6hard":
        if "uturn_02" in n: return "uturn_02"
        if "chain_02" in n: return "chain_02"
    elif split == "test_prior":
        if "test_uturn" in n: return "uturn"
        if "test_chain" in n: return "chain"
        if "ft_l" in n or "td_l" in n: return "ftL"
    elif split == "test_h4":
        m = re.search(r"navgen_31_(\d+)", n)
        if m: return "navgen_31_" + m.group(1)
    return "other"


def eval_episodes(model, ckpt, split, dr):
    out = REPO / f"checkpoints/_h6cmp_eval/perfam_{model}__{split}"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    cmd = [PY, str(EVAL), "--ckpt", str(REPO / ckpt), "--data-root", str(REPO / dr),
           "--split", split, "--track", "A", "--output-dir", str(out),
           "--save-episodes", "--device", "cuda"]
    subprocess.run(cmd, cwd=str(REPO), env={**os.environ, "PYTHONPATH": str(REPO)},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    for d in sorted(out.iterdir()):
        rp = d / "episode_result.json"
        if d.is_dir() and rp.exists():
            r = json.loads(rp.read_text())
            rows.append({"episode": d.name, "family": family(d.name, split),
                         "SR": r.get("SR"), "NE": r.get("NE"), "SPL": r.get("SPL")})
    return rows


def main():
    # agg[(split,family,model)] = list of episode dicts
    agg = {}
    for split, dr in SETS:
        for model, ckpt in MODELS.items():
            for e in eval_episodes(model, ckpt, split, dr):
                agg.setdefault((split, e["family"]), {}).setdefault(model, []).append(e)

    long_rows, table = [], {}
    for (split, fam), per_model in sorted(agg.items()):
        table[f"{split}/{fam}"] = {}
        for model in ("h1", "h5", "h6"):
            eps = per_model.get(model, [])
            n = len(eps)
            succ = sum(1 for e in eps if (e["SR"] or 0) >= 1.0)
            sr = round(succ / n, 3) if n else None
            mne = round(sum(e["NE"] for e in eps) / n, 3) if n else None
            long_rows.append({"split": split, "family": fam, "model": model,
                              "n": n, "successes": succ, "SR": sr, "mean_NE_m": mne})
            table[f"{split}/{fam}"][model] = {"n": n, "successes": succ,
                                              "SR": sr, "mean_NE_m": mne}

    (E / "h6_per_family_failure_table.json").write_text(json.dumps(
        {"note": "per-route-family held-out results; success = SR>=1 at 3 m; "
                 "diagnostic; fixed placeholder goal (h6hard) => imitation fidelity, "
                 "not goal conditioning", "table": table}, indent=2))
    with open(E / "h6_per_family_failure_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["split", "family", "model", "n",
                                          "successes", "SR", "mean_NE_m"])
        w.writeheader()
        for r in long_rows:
            w.writerow(r)

    for k in table:
        row = table[k]
        print(f"{k:28s} " + "  ".join(
            f"{m}:SR={row[m]['SR']}/NE={row[m]['mean_NE_m']}(n{row[m]['n']})"
            for m in ("h1", "h5", "h6")))
    print(f"[h6-perfam] -> h6_per_family_failure_table.{{json,csv}}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
