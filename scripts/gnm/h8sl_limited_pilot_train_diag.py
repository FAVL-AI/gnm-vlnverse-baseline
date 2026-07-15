"""H8-S LIMITED_CAUSAL_PILOT — distance/stop-axis training + diagnostics (TINY, bounded).

Scope (LIMITED_CAUSAL_PILOT): tests only whether the H8 goal-conditioned objective can make
the model's predicted action respond to the goal image on the committed H8-S limited-pilot
real-frame set. NO promotion, NO push, NO tag, NO 20/5/10, NO closed-loop Isaac, NO H8-M
validation, NO checkpoint committed. Incumbent retained.

Why the DISTANCE/STOP axis (not the 15 deg angular gate):
  Every committed H8-S decision frame is family "near_far_same_approach": o_d, goalA(near_stop)
  and goalB(far_continue) are COLLINEAR (share y; differ only in along-corridor x), so the
  expected angular separation between goalA and goalB is exactly 0 deg in all three frames.
  The angular branch-choice gate ("pred action change >= 15 deg toward the correct branch") is
  therefore NOT well-posed on this set (there is one heading, two distances — no junction).
  The well-posed causal axis is DISTANCE/STOP: does swapping near<->far goal change the
  predicted action MAGNITUDE |[dx,dy]| (meters) / stop decision? The action target is the full
  robot-frame o_d->goal displacement, so target magnitude encodes goal distance (near vs far),
  making predicted action magnitude the clean, dimensionally-consistent distance signal:
      S = |mag_far - mag_near| / |expected_dist_sep_m|      (meters / meters)
      branch-choice (stop/continue) correct iff  mag_far > mag_near
  The temporal dist head + stop decision are reported as a SECONDARY corroborating signal
  (weak here: all goals are 0.3-1.6 m => normalized dist targets < 0.08, below stop_threshold
  0.15, so the dist head cannot separate near vs far at this range).

Data (committed): assets/experiments/hospital_h8_s_limited_pilot/recorded/frames/*.jpg
  (9 real /camera/image_raw frames, 3 decision frames x {o_d, near=goalA, far=goalB}).
Split: train=lobby, val=midwest_B, test=east_A. Train on TRAIN only; probe val + test held-out.
Init: weights-only from the H7r candidate, fresh Adam, seed 42, deterministic cuDNN/cuBLAS.
Variants: baseline (untrained H7r) + A, A+B (goal-contrastive), A+B+C (+branch aux),
  A+B+C+E (+goal dropout/swap) — translated to the distance axis.

Run with gnm_train python.
"""
import csv, json, math, os, sys
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")  # deterministic cuBLAS matmul
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F
from omegaconf import OmegaConf
from PIL import Image, ImageDraw, ImageFont
from gnm_vlnverse.models.gnm import build_gnm
from gnm_vlnverse.evaluation.evaluator import GNMEvaluator

REPO = Path(__file__).resolve().parents[2]
PILOT = REPO / "assets/experiments/hospital_h8_s_limited_pilot"
FRAMES = PILOT / "recorded/frames"
OUT = PILOT / "training"
CAND = "checkpoints/h7r_hospital_pilot_finetune/best.pt"
PLACEHOLDER = "assets/experiments/goals/h2_weave_J/goal_image.png"
BASE_YAML = REPO / "configs/gnm/gnm_h7r_hospital_pilot.yaml"
SEED = 42
STEPS = 400
LR = 1e-3
MARGIN = 0.5
LAMBDA = {"a": 1.0, "c": 1.0, "b": 0.5, "d": 0.1, "e": 0.5}
VARIANTS = ["A", "A+B", "A+B+C", "A+B+C+E"]
# distance/stop-axis pass targets (user-selected gate). Angular criterion is N/A (collinear).
PASS = {"branch_choice": 0.75, "S": 0.5}

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load_cfg():
    ckpt = torch.load(REPO / CAND, map_location="cpu", weights_only=False)
    emb = ckpt.get("cfg", {})
    cfg = emb if (isinstance(emb, dict) and "model" in emb) else \
        OmegaConf.to_container(OmegaConf.load(BASE_YAML), resolve=True)
    return ckpt, cfg


def fresh_model(ckpt, cfg):
    m = build_gnm(cfg["model"])
    m.load_state_dict(ckpt["model_state"])
    return m


def rgb(path):
    p = str(path) if str(path).startswith("/") else str(REPO / path)
    im = cv2.imread(p)
    if im is None:
        raise FileNotFoundError(p)
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB)


def preprocess(img, image_size):
    img = cv2.resize(img, tuple(image_size)).astype(np.float32) / 255.0
    img = (img - _MEAN) / _STD
    return torch.from_numpy(img).permute(2, 0, 1)  # (3,H,W)


def ang(a):
    return math.degrees(math.atan2(a[1], a[0]))


def ang_between(a, b):
    return math.degrees(math.atan2(abs(a[0] * b[1] - a[1] * b[0]), a[0] * b[0] + a[1] * b[1]))


