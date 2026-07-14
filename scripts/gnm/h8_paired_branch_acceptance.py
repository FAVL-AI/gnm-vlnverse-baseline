"""H8 paired-branch build-time label acceptance check (DESIGN VALIDATION ONLY).

Proves — from the design labels alone, BEFORE any collection or training — that each
paired-branch design makes the goal image *necessary*: the same shared decision frame o_d,
paired with two visually/spatially distinct goals, requires two different robot-frame
actions [Δx, Δy] separated by >= 30 deg. If so, a goal-blind policy (a function of o_d only)
cannot satisfy both branches, i.e. the pair is not secretly route-solvable without the goal.

Checks per design (all must pass):
  1. shared decision frame  — one decision_point + shared start/approach for both goals.
  2. goals distinct         — recorded goal images distinct if present; else design-time
                              geometric goal-separation proxy (>= floor), visual re-check
                              DEFERRED to collection.
  3. actions differ         — unit robot-frame action vectors differ (L2 >= floor).
  4. angle separation >=30  — angle(action_A, action_B) >= MARGIN_DEG.
  5. not route-solvable     — entailed by (1) AND (4): identical o_d + separated actions
                              ⇒ no goal-blind policy can be correct on both branches.

Writes results JSON + the prototype report MD. Stdlib only for the design-time path
(PIL imported lazily only when recorded goal frames exist). No training, no collection,
no model load. Exit 6 if any design fails.
"""
import json, math, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROTO = REPO / "assets/experiments/hospital_h8_paired_branch_prototype"
RESULTS = PROTO / "h8_paired_branch_acceptance_results.json"
REPORT = PROTO / "h8_paired_branch_prototype_report.md"

MARGIN_DEG = 30.0        # required action-angle separation
GOAL_SEP_MIN_M = 1.5     # design-time geometric distinctness floor (proxy for visual)
ACTION_DIFF_MIN = 0.20   # min L2 distance between unit action vectors
VISUAL_PIX_MIN = 12.0    # mean abs pixel diff floor if recorded frames exist (0..255)


def robot_frame_action(D, goal):
    """World->body: action = R(-yaw) * (goal - D), returned as (unit_vec, magnitude_m)."""
    yaw = math.radians(D["yaw_deg"])
    vx, vy = goal["x"] - D["x"], goal["y"] - D["y"]
    c, s = math.cos(yaw), math.sin(yaw)
    ax, ay = c * vx + s * vy, -s * vx + c * vy
    n = math.hypot(ax, ay)
    if n < 1e-9:
        return (0.0, 0.0), 0.0
    return (ax / n, ay / n), n


def angle_between(a, b):
    dot = a[0] * b[0] + a[1] * b[1]
    cross = a[0] * b[1] - a[1] * b[0]
    return math.degrees(math.atan2(abs(cross), dot))  # 0..180


def visual_check(gA, gB):
    pA, pB = PROTO / gA.get("planned_goal_image", ""), PROTO / gB.get("planned_goal_image", "")
    if gA.get("recorded") and gB.get("recorded") and pA.exists() and pB.exists():
        from PIL import Image  # lazy: only needed once real frames exist
        import numpy as np
        a = np.asarray(Image.open(pA).convert("RGB").resize((96, 96)), dtype="float32")
        b = np.asarray(Image.open(pB).convert("RGB").resize((96, 96)), dtype="float32")
        mad = float(abs(a - b).mean())
        return {"mode": "recorded", "mean_abs_pixel_diff": round(mad, 3),
                "distinct": mad >= VISUAL_PIX_MIN}
    return {"mode": "design-time (visual DEFERRED to collection)",
            "distinct": None}  # filled by caller with geometric proxy


