"""Assemble datasets/isaac_hospital_h7r/{train,val,test} from the committed H7r
raised-mount quality table. Split membership + firewall come ONLY from
h7r_recording_quality_table.csv (route_completed, total_contacts, scene_gate_pass,
camera_mount_raise_m), so no failed/occluded/non-raised episode can leak in.
Episode dirs are the converted GNM episodes in unassigned/ (raised-mount recorded
front-RGB). Family design is instance-disjoint a/b (H6 route-instance protocol):
families are shared train<->eval BY DESIGN, so this asserts EPISODE + ROUTE
disjointness, not family disjointness. NOT a promotion step. system python3.
"""
import csv, json, shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONV = REPO / "datasets/isaac_hospital_imagenav_v0/unassigned"
TABLE = REPO / "assets/experiments/hospital_h7_raise_collection/reports/h7r_recording_quality_table.csv"
OUT = REPO / "datasets/isaac_hospital_h7r"
SPLIT_MAP = {"train": "train", "val": "val", "test": "test"}


def resolve_episode_dir(ep):
    # ep like h7r_reception_01 -> unassigned/h7r_reception_01_<timestamp>
    hits = sorted(CONV.glob(f"{ep}_20*"))
    assert len(hits) == 1, f"{ep}: expected 1 converted dir, found {[h.name for h in hits]}"
    return hits[0]


def main():
    rows = list(csv.DictReader(open(TABLE)))
    assert len(rows) == 8, f"expected 8 H7r rows, got {len(rows)}"

    if OUT.exists():
        shutil.rmtree(OUT)
    for s in ("train", "val", "test"):
        (OUT / s).mkdir(parents=True)

    placed = {"train": [], "val": [], "test": []}
    routes_by_split = {"train": set(), "val": set(), "test": set()}
    ep_ids = {}
    for r in rows:
        ep, fam, split = r["episode"], r["family"], r["split"]
        # firewall — every episode must be a clean, gated, raised-mount recording
        assert r["route_completed"] == "True", f"{ep}: route not completed"
        assert r["total_contacts"] == "0", f"{ep}: contacts!=0"
        assert r["scene_gate_pass"] == "True", f"{ep}: scene gate not passed"
        assert r["camera_mount_raise_m"] == "0.12", f"{ep}: not raised-mount (0.12) data"
        assert r["stop_reason"] in ("", "None"), f"{ep}: stop_reason={r['stop_reason']!r}"
        dst = SPLIT_MAP.get(split)
        assert dst, f"{ep}: unmapped split {split}"
        src = resolve_episode_dir(ep)
        assert (src / "traj_data.pkl").exists(), f"{ep}: no traj_data.pkl"
        assert (src / "goal.png").exists(), f"{ep}: no goal.png"
        shutil.copytree(src, OUT / dst / src.name)
        placed[dst].append((fam, ep, src.name))
        routes_by_split[dst].add(ep)
        ep_ids[ep] = src.name

    # composition + leakage (episode & route disjoint; families shared BY DESIGN)
    assert len(placed["train"]) == 4, placed["train"]
    assert len(placed["val"]) == 2, placed["val"]
    assert len(placed["test"]) == 2, placed["test"]
    assert routes_by_split["train"].isdisjoint(routes_by_split["val"] | routes_by_split["test"]), "route leak"
    assert routes_by_split["val"].isdisjoint(routes_by_split["test"]), "route leak val/test"
    all_eps = [e for s in placed.values() for _, e, _ in s]
    assert len(all_eps) == len(set(all_eps)) == 8, "episode not disjoint"

    summary = {
        "dataset": "Isaac-Hospital-ImageNav-H7r (raised-mount pilot)",
        "scene": "real Isaac 5.1 hospital.usd",
        "camera": "front RGB camera_link/rgb_camera raised +0.12 m, level horizon",
        "counts": {k: len(v) for k, v in placed.items()},
        "train": sorted(e for _, e, _ in placed["train"]),
        "val": sorted(e for _, e, _ in placed["val"]),
        "test": sorted(e for _, e, _ in placed["test"]),
        "train_families": sorted({f for f, _, _ in placed["train"]}),
        "val_families": sorted({f for f, _, _ in placed["val"]}),
        "test_families": sorted({f for f, _, _ in placed["test"]}),
        "episode_ids": ep_ids,
        "design": "instance-disjoint a/b (H6 route-instance protocol); families shared "
                  "train<->eval BY DESIGN; eval = unseen route INSTANCES of trained families",
        "leakage_proof": {"episode_disjoint": True, "route_disjoint": True,
                          "goal_image_fixed_across_all": "h2_weave_J (placeholder; imitation-fidelity, not goal-conditioning)"},
        "firewall": "route_completed & 0 contacts & scene_gate_pass & camera_mount_raise_m=0.12 asserted per episode",
        "claim_boundary": "diagnostic-only hospital pilot; NOT a promotion, NOT SOTA, NOT real-robot",
    }
    (OUT / "split_manifest.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"counts": summary["counts"], "train": summary["train"],
                      "val": summary["val"], "test": summary["test"]}, indent=2))
    print("H7R_DATASET_ROOT_OK")


if __name__ == "__main__":
    main()