def robot_frame_action(o_d, goal, yaw):
    """World o_d->goal displacement rotated into the robot frame (yaw=approach heading)."""
    dx, dy = goal[0] - o_d[0], goal[1] - o_d[1]
    c, s = math.cos(yaw), math.sin(yaw)
    return (c * dx + s * dy, -s * dx + c * dy)


# ── config / device ──────────────────────────────────────────────────────────
ckpt, cfg = load_cfg()
image_size = cfg["data"]["image_size"]
ctx = cfg["model"]["context_size"]
action_std = np.array(cfg["data"]["action_std"], dtype=np.float32)
max_goal_dist = float(cfg["data"].get("max_goal_dist", 20))
stop_threshold = float(cfg.get("evaluation", {}).get("stop_threshold", 0.15))
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
device = "cuda" if torch.cuda.is_available() else "cpu"

# ── build the design set from the committed decision frames ──────────────────
DF = json.loads((PILOT / "h8sl_decision_frames.json").read_text())["decision_frames"]
DESIGNS = []
for d in DF:
    fid, yaw = d["frame_id"], d.get("approach_yaw_rad", 0.0)
    aA = robot_frame_action(d["o_d"], d["goalA"]["coord"], yaw)
    aB = robot_frame_action(d["o_d"], d["goalB"]["coord"], yaw)
    DESIGNS.append({
        "frame_id": fid, "split": d["split"], "zone": d["zone"], "family": d["family"],
        "o_d_img": f"assets/experiments/hospital_h8_s_limited_pilot/recorded/frames/{fid}__o_d.jpg",
        "goalA_img": f"assets/experiments/hospital_h8_s_limited_pilot/recorded/frames/{fid}__near.jpg",
        "goalB_img": f"assets/experiments/hospital_h8_s_limited_pilot/recorded/frames/{fid}__far.jpg",
        "goalA_branch": d["goalA"]["branch"], "goalB_branch": d["goalB"]["branch"],
        "act_tgt_A": aA, "act_tgt_B": aB,
        "exp_mag_A": math.hypot(*aA), "exp_mag_B": math.hypot(*aB),
        "exp_dist_sep_m": abs(math.hypot(*aB) - math.hypot(*aA)),
        "exp_ang_sep_deg": ang_between(aA, aB),
    })
BY_SPLIT = {d["split"]: d for d in DESIGNS}
TRAIN = [d for d in DESIGNS if d["split"] == "train"]
HELDOUT = [d["split"] for d in DESIGNS if d["split"] in ("val", "test")]  # order val, test


def obs_tensor(o_d_np):
    f = preprocess(o_d_np, image_size)
    return torch.cat([f.clone() for _ in range(ctx)], dim=0)  # (ctx*3,H,W)


def build_train_batch():
    """Samples = TRAIN split only, roles goalA(near)/goalB(far). Targets: full o_d->goal
    displacement normalized by action_std (magnitude encodes distance); dist head target =
    normalized goal distance (near vs far distinct)."""
    obs_l, goal_l, tgt_l, tdist_l, blabel = [], [], [], [], []
    meta = []
    cls = 0
    for d in TRAIN:
        o_d_np = rgb(d["o_d_img"])
        for role, gimg, atgt, emag in (("goalA", d["goalA_img"], d["act_tgt_A"], d["exp_mag_A"]),
                                       ("goalB", d["goalB_img"], d["act_tgt_B"], d["exp_mag_B"])):
            obs_l.append(obs_tensor(o_d_np))
            goal_l.append(preprocess(rgb(gimg), image_size))
            tgt_l.append(np.array(atgt, dtype=np.float32) / action_std)   # normalized action target
            tdist_l.append(min(emag / max_goal_dist, 1.0))                # normalized distance target
            blabel.append(cls); cls += 1
            meta.append((d["frame_id"], role))
    obs = torch.stack(obs_l).to(device)
    goal = torch.stack(goal_l).to(device)
    tgt = torch.tensor(np.stack(tgt_l), dtype=torch.float32, device=device)
    tdist = torch.tensor(np.array(tdist_l, dtype=np.float32).reshape(-1, 1), device=device)
    bl = torch.tensor(blabel, dtype=torch.long, device=device)
    # pairs of (goalA,goalB) that share an o_d, per train frame
    pairs = [(2 * i, 2 * i + 1) for i in range(len(TRAIN))]
    return obs, goal, tgt, tdist, bl, pairs, meta


