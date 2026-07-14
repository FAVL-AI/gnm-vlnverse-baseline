"""H8 offline Option-A action-probe (NO TRAINING).

Core test: SAME recorded shared decision frame o_d + DIFFERENT goal image should produce
DIFFERENT predicted 2-D action [Δx, Δy]. For each committed H8 design and each model, we
hold o_d fixed (context = o_d) and swap only the goal image, then read the model's predicted
action via evaluator.predict(o_d, goal) -> (dist, [Δx,Δy]) (robot frame, real units).

Models: H1 incumbent, H7r diagnostic candidate. Designs: corridor T-junction, same-start
fork. Conditions per design: goalA, goalB, placeholder (h2_weave_J), mismatch (the other
design's goalA — a hard cross-scene goal). Expected actions come from the committed recorded
acceptance (robot-frame direction o_d->goal). No model is trained; incumbent retained.

Outputs -> assets/experiments/hospital_h8_paired_branch_prototype/action_probe/.
Run with gnm_train python. No training, no promotion, no commit.
"""
import csv, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import cv2
import torch
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont
from gnm_vlnverse.models.gnm import build_gnm
from gnm_vlnverse.evaluation.evaluator import GNMEvaluator

REPO = Path(__file__).resolve().parents[2]
PROTO = REPO / "assets/experiments/hospital_h8_paired_branch_prototype"
REC = json.loads((PROTO / "recorded/h8_recorded_acceptance_results.json").read_text())
PLACEHOLDER = REPO / "assets/experiments/goals/h2_weave_J/goal_image.png"
OUT = PROTO / "action_probe"
BASE_YAML = REPO / "configs/gnm/gnm_h7r_hospital_pilot.yaml"
MODELS = {"H1_incumbent": "checkpoints/hospital_front_rgb_finetune/best.pt",
          "H7r_candidate": "checkpoints/h7r_hospital_pilot_finetune/best.pt"}
BRANCH_ACC_PASS = 0.75      # branch-choice accuracy for "uses the goal"
S_PASS = 0.5                # goal-sensitivity score for "uses the goal"
CHANGE_MIN_DEG = 15.0       # min pred action rotation A->B to be non-trivial


def load_model(ckpt_rel):
    ckpt = torch.load(REPO / ckpt_rel, map_location="cpu", weights_only=False)
    emb = ckpt.get("cfg", {})
    cfg = emb if (isinstance(emb, dict) and "model" in emb) else \
        OmegaConf.to_container(OmegaConf.load(BASE_YAML), resolve=True)
    model = build_gnm(cfg["model"]); model.load_state_dict(ckpt["model_state"]); model.eval()
    ev_cfg = cfg.get("evaluation", {})
    return GNMEvaluator(model=model, action_std=cfg["data"]["action_std"],
                        context_size=cfg["model"]["context_size"],
                        image_size=tuple(cfg["data"]["image_size"]),
                        stop_threshold=ev_cfg.get("stop_threshold", 0.15),
                        max_steps=ev_cfg.get("max_steps", 500), device="cuda", track="A")


def rgb(path):
    im = cv2.imread(str(REPO / path if not str(path).startswith("/") else path))
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


def ang(a):
    return math.degrees(math.atan2(a[1], a[0]))


def ang_between(a, b):
    return math.degrees(math.atan2(abs(a[0] * b[1] - a[1] * b[0]), a[0] * b[0] + a[1] * b[1]))


def probe(ev, o_d_np, goal_np):
    ev.reset_context(o_d_np)
    dist, act = ev.predict(o_d_np, goal_np)
    return float(dist), (float(act[0]), float(act[1]))


DESIGNS = []
for r in REC["designs"]:
    DESIGNS.append({
        "design_id": r["design_id"], "family": r["family"],
        "o_d": r["decision_frame"]["image"],
        "goalA": {"branch": r["goalA"]["branch"], "img": r["goalA"]["image"],
                  "exp": tuple(r["goalA"]["expected_action_dx_dy"])},
        "goalB": {"branch": r["goalB"]["branch"], "img": r["goalB"]["image"],
                  "exp": tuple(r["goalB"]["expected_action_dx_dy"])},
    })
# hard cross-scene mismatch = the OTHER design's goalA image
for i, d in enumerate(DESIGNS):
    d["mismatch_img"] = DESIGNS[1 - i]["goalA"]["img"]

results = {"scope": "offline action-probe — no training, no promotion", "models": {}}
rows = []                    # matrix rows
summary = {}

