"""Route-type coverage table for H6 planning. Classifies every hospital episode
currently in the H5 setup (train/val) and the held-out sets by canonical route
type, and tallies train/val/heldout counts. Shows which route types the model
FAILS on are absent from training (the coverage hypothesis).
Read-only; emits h6_coverage_table.csv + prints the table. No training.
"""
import csv, json, re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
E = REPO / "assets/experiments/hospital_h2_collection_20260709"
H5 = REPO / "datasets/isaac_hospital_h5"
H4 = REPO / "datasets/isaac_hospital_h4"
H3 = REPO / "datasets/isaac_hospital_h3clean"
APPROVAL = E / "h4_route_family_approval_table.csv"

# H4 family -> (turn_type, zone) from the approval table
h4meta = {}
for r in csv.DictReader(open(APPROVAL)):
    h4meta[r["route_family_id"]] = (r["turn_type"], r["zone_class"])


def route_type(ep):
    """canonical route type for an episode dir name."""
    if ep.startswith("h4rec_"):
        fam = re.search(r"(h4_navgen_31_\d{3})", ep).group(1)
        tt, zone = h4meta.get(fam, ("?", "?"))
        if "amber" in zone:
            return "navgen_amber_zone"
        return "navgen_multi_turn" if tt == "multi" else "navgen_single_turn"
    if ep.startswith("h24_test_uturn") or "uturn" in ep:
        return "uturn_HARD"
    if ep.startswith("h24_test_chain") or "chain" in ep:
        return "chain_HARD"
    if "ft_L" in ep or "td_L" in ep:
        return "ftL_sharp_HARD"
    if ep.startswith("h24_straight"):
        return "straight"
    if ep.startswith("h24_90turn"):
        return "single_90turn"
    if ep.startswith("h24_scurve"):
        return "scurve"
    if ep.startswith("h24_J"):
        return "multi_turn_weave"
    if ep.startswith("h24_I"):
        return "corridor"
    return "other"


def names(root, split):
    d = root / split
    return [p.name for p in d.iterdir()] if d.exists() else []


def main():
    train = names(H5, "train")
    val = names(H5, "val")
    heldout = names(H4, "test") + names(H3, "test")   # H4 heldout + prior heldout

    tally = {}
    for grp, eps in (("train", train), ("val", val), ("heldout", heldout)):
        for ep in eps:
            rt = route_type(ep)
            tally.setdefault(rt, {"train": 0, "val": 0, "heldout": 0})[grp] += 1

    order = ["straight", "single_90turn", "scurve", "corridor", "multi_turn_weave",
             "navgen_single_turn", "navgen_multi_turn", "navgen_amber_zone",
             "uturn_HARD", "chain_HARD", "ftL_sharp_HARD", "other"]
    rows = []
    for rt in order:
        if rt not in tally:
            continue
        t = tally[rt]
        status = ("UNCOVERED_in_train" if t["train"] == 0 and t["heldout"] > 0
                  else "covered")
        rows.append({"route_type": rt, "train_count": t["train"],
                     "val_count": t["val"], "heldout_count": t["heldout"],
                     "status": status})

    with open(E / "h6_coverage_table.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["route_type", "train_count", "val_count",
                                          "heldout_count", "status"])
        w.writeheader()
        w.writerows(rows)

    print(f"{'route_type':22}{'train':>6}{'val':>5}{'heldout':>9}  status")
    for r in rows:
        print(f"{r['route_type']:22}{r['train_count']:>6}{r['val_count']:>5}"
              f"{r['heldout_count']:>9}  {r['status']}")
    uncov = [r["route_type"] for r in rows if r["status"] == "UNCOVERED_in_train"]
    print("\nUNCOVERED-in-training route types:", uncov)
    print("total hard-type episodes available (all currently held-out):",
          sum(r["heldout_count"] for r in rows if "HARD" in r["route_type"]))


if __name__ == "__main__":
    main()