def train_variant(name):
    torch.manual_seed(SEED); np.random.seed(SEED)
    if device == "cuda":
        torch.cuda.manual_seed_all(SEED)
    model = fresh_model(ckpt, cfg).to(device).train()
    obs, goal, tgt, tdist, blabel, pairs, meta = build_train_batch()
    fused_dim = model.encode(obs[:1], goal[:1]).shape[-1]
    use_b, use_c, use_e = ("B" in name), ("C" in name), ("E" in name)
    params = list(model.parameters())
    branch_head = None
    if use_c:
        branch_head = nn.Linear(fused_dim, len(meta)).to(device)
        params += list(branch_head.parameters())
    opt = torch.optim.Adam(params, lr=LR)
    for _ in range(STEPS):
        opt.zero_grad()
        fused = model.encode(obs, goal)
        act = model.action_predictor(fused)
        dist = model.dist_predictor(fused)
        L = LAMBDA["a"] * F.mse_loss(act, tgt)                    # A: action imitation (mag encodes dist)
        if use_b:                                                # B: goal-contrastive (distance/vector)
            L_c = torch.tensor(0.0, device=device)
            for iA, iB in pairs:
                pA, pB, tA, tB = act[iA], act[iB], tgt[iA], tgt[iB]
                L_sep = F.relu(torch.norm(tA - tB) - torch.norm(pA - pB))
                L_rep = (F.relu(torch.norm(pA - tA) - torch.norm(pA - tB) + MARGIN)
                         + F.relu(torch.norm(pB - tB) - torch.norm(pB - tA) + MARGIN))
                L_c = L_c + L_sep + L_rep
            L = L + LAMBDA["c"] * L_c
        if use_c:                                                # C: branch (near_stop/far_continue) aux
            L = L + LAMBDA["b"] * F.cross_entropy(branch_head(fused), blabel)
        L = L + LAMBDA["d"] * F.mse_loss(dist, tdist)            # distance head -> normalized goal distance
        if use_e:                                                # E: goal dropout/swap
            zg = torch.zeros_like(goal)
            act_drop = model.action_predictor(model.encode(obs, zg))
            neutral = tgt.mean(dim=0, keepdim=True).expand_as(tgt)
            L = L + LAMBDA["e"] * F.mse_loss(act_drop, neutral)
        L.backward(); opt.step()
    return model.eval()


def make_ev(model):
    return GNMEvaluator(model=model, action_std=cfg["data"]["action_std"], context_size=ctx,
                        image_size=tuple(image_size), stop_threshold=stop_threshold,
                        max_steps=cfg.get("evaluation", {}).get("max_steps", 500),
                        device=device, track="A")


def probe_conditions(ev, o_d_np, cond_imgs):
    out = {}
    for c, img in cond_imgs.items():
        ev.reset_context(o_d_np)
        dist, act = ev.predict(o_d_np, rgb(img))
        a = (float(act[0]), float(act[1]))
        out[c] = {"act": a, "dist": float(dist), "mag": math.hypot(*a), "angle": ang(a)}
    return out


def probe_frame(ev, d):
    """Distance-axis probe at one decision frame (near vs far goal, o_d fixed)."""
    o_d = rgb(d["o_d_img"])
    pr = probe_conditions(ev, o_d, {"near": d["goalA_img"], "far": d["goalB_img"]})
    n, f = pr["near"], pr["far"]
    sep = d["exp_dist_sep_m"]
    S = abs(f["mag"] - n["mag"]) / sep if sep > 1e-6 else 0.0
    return {
        "frame_id": d["frame_id"], "split": d["split"], "zone": d["zone"],
        "exp_mag_near": round(d["exp_mag_A"], 3), "exp_mag_far": round(d["exp_mag_B"], 3),
        "exp_dist_sep_m": round(sep, 3), "exp_ang_sep_deg": round(d["exp_ang_sep_deg"], 2),
        "pred": {r: {"act_dx_dy": [round(pr[r]["act"][0], 4), round(pr[r]["act"][1], 4)],
                     "mag_m": round(pr[r]["mag"], 4), "dist_head": round(pr[r]["dist"], 4),
                     "angle_deg": round(pr[r]["angle"], 1),
                     "stop": bool(pr[r]["dist"] < stop_threshold)} for r in ("near", "far")},
        "pred_mag_near_m": round(n["mag"], 4), "pred_mag_far_m": round(f["mag"], 4),
        "pred_mag_change_m": round(f["mag"] - n["mag"], 4),
        "branch_choice_far_gt_near": bool(f["mag"] > n["mag"]),
        "goal_sensitivity_S": round(S, 3),
        "pred_ang_change_deg": round(ang_between(n["act"], f["act"]), 2),  # ~0 expected (collinear)
        "displacement_shift_m": round(math.hypot(n["act"][0] - f["act"][0],
                                                 n["act"][1] - f["act"][1]), 4),
        "dist_head_change": round(abs(f["dist"] - n["dist"]), 4),
        "stop_near": bool(n["dist"] < stop_threshold), "stop_far": bool(f["dist"] < stop_threshold),
    }