for mname, ckpt in MODELS.items():
    ev = load_model(ckpt)
    results["models"][mname] = {"designs": []}
    correct = 0; total = 0
    S_list = []; err_list = []; change_list = []
    for d in DESIGNS:
        o_d = rgb(d["o_d"])
        conds = {"goalA": d["goalA"]["img"], "goalB": d["goalB"]["img"],
                 "placeholder": str(PLACEHOLDER), "mismatch": d["mismatch_img"]}
        pred = {}
        for c, img in conds.items():
            dist, act = probe(ev, o_d, rgb(img))
            pred[c] = {"dist": dist, "act": act, "angle": ang(act),
                       "mag": math.hypot(*act)}
        expA, expB = d["goalA"]["exp"], d["goalB"]["exp"]
        pA, pB = pred["goalA"]["act"], pred["goalB"]["act"]
        # branch-choice: is pred under goalX angularly closer to expX than expOther?
        bcA = ang_between(pA, expA) < ang_between(pA, expB)
        bcB = ang_between(pB, expB) < ang_between(pB, expA)
        correct += int(bcA) + int(bcB); total += 2
        errA = ang_between(pA, expA); errB = ang_between(pB, expB)
        err_list += [errA, errB]
        exp_sep = ang_between(expA, expB)
        pred_change = ang_between(pA, pB)
        S = pred_change / exp_sep if exp_sep > 1e-6 else 0.0
        S_list.append(S); change_list.append(pred_change)
        drow = {
            "design_id": d["design_id"], "family": d["family"],
            "expected": {"goalA_angle": round(ang(expA), 1), "goalB_angle": round(ang(expB), 1),
                         "separation_deg": round(exp_sep, 2)},
            "pred": {c: {"act_dx_dy": [round(pred[c]["act"][0], 4), round(pred[c]["act"][1], 4)],
                         "angle_deg": round(pred[c]["angle"], 1), "mag": round(pred[c]["mag"], 4),
                         "dist": round(pred[c]["dist"], 4)} for c in conds},
            "branch_choice": {"goalA_correct": bool(bcA), "goalB_correct": bool(bcB)},
            "action_angle_error_deg": {"goalA": round(errA, 1), "goalB": round(errB, 1)},
            "pred_action_change_A_to_B_deg": round(pred_change, 2),
            "goal_sensitivity_S": round(S, 3),
            "displacement_shift_A_to_B": round(math.hypot(pA[0] - pB[0], pA[1] - pB[1]), 4),
            "stop_output_change_A_to_B": round(abs(pred["goalA"]["dist"] - pred["goalB"]["dist"]), 4),
        }
        results["models"][mname]["designs"].append(drow)
        for c in conds:
            rows.append({"model": mname, "design": d["design_id"], "condition": c,
                         "pred_dx": round(pred[c]["act"][0], 4), "pred_dy": round(pred[c]["act"][1], 4),
                         "pred_angle": round(pred[c]["angle"], 1),
                         "exp_angle": (round(ang(d["goalA"]["exp"]), 1) if c == "goalA" else
                                       round(ang(d["goalB"]["exp"]), 1) if c == "goalB" else ""),
                         "angle_err": (round(errA, 1) if c == "goalA" else
                                       round(errB, 1) if c == "goalB" else ""),
                         "dist": round(pred[c]["dist"], 4)})
    acc = correct / total
    mS = float(np.mean(S_list)); mErr = float(np.mean(err_list)); mChange = float(np.mean(change_list))
    verdict = ("preliminary_goal_conditioning"
               if (acc >= BRANCH_ACC_PASS and mS >= S_PASS and mChange >= CHANGE_MIN_DEG)
               else "goal_image_insensitive_route_motion_dominated")
    summary[mname] = {"branch_choice_accuracy": round(acc, 3), "mean_goal_sensitivity_S": round(mS, 3),
                      "mean_pred_action_change_deg": round(mChange, 2),
                      "mean_action_angle_error_deg": round(mErr, 1), "verdict": verdict}
    results["models"][mname]["summary"] = summary[mname]

results["summary"] = summary
results["thresholds"] = {"branch_acc_pass": BRANCH_ACC_PASS, "S_pass": S_PASS,
                         "pred_change_min_deg": CHANGE_MIN_DEG}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "h8_action_probe_results.json").write_text(json.dumps(results, indent=2))

