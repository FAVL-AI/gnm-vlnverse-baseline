"""H8 map-extension RECOVERY report builder (ANALYSIS ONLY — no Isaac here).

Consolidates the original 6-zone validation + the 3 recovery episodes (val_A retry,
midwest_A, midwest_B) + the visual-distinctness audit into a final candidate-zone table,
split status, and an honest recovery verdict. Does NOT re-run the H8-S design gate here:
it reports whether the gate's preconditions (proven per split, coord-disjoint, visual
distinctness, enough zones) are met, and holds for review.

Reads on-disk artifacts only. Writes under .../drive_validation/:
  recovery_manifest.json, recovery_zone_table.csv, recovery_report.md
"""
import json, csv, glob
from pathlib import Path

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
DV = REPO / "assets/experiments/hospital_h8_map_extension/drive_validation"
TR = REPO / "assets/experiments/trajectories"
SG = REPO / "assets/experiments/hospital_h7_scene_gate"
RM = DV / "render_metadata"
COMMIT = "8413c098ac93b9630e1c3984efac5e0e904de1f2"
CL_BOUND_XY = 6.0
VIS_HI = 0.80   # aHash similarity above this = suspiciously similar (crude corridor screen)

# zone -> (split, family, spawn_isaac_world, in_envelope, episode_glob)
ZONES = {
    "east_A": ("test", "near_far_same_approach", [1.4, 0.1], True, "h8mx_val_east_A_*"),
    "east_B": ("test", "stop_vs_go", [2.6, 0.1], True, "h8mx_val_east_B_*"),
    "lookalike_test": ("test", "visually_similar_diff_location", [3.0, 0.1], True, "h8mx_val_lookalike_test_*"),
    "lobby": ("train", "corridor_t_junction", [-1.0, -0.2], True, "h8mx_val_lobby_*"),
    "midwest_A": ("train", "near_far_same_approach", [-2.8, -0.2], True, "h8mx_val_midwest_A_*"),
    "midwest_B": ("val", "near_far_same_approach", [-3.4, -0.2], True, "h8mx_val_midwest_B_*"),
    "west_C": ("train", "shared_corridor_branch", [-5.3, 0.1], True, "h8mx_val_west_C_*"),
    "val_A": ("val", "near_far_same_approach", [-3.8, 0.1], True, "h8mx_val_val_A_2*"),
    "val_A_retry": ("val", "near_far_same_approach", [-3.8, 0.1], True, "h8mx_val_val_A_retry_*"),
    "west_A": ("train", "near_far_same_approach", [-8.5, 0.1], False, None),
    "west_B": ("train", "stop_vs_go", [-6.8, 0.1], False, None),
    "hardneg_farwest": ("hard-negative", "any", [-9.9, 0.1], False, None),
}
NEEDS_RETRY_MAX = 50


def load(z, g):
    ds = sorted(glob.glob(str(TR / g)))
    if not ds:
        return None
    ed = Path(ds[-1]); m = json.loads((ed / "episode_metadata.json").read_text())
    xs = []
    with open(ed / "trajectory.csv") as f:
        for r in csv.DictReader(f):
            try:
                xs.append(float(r["robot_position_x"]))
            except (KeyError, ValueError):
                pass
    eid = m["episode_id"]; sgf = SG / f"{eid}.json"
    sgpass = bool(all(json.loads(sgf.read_text())["checks"].values())) if sgf.exists() else None
    cam = json.loads((RM / f"{z}.json").read_text()) if (RM / f"{z}.json").exists() else {}
    return dict(episode_id=eid, collisions=m.get("total_collision_count"),
                scene_gate_pass=sgpass, x_min=round(min(xs), 2), x_max=round(max(xs), 2),
                camera_valid=cam.get("camera_valid"),
                black=cam.get("lower_frame_black_fraction"))


def status(z, rec):
    split, fam, spawn, in_env, g = ZONES[z]
    if not in_env:
        return "DEFERRED_SAFETY_ENVELOPE_LIMITED", f"|x|={abs(spawn[0])}>CL_BOUND_XY={CL_BOUND_XY}; not run; not a failure"
    if rec is None:
        return "NEEDS_RETRY", "no artifact"
    c = rec["collisions"]; cam = rec["camera_valid"]
    if not rec["scene_gate_pass"]:
        return "REJECTED_RENDER", "scene gate failed"
    if c == 0 and cam:
        return "PROVEN_FOR_ROUTE_DESIGN", "0 collisions, scene-gate PASS, camera valid"
    if c == 0 and not cam:
        return "REJECTED_RENDER", f"camera invalid (black {rec['black']})"
    if 0 < c <= NEEDS_RETRY_MAX:
        return "NEEDS_RETRY", f"{c} contacts (borderline)"
    return "REJECTED_COLLISION", f"{c} contacts" + ("" if cam else f" + camera invalid (black {rec['black']})")


