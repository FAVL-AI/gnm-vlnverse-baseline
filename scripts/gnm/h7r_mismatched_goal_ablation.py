"""H7r mismatched-goal ablation (NO TRAINING) — does the candidate USE the goal image?

For each H7r TEST episode, roll out the SAME trained H7r candidate on that episode's own
recorded frames, but swap the GOAL IMAGE across 4 conditions:
  1. correct           = the episode's own final recorded frame (scene-aligned)
  2. placeholder       = fixed h2_weave_J
  3. mismatch_same_fam = the SAME route family's other instance (final frame)
  4. mismatch_diff_fam = a DIFFERENT route family's final frame (hard mismatch)
Goal *position* is always the episode's own route endpoint, so SR/NE measure "did it
still complete ITS OWN route?". If SR stays high and the stop location barely moves under
wrong goals -> route/motion imitation (ignores goal image). If behaviour changes/diverts
-> preliminary goal-conditioning. Either way: no promotion.

Outputs -> assets/experiments/hospital_h7_raise_collection/goal_image_check/ (mismatched_*).
Run with gnm_train python. No training, no promotion, no commit.
"""
import csv, json, pickle, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
import cv2
import torch
from omegaconf import OmegaConf
from gnm_vlnverse.models.gnm import build_gnm
from gnm_vlnverse.evaluation.evaluator import GNMEvaluator
from gnm_vlnverse.evaluation.metrics import compute_all_metrics, Episode

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "datasets/isaac_hospital_h7r"
PLACEHOLDER = REPO / "assets/experiments/goals/h2_weave_J/goal_image.png"
OUT = REPO / "assets/experiments/hospital_h7_raise_collection/goal_image_check"
CAND = "checkpoints/h7r_hospital_pilot_finetune/best.pt"
BASE_YAML = REPO / "configs/gnm/gnm_h7r_hospital_pilot.yaml"
FAMILY = {"reception": "reception_to_corridor", "corridor": "corridor_straight",
          "turn": "turn_t_junction", "waiting": "waiting_to_doorway"}


def base(eid): return eid.replace("h7r_", "").split("_20")[0]


def find_ep_dir(basename):
    hits = sorted(ROOT.glob(f"*/h7r_{basename}_20*"))
    assert hits, f"no dir for {basename}"
    return hits[0]


def final_frame_np(basename):
    d = find_ep_dir(basename)
    last = max(int(p.stem) for p in d.glob("*.jpg"))
    img = cv2.imread(str(d / f"{last}.jpg"))
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB), str((d / f"{last}.jpg").relative_to(REPO)), last


def load_candidate():
    ckpt = torch.load(REPO / CAND, map_location="cpu", weights_only=False)
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


def rollout(ev, traj_dir, goal_img):
    """Rollout on traj_dir's own frames; goal IMAGE = goal_img; goal POS = own endpoint.
    Returns (Episode, final_pos, stop_step, n_steps)."""
    data = pickle.load(open(Path(traj_dir) / "traj_data.pkl", "rb"))
    pos, yaws = data["position"], data["yaw"]; T = len(pos)
    goal_pos = tuple(pos[T - 1].tolist())
    ev.reset_context(ev._load_frame_np(traj_dir, 0))
    sim = np.array(pos[0], dtype=np.float32); yaw = float(yaws[0])
    actual = [tuple(sim.tolist())]; stop_step = None
    steps = min(T - 1, ev.max_steps)
    for step in range(steps):
        f = ev._load_frame_np(traj_dir, min(step, T - 1))
        dist_pred, act = ev.predict(f, goal_img)
        c, s = np.cos(yaw), np.sin(yaw)
        sim = sim + np.array([c * act[0] - s * act[1], s * act[0] + c * act[1]])
        actual.append(tuple(sim.tolist()))
        if dist_pred < ev.stop_threshold:
            stop_step = step; break
    ref = [tuple(p.tolist()) for p in pos]
    ep = Episode(actual_path=actual, reference_path=ref, goal_pos=goal_pos, collisions=[])
    return ep, tuple(float(v) for v in sim), (stop_step if stop_step is not None else steps), len(actual) - 1


# mismatch design: test episodes are turn_02, waiting_02
MISMATCH = {
    "turn_02":    {"same_fam": "turn_01",    "diff_fam": "reception_01"},
    "waiting_02": {"same_fam": "waiting_01", "diff_fam": "corridor_01"},
}
TEST = ["turn_02", "waiting_02"]

ev = load_candidate()
ph = cv2.imread(str(PLACEHOLDER)); GOAL_PH = cv2.cvtColor(ph, cv2.COLOR_BGR2RGB)

manifest = {"model": CAND, "note": "goal POSITION always = episode's own endpoint; only the "
            "goal IMAGE is swapped. SR/NE measure completing the episode's OWN route.",
            "conditions": {}, "episodes": []}
