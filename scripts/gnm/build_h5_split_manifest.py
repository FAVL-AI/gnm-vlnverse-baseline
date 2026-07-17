"""Build the H5-run-1 split manifest + dataset root (mixed-family replay).

H5-run-1 replay pool (Frank, 2026-07-11): H4 clean demos (16 / 8 NavGen families)
+ H2.4 clean scripted demos (10 / 5 older families). NO H1 demos in run 1.
Validation spans BOTH distributions. Prior held-out (uturn/chain/ft_L) and H4
held-out (008/012/016) stay held out; never train/val.

Allowlist discipline: every train/val episode MUST come from the explicit H4 or
H2.4 clean sets; every test episode from the explicit held-out sets. Anything
else raises. Emits split_manifest.json (+ human table) and proves leakage-free.
BUILD ONLY — no training.
"""
import csv, json, shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
H4 = REPO / "datasets/isaac_hospital_h4"
H3 = REPO / "datasets/isaac_hospital_h3clean"     # holds H2.4 train + prior held-out
H1 = REPO / "datasets/isaac_hospital_split"        # H1 corpus — EXCLUDED from run 1
OUT = REPO / "datasets/isaac_hospital_h5"
EVID = REPO / "assets/experiments/hospital_h2_collection_20260709"

# ---- explicit episode sets (allowlist) ---------------------------------------
H4_TRAIN = sorted(p.name for p in (H4 / "train").iterdir())          # 16
H4_VAL = sorted(p.name for p in (H4 / "val").iterdir())              # 2  (015,017)
H4_TEST = sorted(p.name for p in (H4 / "test").iterdir())           # 6  (008,012,016)

H24_ALL = sorted(p.name for p in (H3 / "train").iterdir())           # 10 H2.4 demos
H24_VAL = ["h24_scurve_b_20260710_203800", "h24_I_b_20260710_214602"]  # older-family val
H24_TRAIN = [e for e in H24_ALL if e not in H24_VAL]                 # 8 (all 5 families kept)
PRIOR_TEST = sorted(p.name for p in (H3 / "test").iterdir())         # 6 (uturn/chain/ftL)

assert len(H4_TRAIN) == 16 and len(H4_VAL) == 2 and len(H4_TEST) == 6
assert len(H24_ALL) == 10 and len(H24_TRAIN) == 8 and len(PRIOR_TEST) == 6
assert all(v in H24_ALL for v in H24_VAL)

TRAIN = [(H4 / "train", e) for e in H4_TRAIN] + [(H3 / "train", e) for e in H24_TRAIN]
VAL = [(H4 / "val", e) for e in H4_VAL] + [(H3 / "train", e) for e in H24_VAL]
TEST_H4 = [(H4 / "test", e) for e in H4_TEST]
TEST_PRIOR = [(H3 / "test", e) for e in PRIOR_TEST]


