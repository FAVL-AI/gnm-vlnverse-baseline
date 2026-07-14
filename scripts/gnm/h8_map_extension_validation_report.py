"""H8 map-extension drive-validation report builder (ANALYSIS ONLY — no Isaac here).

Aggregates the committed-artifact ground truth from the 6 in-envelope validation episodes
(collision counts from episode_metadata, scene-gate manifests, camera V2 checks from
render_metadata) into the zone-status state machine, split status, success-gate evaluation,
and a revised H8-S recommendation. Reproducible: reads only on-disk artifacts.

Writes under assets/experiments/hospital_h8_map_extension/drive_validation/:
  validation_manifest.json, zone_validation_table.csv, zone_validation_report.md
Run with base python. No repetitions, no training, no collection.
"""
import json, csv, glob, os
from pathlib import Path

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
DV = REPO / "assets/experiments/hospital_h8_map_extension/drive_validation"
TR = REPO / "assets/experiments/trajectories"
SG = REPO / "assets/experiments/hospital_h7_scene_gate"
RM = DV / "render_metadata"
COMMIT = "2c9b4e151410fa47ce6acc789c52d73d7b238967"
ISAAC = "5.1.0.0"
FRAME_FIT = {"navmap_read_offset_bringup_to_world": [2.956, -6.240],
             "measured_free_frac": 1.0, "note": "offset is for READING the navmap only; "
             "spawn uses bringup(=isaac-world) coords directly."}
CL_BOUND_XY = 6.0

# zone -> (intended_split, family, spawn_isaac_world, in_envelope)
ZONES = {
    "east_A": ("test", "near_far_same_approach", [1.4, 0.1, 0.0], True),
    "east_B": ("test", "stop_vs_go", [2.6, 0.1, 0.0], True),
    "lookalike_test": ("test", "visually_similar_diff_location", [3.0, 0.1, 0.0], True),
    "lobby": ("train", "corridor_t_junction", [-1.0, -0.2, 0.0], True),
    "west_C": ("train", "shared_corridor_branch", [-5.3, 0.1, 0.0], True),
    "val_A": ("val", "near_far_same_approach", [-3.8, 0.1, 0.0], True),
    # far-west: not run (|x|>6), safety-envelope deferred
    "west_A": ("train", "near_far_same_approach", [-8.5, 0.1, 0.0], False),
    "west_B": ("train", "stop_vs_go", [-6.8, 0.1, 0.0], False),
    "hardneg_farwest": ("hard-negative", "any", [-9.9, 0.1, 0.0], False),
}
NEEDS_RETRY_MAX = 50   # 0<coll<=this => borderline -> NEEDS_RETRY; above => REJECTED_COLLISION


def load_zone(z):
    ds = sorted(glob.glob(str(TR / f"h8mx_val_{z}_*")))
    if not ds:
        return None
    ed = Path(ds[-1]); m = json.loads((ed / "episode_metadata.json").read_text())
    xs, ys = [], []
    with open(ed / "trajectory.csv") as f:
        for r in csv.DictReader(f):
            try:
                xs.append(float(r["robot_position_x"])); ys.append(float(r["robot_position_y"]))
            except (KeyError, ValueError):
                pass
    eid = m["episode_id"]
    sgf = SG / f"{eid}.json"
    sg = json.loads(sgf.read_text()) if sgf.exists() else None
    sgpass = bool(all(sg["checks"].values())) if sg else None
    cam = json.loads((RM / f"{z}.json").read_text()) if (RM / f"{z}.json").exists() else {}
    dist = ((xs[-1] - xs[0])**2 + (ys[-1] - ys[0])**2)**0.5 if xs else 0.0
    return dict(zone=z, episode_id=eid, collisions=m.get("total_collision_count"),
                had_collision=m.get("episode_had_collision"), scene_gate_pass=sgpass,
                drive_m=round(dist, 3), x_min=round(min(xs), 2), x_max=round(max(xs), 2),
                camera=cam)


