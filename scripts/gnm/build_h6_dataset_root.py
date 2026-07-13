#!/usr/bin/env python3
"""Assemble the H6 diagnostic dataset root from converted episodes + emit the
post-conversion readiness reports. NO training here.

Consumes the converted episodes under
  datasets/isaac_hospital_imagenav_v0/unassigned/<episode>/
(one per RECORDED_OK H6 recording) and builds
  datasets/isaac_hospital_h6/{train,val,test_h6hard}/<episode>/   (physical copy)
mirroring the H4/H5 root layout so 04_train_gnm.py can read train/ + val/ and
06_evaluate.py can score --split test_h6hard.

Split (from the recording families, 5 train / 1 val / 2 fresh_heldout):
  train       <- 5 hard families x2  (uturn_01, chain_01, ftL_01, sharpmulti_01, tightcorr_01)
  val         <- compound_01 x2
  test_h6hard <- fresh held-out families x2 (uturn_02, chain_02)

Emits (into the collection evidence dir):
  1 h6_converted_dataset_summary.json     per-episode frames/goal/collisions
  2 h6_converted_split_counts.{json,csv}   train/val/test_h6hard + route-type coverage
  3 h6_conversion_artifact_check.json      each split ep has frames+pkl+goal+metadata
  4 h6_conversion_leakage_report.json      episode + family disjointness across splits
  5 h6_goal_claimboundary.json             fixed-placeholder-goal confirmation

Sets ready_for_training. If conversion or leakage fails, ready_for_training=False
and the caller must STOP (produce a dataset-readiness report, do not train).
"""
import csv, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import h6_precheck_verdicts as pc

REPO, OUT_DIR = pc.REPO, pc.OUT_DIR
LEDGER = OUT_DIR / "h6_recording_ledger.json"
UNASSIGNED = REPO / "datasets/isaac_hospital_imagenav_v0/unassigned"
DATA_ROOT = REPO / "datasets/isaac_hospital_h6"
SPLIT_SUBDIR = {"train": "train", "validation": "val", "fresh_heldout": "test_h6hard"}
FAM_SPLIT = {rid: split for (rid, rtype, split) in pc.FAMILIES}
FAM_TYPE = {rid: rtype for (rid, rtype, split) in pc.FAMILIES}
EXPECT_GOAL = pc.GOAL_ID  # fixed placeholder reference goal used for all H6 recordings


def converted_dir(episode_dir):
    return UNASSIGNED / Path(episode_dir).name


def load_meta(cd):
    try:
        return json.loads((cd / "metadata.json").read_text())
    except Exception:
        return {}


