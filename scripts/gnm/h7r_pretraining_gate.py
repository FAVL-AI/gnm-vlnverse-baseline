"""H7r pre-training gate — verify the isaac_hospital_h7r data-root is a clean,
leakage-free, raised-mount-only hospital dataset BEFORE any training. Cross-checks
the on-disk data-root against the committed H7r evidence (quality table + scene-gate
manifests). Emits a gate JSON + episode-count table + leakage/artifact reports.
If any check fails -> exit 5 (do not train). system python3.
"""
import csv, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "datasets/isaac_hospital_h7r"
RAISE = REPO / "assets/experiments/hospital_h7_raise_collection"
QT = RAISE / "reports/h7r_recording_quality_table.csv"
GATE_DIR = REPO / "assets/experiments/hospital_h7_scene_gate"
OUT = RAISE / "training"
OUT.mkdir(parents=True, exist_ok=True)

FAMILY = {"reception": "reception_to_corridor", "corridor": "corridor_straight",
          "turn": "turn_t_junction", "waiting": "waiting_to_doorway"}
SPLITS = ("train", "val", "test")
fail = []


def base(ep):  # h7r_reception_01_2026... -> reception_01 ; and h7r_reception_01 -> reception_01
    p = ep.replace("h7r_", "").split("_20")[0]
    return p


man = json.loads((ROOT / "split_manifest.json").read_text())
qt = {r["episode"]: r for r in csv.DictReader(open(QT))}

# 1) episode-count table + collect per-episode facts from the data-root
table = []
per_split = {s: [] for s in SPLITS}
for s in SPLITS:
    for epdir in sorted((ROOT / s).glob("h7r_*")):
        eid = epdir.name
        b = base(eid)
        ep_key = f"h7r_{b}"
        meta = json.loads((epdir / "metadata.json").read_text())
        n_jpg = len(list(epdir.glob("*.jpg")))
        artifacts_ok = all((epdir / f).exists() for f in
                            ("traj_data.pkl", "goal.png", "metadata.json", "checksums.sha256")) and n_jpg > 0
        q = qt.get(ep_key, {})
        # scene-gate manifest for this episode_id
        gm = GATE_DIR / f"{eid}.json"
        gate = json.loads(gm.read_text()) if gm.exists() else {}
        row = {
            "split": s, "episode": ep_key, "episode_id": eid,
            "family": FAMILY.get(b.split("_")[0], "?"),
            "n_frames": n_jpg, "artifacts_complete": artifacts_ok,
            "goal_id": meta.get("goal_id"),
            "source_bag": meta.get("source_bag"),
            "from_h7r_bag": str(meta.get("source_bag", "")).find("h7r_") >= 0,
            "camera_mount_raise_m": q.get("camera_mount_raise_m"),
            "scene_gate_pass": gate.get("scene_identity_pass"),
            "hospital_referenced": bool(gate.get("checks", {}).get("hospital_reference_authored")),
            "route_completed": q.get("route_completed"),
            "total_contacts": q.get("total_contacts"),
            "bottom_third_black_pct": q.get("bottom_third_black_pct"),
        }
        table.append(row)
        per_split[s].append(row)
        if not artifacts_ok:
            fail.append(f"{ep_key}: artifacts incomplete (n_jpg={n_jpg})")
        if row["goal_id"] != "h2_weave_J":
            fail.append(f"{ep_key}: goal_id={row['goal_id']} != h2_weave_J")
        if not row["from_h7r_bag"]:
            fail.append(f"{ep_key}: source bag not an h7r raised-mount bag ({row['source_bag']})")
        if row["camera_mount_raise_m"] != "0.12":
            fail.append(f"{ep_key}: camera_mount_raise_m={row['camera_mount_raise_m']} != 0.12")
        if row["scene_gate_pass"] is not True:
            fail.append(f"{ep_key}: scene_gate_pass={row['scene_gate_pass']}")
        if not row["hospital_referenced"]:
            fail.append(f"{ep_key}: hospital.usd not referenced in scene-gate manifest")
        if row["route_completed"] != "True":
            fail.append(f"{ep_key}: route_completed={row['route_completed']}")
        if row["total_contacts"] != "0":
            fail.append(f"{ep_key}: total_contacts={row['total_contacts']}")

counts = {s: len(per_split[s]) for s in SPLITS}
if counts != {"train": 4, "val": 2, "test": 2}:
    fail.append(f"counts {counts} != train4/val2/test2")