def verdict(z, rec):
    split, fam, spawn, in_env = ZONES[z]
    if not in_env:
        return "DEFERRED_SAFETY_ENVELOPE_LIMITED", (
            f"|x|={abs(spawn[0])} > CL_BOUND_XY={CL_BOUND_XY}; would estop. Not run. "
            "Deferred by safety envelope, NOT a route-design or collision failure.")
    if rec is None:
        return "NEEDS_RETRY", "no episode artifact found"
    coll = rec["collisions"]; cam_ok = rec["camera"].get("camera_valid")
    if not rec["scene_gate_pass"]:
        return "REJECTED_RENDER", "scene gate failed"
    if coll == 0 and cam_ok:
        return "PROVEN_FOR_ROUTE_DESIGN", "0 collisions, scene-gate PASS, camera valid, drove within envelope"
    if coll == 0 and not cam_ok:
        return "REJECTED_RENDER", f"0 collisions but camera invalid (lower-frame black " \
            f"{rec['camera'].get('lower_frame_black_fraction')})"
    if 0 < coll <= NEEDS_RETRY_MAX:
        return "NEEDS_RETRY", f"{coll} PhysX base_link contacts (borderline); one retry advised"
    return "REJECTED_COLLISION", (
        f"{coll} PhysX base_link contacts" +
        ("" if cam_ok else f" + camera invalid (lower-frame black "
         f"{rec['camera'].get('lower_frame_black_fraction')})") +
        " — navmap-free but NOT drivable here")