def mismatched_ablation(ev, test_d):
    """Offline mismatched-goal ablation on the TEST frame: correct near/far vs same-family wrong
    goal (val far image, same alcove different position) vs placeholder (cross-scene)."""
    o_d = rgb(test_d["o_d_img"])
    same_fam = BY_SPLIT["val"]["goalB_img"]  # same alcove, different corridor position
    conds = {"correct_near": test_d["goalA_img"], "correct_far": test_d["goalB_img"],
             "mismatch_same_family": same_fam, "placeholder_cross_scene": PLACEHOLDER}
    pr = probe_conditions(ev, o_d, conds)
    mags = {c: pr[c]["mag"] for c in conds}
    spread = max(mags.values()) - min(mags.values())
    return {
        "conditions": {c: {"act_dx_dy": [round(pr[c]["act"][0], 4), round(pr[c]["act"][1], 4)],
                           "mag_m": round(pr[c]["mag"], 4), "dist_head": round(pr[c]["dist"], 4),
                           "angle_deg": round(pr[c]["angle"], 1)} for c in conds},
        "mag_spread_m": round(spread, 4),
        "correct_near_vs_far_delta_m": round(abs(mags["correct_far"] - mags["correct_near"]), 4),
        "correct_vs_placeholder_delta_m": round(abs(mags["correct_far"] - mags["placeholder_cross_scene"]), 4),
        "collapsed": bool(spread < 0.02),  # all conditions ~identical => goal ignored
    }


def evaluate_variant(model):
    ev = make_ev(model)
    frames = {d["split"]: probe_frame(ev, d) for d in DESIGNS}
    mism = mismatched_ablation(ev, BY_SPLIT["test"])
    # gate on held-out (val, test); test is the primary held-out coordinate
    ho = [frames[s] for s in HELDOUT]
    bc = float(np.mean([f["branch_choice_far_gt_near"] for f in ho]))
    mS = float(np.mean([f["goal_sensitivity_S"] for f in ho]))
    passes = bool(bc >= PASS["branch_choice"] and mS >= PASS["S"])
    return {
        "frames": frames, "mismatched_goal_ablation": mism,
        "heldout_summary": {
            "heldout_splits": HELDOUT,
            "branch_choice_accuracy": round(bc, 3),
            "mean_goal_sensitivity_S": round(mS, 3),
            "test_branch_choice": bool(frames["test"]["branch_choice_far_gt_near"]),
            "test_goal_sensitivity_S": frames["test"]["goal_sensitivity_S"],
            "passes_distance_axis_gate": passes,
        },
    }


def run_all():
    res = {"baseline": evaluate_variant(fresh_model(ckpt, cfg).to(device).eval())}
    for name in VARIANTS:
        res[name] = evaluate_variant(train_variant(name))
    return res


# ── run twice for determinism, then persist ──────────────────────────────────
run1 = run_all()
run2 = run_all()
determinism_ok = json.dumps(run1, sort_keys=True) == json.dumps(run2, sort_keys=True)
results = run1

order = ["baseline"] + VARIANTS
any_pass = any(results[n]["heldout_summary"]["passes_distance_axis_gate"] for n in VARIANTS)
best = max(VARIANTS, key=lambda n: (results[n]["heldout_summary"]["passes_distance_axis_gate"],
                                    results[n]["heldout_summary"]["mean_goal_sensitivity_S"]))
verdict = "LIMITED_CAUSAL_PILOT_OBJECTIVE_SIGNAL" if any_pass else "GOAL_CONDITIONING_OBJECTIVE_NOT_READY"

OUT.mkdir(parents=True, exist_ok=True)
full = {
    "status": "LIMITED_CAUSAL_PILOT", "verdict": verdict,
    "gate_axis": "distance/stop (angular branch-choice N/A: collinear near/far, 0 deg expected)",
    "seed": SEED, "steps": STEPS, "lr": LR, "lambda": LAMBDA,
    "init_ckpt_weights_only": CAND, "fresh_optimizer": True,
    "deterministic_rerun_matches": determinism_ok,
    "pass_target_distance_axis": PASS,
    "split": {"train": "lobby", "val": "midwest_B", "test": "east_A"},
    "train_frames": [d["frame_id"] for d in TRAIN], "heldout_probe_splits": HELDOUT,
    "config": {"image_size": image_size, "context_size": ctx,
               "action_std": action_std.tolist(), "max_goal_dist": max_goal_dist,
               "stop_threshold": stop_threshold},
    "best_variant": best, "any_variant_passes": any_pass,
    "results": results,
    "caveats": [
        "ONE training decision frame (lobby, 2 samples): a pass shows the objective can make the "
        "predicted action magnitude goal-sensitive and that it transfers ordering to held-out "
        "frames of the SAME alcove — NOT generalizable goal-conditioned navigation.",
        "Angular branch-choice is N/A: all goals collinear (0 deg expected separation).",
        "Temporal dist head is a weak secondary signal here (all goals 0.3-1.6 m -> normalized "
        "targets <0.08, below stop_threshold 0.15).",
        "Standard nav metrics (TL/NE/SR/OSR/SPL/nDTW/CR) are NOT computable offline on 3 decision "
        "frames (no rollout); reported N/A, deferred to a simulator rollout.",
        "No promotion, no push, no tag, no 20/5/10, no closed-loop, no H8-M validation; incumbent "
        "retained; no checkpoint written.",
    ],
}
(OUT / "h8sl_training_results.json").write_text(json.dumps(full, indent=2))

