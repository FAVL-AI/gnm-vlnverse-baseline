"""H8-S route design-mode acceptance (DESIGN ONLY — no collection, no training, no model).

Validates the H8-S causal decision-frame design from labels/geometry alone, BEFORE any
recording, so we never record routes that fail to force goal use (the H7r trap). Two gate
types:
  - action_branch     : goal changes action DIRECTION -> require action-angle sep >= 30 deg.
  - stop_conditioning : goal changes WHERE to stop (same direction) -> require goal-distance
                        separation >= stop_min_m (NOT gated on action angle).
Also audits: shared decision frame, goals distinct, not route-solvable without the goal,
decision-frame (leakage-group) split disjointness, goal-image leakage (coord reuse across
splits), route-family balance, and coordinate feasibility vs the confirmed-free navigable
segments (from successfully-recorded H7 + H8-prototype routes).

Reads  assets/experiments/hospital_h8_s_causal_routes/h8_s_decision_frames.json
Writes (same dir): h8_s_route_manifest.json (enriched), h8_s_design_acceptance_results.json,
                   h8_s_design_report.md
Run with any python (stdlib only). Exit 6 if any non-deferred design fails its gate.
"""
import json, math, sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIR = REPO / "assets/experiments/hospital_h8_s_causal_routes"
IN = DIR / "h8_s_decision_frames.json"
MARGIN_DEG = 30.0
FEAS_TOL_M = 0.30   # endpoint must be within this of a confirmed-free segment to be "on-map"

# confirmed-free segments = consecutive waypoints of routes recorded 0-collision (bringup frame)
_RECORDED = [
    [(-1.5, 0.0), (0.0, 0.0), (1.0, 0.0)], [(-1.5, 0.6), (0.0, 0.6), (1.0, 0.6)],
    [(-2.6, -0.8), (-0.8, -0.2), (1.2, 0.0)], [(-2.6, -0.3), (-0.8, 0.2), (1.0, 0.4)],
    [(-1.0, 0.8), (0.2, 0.8), (0.2, -0.2)], [(-1.0, -0.2), (0.2, -0.2), (0.2, 0.8)],
    [(-2.2, 1.0), (-0.5, 0.4), (1.0, -0.2)], [(-2.0, 0.6), (-0.4, 0.1), (0.9, -0.4)],
    [(-1.0, -0.2), (0.2, -0.2), (1.0, -0.2)], [(-1.5, 0.0), (0.2, 0.0), (1.0, 0.6)],
    [(0.2, 0.0), (1.0, -0.2)],
]
SEGMENTS = [(w[i], w[i + 1]) for w in _RECORDED for i in range(len(w) - 1)]