# 2) leakage: episode + route disjoint across splits
sets = {s: {r["episode"] for r in per_split[s]} for s in SPLITS}
episode_disjoint = sets["train"].isdisjoint(sets["val"] | sets["test"]) and sets["val"].isdisjoint(sets["test"])
all_eps = [r["episode"] for r in table]
route_disjoint = len(all_eps) == len(set(all_eps)) == 8
if not episode_disjoint:
    fail.append("episode leak across splits")
if not route_disjoint:
    fail.append("route/episode not disjoint (n!=8 unique)")
# families shared train<->eval BY DESIGN (instance-disjoint a/b) — informational, not a failure
train_fams = {r["family"] for r in per_split["train"]}
eval_fams = {r["family"] for r in per_split["val"] + per_split["test"]}

leakage = {
    "episode_disjoint": episode_disjoint,
    "route_disjoint": route_disjoint,
    "families_shared_by_design": sorted(train_fams & eval_fams),
    "protocol": "H6 route-instance generalization (a/b instance-disjoint); "
                "eval = unseen route INSTANCES of trained families",
    "goal_image_fixed_across_all": "h2_weave_J (placeholder) — imitation-fidelity, NOT goal-conditioning",
    "leakage_clean_episode_and_route_level": episode_disjoint and route_disjoint,
}

goal_claim = {
    "goal_id": "h2_weave_J",
    "nature": "FIXED placeholder goal image reused across all 8 episodes",
    "implication": "this is imitation-fidelity data, NOT goal-image-conditioning evidence; "
                   "SR/OSR/NE measured against the recorded route endpoint (position), goal image is fixed",
    "consistent_with": "same fixed-goal convention disclosed in H4/H5 governance cards",
}

report = {
    "gate": "H7r_PRETRAINING",
    "data_root": str(ROOT.relative_to(REPO)),
    "counts": counts,
    "all_from_raised_mount_recorded_camera_image_raw": all(r["from_h7r_bag"] for r in table),
    "all_camera_mount_raise_m_0_12": all(r["camera_mount_raise_m"] == "0.12" for r in table),
    "all_scene_identity_hospital_usd_pass": all(r["scene_gate_pass"] is True and r["hospital_referenced"] for r in table),
    "all_artifacts_complete": all(r["artifacts_complete"] for r in table),
    "frames_per_episode": {r["episode"]: r["n_frames"] for r in table},
    "leakage": leakage,
    "fixed_goal_image_claim_boundary": goal_claim,
    "episodes": table,
    "PASS": len(fail) == 0,
    "failures": fail,
}
(OUT / "h7r_pretraining_gate.json").write_text(json.dumps(report, indent=2))

# episode-count table (md)
cols = ["split", "episode", "family", "n_frames", "goal_id", "camera_mount_raise_m",
        "scene_gate_pass", "route_completed", "total_contacts", "artifacts_complete"]
md = ["# H7r pre-training gate — episode / split / provenance table", "",
      f"data_root: `datasets/isaac_hospital_h7r`  ·  counts: {counts}", "",
      "| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
for r in table:
    md.append("| " + " | ".join(str(r.get(c)) for c in cols) + " |")
md += ["", f"- all frames from raised-mount recorded /camera/image_raw: **{report['all_from_raised_mount_recorded_camera_image_raw']}**",
       f"- camera_mount_raise_m = 0.12 for all: **{report['all_camera_mount_raise_m_0_12']}**",
       f"- scene identity = verified hospital.usd (gate PASS) for all: **{report['all_scene_identity_hospital_usd_pass']}**",
       f"- artifacts complete for all: **{report['all_artifacts_complete']}**",
       f"- leakage clean (episode+route disjoint): **{leakage['leakage_clean_episode_and_route_level']}**",
       f"- fixed goal image: **h2_weave_J** (placeholder; imitation-fidelity, not goal-conditioning)",
       "", f"## GATE: {'PASS' if report['PASS'] else 'FAIL'}"]
if fail:
    md += ["", "### failures:"] + [f"- {x}" for x in fail]
(OUT / "h7r_pretraining_gate.md").write_text("\n".join(md))

print("\n".join(md[:6]))
print(f"\nfrom_h7r_bag all={report['all_from_raised_mount_recorded_camera_image_raw']} | "
      f"raise0.12 all={report['all_camera_mount_raise_m_0_12']} | "
      f"scene-gate all={report['all_scene_identity_hospital_usd_pass']} | "
      f"artifacts all={report['all_artifacts_complete']} | "
      f"leakage-clean={leakage['leakage_clean_episode_and_route_level']}")
print(f"GATE: {'PASS' if report['PASS'] else 'FAIL — DO NOT TRAIN'}")
if not report["PASS"]:
    print("failures:", fail)
    sys.exit(5)