rows = []           # aggregate per condition
per_ep = {}         # (episode, condition) -> dict
cond_eps = {c: [] for c in ["correct", "placeholder", "mismatch_same_fam", "mismatch_diff_fam"]}

for b in TEST:
    d = find_ep_dir(b)
    fam = FAMILY[b.split("_")[0]]
    # goal images per condition
    own_img, own_path, own_idx = final_frame_np(b)
    sf, sf_path, _ = final_frame_np(MISMATCH[b]["same_fam"])
    df, df_path, _ = final_frame_np(MISMATCH[b]["diff_fam"])
    goals = {"correct": (own_img, f"own final frame ({own_path})"),
             "placeholder": (GOAL_PH, "fixed h2_weave_J placeholder"),
             "mismatch_same_fam": (sf, f"{MISMATCH[b]['same_fam']} final frame ({sf_path})"),
             "mismatch_diff_fam": (df, f"{MISMATCH[b]['diff_fam']} final frame ({df_path})")}
    correct_final = None
    ep_rec = {"episode": f"h7r_{b}", "family": fam, "own_goal_frame": own_path,
              "mismatch_same_fam": MISMATCH[b]["same_fam"], "mismatch_diff_fam": MISMATCH[b]["diff_fam"],
              "conditions": {}}
    for cond, (gimg, desc) in goals.items():
        ep, final_pos, stop_step, n_steps = rollout(ev, d, gimg)
        m = compute_all_metrics([ep]).to_dict()
        if cond == "correct":
            correct_final = final_pos
        dfp = float(np.hypot(final_pos[0] - correct_final[0], final_pos[1] - correct_final[1])) \
            if correct_final else 0.0
        per_ep[(b, cond)] = {"SR": m["SR"], "OSR": m["OSR"], "SPL": m["SPL"], "NE": m["NE"],
                             "nDTW": m["nDTW"], "stop_step": stop_step, "n_steps": n_steps,
                             "final_pos": [round(final_pos[0], 3), round(final_pos[1], 3)],
                             "final_pos_delta_from_correct_m": round(dfp, 3)}
        cond_eps[cond].append(ep)
        ep_rec["conditions"][cond] = {"goal_image": desc, **per_ep[(b, cond)]}
    manifest["episodes"].append(ep_rec)

# aggregate rows
for cond in ["correct", "placeholder", "mismatch_same_fam", "mismatch_diff_fam"]:
    m = compute_all_metrics(cond_eps[cond]).to_dict()
    mean_delta = float(np.mean([per_ep[(b, cond)]["final_pos_delta_from_correct_m"] for b in TEST]))
    rows.append({"goal_condition": cond, "n": m["n_episodes"], "SR": m["SR"], "OSR": m["OSR"],
                 "SPL": m["SPL"], "NE": m["NE"], "nDTW": m["nDTW"],
                 "mean_final_pos_delta_m": round(mean_delta, 3)})

manifest["conditions"] = {r["goal_condition"]: {k: r[k] for k in
                          ("SR", "OSR", "SPL", "NE", "nDTW", "mean_final_pos_delta_m")} for r in rows}
(OUT / "h7r_mismatched_goal_manifest.json").write_text(json.dumps(manifest, indent=2))

# eval matrix csv + md
cols = ["goal_condition", "n", "SR", "OSR", "SPL", "NE", "nDTW", "mean_final_pos_delta_m"]
with open(OUT / "h7r_mismatched_goal_eval_matrix.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(cols)
    for r in rows:
        w.writerow([r["goal_condition"], r["n"], f"{r['SR']:.3f}", f"{r['OSR']:.3f}", f"{r['SPL']:.3f}",
                    f"{r['NE']:.2f}", f"{r['nDTW']:.3f}", f"{r['mean_final_pos_delta_m']:.3f}"])
md = ["# H7r mismatched-goal ablation — does the candidate use the goal image?", "",
      "Same H7r candidate, H7r test episodes. Goal POSITION = episode's own endpoint in every "
      "row; only the goal IMAGE is swapped. `mean_final_pos_delta_m` = how far the final stop "
      "moved vs the correct-goal rollout (0 = identical trajectory ending).", "",
      "| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
for r in rows:
    md.append(f"| {r['goal_condition']} | {r['n']} | {r['SR']:.3f} | {r['OSR']:.3f} | {r['SPL']:.3f} | "
              f"{r['NE']:.2f} | {r['nDTW']:.3f} | {r['mean_final_pos_delta_m']:.3f} |")
(OUT / "h7r_mismatched_goal_eval_matrix.md").write_text("\n".join(md))

print(json.dumps({r["goal_condition"]: {"SR": r["SR"], "NE": round(r["NE"], 2),
                  "final_pos_delta_m": r["mean_final_pos_delta_m"]} for r in rows}, indent=2))
print("MISMATCHED-GOAL ABLATION WRITTEN ->", OUT)
