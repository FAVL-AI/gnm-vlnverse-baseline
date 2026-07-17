"""Assemble datasets/isaac_hospital_h4/{train,val,test} from the H4 validated
quality table. Split membership is taken ONLY from h4_quality_table.csv (the
imitation/evaluation-eligible flags), so failed/superseded attempts and any
non-train episode cannot leak into train. Enforces pre-start checks 3-8.
"""
import csv, json, re, shutil, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONV = REPO / "datasets/isaac_hospital_imagenav_v0/unassigned"
TABLE = REPO / "assets/experiments/hospital_h2_collection_20260709/h4_quality_table.csv"
OUT = REPO / "datasets/isaac_hospital_h4"

TRAIN_FAM = {"h4_navgen_31_000", "h4_navgen_31_001", "h4_navgen_31_002",
             "h4_navgen_31_005", "h4_navgen_31_007", "h4_navgen_31_009",
             "h4_navgen_31_011", "h4_navgen_31_013"}
VAL_FAM = {"h4_navgen_31_015", "h4_navgen_31_017"}
TEST_FAM = {"h4_navgen_31_008", "h4_navgen_31_012", "h4_navgen_31_016"}


def main():
    rows = list(csv.DictReader(open(TABLE)))
    assert len(rows) == 24, f"expected 24 rows, got {len(rows)}"

    if OUT.exists():
        shutil.rmtree(OUT)
    for s in ("train", "val", "test"):
        (OUT / s).mkdir(parents=True)

    placed = {"train": [], "val": [], "test": []}
    for r in rows:
        ep, fam, split = r["episode_id"], r["route_family"], r["split"]
        imit = r["imitation_eligible"] == "True"
        evalq = r["evaluation_eligible"] == "True"
        # firewall assertions (checks 3,4,5,7,8)
        assert r["return_code"] == "0", f"{ep}: rc!=0"
        assert r["artifact_integrity"] == "complete", f"{ep}: artifact"
        assert r["total_contacts"] == "0", f"{ep}: contacts!=0"
        assert r["collector_type"] == "scripted_reference_path", \
            f"{ep}: not scripted expert (policy rollout?)"
        assert r["demonstration_source"] == "expert_scripted_executor", \
            f"{ep}: demo source"
        if split == "train":
            assert fam in TRAIN_FAM and imit and not evalq, f"{ep}: train firewall"
            dst = "train"
        elif split == "validation":
            assert fam in VAL_FAM and not imit and evalq, f"{ep}: val firewall"
            dst = "val"
        elif split == "held_out_test":
            assert fam in TEST_FAM and not imit and evalq, f"{ep}: test firewall"
            dst = "test"
        else:
            raise SystemExit(f"{ep}: unmapped split {split}")
        src = CONV / ep
        assert (src / "traj_data.pkl").exists(), f"{ep}: no traj_data.pkl"
        shutil.copytree(src, OUT / dst / ep)
        placed[dst].append((fam, ep))

    # composition assertions
    assert len(placed["train"]) == 16, placed["train"]
    assert len(placed["val"]) == 2, placed["val"]
    assert len(placed["test"]) == 6, placed["test"]
    assert {f for f, _ in placed["train"]} == TRAIN_FAM
    assert {f for f, _ in placed["val"]} == VAL_FAM
    assert {f for f, _ in placed["test"]} == TEST_FAM
    # no train family appears in val/test (disjoint) — check 7
    assert TRAIN_FAM.isdisjoint(VAL_FAM | TEST_FAM)

    summary = {"train": sorted(e for _, e in placed["train"]),
               "val": sorted(e for _, e in placed["val"]),
               "test": sorted(e for _, e in placed["test"]),
               "train_families": sorted(TRAIN_FAM),
               "val_families": sorted(VAL_FAM),
               "test_families": sorted(TEST_FAM)}
    (OUT / "split_manifest.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: len(v) if isinstance(v, list) else v
                      for k, v in summary.items()}, indent=2))
    print("H4_DATASET_ROOT_OK")


if __name__ == "__main__":
    main()