def copy_set(pairs, split):
    dst = OUT / split
    dst.mkdir(parents=True)
    names = []
    for src_root, name in pairs:
        src = src_root / name
        assert (src / "traj_data.pkl").exists(), f"{name}: no traj_data.pkl"
        shutil.copytree(src, dst / name)
        names.append(name)
    return sorted(names)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)

    train = copy_set(TRAIN, "train")
    val = copy_set(VAL, "val")
    test_h4 = copy_set(TEST_H4, "test_h4")
    test_prior = copy_set(TEST_PRIOR, "test_prior")
    # combined test = both held-out sets
    (OUT / "test_combined").mkdir()
    for src_root, name in TEST_H4 + TEST_PRIOR:
        shutil.copytree(src_root / name, OUT / "test_combined" / name)
    test_combined = sorted(n for _, n in TEST_H4 + TEST_PRIOR)

    # ---- leakage proof (item 6) ----------------------------------------------
    s_train, s_val = set(train), set(val)
    s_test = set(test_h4) | set(test_prior)
    assert s_train.isdisjoint(s_val), "train∩val"
    assert s_train.isdisjoint(s_test), "train∩test"
    assert s_val.isdisjoint(s_test), "val∩test"
    assert set(test_combined) == s_test and len(test_combined) == 12

    # ---- allowlist proof: nothing outside the approved sets ------------------
    allowed_trainval = set(H4_TRAIN) | set(H4_VAL) | set(H24_ALL)
    for e in train + val:
        assert e in allowed_trainval, f"{e} not in approved H4/H2.4 train/val set"
    # explicit H1 exclusion: no isaac_hospital_split episode present anywhere
    h1_names = set()
    for s in ("train", "val", "test"):
        h1_names |= {p.name for p in (H1 / s).iterdir()}
    for e in train + val + test_h4 + test_prior:
        assert e not in h1_names, f"H1 episode leaked: {e}"

    # ---- excluded inventory (item 5) -----------------------------------------
    excluded = {
        "H1_corpus_isaac_hospital_split": sorted(h1_names),
        "H1_era_h3clean_val_not_used_as_H5_val":
            sorted(p.name for p in (H3 / "val").iterdir()),
        "reason": ("run-1 excludes H1 (physeval_collision_control*/physeval_*/"
                   "authcmp/normcmp/dash/livefinal etc. are not clean imitation "
                   "demos); H1 is a later ablation only after a clean inventory"),
    }

    manifest = {
        "experiment": "H5-run-1 mixed-family replay (H4 + H2.4-clean)",
        "status": "BUILT — NOT TRAINED (awaiting Frank's approval of this manifest)",
        "counts": {"train": len(train), "val": len(val),
                   "test_h4": len(test_h4), "test_prior": len(test_prior),
                   "test_combined": len(test_combined)},
        "train_episodes": train,
        "validation_episodes": val,
        "validation_composition": {"h4_val_families": H4_VAL,
                                   "older_h24_val_holdout": H24_VAL,
                                   "note": "spans both distributions; H2.4 val is "
                                           "the b-variant of scurve+corridor_I so "
                                           "all 5 H2.4 families remain in train"},
        "heldout_h4_test_episodes": test_h4,
        "heldout_prior_family_test_episodes": test_prior,
        "heldout_combined_test_episodes": test_combined,
        "excluded_episodes": excluded,
        "leakage_proof": {"train_disjoint_val": True, "train_disjoint_test": True,
                          "val_disjoint_test": True,
                          "no_heldout_test_in_train_or_val": True,
                          "allowlist_enforced": True, "no_h1_episode_present": True},
        "forced_data_root_eval_rule": (
            "every eval passes --data-root explicitly for BOTH candidate and "
            "incumbent; never rely on checkpoint-embedded data_root. Planned evals: "
            "(1) --data-root datasets/isaac_hospital_h5 --split test_h4  "
            "(2) --split test_prior  (3) --split test_combined — for BOTH "
            "checkpoints; verify printed data=… and n before trusting numbers"),
        "claim_boundary": (
            "Internal Isaac-Hospital-ImageNav-v0 simulation evidence; fixed "
            "placeholder goal image ⇒ evidence about route-family-diverse scripted "
            "imitation under the current pipeline, NOT stronger goal-image "
            "conditioning; not real-robot, not a public benchmark."),
        "planned_training": {
            "config": "configs/gnm/gnm_h5_mixed_replay.yaml (to be written on approval)",
            "init_ckpt": "checkpoints/hospital_front_rgb_finetune/best.pt (H1 incumbent, weights-only)",
            "action_std": [0.115528, 0.115528], "seed": 42, "epochs": 50,
            "batch_size": 128, "lr": 1e-4, "select_on": "H5 val (both distributions)"},
    }
    (OUT / "split_manifest.json").write_text(json.dumps(manifest, indent=2))
    (EVID / "h5_split_manifest.json").write_text(json.dumps(manifest, indent=2))

    # human-readable table
    with open(EVID / "h5_split_table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["split", "source", "episode"])
        for e in train:
            w.writerow(["train", "H4" if e in H4_TRAIN else "H2.4", e])
        for e in val:
            w.writerow(["val", "H4" if e in H4_VAL else "H2.4", e])
        for e in test_h4:
            w.writerow(["test_h4_heldout", "H4", e])
        for e in test_prior:
            w.writerow(["test_prior_heldout", "H2/H1-era", e])

    print(json.dumps(manifest["counts"], indent=2))
    print("H5_SPLIT_MANIFEST_BUILT — leakage-free, allowlist-enforced, NOT trained")


if __name__ == "__main__":
    main()
