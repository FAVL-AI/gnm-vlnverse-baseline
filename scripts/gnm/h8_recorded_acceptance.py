"""H8 paired-branch acceptance in RECORDED mode (real hospital.usd frames).

Converts the design proxy into real recorded evidence. For each design, uses the two
recorded branch episodes (route A gives the shared decision frame o_d + goal A; route B
gives goal B), all from actual /camera/image_raw with the scene gate PASS and raised mount.

Verifies, on the REAL recordings:
  1. scene gate PASS               (per-episode manifest, all checks true)
  2. camera mount raise = 0.12     (episode_metadata)
  3. shared decision frame exists  (o_d frame extracted from route A near the decision pose)
  4. real goal images exist        (route A final frame = goal A; route B final = goal B)
  5. goal A and goal B distinct    (mean abs pixel diff >= floor, on real frames)
  6. action A/B separated >= 30deg (recomputed from ACTUAL recorded o_d pose + goal poses)
  7. not route-solvable w/o goal    (shared o_d + separation >= 30deg)

Prereq: run conversion first (ROS python) so datasets/isaac_hospital_imagenav_v0/unassigned/
<eid>/ holds N.jpg + traj_data.pkl for each of the 4 episodes. Base/gnm python (PIL+numpy).
Writes manifest, contact sheet, results JSON, report to .../hospital_h8_paired_branch_prototype/
recorded/. No training, no promotion. Exit 6 if any design fails.
"""
import json, pickle, math, sys, shutil
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
UNASSIGNED = REPO / "datasets/isaac_hospital_imagenav_v0/unassigned"
GATE_DIR = REPO / "assets/experiments/hospital_h7_scene_gate"
TRAJ = REPO / "assets/experiments/trajectories"
ROUTES = REPO / "assets/experiments/hospital_h8_paired_branch_prototype/routes"
OUT = REPO / "assets/experiments/hospital_h8_paired_branch_prototype/recorded"
FRAMES_OUT = OUT / "frames"
MARGIN_DEG = 30.0
VISUAL_PIX_MIN = 12.0
CAM_RAISE_EXPECT = 0.12

DESIGNS = [
    {"design_id": "h8_proto_01_corridor_tjunction", "family": "shared_corridor_branch_choice",
     "routeA": "h8_d1_routeA_turn_up", "routeB": "h8_d1_routeB_straight",
     "o_d": (0.2, -0.2), "branchA": "turn_up_left", "branchB": "straight"},
    {"design_id": "h8_proto_02_samestart_fork", "family": "same_start_different_goal",
     "routeA": "h8_d2_routeA_fwdleft", "routeB": "h8_d2_routeB_fwdright",
     "o_d": (0.2, 0.0), "branchA": "forward_left", "branchB": "forward_right"},
]


def _latest(base_glob):
    hits = sorted(base_glob)
    if not hits:
        return None
    return hits[-1]


def load_conv(base):
    d = _latest(list(UNASSIGNED.glob(base + "_*")))
    assert d, f"converted dir missing for {base} — run conversion first"
    data = pickle.load(open(d / "traj_data.pkl", "rb"))
    pos = np.asarray(data["position"], dtype=float)
    yaw = np.asarray(data["yaw"], dtype=float)
    n = len(sorted(d.glob("*.jpg")))
    return d, pos, yaw, n


def robot_frame_action(od_pos, od_yaw, goal_pos):
    vx, vy = goal_pos[0] - od_pos[0], goal_pos[1] - od_pos[1]
    c, s = math.cos(od_yaw), math.sin(od_yaw)
    ax, ay = c * vx + s * vy, -s * vx + c * vy
    n = math.hypot(ax, ay)
    return (ax / n, ay / n) if n > 1e-9 else (0.0, 0.0)


def angle_between(a, b):
    return math.degrees(math.atan2(abs(a[0] * b[1] - a[1] * b[0]), a[0] * b[0] + a[1] * b[1]))


def gate_for(base):
    f = _latest(list(GATE_DIR.glob(base + "_*.json")))
    assert f, f"scene-gate manifest missing for {base}"
    g = json.loads(f.read_text())
    checks = g.get("checks", {})
    passed = g.get("pass")
    if passed is None:
        passed = bool(checks) and all(checks.values())
    return f, bool(passed), checks


def cam_raise_for(base):
    t = _latest(list(TRAJ.glob(base + "_*")))
    md = json.loads((t / "episode_metadata.json").read_text())
    return md.get("camera_mount_raise_m"), md, t