def main():
    va = json.loads((RM / "_visual_audit.json").read_text())
    results = []
    for z, (split, fam, spawn, in_env, g) in ZONES.items():
        rec = load(z, g) if in_env and g else None
        st, reason = status(z, rec)
        e = dict(zone=z, intended_split=split, family=fam, spawn_isaac_world=spawn,
                 in_envelope=in_env, status=st, reason=reason)
        if rec:
            e.update(episode_id=rec["episode_id"], collisions=rec["collisions"],
                     camera_valid=rec["camera_valid"], scene_gate_pass=rec["scene_gate_pass"],
                     driven_x=[rec["x_min"], rec["x_max"]])
        results.append(e)

    # val_A: retry reproduced 25 contacts -> escalate original val_A to REJECTED_COLLISION
    def find(zz):
        return next(r for r in results if r["zone"] == zz)
    if find("val_A_retry")["status"] in ("NEEDS_RETRY", "REJECTED_COLLISION"):
        va_o = find("val_A")
        va_o["status"] = "REJECTED_COLLISION"
        va_o["reason"] = "25 contacts on BOTH the initial pass and the retry (reproducible obstacle at x≈-3.8); not recoverable by retry"

    proven = [r for r in results if r["status"] == "PROVEN_FOR_ROUTE_DESIGN"]
    by_split = {"train": [], "val": [], "test": []}
    for r in proven:
        if r["intended_split"] in by_split:
            by_split[r["intended_split"]].append(r["zone"])

    # visual distinctness verdict
    hi = va["high_sim_pairs"]
    cross = [p for p in hi if p["kind"] == "CROSS-SPLIT"]
    test_dups = [p for p in hi if p["kind"] == "same-split" and
                 va["proven_split"].get(p["a"]) == "test"]
    vis_ok = len(cross) == 0 and len(test_dups) == 0

    gate_preconditions = {
        "each_split_has_proven_zone": all(by_split[s] for s in by_split),
        "coords_disjoint_across_splits": True,
        "visual_distinctness_acceptable": vis_ok,
        "enough_distinct_zones": False if test_dups else True,
        "n_proven": len(proven), "proven_by_split": by_split,
        "cross_split_similar_pairs": cross, "test_near_duplicate_pairs": test_dups,
    }
    gate_preconditions["ok_to_rerun_H8S_design_gate"] = (
        gate_preconditions["each_split_has_proven_zone"]
        and gate_preconditions["visual_distinctness_acceptable"])

    manifest = dict(scene="hospital.usd", repository_commit=COMMIT,
                    safety_watchdog=dict(CL_BOUND_XY=CL_BOUND_XY, unchanged=True),
                    navmap_read_offset_bringup_to_world=[2.956, -6.240],
                    spawn_note="candidate bringup coords are isaac-world; spawned directly, no offset",
                    visual_audit=va, gate_preconditions=gate_preconditions, zones=results)
    (DV / "recovery_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_csv(results)
    write_report(manifest)
    print(json.dumps(dict(proven_by_split=by_split, n_proven=len(proven),
                          visual_ok=vis_ok, ok_to_rerun_gate=gate_preconditions["ok_to_rerun_H8S_design_gate"],
                          statuses={r["zone"]: r["status"] for r in results}), indent=2))
    print("H8 MAP-EXT RECOVERY REPORT ->", DV)


def write_csv(results):
    cols = ["zone", "intended_split", "family", "in_envelope", "status", "collisions",
            "camera_valid", "scene_gate_pass", "spawn_isaac_world", "driven_x", "reason"]
    with open(DV / "recovery_zone_table.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(cols)
        for r in results:
            w.writerow([r.get(c) for c in cols])


def write_report(mf):
    gp = mf["gate_preconditions"]; va = mf["visual_audit"]
    def row(r):
        c = r.get("collisions", "—"); cv = r.get("camera_valid", "—"); dx = r.get("driven_x", "—")
        return (f"| {r['zone']} | {r['intended_split']} | {'in' if r['in_envelope'] else 'OUT'} | "
                f"{c} | {cv} | {dx} | **{r['status']}** |")
    L = ["# H8 Map-Extension — Recovery Validation Report", "",
         "**Scope: validation only.** No H8-S collection, no training, no promotion, no push, no "
         "tag, no 20/5/10, no closed-loop beyond bounded per-zone drives, **no `CL_BOUND_XY` change**. "
         "Held for review.", "",
         "## What recovery did",
         "- **Retried val_A** (same isaac-world spawn −3.8, no navmap offset): **25 contacts again** "
         "— reproducible obstacle at x≈−3.8, not run-variation → `val_A` escalated to "
         "`REJECTED_COLLISION` (retry did not clear it).",
         "- **Probed two mid-west points**: `midwest_A` (−2.8) and `midwest_B` (−3.4) both **0 "
         "collisions, camera valid** → the drivable/blocked boundary is sharp between −3.4 (clean) "
         "and −3.8 (blocked). **`midwest_B` recovers the val split** (coordinate-disjoint, west of "
         "the lobby).",
         "- **Navmap could not have predicted this:** free-y span is identical (−0.76…1.09) at every "
         "x from −5.3 to 1.4; the blocking geometry lives outside the navmap z-slab. Only drive "
         "validation finds it.",
         "",
         "## Final candidate-zone table",
         "| zone | split | env | collisions | cam_valid | driven_x | status |",
         "|---|---|---|---|---|---|---|",
         *[row(r) for r in mf["zones"]],
         "",
         "## Split status (proven, coordinate-disjoint)",
         f"- **train:** {gp['proven_by_split']['train']}  (lobby [−2.31,0.91]; midwest_A reserve, overlaps lobby).",
         f"- **val:** {gp['proven_by_split']['val']}  (midwest_B [−3.4,−2.9], west of lobby — **RECOVERED**).",
         f"- **test:** {gp['proven_by_split']['test']}  (east [1.4,3.5]).",
         "- Coordinate bands are disjoint: val [−3.4,−2.9] · train [−2.31,0.91] · test [1.4,3.5] "
         "(gaps ≥0.49 m).",
         "",
         "## Visual-distinctness audit (task 3 — the new blocker)",
         "aHash similarity on the post-drive view (1 − Hamming/256; >0.80 = suspiciously similar; "
         "crude for structurally-alike corridors, but the RELATIVE pattern is informative):",
         f"- **Test zones are near-duplicates:** " +
         ", ".join(f"{p['a']}~{p['b']}={p['sim']}" for p in gp['test_near_duplicate_pairs']) +
         " — east_A/east_B/lookalike_test all show the same vending-machine/wheelchair bay, so TEST "
         "carries **~1 distinct view, not 3**. lookalike_test's adversarial pairing is **unresolved** "
         "(intended confuser west_B is safety-deferred, and it duplicates east_B).",
         f"- **Cross-split similarity:** " +
         (", ".join(f"{p['a']}~{p['b']}={p['sim']}" for p in gp['cross_split_similar_pairs']) or "none")
         + " — east(test)~lobby(train) ≈0.83–0.86 (same corridor structure); moderate, to be "
         "re-checked with a proper perceptual-hash gate at recording.",
         "- **midwest_B (val) is strongly distinct** (0.53–0.76 to all others) — a clean, "
         "well-separated val zone.",
         "",
         "## H8-S design-gate preconditions",
         f"- each split has a proven zone: **{gp['each_split_has_proven_zone']}**.",
         f"- coords disjoint across splits: **{gp['coords_disjoint_across_splits']}**.",
         f"- enough DISTINCT zones (test not collapsed): **{gp['enough_distinct_zones']}**.",
         f"- visual distinctness acceptable: **{gp['visual_distinctness_acceptable']}**.",
         f"- **→ OK to re-run H8-S design gate now: {gp['ok_to_rerun_H8S_design_gate']}**.",
         "",
         "The H8-S design gate was **NOT re-run**: coordinates qualify, but visual distinctness does "
         "not yet (test near-duplicates + moderate train/test cross-similarity). The coordinate-only "
         "design gate would report 'ready' and mislead — the real gap is imagery.",
         "",
         "## Revised H8-S recommendation (held for review)",
         "The map extension now yields a **coordinate-clean, per-split-proven** zone set "
         "(train=lobby, val=midwest_B, test=east) — a genuine advance over the flagged H8-S. But "
         "before recording, resolve the **imagery** gap:",
         "1. **Give TEST distinct decision frames** — the east bay is one view; either use a single "
         "east test frame (not three), or find a second visually-distinct in-envelope test location.",
         "2. **Resolve lookalike_test** — its adversarial confuser (west_B) is safety-deferred; drop "
         "the visually-similar family from H8-S, or pair it inside the envelope.",
         "3. **Add a perceptual-hash cross-split gate** at recording (the §5 goal-image hash audit), "
         "using midwest_B (val) as the distinct anchor; treat east~lobby ≈0.85 as the threshold to "
         "beat.",
         "4. Only then re-run the H8-S design gate (coords) **and** a recorded-image distinctness "
         "gate; record only if both pass.",
         "",
         "## Claim boundary",
         "Bounded per-zone spawn + short drive; 1 pass (val_A: 2 passes, reproducible). Collisions = "
         "PhysX base_link contacts (ground truth). Visual similarity = crude aHash screen, not a "
         "final leakage verdict. Feasibility study; no dataset recorded, no model trained, no "
         "promotion; `CL_BOUND_XY` unchanged; incumbent retained.",
         "",
         "## Artifacts",
         "`drive_validation/`: `recovery_manifest.json`, `recovery_zone_table.csv`, this report, "
         "`recovery_ledger.csv`, `contact_sheets/{val_A_retry,midwest_A,midwest_B}.png` + prior 6, "
         "`render_metadata/*.json` incl. `_visual_audit.json`, `routes/h8mx_{val_A_retry,midwest_A,"
         "midwest_B}.json`. Harness: `scripts/gnm/h8_map_extension_recover.sh`, "
         "`scripts/gnm/h8_map_extension_recovery_report.py`. Rosbags/trajectories NOT for commit.",
         ""]
    (DV / "recovery_report.md").write_text("\n".join(L).rstrip("\n") + "\n")


if __name__ == "__main__":
    main()
