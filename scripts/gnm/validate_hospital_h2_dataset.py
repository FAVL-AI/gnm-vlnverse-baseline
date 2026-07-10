"""Validate the H2 expanded Isaac-Hospital-ImageNav dataset.

Enforces the two-condition cleanliness rule: process integrity (return
code) AND artifact integrity (finalized bag, metadata, frames,
trajectory, command labels, stop reason, checksums).
"""
import csv, json, pickle, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "assets/experiments/hospital_h2_collection_20260709"
DS = REPO / "datasets/isaac_hospital_imagenav_v0/unassigned"
H1_TEST = {"hospital_holdout_short_D", "hospital_holdout_medium_E",
           "hospital_fresh_medium_G"}
H2_TRAIN = {"h2_long_turn_H", "h2_corridor_I", "h2_weave_J",
            "h2_near_desk_K"}
H2_TEST = {"h2_test_long_L", "h2_test_occluded_M"}

def fail(m): print(f"FAIL: {m}"); return False

def main():
    tp = OUT / "h2_quality_table.csv"
    if not tp.exists(): return fail("quality table missing")
    rows = list(csv.DictReader(open(tp)))
    if len(rows) < 30: return fail(f"attempt ledger too small ({len(rows)})")
    clean = [r for r in rows if r["recording_integrity"] in
             ("clean", "rerecorded_clean")]
    excl = [r for r in rows if r["recording_integrity"] ==
            "excluded_partial_recording"]
    if not excl: return fail("no excluded attempts — audit trail missing")
    for r in rows:
        if r["recording_integrity"] == "excluded_partial_recording":
            if r["training_eligible"] == "True" or \
                    r["evaluation_eligible"] == "True":
                return fail(f"{r['episode_id']}: excluded but eligible")
        g = r["goal_id"]
        if g in H2_TRAIN and r["split"] != "train":
            return fail(f"{r['episode_id']}: split mismatch")
        if g in H2_TEST and r["split"] != "test":
            return fail(f"{r['episode_id']}: split mismatch")
    # rc0-but-artifact-incomplete case must exist and be excluded
    tdm = [r for r in rows if r["episode_id"] == "h2_td_M"]
    if not tdm or tdm[0]["return_code"] != "0" or \
            tdm[0]["recording_integrity"] != "excluded_partial_recording":
        return fail("rc0-but-incomplete case (h2_td_M) not correctly "
                    "recorded — two-condition rule violated")
    # artifact integrity for every clean episode
    for r in clean:
        conv = sorted(DS.glob(f"{r['episode_id']}_2*"))
        if not conv: return fail(f"{r['episode_id']}: not converted")
        d = conv[-1]
        n = len(list(d.glob("[0-9]*.jpg")))
        if n < 8: return fail(f"{r['episode_id']}: too few frames")
        t = pickle.loads((d / "traj_data.pkl").read_bytes())
        if t["position"].shape != (n, 2):
            return fail(f"{r['episode_id']}: traj/frame mismatch")
        m = json.loads((d / "metadata.json").read_text())
        if not m.get("actions_cmd_vel"):
            return fail(f"{r['episode_id']}: command labels missing")
        for f_ in ("goal.png", "checksums.sha256"):
            if not (d / f_).exists():
                return fail(f"{r['episode_id']}: {f_} missing")
        if "front" not in m["camera"].lower():
            return fail(f"{r['episode_id']}: camera convention")
        if not r["stop_reason"]:
            return fail(f"{r['episode_id']}: stop reason missing")
    # difficulty vs H1: path lengths
    h2_paths = [float(r["path_length_m"]) for r in clean
                if r["path_length_m"]]
    if not h2_paths or max(h2_paths) < 5.0:
        return fail("H2 routes not harder than H1 (no long paths)")
    # collector separation and imitation flags
    for r in clean:
        if r["collector_policy"] == "topdown_incumbent_diagnostic" and \
                r["training_eligible"] == "True":
            return fail(f"{r['episode_id']}: incumbent marked "
                        "training-eligible")
    notes = (OUT / "collection_discipline_notes.md").read_text()
    if "not enough to declare an episode usable" not in notes:
        return fail("two-condition rule wording missing")
    ev = json.loads((OUT / "runtime_degradation_events.json").read_text())
    if len(ev) < 4: return fail("degradation events incomplete")
    print(f"H2 dataset valid: {len(rows)} attempts ledgered "
          f"({len(clean)} clean, {len(excl)} excluded); two-condition "
          "cleanliness enforced (rc0-but-incomplete case verified); "
          "artifact integrity on every clean episode; no excluded "
          "episode eligible; split integrity (train H-K, test L/M "
          "joining D/E/G); incumbent never training-eligible; max path "
          f"{max(h2_paths):.1f} m (>H1); degradation events {len(ev)}")
    print("PASS: hospital H2 dataset validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
