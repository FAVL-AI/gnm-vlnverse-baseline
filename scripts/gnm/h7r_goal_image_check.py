"""H7r scene-aligned goal-image check (NO TRAINING).

Premise correction (verified in gnm_vlnverse/evaluation/evaluator.py:24,175-179,192):
the offline Track-A eval ALREADY uses each episode's OWN final recorded frame as the
goal image (scene-aligned, episode-specific). The fixed placeholder h2_weave_J was only
the recording-time goal-id; it never entered the offline eval metrics.

This harness runs the comparison Frank asked for, on the existing H1 incumbent and H7r
candidate, over the H7r data-root splits:
  A) scene-aligned goal  = each episode's own final recorded frame (eval default).
  B) placeholder goal    = fixed h2_weave_J goal image for ALL episodes.
Condition A reproduces the committed eval (faithfulness check). B tests whether the
result is placeholder-goal-sensitive / whether the policy uses the goal image at all.

Outputs -> assets/experiments/hospital_h7_raise_collection/goal_image_check/.
Run with the gnm_train python. No training, no promotion, no commit.
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
TRAJ = REPO / "assets/experiments/trajectories"
QT = REPO / "assets/experiments/hospital_h7_raise_collection/reports/h7r_recording_quality_table.csv"
PLACEHOLDER = REPO / "assets/experiments/goals/h2_weave_J/goal_image.png"
OUT = REPO / "assets/experiments/hospital_h7_raise_collection/goal_image_check"
(OUT / "goals").mkdir(parents=True, exist_ok=True)
BASE_YAML = REPO / "configs/gnm/gnm_h7r_hospital_pilot.yaml"
INC = "checkpoints/hospital_front_rgb_finetune/best.pt"
CAND = "checkpoints/h7r_hospital_pilot_finetune/best.pt"
FAMILY = {"reception": "reception_to_corridor", "corridor": "corridor_straight",
          "turn": "turn_t_junction", "waiting": "waiting_to_doorway"}
SPLITS = ["test", "val", "train"]


def base(eid):
    return eid.replace("h7r_", "").split("_20")[0]


def load_evaluator(ckpt_rel):
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
                        max_steps=ev_cfg.get("max_steps", 500),
                        device="cuda", track="A")


def rollout_fixed_goal(ev, traj_dir, goal_img):
    """Replicate evaluate_from_files but with a FIXED (placeholder) goal image."""
    data = pickle.load(open(Path(traj_dir) / "traj_data.pkl", "rb"))
    pos, yaws = data["position"], data["yaw"]; T = len(pos)
    goal_pos = tuple(pos[T - 1].tolist())
    ev.reset_context(ev._load_frame_np(traj_dir, 0))
    sim = np.array(pos[0], dtype=np.float32); yaw = float(yaws[0])
    actual = [tuple(sim.tolist())]
    for step in range(min(T - 1, ev.max_steps)):
        f = ev._load_frame_np(traj_dir, min(step, T - 1))
        dist_pred, act = ev.predict(f, goal_img)
        c, s = np.cos(yaw), np.sin(yaw)
        sim = sim + np.array([c * act[0] - s * act[1], s * act[0] + c * act[1]])
        actual.append(tuple(sim.tolist()))
        if dist_pred < ev.stop_threshold:
            break
    ref = [tuple(p.tolist()) for p in pos]
    return Episode(actual_path=actual, reference_path=ref, goal_pos=goal_pos, collisions=[])


def episodes_of(split):
    return sorted((ROOT / split).glob("h7r_*"))


# ---- placeholder goal image (RGB np) ----
_ph = cv2.imread(str(PLACEHOLDER))
GOAL_PH = cv2.cvtColor(_ph, cv2.COLOR_BGR2RGB)

# ---- quality-table facts for manifest ----
qt = {r["episode"]: r for r in csv.DictReader(open(QT))}

# ======== Task 1: inspect + Task 2/3: extract scene-aligned goals + manifest ========
manifest = []
inspect_ok = True
for split in SPLITS:
    for d in episodes_of(split):
        eid = d.name; b = base(eid); ep_key = f"h7r_{b}"
        jpgs = sorted(int(p.stem) for p in d.glob("*.jpg"))
        T = len(jpgs); last = jpgs[-1] if jpgs else None
        has_start = 0 in jpgs; has_mid = (T // 2) in jpgs; has_goal = last is not None
        if not (has_start and has_mid and has_goal and T > 2):
            inspect_ok = False
        # scene-aligned goal = final recorded frame
        goal_src = d / f"{last}.jpg"
        goal_dst = OUT / "goals" / f"{ep_key}_goal.jpg"
        goal_dst.write_bytes(goal_src.read_bytes())
        # rosbag provenance from the recorded episode's metadata
        tmeta_dirs = sorted(TRAJ.glob(f"{eid}"))
        rosbag = None
        if tmeta_dirs and (tmeta_dirs[0] / "episode_metadata.json").exists():
            rosbag = json.loads((tmeta_dirs[0] / "episode_metadata.json").read_text()).get("rosbag_path")
        q = qt.get(ep_key, {})
        manifest.append({
            "episode_id": eid, "episode": ep_key, "split": split,
            "route_family": FAMILY.get(b.split("_")[0], "?"),
            "n_frames": T, "goal_frame_index": last,
            "source_frame_path": str(goal_src.relative_to(REPO)),
            "extracted_goal_image": str(goal_dst.relative_to(REPO)),
            "source_rosbag_path": rosbag,
            "camera_mount_raise_m": q.get("camera_mount_raise_m"),
            "scene_gate_pass": q.get("scene_gate_pass"),
            "from_recorded_camera_image_raw": True,
            "goal_facing": "final recorded frame (T-1) = route endpoint the robot faced",
        })
(OUT / "h7r_goal_image_manifest.json").write_text(json.dumps({
    "note": ("scene-aligned goal images = each episode's OWN final recorded /camera/image_raw "
             "frame; this is what the offline Track-A evaluator already uses (goal_idx=-1)."),
    "inspection_all_usable": inspect_ok, "n_episodes": len(manifest),
    "episodes": manifest}, indent=2))

# ======== Task 4/5: A (scene-aligned) vs B (placeholder) for both models ========
RUNS = [("incumbent", INC, "test"), ("candidate", CAND, "test"),
        ("candidate", CAND, "val"), ("candidate", CAND, "train"),
        ("incumbent", INC, "val")]
rows = []
per_ep_test = {}   # (model, cond, ep_base) -> per-episode metrics
for model_name, ckpt, split in RUNS:
    ev = load_evaluator(ckpt)
    epA, epB = [], []
    for d in episodes_of(split):
        b = base(d.name)
        a = ev.evaluate_from_files(d, goal_idx=-1)          # A: scene-aligned (own final frame)
        pb = rollout_fixed_goal(ev, d, GOAL_PH)             # B: fixed placeholder
        epA.append(a); epB.append(pb)
        if split == "test":
            per_ep_test[(model_name, "aligned", b)] = compute_all_metrics([a]).to_dict()
            per_ep_test[(model_name, "placeholder", b)] = compute_all_metrics([pb]).to_dict()
    for cond, eps in [("scene_aligned", epA), ("placeholder", epB)]:
        m = compute_all_metrics(eps).to_dict()
        rows.append({"model": model_name, "split": split, "goal_condition": cond,
                     "n": m["n_episodes"], "SR": m["SR"], "OSR": m["OSR"], "SPL": m["SPL"],
                     "NE": m["NE"], "nDTW": m["nDTW"]})
    del ev
    torch.cuda.empty_cache()

# ---- eval matrix csv + md ----
cols = ["model", "split", "goal_condition", "n", "SR", "OSR", "SPL", "NE", "nDTW"]
with open(OUT / "h7r_goal_image_eval_matrix.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for r in rows:
        w.writerow({**r, "SR": f"{r['SR']:.3f}", "OSR": f"{r['OSR']:.3f}", "SPL": f"{r['SPL']:.3f}",
                    "NE": f"{r['NE']:.2f}", "nDTW": f"{r['nDTW']:.3f}"})
md = ["# H7r goal-image eval matrix — scene-aligned vs fixed-placeholder goal", "",
      "No training. OSR>=SR invariant holds by construction. Scene-aligned = each episode's "
      "own final recorded frame (the eval default that the committed results used); placeholder "
      "= fixed h2_weave_J for all episodes.", "",
      "| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
for r in rows:
    md.append(f"| {r['model']} | {r['split']} | {r['goal_condition']} | {r['n']} | {r['SR']:.3f} | "
              f"{r['OSR']:.3f} | {r['SPL']:.3f} | {r['NE']:.2f} | {r['nDTW']:.3f} |")
(OUT / "h7r_goal_image_eval_matrix.md").write_text("\n".join(md))

# ---- per-family failure table on test (scene-aligned condition) ----
fam_rows = []
for b in ["turn_02", "waiting_02"]:
    fam = FAMILY[b.split("_")[0]]
    ia = per_ep_test[("incumbent", "aligned", b)]; ca = per_ep_test[("candidate", "aligned", b)]
    ip = per_ep_test[("incumbent", "placeholder", b)]; cp = per_ep_test[("candidate", "placeholder", b)]
    fam_rows.append({"episode": f"h7r_{b}", "family": fam,
                     "inc_aligned_SR": int(ia["SR"]), "cand_aligned_SR": int(ca["SR"]),
                     "cand_aligned_NE": round(ca["NE"], 2),
                     "inc_placeholder_SR": int(ip["SR"]), "cand_placeholder_SR": int(cp["SR"]),
                     "cand_placeholder_NE": round(cp["NE"], 2)})
fcols = ["episode", "family", "inc_aligned_SR", "cand_aligned_SR", "cand_aligned_NE",
         "inc_placeholder_SR", "cand_placeholder_SR", "cand_placeholder_NE"]
with open(OUT / "h7r_goal_image_per_family.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fcols); w.writeheader(); w.writerows(fam_rows)

# ---- summary numbers for the report ----
def get(model, split, cond):
    return next(r for r in rows if r["model"] == model and r["split"] == split and r["goal_condition"] == cond)
ca_t = get("candidate", "test", "scene_aligned"); cp_t = get("candidate", "test", "placeholder")
ia_t = get("incumbent", "test", "scene_aligned"); ip_t = get("incumbent", "test", "placeholder")
print(json.dumps({
    "inspection_all_usable": inspect_ok,
    "candidate_test_scene_aligned": {k: round(ca_t[k], 3) for k in ("SR", "OSR", "SPL", "NE", "nDTW")},
    "candidate_test_placeholder": {k: round(cp_t[k], 3) for k in ("SR", "OSR", "SPL", "NE", "nDTW")},
    "incumbent_test_scene_aligned": {k: round(ia_t[k], 3) for k in ("SR", "OSR", "SPL", "NE", "nDTW")},
    "incumbent_test_placeholder": {k: round(ip_t[k], 3) for k in ("SR", "OSR", "SPL", "NE", "nDTW")},
}, indent=2))
print("MANIFEST + MATRIX + PER-FAMILY WRITTEN ->", OUT)