def main():
    rows = [r for r in json.loads(LEDGER.read_text()) if r.get("status") == "RECORDED_OK"]
    if not rows:
        print("[h6-build] ERROR: no RECORDED_OK episodes in ledger", file=sys.stderr)
        return 2

    # ---- build per-episode records -----------------------------------------
    eps = []
    for r in rows:
        rid = r["route_id"]
        subdir = SPLIT_SUBDIR[FAM_SPLIT[rid]]
        cd = converted_dir(r["episode_dir"])
        meta = load_meta(cd)
        n_jpg = len(list(cd.glob("*.jpg"))) if cd.exists() else 0
        eps.append({
            "episode": cd.name, "route_id": rid, "route_type": FAM_TYPE[rid],
            "split_target": FAM_SPLIT[rid], "split_subdir": subdir,
            "converted_dir": str(cd.relative_to(REPO)) if cd.exists() else None,
            "exists": cd.exists(), "n_jpg": n_jpg,
            "n_frames_meta": meta.get("n_frames"), "goal_id": meta.get("goal_id"),
            "collisions": meta.get("collisions"),
            "has_pkl": (cd / "traj_data.pkl").exists() if cd.exists() else False,
            "has_goal": (cd / "goal.png").exists() if cd.exists() else False,
            "has_meta": (cd / "metadata.json").exists() if cd.exists() else False,
        })

    # ---- report 3: artifact completeness (compute before copy) -------------
    for e in eps:
        e["artifact_complete"] = bool(e["exists"] and e["n_jpg"] > 0 and e["has_pkl"]
                                      and e["has_goal"] and e["has_meta"])
    all_complete = all(e["artifact_complete"] for e in eps) and len(eps) > 0
    (OUT_DIR / "h6_conversion_artifact_check.json").write_text(json.dumps(
        {"n_episodes": len(eps), "n_complete": sum(e["artifact_complete"] for e in eps),
         "all_complete": all_complete,
         "incomplete": [e["episode"] for e in eps if not e["artifact_complete"]],
         "items": eps}, indent=2))

    # ---- report 5: fixed-placeholder-goal claim boundary -------------------
    goals = sorted({e["goal_id"] for e in eps})
    goal_ok = goals == [EXPECT_GOAL]
    (OUT_DIR / "h6_goal_claimboundary.json").write_text(json.dumps(
        {"expected_goal_id": EXPECT_GOAL, "observed_goal_ids": goals,
         "single_fixed_goal": goal_ok,
         "boundary": ("All H6 episodes share one FIXED placeholder goal image "
                      f"({EXPECT_GOAL}). Metrics computed against it measure "
                      "route-family-diverse scripted imitation under the current "
                      "pipeline, NOT goal-image conditioning. No goal-conditioning "
                      "claim is admissible from this collection."),
         "not_real_robot": True, "not_public_benchmark": True}, indent=2))

    # ---- report 4: leakage (episode + family disjoint across splits) -------
    by_split = {}
    for e in eps:
        by_split.setdefault(e["split_subdir"], set()).add(e["episode"])
    pairs = [("train", "test_h6hard"), ("train", "val"), ("val", "test_h6hard")]
    ep_overlap = {f"{a}__{b}": sorted(by_split.get(a, set()) & by_split.get(b, set()))
                  for a, b in pairs}
    train_fams = {e["route_id"] for e in eps if e["split_subdir"] == "train"}
    held_fams = {e["route_id"] for e in eps if e["split_subdir"] == "test_h6hard"}
    fam_overlap = sorted(train_fams & held_fams)
    leakage_clean = (not any(ep_overlap.values())) and (not fam_overlap)
    (OUT_DIR / "h6_conversion_leakage_report.json").write_text(json.dumps(
        {"episode_level_overlaps": ep_overlap,
         "episode_level_disjoint": not any(ep_overlap.values()),
         "train_families": sorted(train_fams),
         "test_h6hard_families": sorted(held_fams),
         "family_overlap_train_vs_heldout": fam_overlap,
         "family_level_disjoint": not fam_overlap,
         "leakage_clean": leakage_clean}, indent=2))

    # ---- report 1: dataset summary -----------------------------------------
    (OUT_DIR / "h6_converted_dataset_summary.json").write_text(json.dumps(
        {"dataset": "Isaac-Hospital-ImageNav-v0 (H6 hard-route families)",
         "data_root": str(DATA_ROOT.relative_to(REPO)), "frame_stride": 12,
         "n_episodes": len(eps),
         "total_frames": sum(e["n_jpg"] for e in eps),
         "goal_ids": goals, "camera": "Yahboom front RGB (Isaac Sim)",
         "scripted_expert": True, "learned_policy_rollout": False,
         "episodes": eps}, indent=2))

    # ---- report 2: split + route-type coverage -----------------------------
    counts = {"train": 0, "val": 0, "test_h6hard": 0}
    for e in eps:
        counts[e["split_subdir"]] += 1
    types = sorted({e["route_type"] for e in eps})
    cov = {t: {"train": 0, "val": 0, "test_h6hard": 0} for t in types}
    for e in eps:
        cov[e["route_type"]][e["split_subdir"]] += 1
    (OUT_DIR / "h6_converted_split_counts.json").write_text(json.dumps(
        {"counts": counts, "route_type_coverage": cov, "n_episodes": len(eps)}, indent=2))
    with open(OUT_DIR / "h6_converted_split_counts.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["route_type", "train", "val", "test_h6hard", "total"])
        for t in types:
            c = cov[t]
            w.writerow([t, c["train"], c["val"], c["test_h6hard"],
                        c["train"] + c["val"] + c["test_h6hard"]])

    ready = all_complete and leakage_clean and goal_ok

    # ---- assemble the dataset root (physical copy) only if ready -----------
    manifest = {"train": [], "val": [], "test_h6hard": []}
    if ready:
        if DATA_ROOT.exists():
            shutil.rmtree(DATA_ROOT)
        for sub in ("train", "val", "test_h6hard"):
            (DATA_ROOT / sub).mkdir(parents=True, exist_ok=True)
        for e in eps:
            src = REPO / e["converted_dir"]
            dst = DATA_ROOT / e["split_subdir"] / e["episode"]
            shutil.copytree(src, dst)
            manifest[e["split_subdir"]].append(e["episode"])
        (DATA_ROOT / "split_manifest.json").write_text(json.dumps(
            {"experiment": "H6 hard-route-family diagnostic",
             "status": "BUILT (diagnostic; not promoted)",
             "data_root": str(DATA_ROOT.relative_to(REPO)),
             "counts": {k: len(v) for k, v in manifest.items()},
             "splits": manifest,
             "goal": EXPECT_GOAL, "frame_stride": 12,
             "note": "scripted-expert imitation; fixed placeholder goal; "
                     "select on val (compound-turn); test_h6hard is fresh held-out."},
            indent=2))

    verdict = {"ready_for_training": ready, "artifacts_all_complete": all_complete,
               "leakage_clean": leakage_clean, "single_fixed_goal": goal_ok,
               "counts": counts, "data_root": str(DATA_ROOT.relative_to(REPO))}
    (OUT_DIR / "h6_dataset_readiness.json").write_text(json.dumps(verdict, indent=2))

    print(f"[h6-build] episodes={len(eps)} counts={counts}")
    print(f"[h6-build] artifacts_all_complete={all_complete} leakage_clean={leakage_clean} "
          f"single_fixed_goal={goal_ok} (goals={goals})")
    print(f"[h6-build] READY_FOR_TRAINING={ready} data_root={DATA_ROOT.relative_to(REPO)}")
    if not ready:
        print("[h6-build] NOT READY -> STOP: produce dataset-readiness report, do not train.")
    return 0 if ready else 4


if __name__ == "__main__":
    sys.exit(main())