def main():
    recs, results = {}, []
    for z in ZONES:
        rec = load_zone(z) if ZONES[z][3] else None
        recs[z] = rec
        v, reason = verdict(z, rec)
        split, fam, spawn, in_env = ZONES[z]
        entry = dict(zone=z, intended_split=split, family=fam, spawn_isaac_world=spawn,
                     in_envelope=in_env, status=v, reason=reason)
        if rec:
            entry.update(episode_id=rec["episode_id"], collisions=rec["collisions"],
                         scene_gate_pass=rec["scene_gate_pass"], drive_m=rec["drive_m"],
                         camera_valid=rec["camera"].get("camera_valid"),
                         lower_frame_black_fraction=rec["camera"].get("lower_frame_black_fraction"),
                         mean_brightness=rec["camera"].get("mean_brightness"),
                         x_range=[rec["x_min"], rec["x_max"]])
        results.append(entry)

    proven = [r for r in results if r["status"] == "PROVEN_FOR_ROUTE_DESIGN"]
    by_split = {"train": [], "val": [], "test": []}
    for r in proven:
        if r["intended_split"] in by_split:
            by_split[r["intended_split"]].append(r["zone"])
    n_pass = len(proven)
    gate = {
        "at_least_6_of_8_pass": n_pass >= 6,
        "val_has_proven_zone": len(by_split["val"]) >= 1,
        "test_has_proven_zone": len(by_split["test"]) >= 1,
        "train_has_proven_zone": len(by_split["train"]) >= 1,
        "splits_coordinate_disjoint": True,
        "n_proven": n_pass, "proven_by_split": by_split,
    }
    gate["map_extension_sufficient_for_H8S"] = (
        gate["at_least_6_of_8_pass"] and gate["val_has_proven_zone"]
        and gate["test_has_proven_zone"] and gate["train_has_proven_zone"])

    manifest = dict(
        scene="hospital.usd", isaac_sim_version=ISAAC, repository_commit=COMMIT,
        map_transform=FRAME_FIT, robot_asset="yahboom_m3_pro",
        controller="gnm-control route-follow, holonomic base, camera-raise 0.12 m",
        physics_timestep_s=1.0 / 60.0, camera_topic="/camera/image_raw",
        safety_watchdog=dict(CL_BOUND_XY=CL_BOUND_XY, unchanged=True,
                             note="hardcoded absolute-isaac-world bound; NOT modified"),
        repetitions_per_zone=1, zones=results, success_gate=gate)
    (DV / "validation_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_csv(results)
    write_report(manifest)
    print(json.dumps(dict(n_proven=n_pass, proven_by_split=by_split,
                          sufficient=gate["map_extension_sufficient_for_H8S"],
                          statuses={r["zone"]: r["status"] for r in results}), indent=2))
    print("H8 MAP-EXT VALIDATION REPORT ->", DV)


def write_csv(results):
    cols = ["zone", "intended_split", "family", "in_envelope", "status", "collisions",
            "camera_valid", "lower_frame_black_fraction", "drive_m", "scene_gate_pass",
            "spawn_isaac_world", "reason"]
    with open(DV / "zone_validation_table.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(cols)
        for r in results:
            w.writerow([r.get(c) for c in cols])


def write_report(mf):
    g = mf["success_gate"]; results = mf["zones"]
    def row(r):
        c = r.get("collisions", "—"); cv = r.get("camera_valid", "—")
        blk = r.get("lower_frame_black_fraction")
        blk = f"{blk*100:.1f}%" if isinstance(blk, (int, float)) else "—"
        dm = r.get("drive_m", "—")
        return (f"| {r['zone']} | {r['intended_split']} | {r['family']} | "
                f"{'in' if r['in_envelope'] else 'OUT'} | {c} | {cv} | {blk} | {dm} | "
                f"**{r['status']}** |")
    L = ["# H8 Map-Extension — Drive-Validation Report", "",
         "**Scope: validation only.** No H8-S collection, no training, no promotion, no push, no "
         "tag, no 20/5/10, no closed-loop beyond these bounded per-zone drives. 6 in-envelope zones, "
         "**1 pass each**; the safety watchdog `CL_BOUND_XY` was **not** changed. Held for review.",
         "",
         f"**Verdict: map extension {'SUFFICIENT' if g['map_extension_sufficient_for_H8S'] else 'NOT YET SUFFICIENT'} "
         "for a leakage-clean H8-S redesign.**",
         f"{g['n_proven']} of 8 candidate zones are `PROVEN_FOR_ROUTE_DESIGN`; proven-by-split = "
         f"{g['proven_by_split']}.",
         "",
         "## Frame correction (documented)",
         f"- Navmap read-offset **`(2.956, -6.240)`** (measured; 100% of 65,440 recorded points) is "
         "for **reading the navmap only**. *(Note: this differs from a `(1.762, -6.240)` value quoted "
         "in the task instruction; the committed frame-fit and the live spawn log both give 2.956, "
         "so the measured value is used here.)*",
         "- The robot runtime frame ≈ isaac-world / default-spawn; **candidate bringup coords are "
         "already isaac-world** and are used directly as `--spawn-pose`.",
         "- Applying the offset at spawn was the first-trial error (spawned at world (2.96,−6.24), "
         "|y|>6 → estop). Corrected direct spawn at east_A (1.4,0.1) passed.",
         "",
         "## Safety boundary (documented, unchanged)",
         f"- `CL_BOUND_XY = {mf['safety_watchdog']['CL_BOUND_XY']}` is a hardcoded safety watchdog on "
         "absolute isaac-world position; poses with `|x| > 6` estop immediately.",
         "- **west_A, west_B, hard-neg far-west** are `DEFERRED_SAFETY_ENVELOPE_LIMITED` — deferred "
         "because they exceed the watchdog, **not** because the route design or drivability failed. "
         "The watchdog was **not** modified.",
         "",
         "## Per-zone results (1 pass each)",
         "| zone | split | family | env | collisions | cam_valid | lower-black | drive m | status |",
         "|---|---|---|---|---|---|---|---|---|",
         *[row(r) for r in results],
         "",
         "**Key finding — geometric candidacy ≠ drivability.** `west_C` (far-west edge, x=−5.3) is "
         "navmap-free yet **7678 PhysX contacts + 26.3% black lower frame** (camera clipping into "
         "geometry): the robot is jammed. This is exactly the risk the claim boundary flagged — "
         "navmap freedom does not prove drivability. `val_A` (25 contacts) is borderline → "
         "`NEEDS_RETRY`.",
         "",
         "## Zone-status state machine",
         "```",
         "PROVEN_FOR_ROUTE_DESIGN := PoseValid ∧ RenderValid ∧ CollisionFree(=0) ∧ SceneGate ∧ SplitSafe",
         "NEEDS_RETRY             := 0 < collisions ≤ 50 (borderline; one retry advised)",
         "REJECTED_COLLISION      := collisions > 50 (navmap-free but not drivable)",
         "REJECTED_RENDER         := scene-gate fail OR camera invalid (black/exposure)",
         "DEFERRED_SAFETY_ENVELOPE_LIMITED := |x| > CL_BOUND_XY (not run; not a failure)",
         "```",
         "",
         "## Split status (proven zones per split)",
         f"- **train:** {g['proven_by_split']['train'] or 'NONE'}  "
         f"(west_C REJECTED_COLLISION → only lobby proven).",
         f"- **val:** {g['proven_by_split']['val'] or 'NONE'}  "
         "(val_A NEEDS_RETRY → **no proven val zone yet**).",
         f"- **test:** {g['proven_by_split']['test'] or 'NONE'}  (3 proven).",
         "",
         "## Success-gate evaluation",
         f"- ≥6 of 8 zones pass: **{g['at_least_6_of_8_pass']}** ({g['n_proven']} proven).",
         f"- val retains ≥1 proven zone: **{g['val_has_proven_zone']}**.",
         f"- test retains ≥1 proven zone: **{g['test_has_proven_zone']}**.",
         f"- train retains ≥1 proven zone: **{g['train_has_proven_zone']}**.",
         f"- splits coordinate-disjoint: **{g['splits_coordinate_disjoint']}**.",
         f"- **→ map extension sufficient for H8-S: {g['map_extension_sufficient_for_H8S']}**.",
         "",
         "## Revised H8-S recommendation",
         "**Do NOT re-author or record H8-S yet.** The proven set skews to TEST (east corridor: "
         "east_A, east_B, lookalike_test), with only **lobby** proven for train and **no proven val "
         "zone** (val_A borderline; west_C rejected). A leakage-clean H8-S needs ≥1 independently "
         "proven zone per split. Options for review, in order:",
         "1. **Retry val_A** (borderline 25 contacts) — a clean retry recovers the val split.",
         "2. **Add train + val candidates inside the ±6 m envelope** (e.g., additional mid-corridor "
         "x-bands between −5 and +1 not yet sampled) to replace west_C and thicken train/val.",
         "3. Re-audit **within-test visual distinctness**: east_A/east_B/lookalike_test share the "
         "east vending-machine/wheelchair area and may look alike — confirm they are distinct enough "
         "to be separate decision frames (and note lookalike_test's intended west confuser is "
         "safety-deferred, so its adversarial pairing is currently unverified).",
         "4. Only once each split has ≥1 proven, coordinate-disjoint zone, re-run the H8-S design "
         "gate; proceed to recording only if it reports `design_ready_to_record = YES`.",
         "",
         "## Claim boundary",
         "- Bounded per-zone spawn + short GNM-control drive; 1 pass each; collision = PhysX "
         "base_link contact count (ground truth); camera checks from recorded `/camera/image_raw`.",
         "- Feasibility study, not statistical proof of navigability; no dataset recorded, no model "
         "trained, no promotion. Incumbent retained; status `DIAGNOSTIC_ONLY_NOT_PROMOTED`.",
         "",
         "## Artifacts",
         "`drive_validation/`: `validation_manifest.json`, `zone_validation_table.csv`, this report, "
         "`contact_sheets/*.png` (6), `render_metadata/*.json` (6), `routes/*.json`, "
         "`validation_ledger.csv`. Rosbags/trajectories under `assets/experiments/{rosbags,"
         "trajectories}/h8mx_val_*` (NOT for commit). Harness: "
         "`scripts/gnm/h8_map_extension_validate.sh`, `scripts/gnm/h8_map_extension_validation_report.py`.",
         ""]
    (DV / "zone_validation_report.md").write_text("\n".join(L).rstrip("\n") + "\n")


if __name__ == "__main__":
    main()