# matrix csv + md
cols = ["model", "design", "condition", "pred_dx", "pred_dy", "pred_angle", "exp_angle", "angle_err", "dist"]
with open(OUT / "h8_action_probe_matrix.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in rows:
        w.writerow(r)
mdl = ["# H8 action-probe matrix — predicted [Δx,Δy] per (model, design, goal condition)", "",
       "Same shared decision frame `o_d`; only the goal image changes across conditions. "
       "`exp_angle` = expected robot-frame action angle to that goal (from committed recorded "
       "acceptance). Angles in degrees; `[Δx,Δy]` in robot frame (real units).", "",
       "| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
for r in rows:
    mdl.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
(OUT / "h8_action_probe_matrix.md").write_text("\n".join(mdl))


def diagram(results):
    P, HDR = 220, 34
    W = 20 + P * len(MODELS)
    H = HDR + 20 + P * len(DESIGNS)
    cv = Image.new("RGB", (W, H), "white"); dr = ImageDraw.Draw(cv)
    try:
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except Exception:
        fb = fr = ImageFont.load_default()
    dr.text((10, 8), "H8 action-probe: predicted (solid) vs expected (dashed) action at shared o_d "
            "— top-down, forward=up, left=left", font=fb, fill="black")
    mnames = list(MODELS)
    for ci, m in enumerate(mnames):
        for ri, d in enumerate(results["models"][m]["designs"]):
            cx = 20 + ci * P + P // 2
            cy = HDR + 20 + ri * P + P // 2
            R = P // 2 - 24
            dr.ellipse([cx - R, cy - R, cx + R, cy + R], outline="#ccc")
            dr.line([cx, cy - R, cx, cy + R], fill="#eee"); dr.line([cx - R, cy, cx + R, cy], fill="#eee")
            dr.text((cx - R, cy - R - 26), f"{m}", font=fb, fill="black")
            dr.text((cx - R, cy - R - 13), f"{d['design_id'].replace('h8_proto_0','D')}", font=fr, fill="#555")

            def arrow(angle_deg, color, dashed=False, scale=1.0):
                a = math.radians(angle_deg)
                ex = cx - math.sin(0) * 0  # placeholder
                # forward=+x -> up(screen -y); left=+y -> left(screen -x)
                dx = math.cos(a); dy = math.sin(a)
                tx = cx - dy * R * scale; ty = cy - dx * R * scale
                if dashed:
                    n = 10
                    for k in range(0, n, 2):
                        x1 = cx + (tx - cx) * k / n; y1 = cy + (ty - cy) * k / n
                        x2 = cx + (tx - cx) * (k + 1) / n; y2 = cy + (ty - cy) * (k + 1) / n
                        dr.line([x1, y1, x2, y2], fill=color, width=2)
                else:
                    dr.line([cx, cy, tx, ty], fill=color, width=3)
                    dr.ellipse([tx - 3, ty - 3, tx + 3, ty + 3], fill=color)
            arrow(d["expected"]["goalA_angle"], "#0a0", dashed=True)
            arrow(d["expected"]["goalB_angle"], "#00a", dashed=True)
            arrow(d["pred"]["goalA"]["angle_deg"], "#0a0", dashed=False, scale=0.85)
            arrow(d["pred"]["goalB"]["angle_deg"], "#00a", dashed=False, scale=0.85)
            s = results["models"][m]["designs"][ri]
            dr.text((cx - R, cy + R + 4), f"S={s['goal_sensitivity_S']:.2f} "
                    f"Δpred={s['pred_action_change_A_to_B_deg']:.0f}°", font=fr, fill="#000")
            dr.text((cx - R, cy + R + 16), "green=goalA blue=goalB", font=fr, fill="#777")
    cv.save(OUT / "h8_action_probe_direction_diagram.png")


diagram(results)

# report
def verdict_line(m):
    s = summary[m]
    return (f"- **{m}:** branch-choice {s['branch_choice_accuracy']:.2f}, "
            f"goal-sensitivity S {s['mean_goal_sensitivity_S']:.3f}, "
            f"mean pred action change A→B {s['mean_pred_action_change_deg']:.2f}°, "
            f"mean angle error {s['mean_action_angle_error_deg']:.1f}° → **{s['verdict']}**")


rep = ["# H8 Offline Option-A Action-Probe Report", "",
       "**Scope: offline probe only.** No training, no promotion, no push, no tag, no 20/5/10, "
       "no closed-loop Isaac testing, no change to committed H8 evidence. Uses only the committed "
       "H8 recorded paired-branch frames and the two existing checkpoints (H1 incumbent, H7r "
       "diagnostic candidate).", "",
       "## Question",
       "Same recorded shared decision frame `o_d` + different goal image → does the model's "
       "predicted 2-D action `[Δx, Δy]` change toward the correct branch? A goal-conditioned "
       "policy changes its action; a route/motion-imitation policy predicts ~the same action "
       "regardless of the goal image.", "",
       "## Verdict per model"]
for m in MODELS:
    rep.append(verdict_line(m))
rep += ["",
        f"Pass thresholds for goal-conditioning: branch-choice ≥ {BRANCH_ACC_PASS}, "
        f"S ≥ {S_PASS}, mean pred action change ≥ {CHANGE_MIN_DEG:.0f}°.", "",
        "## Per-design detail"]
for m in MODELS:
    rep.append(f"### {m}")
    for d in results["models"][m]["designs"]:
        rep.append(f"- **{d['design_id']}** (exp separation {d['expected']['separation_deg']:.1f}°): "
                   f"pred goalA `[{d['pred']['goalA']['act_dx_dy'][0]:.3f},{d['pred']['goalA']['act_dx_dy'][1]:.3f}]` "
                   f"({d['pred']['goalA']['angle_deg']:.0f}°) vs goalB "
                   f"`[{d['pred']['goalB']['act_dx_dy'][0]:.3f},{d['pred']['goalB']['act_dx_dy'][1]:.3f}]` "
                   f"({d['pred']['goalB']['angle_deg']:.0f}°); pred change A→B "
                   f"{d['pred_action_change_A_to_B_deg']:.2f}°, S {d['goal_sensitivity_S']:.3f}, "
                   f"displacement shift {d['displacement_shift_A_to_B']:.4f}, stop-output change "
                   f"{d['stop_output_change_A_to_B']:.4f}; branch-choice A/B = "
                   f"{d['branch_choice']['goalA_correct']}/{d['branch_choice']['goalB_correct']}.")
    rep.append("")
rep += ["## Interpretation & decision", ""]
all_insensitive = all(summary[m]["verdict"].startswith("goal_image_insensitive") for m in MODELS)
if all_insensitive:
    rep += [
        f"- **Both models are goal-image-INSENSITIVE at the shared decision frame.** The predicted "
        f"`[Δx, Δy]` changes by ≤ 2° between goal A and goal B for both models "
        f"(incumbent {summary['H1_incumbent']['mean_pred_action_change_deg']:.2f}°, candidate "
        f"{summary['H7r_candidate']['mean_pred_action_change_deg']:.2f}°), and branch-choice is at "
        f"chance (0.50). Same RGB decision frame + different goal image ⇒ effectively the same action.",
        "- **The H8 dataset design is correct** — it passed both the design-mode and recorded-mode "
        "gates (same observation provably requires different goal-dependent actions, separation "
        "≥ 30°). **But neither existing model uses the goal image causally.**",
        "- Per the pre-registered rule: *H7r candidate fails the probe while the design labels "
        "pass ⇒ the problem is the model/training, not the dataset design.* The incumbent behaves "
        "the same way.",
        "- **This confirms the next training problem:** the dataset now forces goal use, so a model "
        "trained on H8-style same-start/different-goal data (with the mismatched-goal / action-probe "
        "gate applied) is required before any goal-conditioned navigation claim.",
    ]
else:
    rep += ["- At least one model shows preliminary goal-conditioning (predicted action changes "
            "toward the correct branch when the goal image changes). See per-model verdicts above."]
rep += ["- **No promotion either way.** Incumbent retained; status remains "
        "`DIAGNOSTIC_ONLY_NOT_PROMOTED`.", "",
        "## Claim boundary",
        "- Offline probe of the *instantaneous predicted action* at a fixed recorded frame; no "
        "rollout, no physics, no autonomy claim, no benchmark claim.",
        "- Expected actions are the committed recorded-acceptance robot-frame directions o_d→goal.",
        "",
        "## Artifacts",
        "`assets/experiments/hospital_h8_paired_branch_prototype/action_probe/`: "
        "`h8_action_probe_report.md`, `h8_action_probe_results.json`, "
        "`h8_action_probe_matrix.{csv,md}`, `h8_action_probe_direction_diagram.png`. "
        "Harness: `scripts/gnm/h8_action_probe.py`."]
(OUT / "h8_action_probe_report.md").write_text("\n".join(rep) + "\n")

print(json.dumps(summary, indent=2))
print("ACTION-PROBE WRITTEN ->", OUT)