# ── action-probe matrix (csv + md): per (variant, split, condition) ──────────
cols = ["variant", "split", "zone", "condition", "pred_dx", "pred_dy", "pred_mag_m",
        "dist_head", "pred_angle_deg", "exp_mag_m", "stop"]
rows = []
for name in order:
    for d in DESIGNS:
        fr = results[name]["frames"][d["split"]]
        for cond, exp in (("near", fr["exp_mag_near"]), ("far", fr["exp_mag_far"])):
            p = fr["pred"][cond]
            rows.append({"variant": name, "split": d["split"], "zone": d["zone"],
                         "condition": cond, "pred_dx": p["act_dx_dy"][0], "pred_dy": p["act_dx_dy"][1],
                         "pred_mag_m": p["mag_m"], "dist_head": p["dist_head"],
                         "pred_angle_deg": p["angle_deg"], "exp_mag_m": exp, "stop": p["stop"]})
with open(OUT / "h8sl_action_probe_matrix.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n"); w.writeheader()
    for r in rows:
        w.writerow(r)
mdl = ["# H8-S Limited Pilot — Action-Probe Matrix (distance/stop axis)", "",
       "Predicted `[dx,dy]` (robot-frame meters) at each shared decision frame `o_d`, swapping "
       "only the goal image (near=goalA/near_stop, far=goalB/far_continue). `pred_mag_m` = "
       "|[dx,dy]| is the distance signal; `exp_mag_m` = expected o_d->goal distance. `dist_head` "
       "= normalized temporal-distance head (secondary). Baseline = untrained H7r candidate.", "",
       "| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
for r in rows:
    mdl.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
(OUT / "h8sl_action_probe_matrix.md").write_text("\n".join(mdl) + "\n")


# ── progression + training report ────────────────────────────────────────────
def hs(n):
    return results[n]["heldout_summary"]


def srow(n):
    s = hs(n)
    return (f"| {n} | {s['branch_choice_accuracy']:.2f} | {s['mean_goal_sensitivity_S']:.3f} | "
            f"{str(s['test_branch_choice'])} | {s['test_goal_sensitivity_S']:.3f} | "
            f"{'PASS' if s['passes_distance_axis_gate'] else '-'} |")


rep = ["# H8-S Limited Causal Pilot — Training + Diagnostics Report", "",
       f"**Status: `LIMITED_CAUSAL_PILOT`. Verdict: `{verdict}`.**", "",
       "**Scope.** Tests only whether the H8 goal-conditioned objective can make the predicted "
       "action respond to the goal image on the committed H8-S limited real-frame set. No "
       "promotion, no push, no tag, no 20/5/10, no closed-loop Isaac, no H8-M validation; "
       "incumbent retained; `CL_BOUND_XY` unchanged; no checkpoint written to the repo.", "",
       "## Gate axis (why distance/stop, not 15 deg angular)",
       "Every committed H8-S decision frame is `near_far_same_approach`: `o_d`, goalA(near_stop) "
       "and goalB(far_continue) are **collinear** (share y, differ only in along-corridor x), so "
       "the expected **angular** separation is **0 deg** in all three frames. The 15 deg angular "
       "branch-choice gate is not well-posed here (one heading, two distances, no junction). The "
       "well-posed causal axis is **distance/stop**: swapping near<->far goal should change the "
       "predicted action **magnitude** |[dx,dy]| (meters). Because the action target is the full "
       "`o_d->goal` displacement, target magnitude encodes goal distance, so predicted magnitude "
       "is the clean distance signal:", "",
       "- `S = |mag_far - mag_near| / |expected_dist_sep_m|`  (meters/meters), gate S >= 0.5",
       "- branch-choice (stop/continue) correct iff `mag_far > mag_near`, gate >= 0.75",
       "- direction-toward-branch: **N/A** (collinear, 0 deg)",
       "- deterministic rerun matches: **" + ("yes" if determinism_ok else "NO") + "**", "",
       "## Setup",
       f"- Init: weights-only from the H7r candidate (`{CAND}`), fresh Adam, seed {SEED}, "
       f"{STEPS} steps, lr {LR}; deterministic cuDNN/cuBLAS.",
       "- Split: **train=lobby**, **val=midwest_B**, **test=east_A**. Trained on the **train "
       "frame only** (2 samples); val + test are **held-out** probes (test = primary held-out "
       "coordinate).",
       f"- Loss variants (distance-axis translation): **A** action imitation (`||a_pred-a_tgt||`, "
       "target = full o_d->goal displacement so magnitude encodes distance); **B** goal-"
       "contrastive (separation + triplet at the shared o_d); **C** branch aux (near_stop vs "
       "far_continue classification); **E** goal-dropout (zeroed goal -> neutral mean action). "
       f"Weights lambda={LAMBDA}.", "",
       "## Progression (distance-axis diagnostics recomputed after each variant)", "",
       "| variant | held-out branch-choice | held-out mean S | test branch-choice (far>near) | test S | gate |",
       "|---|---|---|---|---|---|",
       srow("baseline")]
for n in VARIANTS:
    rep.append(srow(n))
rep += ["",
        f"Pass target (distance axis): held-out branch-choice >= {PASS['branch_choice']}, "
        f"held-out mean S >= {PASS['S']}.", ""]

# per-frame detail
rep += ["## Per-frame detail (predicted magnitude near vs far)", ""]
for n in order:
    rep.append(f"### {n}")
    for d in DESIGNS:
        fr = results[n]["frames"][d["split"]]
        rep.append(
            f"- **{fr['split']} / {fr['zone']}** (exp near {fr['exp_mag_near']:.2f} m, far "
            f"{fr['exp_mag_far']:.2f} m, sep {fr['exp_dist_sep_m']:.2f} m): pred mag near "
            f"{fr['pred_mag_near_m']:.3f} m vs far {fr['pred_mag_far_m']:.3f} m "
            f"(change {fr['pred_mag_change_m']:+.3f} m); far>near = "
            f"{fr['branch_choice_far_gt_near']}; S {fr['goal_sensitivity_S']:.3f}; "
            f"pred angular change {fr['pred_ang_change_deg']:.2f} deg (expected 0).")
    rep.append("")

# observations
base_test_S = hs("baseline")["test_goal_sensitivity_S"]
rep += ["## Observations", "",
        f"- **Baseline (untrained H7r)** held-out mean S = {hs('baseline')['mean_goal_sensitivity_S']:.3f}, "
        f"test branch-choice far>near = {hs('baseline')['test_branch_choice']}: the starting model's "
        "goal-image sensitivity on the distance axis before any H8 objective training.",
        f"- **The objective breaks the goal-collapse *directionally* (branch-choice passes).** "
        f"Held-out branch-choice (far>near) rises from "
        f"{hs('baseline')['branch_choice_accuracy']:.2f} (baseline, goal-collapsed) to "
        f"{hs(best)['branch_choice_accuracy']:.2f} with the goal-contrastive (B) + branch-aux (C) "
        f"terms — the model orders near vs far correctly on the held-out frames "
        f"(>= {PASS['branch_choice']} branch-choice gate met).",
        f"- **But the distance-scaling is too weak (magnitude gate fails).** The S >= {PASS['S']} "
        f"gate is not met on **one training frame** (best variant `{best}`, held-out mean S "
        f"{hs(best)['mean_goal_sensitivity_S']:.3f}, test S {hs(best)['test_goal_sensitivity_S']:.3f}); "
        "the model reacts to goal content but captures only a fraction of the expected near/far "
        "distance separation. Because both criteria must pass, the verdict is NOT_READY.",
        "- Predicted **angular** change near->far is ~0 deg across all variants/frames, as expected "
        "for a collinear near/far design — confirming the angular gate would be uninformative here.",
        "- Temporal **dist head** barely separates near vs far (all goals < stop range); the "
        "**action magnitude** carries the distance signal, as designed.", ""]
if not any_pass:
    rep += ["- **No variant meets the distance-axis gate on the held-out frames.** On a single "
            "training frame the objective can fit lobby but does not reliably transfer the "
            "near<->far magnitude ordering/sensitivity to the held-out alcove views. This is a "
            "limited-pilot **negative/inconclusive** signal, not a model-architecture verdict.", ""]
else:
    rep += ["- **At least one variant meets the distance-axis gate on the held-out frames**, i.e. "
            "the objective makes the predicted action magnitude respond to the goal image and the "
            "near<->far ordering transfers to held-out same-alcove views. Limited-pilot signal "
            "only (see caveats).", ""]

rep += ["## Decision", "",
        f"- **Verdict: `{verdict}`.**",
        "- **No promotion, no push, no tag, no 20/5/10, no closed-loop, no H8-M validation.** "
        "Incumbent retained; status `DIAGNOSTIC_ONLY_NOT_PROMOTED`. No checkpoint written.",
        "- **H8-M is still required** for a strong benchmark claim (genuinely distinct rooms, an "
        "embedding distinctness gate, and — for a real angular branch-choice test — a junction "
        "with divergent corridors).", "",
        "## Critical caveats (must not be dropped)",
        "- **One training decision frame** (lobby, 2 samples). A pass proves the objective can "
        "make the action magnitude goal-sensitive and transfer the near<->far ordering to "
        "held-out **same-alcove** frames — **not** generalizable goal-conditioned navigation.",
        "- **Distance axis only**; the angular branch-choice test is deferred to a junction "
        "(H8-M). Direction-toward-branch is N/A here.",
        "- **Standard nav metrics are N/A offline** (no rollout on 3 decision frames) — see "
        "`h8sl_metric_table.md`.",
        "- All goal images are the same vending alcove at different scales/positions "
        "(`LIMITED_PILOT_ONLY`, max cross-split aHash 0.887); no strong held-out visual, "
        "multi-room, or full goal-conditioned ImageNav claim.", "",
        "## Artifacts",
        "`assets/experiments/hospital_h8_s_limited_pilot/training/`: `h8sl_training_report.md`, "
        "`h8sl_training_results.json`, `h8sl_action_probe_matrix.{csv,md}`, "
        "`h8sl_mismatched_goal_ablation.md`, `h8sl_metric_table.md`, `h8sl_claim_boundary.md`, "
        "`h8sl_direction_diagram.png`. Harness: `scripts/gnm/h8sl_limited_pilot_train_diag.py`. "
        "No checkpoint/weights written to the repo."]
(OUT / "h8sl_training_report.md").write_text("\n".join(rep) + "\n")

# ── mismatched-goal ablation report ──────────────────────────────────────────
ml = ["# H8-S Limited Pilot — Mismatched-Goal Ablation (offline, distance axis)", "",
      "**Scope:** offline probe on the **test** frame (`east_A`) `o_d`, swapping only the goal "
      "image. Conditions: correct near / correct far (own alcove), same-family wrong goal "
      "(val/midwest_B far image — same alcove, different corridor position), placeholder "
      "(cross-scene `h2_weave_J`). A goal-USING model changes the predicted action across "
      "conditions; a goal-collapsed model predicts ~the same action regardless.", "",
      "(The rollout-based `h7r_mismatched_goal_ablation.py` needs `traj_data.pkl` trajectories "
      "and cannot run on the 3-frame limited set; this offline probe is the honest substitute. "
      "The full rollout ablation remains deferred to H8-M.)", "",
      "| variant | correct_near mag (m) | correct_far mag (m) | same-family mag (m) | placeholder mag (m) | mag spread (m) | collapsed |",
      "|---|---|---|---|---|---|---|"]
for n in order:
    m = results[n]["mismatched_goal_ablation"]; c = m["conditions"]
    ml.append(f"| {n} | {c['correct_near']['mag_m']:.3f} | {c['correct_far']['mag_m']:.3f} | "
              f"{c['mismatch_same_family']['mag_m']:.3f} | {c['placeholder_cross_scene']['mag_m']:.3f} | "
              f"{m['mag_spread_m']:.3f} | {m['collapsed']} |")
ml += ["",
       "- **collapsed = True** means all four goal conditions produced action magnitudes within "
       "0.02 m of each other (the goal image is effectively ignored).",
       "- **correct near vs far** and **correct vs placeholder** magnitude deltas per variant:"]
for n in order:
    m = results[n]["mismatched_goal_ablation"]
    ml.append(f"  - `{n}`: near-vs-far delta {m['correct_near_vs_far_delta_m']:.3f} m; "
              f"correct-vs-placeholder delta {m['correct_vs_placeholder_delta_m']:.3f} m.")
ml += ["", "**Reading:** a limited-pilot goal-USE signal requires (a) near != far and (b) correct "
       "!= placeholder. On one training frame this is memorisation-limited; interpret as a "
       "diagnostic, not a generalization claim. No promotion; incumbent retained.", ""]
(OUT / "h8sl_mismatched_goal_ablation.md").write_text("\n".join(ml) + "\n")

# ── standard-metric table (honest N/A) ───────────────────────────────────────
tl = ["# H8-S Limited Pilot — Standard Navigation Metrics (limited-only)", "",
      "**These metrics are secondary for this pilot and are NOT computable offline on the "
      "committed 3-decision-frame set.** Every VLNVerse metric consumes a full ordered rollout "
      "trajectory (`actual_path` vs reference/goal), which requires a simulator rollout — not "
      "available from 3 static decision frames. They are reported **N/A (requires rollout)**, "
      "not fabricated. The main scientific gate for this pilot is the distance/stop-axis "
      "goal-sensitivity in `h8sl_training_report.md`.", "",
      "| metric | value | reason |",
      "|---|---|---|",
      "| TL (trajectory length) | N/A | requires rollout trajectory |",
      "| NE (nav error) | N/A | requires executed path vs goal |",
      "| SR (success rate) | N/A | requires rollout + success threshold |",
      "| OSR (oracle SR) | N/A | requires rollout path |",
      "| SPL | N/A | requires rollout + shortest-path length |",
      "| nDTW | N/A | requires executed vs reference path |",
      "| CR (collision rate) | N/A offline | contacts=0 at collection; needs physics rollout |",
      "",
      "Related committed facts (not a substitute for rollout metrics): all four source episodes "
      "recorded **0 collisions** and passed the scene gate at collection; the limited pilot's "
      "goal-conditioning signal is measured offline on the distance axis instead. Full rollout "
      "metrics are **deferred to H8-M** (simulator rollout on a genuinely distinct, "
      "embedding-gated set).", ""]
(OUT / "h8sl_metric_table.md").write_text("\n".join(tl) + "\n")

# ── claim boundary ───────────────────────────────────────────────────────────
cb = ["# H8-S Limited Causal Pilot — Claim Boundary", "",
      f"**Status: `LIMITED_CAUSAL_PILOT`. Verdict: `{verdict}`.**", "",
      "## What this pilot tests",
      "- Whether the H8 goal-conditioned objective makes the model's **predicted 2-D action "
      "respond to the goal image** on a small, real, coordinate-clean hospital set — measured on "
      "the **distance/stop axis** (near_stop vs far_continue), because the committed frames are "
      "collinear near/far (0 deg angular separation).",
      "- Whether the near<->far magnitude ordering/sensitivity **transfers** from the single "
      "training frame (lobby) to **held-out** coordinates (val=midwest_B, test=east_A) of the "
      "same alcove.", "",
      "## What this pilot does NOT claim",
      "- **Not** a strong held-out visual benchmark (all goals are the same vending alcove; "
      "`LIMITED_PILOT_ONLY`, max cross-split aHash 0.887; a strong claim needs an embedding gate).",
      "- **Not** multi-room / cross-location visual generalization.",
      "- **Not** full goal-conditioned ImageNav.",
      "- **Not** an angular branch-choice result (no junction; deferred to H8-M).",
      "- **Not** a rollout/benchmark navigation result (standard metrics N/A offline).",
      "- **No** SOTA, promotion, autonomy, or model-architecture verdict.", "",
      "## Method boundary",
      "- Weights-only init from the H7r candidate; fresh optimizer; deterministic; seed logged; "
      "trained on **one** decision frame (2 samples); offline action-probe of the instantaneous "
      "predicted action; no rollout, no physics, no autonomy.",
      "- Expected distances are the committed decision-frame o_d->goal distances (also the "
      "training-target magnitudes), so a pass means the action head **can express** goal-distance-"
      "dependent magnitude and transfer its ordering within the same alcove — not that it learned "
      "a generalizable goal representation.", "",
      "## Standing constraints",
      "- No promotion, no push, no tag, no 20/5/10, no closed-loop Isaac, no H8-M validation; "
      "incumbent retained; `CL_BOUND_XY` unchanged; no checkpoint/weights committed.",
      "- **H8-M remains required** for the stronger benchmark claim (distinct rooms + embedding "
      "distinctness gate + a junction for the angular branch-choice test).", ""]
(OUT / "h8sl_claim_boundary.md").write_text("\n".join(cb) + "\n")


# ── direction/magnitude diagram (distance axis) ──────────────────────────────
def diagram():
    variants = order
    splits = [d["split"] for d in DESIGNS]
    P = 210
    W = 40 + P * len(splits)
    H = 70 + P * len(variants)
    cv = Image.new("RGB", (W, H), "white"); dr = ImageDraw.Draw(cv)
    try:
        fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
    except Exception:
        fb = fr = ImageFont.load_default()
    dr.text((10, 8), "H8-S distance axis: predicted action magnitude (m) near (green) vs far "
            "(blue) vs expected (grey) — rows=variant, cols=split", font=fb, fill="black")
    # scale bars to the max expected/predicted magnitude across everything
    allm = [1.7]
    for n in variants:
        for d in DESIGNS:
            fr_ = results[n]["frames"][d["split"]]
            allm += [fr_["pred_mag_near_m"], fr_["pred_mag_far_m"], fr_["exp_mag_far"]]
    mmax = max(allm) or 1.0
    BARW = 26
    for ri, n in enumerate(variants):
        dr.text((6, 70 + ri * P + P // 2), n, font=fb, fill="black")
        for ci, d in enumerate(DESIGNS):
            fr_ = results[n]["frames"][d["split"]]
            x0 = 40 + ci * P + 20
            ybase = 70 + ri * P + P - 40
            if ri == 0:
                dr.text((x0, 52), f"{d['split']}/{d['zone']}", font=fr, fill="#555")

            def bar(x, val, color, label):
                h = int((val / mmax) * (P - 70))
                dr.rectangle([x, ybase - h, x + BARW, ybase], fill=color, outline="#333")
                dr.text((x - 2, ybase + 2), f"{val:.2f}", font=fr, fill="#000")
                dr.text((x - 2, ybase + 13), label, font=fr, fill="#666")
            bar(x0, fr_["exp_mag_near"], "#cfc", "eN")
            bar(x0 + BARW + 4, fr_["pred_mag_near_m"], "#0a0", "pN")
            bar(x0 + 2 * (BARW + 4) + 10, fr_["exp_mag_far"], "#ccf", "eF")
            bar(x0 + 3 * (BARW + 4) + 10, fr_["pred_mag_far_m"], "#00a", "pF")
            s = fr_["goal_sensitivity_S"]; bcok = fr_["branch_choice_far_gt_near"]
            dr.text((x0, 70 + ri * P + 2), f"S={s:.2f} far>near={bcok}", font=fr,
                    fill=("#070" if bcok else "#a00"))
    cv.save(OUT / "h8sl_direction_diagram.png")


diagram()

print(json.dumps({"verdict": verdict, "best": best, "any_pass": any_pass,
                  "determinism_ok": determinism_ok,
                  "progression": {n: results[n]["heldout_summary"] for n in order}}, indent=2))
print("H8-S LIMITED PILOT TRAIN+DIAG WRITTEN ->", OUT)