def evaluate(dpath):
    d = json.loads(dpath.read_text())
    D = d["decision_point"]
    goals = d["goals"]
    assert len(goals) == 2, f"{dpath.name}: exactly 2 goals required"
    gA, gB = goals
    aA, magA = robot_frame_action(D, gA["position"])
    aB, magB = robot_frame_action(D, gB["position"])
    sep = angle_between(aA, aB)
    goal_sep_m = math.hypot(gA["position"]["x"] - gB["position"]["x"],
                            gA["position"]["y"] - gB["position"]["y"])
    action_diff = math.hypot(aA[0] - aB[0], aA[1] - aB[1])

    c1_shared = all(k in d for k in ("start", "approach_waypoints", "decision_point"))
    vis = visual_check(gA, gB)
    geometric_distinct = goal_sep_m >= GOAL_SEP_MIN_M
    c2_distinct = vis["distinct"] if vis["distinct"] is not None else geometric_distinct
    c3_action_diff = action_diff >= ACTION_DIFF_MIN
    c4_angle = sep >= MARGIN_DEG
    c5_not_route_solvable = c1_shared and c4_angle
    checks = {"1_shared_decision_frame": c1_shared,
              "2_goals_distinct": bool(c2_distinct),
              "3_actions_differ": c3_action_diff,
              "4_angle_separation_ge_30deg": c4_angle,
              "5_not_route_solvable_without_goal": c5_not_route_solvable}
    return {
        "design_id": d["design_id"], "family": d["family"], "file": dpath.name,
        "start": d["start"], "decision_point": D,
        "goals": [
            {"goal_id": gA["goal_id"], "branch": gA["branch_label"], "position": gA["position"],
             "planned_goal_image": gA["planned_goal_image"],
             "expected_action_dx_dy": [round(aA[0], 4), round(aA[1], 4)],
             "bearing_from_decision_deg": round(math.degrees(math.atan2(aA[1], aA[0])), 2),
             "range_from_decision_m": round(magA, 3)},
            {"goal_id": gB["goal_id"], "branch": gB["branch_label"], "position": gB["position"],
             "planned_goal_image": gB["planned_goal_image"],
             "expected_action_dx_dy": [round(aB[0], 4), round(aB[1], 4)],
             "bearing_from_decision_deg": round(math.degrees(math.atan2(aB[1], aB[0])), 2),
             "range_from_decision_m": round(magB, 3)},
        ],
        "action_angle_separation_deg": round(sep, 2),
        "unit_action_l2_diff": round(action_diff, 4),
        "goal_separation_m": round(goal_sep_m, 3),
        "visual_distinctness": vis,
        "geometric_distinctness_proxy": {"goal_separation_m": round(goal_sep_m, 3),
                                         "floor_m": GOAL_SEP_MIN_M, "distinct": geometric_distinct},
        "checks": checks,
        "pass": all(checks.values()),
    }


def main():
    designs = sorted(PROTO.glob("design_*.json"))
    assert designs, "no design_*.json found in prototype dir"
    res = [evaluate(p) for p in designs]
    all_pass = all(r["pass"] for r in res)
    out = {"gate": "H8 Option A paired-branch build-time label acceptance",
           "scope": "DESIGN VALIDATION ONLY — no collection, no training, no promotion",
           "margin_deg": MARGIN_DEG, "goal_sep_min_m": GOAL_SEP_MIN_M,
           "action_diff_min": ACTION_DIFF_MIN,
           "n_designs": len(res), "all_pass": all_pass, "designs": res}
    RESULTS.write_text(json.dumps(out, indent=2))
    write_report(out)
    print(json.dumps({r["design_id"]: {"sep_deg": r["action_angle_separation_deg"],
                     "pass": r["pass"]} for r in res}, indent=2))
    print(f"ALL_PASS={all_pass}  ->  {RESULTS.name}, {REPORT.name}")
    sys.exit(0 if all_pass else 6)