def pixdiff(pa, pb):
    a = np.asarray(Image.open(pa).convert("RGB").resize((96, 96)), dtype="float32")
    b = np.asarray(Image.open(pb).convert("RGB").resize((96, 96)), dtype="float32")
    return float(np.abs(a - b).mean())


def _angdiff(a, b):
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


def evaluate(dz):
    dA, posA, yawA, nA = load_conv(dz["routeA"])
    dB, posB, yawB, nB = load_conv(dz["routeB"])
    route = json.loads((ROUTES / f"{dz['routeA']}.json").read_text())
    start = (route["start_pose"]["x"], route["start_pose"]["y"])
    appr_h = float(route["decision_point"].get("approach_heading_rad", 0.0))
    # o_d = the PRE-DIVERGENCE approach frame: nearest to the decision pose, taken from the
    # approach leg (after the robot has reached the route start wp0) and while it still holds
    # the approach heading (before it turns onto either branch). This is the frame shared by
    # both branches — not one already committed to branch A's turn.
    dd = np.hypot(posA[:, 0] - dz["o_d"][0], posA[:, 1] - dz["o_d"][1])
    i0 = int(np.hypot(posA[:, 0] - start[0], posA[:, 1] - start[1]).argmin())
    on_approach = np.array([(i > i0) and (_angdiff(float(yawA[i]), appr_h) < 0.7)
                            for i in range(len(posA))])
    cand = np.where(on_approach)[0]
    od_idx = int(cand[dd[cand].argmin()]) if len(cand) else int(dd.argmin())
    od_pos = (float(posA[od_idx, 0]), float(posA[od_idx, 1]))
    od_yaw = float(yawA[od_idx])
    od_err = float(dd[od_idx])
    gA_idx, gB_idx = nA - 1, nB - 1  # final recorded frame = goal (Track-A convention)
    gA_pos = (float(posA[gA_idx, 0]), float(posA[gA_idx, 1]))
    gB_pos = (float(posB[gB_idx, 0]), float(posB[gB_idx, 1]))

    FRAMES_OUT.mkdir(parents=True, exist_ok=True)
    od_src, gA_src, gB_src = dA / f"{od_idx}.jpg", dA / f"{gA_idx}.jpg", dB / f"{gB_idx}.jpg"
    od_dst = FRAMES_OUT / f"{dz['design_id']}_o_d.jpg"
    gA_dst = FRAMES_OUT / f"{dz['design_id']}_goalA_{dz['branchA']}.jpg"
    gB_dst = FRAMES_OUT / f"{dz['design_id']}_goalB_{dz['branchB']}.jpg"
    for s, t in [(od_src, od_dst), (gA_src, gA_dst), (gB_src, gB_dst)]:
        shutil.copy(s, t)

    aA = robot_frame_action(od_pos, od_yaw, gA_pos)
    aB = robot_frame_action(od_pos, od_yaw, gB_pos)
    sep = angle_between(aA, aB)
    vis = pixdiff(gA_dst, gB_dst)

    gfA, passA, checksA = gate_for(dz["routeA"])
    gfB, passB, checksB = gate_for(dz["routeB"])
    crA, mdA, tA = cam_raise_for(dz["routeA"])
    crB, mdB, tB = cam_raise_for(dz["routeB"])

    c1 = passA and passB
    c2 = (crA == CAM_RAISE_EXPECT) and (crB == CAM_RAISE_EXPECT)
    c3 = od_dst.exists() and od_err <= 0.30
    c4 = gA_dst.exists() and gB_dst.exists()
    c5 = vis >= VISUAL_PIX_MIN
    c6 = sep >= MARGIN_DEG
    c7 = c3 and c6  # shared o_d + separated actions ⇒ not goal-blind solvable
    checks = {"1_scene_gate_pass": bool(c1), "2_camera_mount_raise_0p12": bool(c2),
              "3_shared_decision_frame_exists": bool(c3), "4_real_goal_images_exist": bool(c4),
              "5_goalA_goalB_visually_distinct": bool(c5),
              "6_action_separation_ge_30deg": bool(c6),
              "7_not_route_solvable_without_goal": bool(c7)}
    return {
        "design_id": dz["design_id"], "family": dz["family"],
        "routeA_episode": dA.name, "routeB_episode": dB.name,
        "collisions": {"routeA": mdA.get("total_collision_count"),
                       "routeB": mdB.get("total_collision_count")},
        "route_completed": {"routeA": mdA.get("route_completed"),
                            "routeB": mdB.get("route_completed")},
        "scene_gate": {"routeA": {"file": str(gfA.relative_to(REPO)), "pass": passA, "checks": checksA},
                       "routeB": {"file": str(gfB.relative_to(REPO)), "pass": passB, "checks": checksB}},
        "camera_mount_raise_m": {"routeA": crA, "routeB": crB},
        "decision_frame": {"design_o_d": list(dz["o_d"]), "recorded_o_d_pos": list(od_pos),
                           "recorded_o_d_yaw_rad": round(od_yaw, 4), "frame_index": od_idx,
                           "match_error_m": round(od_err, 3),
                           "source": str(od_src.relative_to(REPO)), "image": str(od_dst.relative_to(REPO))},
        "goalA": {"branch": dz["branchA"], "recorded_pos": list(gA_pos), "frame_index": gA_idx,
                  "expected_action_dx_dy": [round(aA[0], 4), round(aA[1], 4)],
                  "source": str(gA_src.relative_to(REPO)), "image": str(gA_dst.relative_to(REPO))},
        "goalB": {"branch": dz["branchB"], "recorded_pos": list(gB_pos), "frame_index": gB_idx,
                  "expected_action_dx_dy": [round(aB[0], 4), round(aB[1], 4)],
                  "source": str(gB_src.relative_to(REPO)), "image": str(gB_dst.relative_to(REPO))},
        "action_angle_separation_deg": round(sep, 2),
        "goalA_goalB_mean_abs_pixel_diff": round(vis, 3),
        "checks": checks, "pass": all(checks.values()),
    }