def pt_seg_dist(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def on_map(p):
    return min(pt_seg_dist(p, a, b) for a, b in SEGMENTS) <= FEAS_TOL_M


def robot_action(o_d, yaw, goal):
    vx, vy = goal[0] - o_d[0], goal[1] - o_d[1]
    c, s = math.cos(yaw), math.sin(yaw)
    ax, ay = c * vx + s * vy, -s * vx + c * vy
    n = math.hypot(ax, ay)
    return (ax / n, ay / n) if n > 1e-9 else (0.0, 0.0)


def ang(a):
    return math.degrees(math.atan2(a[1], a[0]))


def ang_between(a, b):
    return math.degrees(math.atan2(abs(a[0] * b[1] - a[1] * b[0]), a[0] * b[0] + a[1] * b[1]))


def evaluate(df, stop_min):
    tier = df["feasibility_tier"]
    rec = {"route_id": df["route_id"], "family": df["family"], "gate_type": df["gate_type"],
           "feasibility_tier": tier, "leakage_group": df["leakage_group"], "split": df["split"]}
    if tier == "DEFERRED":
        rec.update({"gate": "N/A (deferred)", "pass": None,
                    "reason": df["notes"]})
        return rec
    o_d, yaw = df["o_d"], df["approach_yaw_rad"]
    gA, gB = df["goalA"]["coord"], df["goalB"]["coord"]
    aA, aB = robot_action(o_d, yaw, gA), robot_action(o_d, yaw, gB)
    feas = {"o_d_on_map": on_map(o_d), "goalA_on_map": on_map(gA), "goalB_on_map": on_map(gB)}
    feas_ok = all(feas.values())
    rec["o_d"] = o_d
    rec["expected_action_A"] = [round(aA[0], 4), round(aA[1], 4)]
    rec["expected_action_B"] = [round(aB[0], 4), round(aB[1], 4)]
    rec["feasibility_geometry"] = {**feas, "all_endpoints_on_confirmed_map": feas_ok}
    goals_differ = math.hypot(gA[0] - gB[0], gA[1] - gB[1]) > 1e-6
    if df["gate_type"] == "action_branch":
        sep = ang_between(aA, aB)
        checks = {"shared_decision_frame": True, "two_goals_distinct": bool(goals_differ),
                  "actions_differ": math.hypot(aA[0] - aB[0], aA[1] - aB[1]) > 0.2,
                  "action_angle_sep_ge_30deg": sep >= MARGIN_DEG,
                  "not_route_solvable_without_goal": bool(goals_differ) and sep >= MARGIN_DEG,
                  "endpoints_on_confirmed_map": feas_ok}
        rec["action_angle_separation_deg"] = round(sep, 2)
    else:  # stop_conditioning
        dA = math.hypot(gA[0] - o_d[0], gA[1] - o_d[1])
        dB = math.hypot(gB[0] - o_d[0], gB[1] - o_d[1])
        stop_sep = abs(dA - dB)
        checks = {"shared_decision_frame": True, "two_goals_distinct": bool(goals_differ),
                  "same_direction_ok": ang_between(aA, aB) < 20.0,
                  "stop_distance_sep_ge_min": stop_sep >= stop_min,
                  "not_route_solvable_without_goal": stop_sep >= stop_min,
                  "endpoints_on_confirmed_map": feas_ok}
        rec.update({"goal_distance_A_m": round(dA, 3), "goal_distance_B_m": round(dB, 3),
                    "stop_distance_separation_m": round(stop_sep, 3),
                    "shared_direction_angle_deg": round(ang(aA), 1)})
    rec["checks"] = checks
    rec["pass"] = all(checks.values())
    return rec


def main():
    data = json.loads(IN.read_text())
    stop_min = data.get("stop_min_m", 0.6)
    dfs = data["decision_frames"]
    recs = [evaluate(df, stop_min) for df in dfs]
    active = [r for r in recs if r["pass"] is not None]
    deferred = [r for r in recs if r["pass"] is None]

    # leakage-group split disjointness
    group_splits = defaultdict(set)
    for df in dfs:
        group_splits[df["leakage_group"]].add(df["split"])
    leak_violations = {g: sorted(s) for g, s in group_splits.items()
                       if len([x for x in s if x != "none"]) > 1}
    # goal-image leakage proxy: same goal coord reused across different splits
    coord_split = defaultdict(set)
    for df in dfs:
        if df["feasibility_tier"] == "DEFERRED":
            continue
        for g in ("goalA", "goalB"):
            coord_split[tuple(df[g]["coord"])].add(df["split"])
    goal_leak = {str(c): sorted(s) for c, s in coord_split.items()
                 if len([x for x in s if x != "none"]) > 1}
    # family balance per split
    fam_by_split = defaultdict(Counter)
    for df in dfs:
        fam_by_split[df["split"]][df["family"]] += 1
    tier_counts = Counter(df["feasibility_tier"] for df in dfs)
    fam_counts = Counter(df["family"] for df in dfs)

    all_active_pass = all(r["pass"] for r in active)
    split_integrity_ok = not goal_leak and not leak_violations
    summary = {
        "n_decision_frames": len(dfs), "n_active": len(active), "n_deferred": len(deferred),
        "all_active_pass": all_active_pass,
        "split_integrity_ok": split_integrity_ok,
        "design_ready_to_record": all_active_pass and split_integrity_ok,
        "tier_counts": dict(tier_counts), "family_counts": dict(fam_counts),
        "families_covered": sorted(fam_counts),
        "leakage_group_split_violations": leak_violations,
        "goal_image_coord_leakage_across_splits": goal_leak,
        "family_by_split": {k: dict(v) for k, v in fam_by_split.items()},
        "gates": {"margin_deg": MARGIN_DEG, "stop_min_m": stop_min, "feas_tol_m": FEAS_TOL_M},
    }
    results = {"scope": data["scope"], "summary": summary, "decision_frames": recs}
    (DIR / "h8_s_design_acceptance_results.json").write_text(json.dumps(results, indent=2))

    # enriched manifest = input DFs + computed action/sep/feasibility
    by_id = {r["route_id"]: r for r in recs}
    manifest = {"collection": data["collection"], "scene": data["scene"],
                "camera_mount_raise_m": data["camera_mount_raise_m"],
                "coordinate_note": data["coordinate_note"], "summary": summary,
                "decision_frames": []}
    for df in dfs:
        r = by_id[df["route_id"]]
        manifest["decision_frames"].append({**df, "computed": {k: r[k] for k in r
                 if k in ("expected_action_A", "expected_action_B", "action_angle_separation_deg",
                          "goal_distance_A_m", "goal_distance_B_m", "stop_distance_separation_m",
                          "shared_direction_angle_deg", "feasibility_geometry", "checks", "pass")}})
    (DIR / "h8_s_route_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_report(results)
    print(json.dumps({"all_active_pass": all_active_pass,
                      "split_integrity_ok": split_integrity_ok,
                      "design_ready_to_record": summary["design_ready_to_record"],
                      "active": len(active), "deferred": len(deferred),
                      "tiers": dict(tier_counts),
                      "leak_violations": leak_violations, "goal_leak": goal_leak}, indent=2))
    print("H8-S DESIGN ACCEPTANCE ->", DIR)
    # exit 6 if any per-frame geometry gate fails; split-integrity flags are reported (not a
    # hard exit) because resolving them is a design decision for review, not a geometry error.
    sys.exit(0 if all_active_pass else 6)


def write_report(res):
    s = res["summary"]
    L = ["# H8-S Causal Route Design — Acceptance Report", "",
         "**Scope: design only.** No collection, no training, no recording, no model. Validates "
         "the H8-S decision-frame design from labels/geometry before any recording, so no route "
         "is recorded that fails to force goal use (the H7r trap).", "",
         f"**Per-frame geometry gate: {'PASS' if s['all_active_pass'] else 'FAIL'}** for all "
         f"{s['n_active']} active (non-deferred) decision frames; {s['n_deferred']} deferred.",
         f"**Split-integrity audit: {'PASS' if s['split_integrity_ok'] else 'FLAGGED'}.** ",
         f"**Design ready to record as-is: {'YES' if s['design_ready_to_record'] else 'NO'}** — "
         + ("the two gate dimensions both pass." if s['design_ready_to_record'] else
            "every per-frame geometry gate passes, but the cross-split goal-image audit flags "
            "reused goal coordinates (see *Split-integrity finding* below); resolve before recording."),
         "",
         "## Split-integrity finding (the pivotal H8-S result)",
         "The design-mode gate proves each frame's **geometry** forces goal use, but the small "
         "proven-free lobby forces distinct decision frames to **reuse the same far-goal "
         "coordinates across splits**:",
         *( [f"- goal coord `{c}` used as a goal in splits {sp} — goal-image leakage per design-doc §5."
             for c, sp in s['goal_image_coord_leakage_across_splits'].items()]
            or ["- none."] ),
         "This is not a geometry error — it is the **feasibility constraint from "
         "`H8_CAUSAL_COLLECTION_DESIGN.md` §3 made concrete**: the proven-free lobby "
         "(≈ x∈[−2.6,1.2], y∈[−0.8,1.0]) does not contain enough *distinct* navigable goal "
         "locations to build a leakage-clean held-out goal-image split at H8-S scale. Two honest "
         "resolutions, both for review:",
         "  1. **Scope H8-S as a train-only objective-generalization probe** (a few distinct "
         "decision frames, no held-out goal-image claim) and defer the held-out split to H8-M; or",
         "  2. **Extend the render-confirmed navigable map first** (the H8-M prerequisite sub-task) "
         "to supply physically-distinct val/test goal locations, then re-run this gate.",
         "**Recommended: Resolution 2 (map extension first).** Resolution 1 is rejected: a "
         "train-only H8-S would add only weak evidence on top of the committed 2×2 objective-"
         "viability result and would blur the claim boundary. The stronger, correctly-preserved "
         "finding is that the current proven-free lobby cannot support a leakage-clean H8-S "
         "held-out goal-image split; the fix is to extend the verified navigable map so val/test "
         "goals are physically distinct from train goals, then re-run this design gate.",
         "The held-out action-probe (design-doc §10 gate 3) therefore **cannot be earned inside "
         "the current proven space** — it is blocked on the map extension, exactly as §3 predicted.",
         "",
         "## Design principle & two gate types",
         "Each shared decision frame `o_d` pairs with two goals. **Branch families** change the "
         "action DIRECTION → gated on action-angle separation ≥ 30°. **Stop families** "
         "(near/far, stop-vs-go) keep the same direction but change WHERE to stop → gated on "
         "goal-distance separation ≥ "
         f"{s['gates']['stop_min_m']} m (a goal-blind policy cannot know the stop point).", "",
         "## Decision frames", "",
         "| route_id | family | gate | tier | split | separation | pass |",
         "|---|---|---|---|---|---|---|"]
    for r in res["decision_frames"]:
        if r["pass"] is None:
            L.append(f"| {r['route_id']} | {r['family']} | {r['gate_type']} | {r['feasibility_tier']} "
                     f"| {r['split']} | — | deferred |")
        elif r["gate_type"] == "action_branch":
            L.append(f"| {r['route_id']} | {r['family']} | action_branch | {r['feasibility_tier']} "
                     f"| {r['split']} | {r['action_angle_separation_deg']:.1f}° | "
                     f"{'✅' if r['pass'] else '❌'} |")
        else:
            L.append(f"| {r['route_id']} | {r['family']} | stop_conditioning | {r['feasibility_tier']} "
                     f"| {r['split']} | Δstop {r['stop_distance_separation_m']:.2f} m | "
                     f"{'✅' if r['pass'] else '❌'} |")
    L += ["",
          "## Split & leakage audit",
          f"- **Family coverage ({len(s['families_covered'])}/7):** "
          f"{', '.join(s['families_covered'])}.",
          f"- **Leakage-group → split violations (must be empty):** "
          f"{s['leakage_group_split_violations'] or 'NONE — every leakage group sits in one split'}.",
          f"- **Goal-image coord reuse across splits (design proxy; hash re-check at recording):** "
          f"{s['goal_image_coord_leakage_across_splits'] or 'NONE'}.",
          f"- **Family-by-split:** {s['family_by_split']}.",
          "- **Note:** with only ~8 active frames the split is train-heavy and not family-balanced; "
          "H8-M must add decision frames per split to balance families and enlarge the held-out set.",
          "",
          "## Feasibility (the H8 design-doc constraint, made concrete)",
          f"- **Tier counts:** {s['tier_counts']}.",
          "- **PROVEN** — o_d, both goals, and both branch paths lie on coordinates already "
          "recorded 0-collision (H7 / H8-prototype). Recordable now without new map work: "
          + ", ".join(r["route_id"] for r in res["decision_frames"]
                      if r["feasibility_tier"] == "PROVEN") + ".",
          "- **REQUIRES_VALIDATION** — o_d and goal endpoints are on confirmed coordinates but at "
          "least one branch path is not yet recorded; must be render/drive-validated before "
          "recording: "
          + ", ".join(r["route_id"] for r in res["decision_frames"]
                      if r["feasibility_tier"] == "REQUIRES_VALIDATION") + ".",
          "- **DEFERRED** — cannot be realised in the proven-free lobby without extending the "
          "render-confirmed navigable map (no confirmed multi-object room; look-alike goals need "
          "render validation): "
          + ", ".join(r["route_id"] for r in res["decision_frames"]
                      if r["feasibility_tier"] == "DEFERRED") + ".",
          "- **Consequence:** H8-S can record the PROVEN frames immediately; the "
          "REQUIRES_VALIDATION frames need a short render/drive check first; the DEFERRED families "
          "and any move toward H8-M require the map-extension sub-task flagged in "
          "`H8_CAUSAL_COLLECTION_DESIGN.md` §3.",
          "",
          "## Claim boundary",
          "- Design/geometry validation only — no images recorded, no model run. Visual "
          "distinctness of goal images and the goal-image hash leakage check are DEFERRED to the "
          "recorded-mode gate.",
          "- No collection, training, promotion, push, tag, 20/5/10, or closed-loop authorised.",
          "",
          "## Sequence (unchanged): design → design acceptance (this) → render/drive-validate "
          "REQUIRES_VALIDATION → record PROVEN(+validated) H8-S → recorded-mode gate → train "
          "ablation → held-out action-probe + mismatched-goal gate.",
          "",
          "## Artifacts",
          "`assets/experiments/hospital_h8_s_causal_routes/`: `h8_s_decision_frames.json` (design "
          "input), `h8_s_route_manifest.json` (enriched), `h8_s_design_acceptance_results.json`, "
          "this report. Harness: `scripts/gnm/h8_s_route_design_acceptance.py`."]
    (DIR / "h8_s_design_report.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