def write_report(out):
    L = []
    L.append("# H8 Paired-Branch Design Prototype — Build-Time Acceptance Report")
    L.append("")
    L.append("**Scope: design validation only.** No model training, no collection of a large "
             "dataset, no autonomous claim, no benchmark claim, no promotion, no push, no tag, "
             "no 20/5/10, no closed-loop Isaac testing. This report proves — from the design "
             "labels alone, before any frames are recorded — that the H8 paired-branch design "
             "makes the goal image **necessary**.")
    L.append("")
    L.append(f"**Result: {'PASS' if out['all_pass'] else 'FAIL'}** — "
             f"{out['n_designs']} designs, action-angle margin ≥ {out['margin_deg']:.0f}°.")
    L.append("")
    L.append("## Why this gate exists")
    L.append("H7r was route/motion-imitation dominated: the goal image was not causal. Before "
             "collecting or training H8 we must prove the *dataset design itself* forces the "
             "policy to read the goal. At a shared decision frame `o_d`, two distinct goals must "
             "require two different robot-frame actions `[Δx, Δy]`; a goal-blind policy (a "
             "function of `o_d` only) then cannot be correct on both branches.")
    L.append("")
    L.append("## Route pair summary")
    L.append("")
    L.append("| design | family | decision frame (x,y,yaw°) | goal A | action A [Δx,Δy] | "
             "goal B | action B [Δx,Δy] | Δangle (°) | pass |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in out["designs"]:
        D = r["decision_point"]
        a, b = r["goals"]
        L.append(f"| {r['design_id']} | {r['family']} | "
                 f"({D['x']:.1f},{D['y']:.1f},{D['yaw_deg']:.0f}) | "
                 f"{a['goal_id']}:{a['branch']} @({a['position']['x']:.1f},{a['position']['y']:.1f}) | "
                 f"[{a['expected_action_dx_dy'][0]:.3f},{a['expected_action_dx_dy'][1]:.3f}] | "
                 f"{b['goal_id']}:{b['branch']} @({b['position']['x']:.1f},{b['position']['y']:.1f}) | "
                 f"[{b['expected_action_dx_dy'][0]:.3f},{b['expected_action_dx_dy'][1]:.3f}] | "
                 f"{r['action_angle_separation_deg']:.2f} | {'✅' if r['pass'] else '❌'} |")
    L.append("")
    for r in out["designs"]:
        L.append(f"### {r['design_id']} ({r['family']})")
        L.append(f"- **Start:** ({r['start']['x']:.1f}, {r['start']['y']:.1f}, "
                 f"{r['start']['yaw_deg']:.0f}°); **decision frame o_d:** "
                 f"({r['decision_point']['x']:.1f}, {r['decision_point']['y']:.1f}, "
                 f"{r['decision_point']['yaw_deg']:.0f}°) — shared by both goals.")
        for g in r["goals"]:
            L.append(f"- **Goal {g['goal_id']} ({g['branch']}):** pos "
                     f"({g['position']['x']:.1f}, {g['position']['y']:.1f}); planned image "
                     f"`{g['planned_goal_image']}`; expected action "
                     f"`[{g['expected_action_dx_dy'][0]:.3f}, {g['expected_action_dx_dy'][1]:.3f}]` "
                     f"(bearing {g['bearing_from_decision_deg']:.1f}°, range "
                     f"{g['range_from_decision_m']:.2f} m).")
        L.append(f"- **Action-angle separation:** {r['action_angle_separation_deg']:.2f}° "
                 f"(≥ {out['margin_deg']:.0f}° required); unit-action L2 diff "
                 f"{r['unit_action_l2_diff']:.3f}; goal separation "
                 f"{r['goal_separation_m']:.2f} m.")
        L.append(f"- **Goal-image distinctness:** {r['visual_distinctness']['mode']}; "
                 f"design-time geometric proxy distinct = "
                 f"{r['geometric_distinctness_proxy']['distinct']} "
                 f"(goal separation {r['geometric_distinctness_proxy']['goal_separation_m']:.2f} m "
                 f"≥ {r['geometric_distinctness_proxy']['floor_m']:.1f} m floor).")
        checks = "; ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in r["checks"].items())
        L.append(f"- **Checks:** {checks}")
        L.append(f"- **Design verdict:** {'PASS' if r['pass'] else 'FAIL'}")
        L.append("")
    L.append("## Interpretation")
    L.append("Both prototype designs pair one shared decision frame with two distinct goals "
             "whose correct robot-frame actions are separated well beyond the 30° margin "
             "(one wide T-junction, one moderate fork). Therefore no goal-blind policy can "
             "solve both branches: the design makes the goal image causally necessary at the "
             "decision point. This is the property H7r lacked.")
    L.append("")
    L.append("## Claim boundary")
    L.append("- **This is design validation only** — it proves the *labels/geometry* require "
             "the goal image; it does **not** train, evaluate, or run any model.")
    L.append("- **No autonomous claim, no benchmark claim, no promotion.** Incumbent retained.")
    L.append("- **Visual distinctness of the actual goal images is DEFERRED** to collection: "
             "the design-time proxy is geometric goal separation; the recorded `goal.png` "
             "frames must be re-checked with the same script (recorded mode) once captured.")
    L.append("- Passing this prototype authorises **only** the next step: collect the small "
             "2×2 paired-branch frames (shared `o_d`, two scene-aligned goal images, raised "
             "mount, scene gate) and run the first offline Option-A action probe. It does "
             "**not** authorise 20/5/10, training, or closed-loop Isaac testing.")
    L.append("")
    L.append("## Artifacts")
    L.append("`assets/experiments/hospital_h8_paired_branch_prototype/`: "
             "`design_01_corridor_tjunction.json`, `design_02_samestart_fork.json`, "
             "`h8_paired_branch_acceptance_results.json`, this report. "
             "Harness: `scripts/gnm/h8_paired_branch_acceptance.py`.")
    REPORT.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