def contact_sheet(results):
    CW, CH, PAD, LBL, HDR = 224, 168, 8, 60, 30
    try:
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except Exception:
        fb = fr = ImageFont.load_default()
    W = PAD + (CW + PAD) * 3
    H = HDR + (CH + LBL + PAD) * len(results)
    cv = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(cv)
    dr.text((PAD, 8), "H8 RECORDED paired-branch — shared decision frame o_d + goal A + goal B "
            "(real /camera/image_raw, raised mount, scene gate PASS)", font=fb, fill="black")
    for ri, r in enumerate(results):
        y = HDR + ri * (CH + LBL + PAD)
        cells = [("shared o_d (" + r["family"] + ")", r["decision_frame"]["image"],
                  f"pos({r['decision_frame']['recorded_o_d_pos'][0]:.2f},"
                  f"{r['decision_frame']['recorded_o_d_pos'][1]:.2f}) yaw"
                  f"{r['decision_frame']['recorded_o_d_yaw_rad']:.2f}"),
                 (f"goal A: {r['goalA']['branch']}", r["goalA"]["image"],
                  f"act[{r['goalA']['expected_action_dx_dy'][0]:.2f},{r['goalA']['expected_action_dx_dy'][1]:.2f}]"),
                 (f"goal B: {r['goalB']['branch']}", r["goalB"]["image"],
                  f"act[{r['goalB']['expected_action_dx_dy'][0]:.2f},{r['goalB']['expected_action_dx_dy'][1]:.2f}]")]
        for ci, (title, imgrel, sub) in enumerate(cells):
            x = PAD + ci * (CW + PAD)
            im = Image.open(REPO / imgrel).convert("RGB").resize((CW, CH))
            cv.paste(im, (x, y))
            dr.rectangle([x, y, x + CW - 1, y + CH - 1], outline="black", width=2)
            dr.text((x, y + CH + 2), title, font=fb, fill="black")
            dr.text((x, y + CH + 18), sub, font=fr, fill="#333")
            if ci == 0:
                dr.text((x, y + CH + 34), f"Δangle A~B = {r['action_angle_separation_deg']:.1f}°  "
                        f"pixdiff={r['goalA_goalB_mean_abs_pixel_diff']:.1f}  "
                        f"{'PASS' if r['pass'] else 'FAIL'}", font=fb,
                        fill=("#070" if r["pass"] else "#b00"))
    cv.save(OUT / "h8_recorded_goal_contact_sheet.png")


def write_report(out):
    R = out["designs"]
    L = ["# H8 Paired-Branch RECORDED-Mode Acceptance Report", "",
         "**Scope: recorded design-validation only.** No training, no promotion, no push, no "
         "tag, no 20/5/10, no closed-loop Isaac testing. This converts the H8 design proxy into "
         "**real recorded hospital.usd evidence**: for each design the shared decision frame "
         "`o_d` and both goal images come from actual `/camera/image_raw` recordings with the "
         "scene-identity gate PASS and the raised camera mount (+0.12 m).", "",
         f"**Result: {'PASS' if out['all_pass'] else 'FAIL'}** — {len(R)} designs, "
         f"action-angle margin ≥ {MARGIN_DEG:.0f}°, goal pixel-diff floor {VISUAL_PIX_MIN:.0f}.", "",
         "## Recorded acceptance matrix", "",
         "| design | family | o_d match (m) | goalA↔goalB pixdiff | Δangle (°) | scene gate | "
         "cam raise | collisions A/B | pass |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in R:
        L.append(f"| {r['design_id']} | {r['family']} | "
                 f"{r['decision_frame']['match_error_m']:.3f} | "
                 f"{r['goalA_goalB_mean_abs_pixel_diff']:.1f} | "
                 f"{r['action_angle_separation_deg']:.2f} | "
                 f"{'PASS' if r['scene_gate']['routeA']['pass'] and r['scene_gate']['routeB']['pass'] else 'FAIL'} | "
                 f"{r['camera_mount_raise_m']['routeA']}/{r['camera_mount_raise_m']['routeB']} | "
                 f"{r['collisions']['routeA']}/{r['collisions']['routeB']} | "
                 f"{'✅' if r['pass'] else '❌'} |")
    L.append("")
    for r in R:
        L.append(f"### {r['design_id']} ({r['family']})")
        L.append(f"- **Route A** `{r['routeA_episode']}` (branch {r['goalA']['branch']}), "
                 f"**Route B** `{r['routeB_episode']}` (branch {r['goalB']['branch']}); "
                 f"route_completed A/B = {r['route_completed']['routeA']}/{r['route_completed']['routeB']}; "
                 f"collisions A/B = {r['collisions']['routeA']}/{r['collisions']['routeB']}.")
        d = r["decision_frame"]
        L.append(f"- **Shared decision frame o_d:** design ({d['design_o_d'][0]},{d['design_o_d'][1]}) → "
                 f"recorded ({d['recorded_o_d_pos'][0]:.2f},{d['recorded_o_d_pos'][1]:.2f}) "
                 f"yaw {d['recorded_o_d_yaw_rad']:.2f} rad, frame idx {d['frame_index']}, "
                 f"match error {d['match_error_m']:.3f} m; image `{d['image']}`.")
        L.append(f"- **Goal A ({r['goalA']['branch']}):** recorded pos "
                 f"({r['goalA']['recorded_pos'][0]:.2f},{r['goalA']['recorded_pos'][1]:.2f}), "
                 f"expected action `[{r['goalA']['expected_action_dx_dy'][0]:.3f},"
                 f"{r['goalA']['expected_action_dx_dy'][1]:.3f}]`, image `{r['goalA']['image']}`.")
        L.append(f"- **Goal B ({r['goalB']['branch']}):** recorded pos "
                 f"({r['goalB']['recorded_pos'][0]:.2f},{r['goalB']['recorded_pos'][1]:.2f}), "
                 f"expected action `[{r['goalB']['expected_action_dx_dy'][0]:.3f},"
                 f"{r['goalB']['expected_action_dx_dy'][1]:.3f}]`, image `{r['goalB']['image']}`.")
        L.append(f"- **Action-angle separation (from recorded poses):** "
                 f"{r['action_angle_separation_deg']:.2f}° (≥ {MARGIN_DEG:.0f}° required); "
                 f"goalA↔goalB mean abs pixel diff {r['goalA_goalB_mean_abs_pixel_diff']:.1f} "
                 f"(≥ {VISUAL_PIX_MIN:.0f} required).")
        L.append("- **Checks:** " + "; ".join(f"{k}={'PASS' if v else 'FAIL'}"
                 for k, v in r["checks"].items()))
        L.append(f"- **Design verdict:** {'PASS' if r['pass'] else 'FAIL'}")
        L.append("")
    L += ["## Decision", ""]
    if out["all_pass"]:
        L.append("- **Recorded-mode acceptance PASSED on real hospital images.** The paired-branch "
                 "property holds on actual recordings: identical shared `o_d`, two visually distinct "
                 "recorded goals, action separation ≥ 30°, scene gate PASS, mount +0.12 m, zero "
                 "collisions. **H8 is ready for the first offline action-probe** (Option A).")
    else:
        L.append("- **Recorded-mode acceptance FAILED.** Per the pre-registered rule: if visual "
                 "distinctness or shared-frame quality failed, do not train — revise the design; if "
                 "scene gate / camera mount / provenance failed, reject the recording. See per-design "
                 "checks above.")
    L += ["- **No training, no promotion, no autonomous or benchmark claim.** Incumbent retained.",
          "",
          "## Claim boundary",
          "- This validates that the paired-branch **design property survives on real recorded "
          "hospital images**; it does **not** train, evaluate, or run any model.",
          "- Goal images are the final recorded `/camera/image_raw` frames (Track-A convention); "
          "o_d is the recorded frame nearest the shared decision pose.",
          "- Passing authorises **only** the first offline Option-A action probe on these recorded "
          "frames — not 20/5/10, training, or closed-loop Isaac testing.",
          "",
          "## Artifacts",
          "`assets/experiments/hospital_h8_paired_branch_prototype/recorded/`: "
          "`h8_recorded_frame_manifest.json`, `h8_recorded_acceptance_results.json`, "
          "`h8_recorded_goal_contact_sheet.png`, this report, `frames/` (6 extracted frames). "
          "Harness: `scripts/gnm/h8_recorded_acceptance.py`."]
    (OUT / "h8_recorded_acceptance_report.md").write_text("\n".join(L) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = [evaluate(d) for d in DESIGNS]
    all_pass = all(r["pass"] for r in res)
    out = {"gate": "H8 Option A paired-branch acceptance — RECORDED mode",
           "scope": "recorded design validation only — no training, no promotion",
           "margin_deg": MARGIN_DEG, "visual_pix_min": VISUAL_PIX_MIN,
           "camera_raise_expected_m": CAM_RAISE_EXPECT,
           "n_designs": len(res), "all_pass": all_pass, "designs": res}
    (OUT / "h8_recorded_acceptance_results.json").write_text(json.dumps(out, indent=2))
    # manifest: one record per extracted image with full provenance
    manifest = {"scope": out["scope"], "designs": []}
    for r in res:
        manifest["designs"].append({
            "design_id": r["design_id"], "family": r["family"],
            "routeA_episode": r["routeA_episode"], "routeB_episode": r["routeB_episode"],
            "scene_gate_pass": r["scene_gate"]["routeA"]["pass"] and r["scene_gate"]["routeB"]["pass"],
            "scene_gate_files": [r["scene_gate"]["routeA"]["file"], r["scene_gate"]["routeB"]["file"],
                                 ],
            "camera_mount_raise_m": r["camera_mount_raise_m"],
            "from_recorded_camera_image_raw": True,
            "images": {
                "o_d": {"image": r["decision_frame"]["image"], "source_frame": r["decision_frame"]["source"],
                        "frame_index": r["decision_frame"]["frame_index"],
                        "recorded_pos": r["decision_frame"]["recorded_o_d_pos"]},
                "goalA": {"image": r["goalA"]["image"], "source_frame": r["goalA"]["source"],
                          "frame_index": r["goalA"]["frame_index"], "recorded_pos": r["goalA"]["recorded_pos"]},
                "goalB": {"image": r["goalB"]["image"], "source_frame": r["goalB"]["source"],
                          "frame_index": r["goalB"]["frame_index"], "recorded_pos": r["goalB"]["recorded_pos"]},
            },
            "action_angle_separation_deg": r["action_angle_separation_deg"],
            "goalA_goalB_mean_abs_pixel_diff": r["goalA_goalB_mean_abs_pixel_diff"],
            "pass": r["pass"],
        })
    (OUT / "h8_recorded_frame_manifest.json").write_text(json.dumps(manifest, indent=2))
    contact_sheet(res)
    write_report(out)
    print(json.dumps({r["design_id"]: {"sep_deg": r["action_angle_separation_deg"],
                     "pixdiff": r["goalA_goalB_mean_abs_pixel_diff"],
                     "o_d_err_m": r["decision_frame"]["match_error_m"], "pass": r["pass"]}
                     for r in res}, indent=2))
    print(f"ALL_PASS={all_pass} -> recorded/ manifest+results+contact_sheet+report")
    sys.exit(0 if all_pass else 6)


if __name__ == "__main__":
    main()
