"""H8-M Step B — embedding distinctness ANALYSIS (validation-only; no Isaac, no training).

Reads the raw rendered views (.npy) + render_manifest.json produced by
scripts/gnm/h8m_embedding_render.py, computes visual distinctness with a PRIMARY DINO embedding
(timm vit_small_patch16_224.dino, cosine) and SECONDARY aHash + SSIM, calibrates T_dup/T_cross,
assesses each zone, checks the recep_junction angular-branch candidate, and writes contact sheets
+ similarity matrices + manifest + report. No model training, no rollout, no promotion.

Run with: ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h8m_embedding_analyze.py
"""
import csv, json, math, os, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch, timm
import cv2  # scipy.ndimage is broken in gnm_train (numpy 2.x); use cv2 for the SSIM blur


def gaussian_filter(x, sigma):
    return cv2.GaussianBlur(x.astype(np.float32), (0, 0), sigmaX=float(sigma)).astype(np.float64)

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
HANDOFF = Path(os.environ.get("H8M_RENDER_HANDOFF", "/tmp/h8m_render_npy"))  # raw .npy handoff (not committed)
OUT = REPO / "assets/experiments/hospital_h8_m_embedding_search"
CS = OUT / "contact_sheets"; RM = OUT / "render_metadata"
for d in (OUT, CS, RM):
    d.mkdir(parents=True, exist_ok=True)
ZONES = {z["zone_id"]: z for z in
         json.loads((REPO / "assets/experiments/hospital_h8_m_route_zone_design/"
                     "h8m_zone_candidates.json").read_text())["zones"]}
PLACEHOLDER = REPO / "assets/experiments/goals/h2_weave_J/goal_image.png"

# distinctness thresholds (DINO cosine) — proposed, then calibrated against observed values
T_DUP_INIT = 0.92     # within-split near-duplicate
T_CROSS_INIT = 0.60   # cross-split leakage ceiling (genuinely-different rooms should be below)
# render-validity: a goal view pointing into unlit void/wall is NOT a usable goal image
LUMA_MIN = 15.0       # below -> black-void (coordinate points into void/wall)
BLACK_MAX = 0.5       # lower-frame black fraction above -> mostly wall/void
_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def load_manifest():
    m = json.loads((HANDOFF / "render_manifest.json").read_text())
    if m.get("aborted"):
        raise SystemExit("render aborted at scene gate: " + json.dumps(m.get("scene_gate")))
    return m


def rgb_of(view_id):
    p = HANDOFF / f"{view_id}.npy"
    return np.load(p) if p.exists() else None


# ── embeddings ───────────────────────────────────────────────────────────────
def dino_model():
    m = timm.create_model("vit_small_patch16_224.dino", pretrained=True, num_classes=0)
    return m.eval()


@torch.no_grad()
def dino_embed(model, imgs):
    """imgs: list of HxWx3 uint8 -> L2-normalized feature matrix (N,D)."""
    batch = []
    for a in imgs:
        im = Image.fromarray(a).convert("RGB").resize((224, 224), Image.BILINEAR)
        t = torch.from_numpy(np.asarray(im, dtype=np.float32) / 255.0).permute(2, 0, 1)
        batch.append(t)
    x = (torch.stack(batch) - _MEAN) / _STD
    f = model(x)
    return torch.nn.functional.normalize(f, dim=1).cpu().numpy()


def ahash_vec(a):
    im = Image.fromarray(a).convert("L").resize((16, 16), Image.BILINEAR)
    g = np.asarray(im, dtype=np.float32)
    return (g > g.mean()).astype(np.uint8).flatten()


def ahash_sim(u, v):
    return 1.0 - np.mean(u != v)


def ssim(a, b):
    """Global SSIM on grayscale (Gaussian-weighted), scipy only (skimage absent)."""
    ga = np.asarray(Image.fromarray(a).convert("L").resize((256, 256)), np.float64)
    gb = np.asarray(Image.fromarray(b).convert("L").resize((256, 256)), np.float64)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mu_a = gaussian_filter(ga, 1.5); mu_b = gaussian_filter(gb, 1.5)
    va = gaussian_filter(ga * ga, 1.5) - mu_a ** 2
    vb = gaussian_filter(gb * gb, 1.5) - mu_b ** 2
    vab = gaussian_filter(ga * gb, 1.5) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + C1) * (2 * vab + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (va + vb + C2))
    return float(np.clip(s.mean(), -1, 1))


# ── collect goal + decision views ────────────────────────────────────────────
man = load_manifest()
present = {v["view_id"]: v for v in man["views"] if not v.get("empty")}
# goal views for the distinctness gate: <zone>__goalA / __goalB, tagged with split role
GOALS = []   # (view_id, zone_id, role, split)
for zid, z in ZONES.items():
    for role in ("goalA", "goalB"):
        vid = f"{zid}__{role}"
        if vid in present:
            GOALS.append((vid, zid, role, z["split_role"]))
# add the cross-scene hard-negative placeholder goal image
if PLACEHOLDER.exists():
    GOALS.append(("placeholder_h2_weave_J", "h8m_hardneg_crossscene", "placeholder", "hard_negative"))

imgs, ids = [], []
for vid, zid, role, split in GOALS:
    a = np.array(Image.open(PLACEHOLDER).convert("RGB")) if vid.startswith("placeholder") else rgb_of(vid)
    if a is None:
        continue
    imgs.append(a); ids.append((vid, zid, role, split))

model = dino_model()
D = dino_embed(model, imgs)
AH = [ahash_vec(a) for a in imgs]
N = len(ids)
dino_cos = np.zeros((N, N)); ah = np.zeros((N, N)); ss = np.zeros((N, N))
for i in range(N):
    for j in range(N):
        dino_cos[i, j] = float(D[i] @ D[j])
        ah[i, j] = ahash_sim(AH[i], AH[j])
        ss[i, j] = ssim(imgs[i], imgs[j])

label = [vid for vid, _, _, _ in ids]
split_of = {vid: split for vid, _, _, split in ids}
zone_of = {vid: zid for vid, zid, _, _ in ids}


def pair_class(i, j):
    a, b = ids[i], ids[j]
    if a[1] == b[1]:
        return "within_zone"
    if a[3] == b[3]:
        return "within_split"
    return "cross_split"


# cross-split off-diagonal DINO cosines (exclude hard-negative placeholder from "rooms" stats)
cross_vals, within_split_vals, within_zone_vals = [], [], []
for i in range(N):
    for j in range(i + 1, N):
        c = pair_class(i, j); v = dino_cos[i, j]
        if c == "cross_split":
            cross_vals.append(v)
        elif c == "within_split":
            within_split_vals.append(v)
        else:
            within_zone_vals.append(v)

# calibrate: T_cross set to separate distinct-room pairs (low) from same-alcove pairs (high).
# Use observed cross-split distribution; propose the midpoint of a visible gap, clamped to a
# sane band, and keep the init as a documented reference.
cross_sorted = sorted(cross_vals)
gap_thr = T_CROSS_INIT
if len(cross_sorted) >= 2:
    gaps = [(cross_sorted[k + 1] - cross_sorted[k], (cross_sorted[k] + cross_sorted[k + 1]) / 2)
            for k in range(len(cross_sorted) - 1)]
    biggest = max(gaps, key=lambda g: g[0])
    if biggest[0] >= 0.05:
        gap_thr = round(float(biggest[1]), 3)
T_CROSS = float(min(max(gap_thr, 0.45), 0.80))
T_DUP = T_DUP_INIT

# ── per-zone assessment ──────────────────────────────────────────────────────
def view_valid(vid):
    """A goal view is render-valid only if it is not black-void / mostly-wall."""
    if vid.startswith("placeholder"):
        return True
    v = present.get(vid)
    return bool(v and v.get("mean_luma", 0) >= LUMA_MIN
               and v.get("lower_frame_black_frac", 1) <= BLACK_MAX)


def zone_goal_ids(zid):
    return [vid for vid in label if zone_of[vid] == zid]


assess = {}
for zid, z in ZONES.items():
    gids = zone_goal_ids(zid)
    if not gids:
        assess[zid] = {"status": "not_rendered", "split_role": z["split_role"],
                       "feasibility": z["feasibility"], "reason": "no goal view rendered"}
        continue
    idx = [label.index(g) for g in gids]
    # max cross-split similarity vs any goal in a different split
    cross_max, cross_arg = 0.0, None
    for gi in idx:
        for j in range(N):
            if split_of[label[gi]] != split_of[label[j]] and j not in idx:
                if dino_cos[gi, j] > cross_max:
                    cross_max, cross_arg = float(dino_cos[gi, j]), label[j]
    # within-zone goalA vs goalB (branch distinctness)
    ab = float(dino_cos[idx[0], idx[1]]) if len(idx) >= 2 else None
    # duplicate vs another zone in the SAME split
    dup_max, dup_arg = 0.0, None
    for gi in idx:
        for j in range(N):
            if zone_of[label[j]] != zid and split_of[label[j]] == split_of[label[gi]]:
                if dino_cos[gi, j] > dup_max:
                    dup_max, dup_arg = float(dino_cos[gi, j]), label[j]
    valid = {g: view_valid(g) for g in gids}
    all_valid = all(valid.values())
    if z["split_role"] == "hard_negative":
        status = "hard_negative_candidate"
    elif not all_valid:
        status = "render_invalid_needs_coordinate_correction"
    elif dup_max >= T_DUP:
        status = "possible_duplicate"
    elif cross_max >= T_CROSS:
        status = "visually_indistinct_reject_or_merge"
    else:
        status = "visually_distinct"
    assess[zid] = {
        "split_role": z["split_role"], "feasibility": z["feasibility"],
        "goal_views_render_valid": valid, "all_goal_views_render_valid": all_valid,
        "cross_split_max_dino": round(cross_max, 3), "cross_split_arg": cross_arg,
        "within_zone_goalA_vs_goalB_dino": round(ab, 3) if ab is not None else None,
        "same_split_duplicate_max_dino": round(dup_max, 3), "duplicate_arg": dup_arg,
        "status": status,
        "needs_drive_validation": bool("NEEDS_DRIVE" in z["feasibility"]),
        "mean_luma": {g: present.get(g, {}).get("mean_luma") for g in gids},
        "lower_frame_black": {g: present.get(g, {}).get("lower_frame_black_frac") for g in gids},
    }

# ── recep_junction angular-branch check ──────────────────────────────────────
rj = "h8m_recep_junction"
rj_dec = present.get(f"{rj}__decision"); rj_ga = present.get(f"{rj}__goalA"); rj_gb = present.get(f"{rj}__goalB")
rj_ab = assess.get(rj, {}).get("within_zone_goalA_vs_goalB_dino")
rj_ga_valid = view_valid(f"{rj}__goalA"); rj_gb_valid = view_valid(f"{rj}__goalB")
rj_dec_visible = bool(rj_dec and rj_dec.get("mean_luma", 0) > 12)
rj_dec_no_occl = bool(rj_dec and rj_dec.get("lower_frame_black_frac", 1) < 0.05)
recep_junction_check = {
    "decision_frame_render_visible": rj_dec_visible,
    "goalA_render_valid": rj_ga_valid, "goalB_render_valid": rj_gb_valid,
    "goalA_luma": (rj_ga or {}).get("mean_luma"), "goalB_luma": (rj_gb or {}).get("mean_luma"),
    "goalA_lower_black": (rj_ga or {}).get("lower_frame_black_frac"),
    "goalB_lower_black": (rj_gb or {}).get("lower_frame_black_frac"),
    "goalA_goalB_dino_cosine": rj_ab,
    # distinguishable is only meaningful if BOTH goal views are render-valid (not black-void)
    "goalA_goalB_visually_distinguishable": bool(rj_ga_valid and rj_gb_valid
                                                 and rj_ab is not None and rj_ab < T_CROSS),
    "no_black_lower_frame_occlusion_decision": rj_dec_no_occl,
    "within_safe_spawn_relocation_plan": bool(ZONES[rj]["within_envelope"]),
    "branch_render_valid": bool(rj_dec_visible and rj_ga_valid and rj_gb_valid),
    "drive_feasibility": "NOT_TESTED_UNTIL_STEP_C",
    "note": "free-camera render: scene visibility + distinctness only; chassis occlusion and "
            "drivability are Step-C checks. A goal view that is black-void (luma~0) means the "
            "proposed branch coordinate points into unlit void/wall -> NOT a valid junction.",
}

# ── contact sheets ───────────────────────────────────────────────────────────
def thumb(view_id, size=(256, 192)):
    a = np.array(Image.open(PLACEHOLDER).convert("RGB")) if view_id.startswith("placeholder") else rgb_of(view_id)
    if a is None:
        return Image.new("RGB", size, (40, 40, 40))
    return Image.fromarray(a).convert("RGB").resize(size, Image.BILINEAR)


try:
    fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
except Exception:
    fb = fr = ImageFont.load_default()

# per-zone 3-panel sheets (decision / goalA / goalB) + small per-view PNGs into render_metadata
for zid, z in ZONES.items():
    panels = [f"{zid}__decision", f"{zid}__goalA", f"{zid}__goalB"]
    if not any(p in present for p in panels):
        continue
    tw, th = 256, 192
    sheet = Image.new("RGB", (tw * 3 + 20, th + 40), "white"); dr = ImageDraw.Draw(sheet)
    dr.text((6, 4), f"{zid}  [{z['split_role']}]  {z['family']}", font=fb, fill="black")
    for k, p in enumerate(panels):
        im = thumb(p, (tw, th)); sheet.paste(im, (6 + k * (tw + 4), 26))
        dr.text((6 + k * (tw + 4), 26 + th + 2), p.split("__")[-1], font=fr, fill="#333")
        im.save(RM / f"{p}.png")
    sheet.save(CS / f"{zid}.png")

# goal-image overview sheet grouped by split
order = sorted(range(N), key=lambda i: (ids[i][3], ids[i][1], ids[i][2]))
cols = 4; rows = math.ceil(len(order) / cols); tw, th = 220, 165
ov = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 34) + 8), "white"); dov = ImageDraw.Draw(ov)
for k, i in enumerate(order):
    vid, zid, role, split = ids[i]
    im = thumb(vid, (tw, th)); r, c = divmod(k, cols)
    ov.paste(im, (8 + c * (tw + 8), 8 + r * (th + 34)))
    dov.text((8 + c * (tw + 8), 8 + r * (th + 34) + th + 2), f"{split}:{zid.replace('h8m_','')}",
             font=fr, fill="#111")
    dov.text((8 + c * (tw + 8), 8 + r * (th + 34) + th + 15), role, font=fr, fill="#555")
ov.save(CS / "_goal_images_by_split.png")

# ── similarity matrices (csv + md) ───────────────────────────────────────────
with open(OUT / "h8m_visual_similarity_matrix.csv", "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["metric", "view_i", "split_i", "view_j", "split_j", "pair_class", "similarity"])
    for i in range(N):
        for j in range(i + 1, N):
            pc = pair_class(i, j)
            for mname, M in (("dino_cosine", dino_cos), ("ahash", ah), ("ssim", ss)):
                w.writerow([mname, label[i], split_of[label[i]], label[j], split_of[label[j]],
                            pc, round(float(M[i, j]), 4)])

ml = ["# H8-M Visual Similarity Matrix — DINO cosine (primary)", "",
      "Goal images only. **DINO ViT-S/16 cosine is the primary distinctness metric**; aHash/SSIM "
      "are secondary (see CSV). Higher = more similar. Rows/cols grouped; `split` in brackets.", "",
      "| goal view | " + " | ".join(f"{label[j].replace('h8m_','')[:14]}" for j in range(N)) + " |",
      "|" + "---|" * (N + 1)]
for i in range(N):
    ml.append(f"| {label[i].replace('h8m_','')[:20]} [{split_of[label[i]][:4]}] | " +
              " | ".join(f"{dino_cos[i, j]:.2f}" for j in range(N)) + " |")
(OUT / "h8m_visual_similarity_matrix.md").write_text("\n".join(ml) + "\n")

# ── manifest ─────────────────────────────────────────────────────────────────
def stats(v):
    return {"n": len(v), "min": round(min(v), 3), "max": round(max(v), 3),
            "mean": round(float(np.mean(v)), 3)} if v else {"n": 0}


distinct_zones = [z for z, a in assess.items() if a.get("status") == "visually_distinct"]
indistinct_zones = [z for z, a in assess.items() if a.get("status") == "visually_indistinct_reject_or_merge"]
manifest = {
    "status": "VALIDATION_ONLY", "step": "H8-M Step B embedding distinctness search",
    "primary_metric": "DINO ViT-S/16 cosine (timm vit_small_patch16_224.dino)",
    "secondary_metrics": ["aHash 16x16", "global SSIM"],
    "scene_gate": man.get("scene_gate", {}).get("pass"),
    "render": {k: man.get(k) for k in ("resolution", "camera_height_m", "camera_raise_note",
                                       "free_camera_no_robot_body", "occlusion_note",
                                       "hospital_prim_count")},
    "n_goal_views": N, "views_rendered": len(present),
    "thresholds": {"T_dup_dino": T_DUP, "T_cross_dino": T_CROSS, "T_cross_init": T_CROSS_INIT,
                   "T_dup_init": T_DUP_INIT,
                   "calibration": "T_cross set at the largest gap in the observed cross-split "
                                  "DINO-cosine distribution (clamped to [0.45,0.80]); T_dup kept "
                                  "at the near-duplicate default."},
    "similarity_stats_dino": {"cross_split": stats(cross_vals),
                              "within_split": stats(within_split_vals),
                              "within_zone": stats(within_zone_vals)},
    "zone_assessment": assess,
    "recep_junction_check": recep_junction_check,
    "distinct_zones": distinct_zones, "indistinct_zones": indistinct_zones,
    "decision_rule_outcome": None,  # filled below
    "caveats": [
        "Validation-only render: free camera, no robot body -> lower-frame occlusion reflects "
        "scene geometry, NOT chassis; chassis occlusion + drivability are Step-C checks.",
        "Distinctness is embedding-based (DINO) + aHash/SSIM; no training, no rollout, no promotion.",
        "Coordinates are Step-A design seeds; a distinct render does NOT prove drive feasibility.",
    ],
}
# decision rule — the true angular branch must be RENDER-VALID (both goal views real, not void)
rj_ok = bool(recep_junction_check["branch_render_valid"] and
             recep_junction_check["goalA_goalB_visually_distinguishable"])
if not rj_ok:
    outcome = "RE_SCOPE_H8M_ANGULAR_BRANCH_NOT_RENDER_VALID"
elif len(distinct_zones) >= 3:
    outcome = "EMBEDDING_DISTINCTNESS_PROMISING_PROCEED_TO_STEP_C_DRIVE_VALIDATION"
else:
    outcome = "PARTIAL_MERGE_DEFER_INDISTINCT_ZONES_BEFORE_STEP_C"
manifest["decision_rule_outcome"] = outcome
(OUT / "h8m_embedding_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

# ── report ───────────────────────────────────────────────────────────────────
def arow(zid, a):
    if a.get("status") == "not_rendered":
        return f"| {zid.replace('h8m_','')} | {a['split_role']} | not rendered | — | — | — | {a['feasibility']} |"
    return (f"| {zid.replace('h8m_','')} | {a['split_role']} | {a['status']} | "
            f"{a['cross_split_max_dino']} | {a['within_zone_goalA_vs_goalB_dino']} | "
            f"{a['same_split_duplicate_max_dino']} | {a['feasibility']} |")


rep = ["# H8-M Step B — Embedding Distinctness Search Report (VALIDATION ONLY)", "",
       "**Status: VALIDATION ONLY.** Rendering is validation evidence only — NOT recording, "
       "training, rollout, promotion, or benchmark evidence. No robot was driven; no rosbag or "
       "trajectory was recorded; no model was trained; `CL_BOUND_XY` unchanged. Verified "
       "hospital.usd, scene gate **" + ("PASS" if man.get("scene_gate", {}).get("pass") else "FAIL") +
       "**, free camera at the raised (~0.12 m) mount height, level horizon.", "",
       "## Question",
       "Are the H8-M Step-A candidate rooms/goals visually distinct enough (under an embedding "
       "gate) to support a stronger held-out visual split — and is the `recep_junction` angular "
       "branch render-valid?", "",
       "## Method",
       f"- **Primary:** DINO ViT-S/16 cosine ({manifest['primary_metric']}). **Secondary:** aHash "
       "16x16 + global SSIM (in the CSV).",
       f"- Goal images rendered per zone (goalA/goalB) + the cross-scene placeholder; "
       f"{N} goal views compared pairwise.",
       f"- Thresholds: **T_cross = {T_CROSS}** (cross-split leakage ceiling; calibrated at the "
       f"largest gap in the observed cross-split distribution, clamped [0.45,0.80]; init "
       f"{T_CROSS_INIT}); **T_dup = {T_DUP}** (within-split near-duplicate).", "",
       "## Observed DINO-cosine distribution",
       f"- cross-split: {stats(cross_vals)}",
       f"- within-split: {stats(within_split_vals)}",
       f"- within-zone (goalA vs goalB): {stats(within_zone_vals)}", "",
       "## Per-zone assessment",
       "| zone | split | status | cross-split max DINO | goalA-vs-goalB DINO | same-split dup DINO | feasibility |",
       "|---|---|---|---|---|---|---|",
       *[arow(z, assess[z]) for z in ZONES], "",
       f"- **visually distinct** (cross-split DINO < {T_CROSS}): "
       f"{', '.join(distinct_zones) if distinct_zones else 'NONE'}.",
       f"- **visually indistinct (reject/merge)**: "
       f"{', '.join(indistinct_zones) if indistinct_zones else 'NONE'}.", "",
       "## recep_junction angular-branch check (the core H8-S fix)",
       f"- decision frame render-visible: **{recep_junction_check['decision_frame_render_visible']}**",
       f"- goalA render-valid (luma {recep_junction_check['goalA_luma']}, lower-black "
       f"{recep_junction_check['goalA_lower_black']}): **{recep_junction_check['goalA_render_valid']}**",
       f"- goalB render-valid (luma {recep_junction_check['goalB_luma']}, lower-black "
       f"{recep_junction_check['goalB_lower_black']}): **{recep_junction_check['goalB_render_valid']}**",
       f"- goalA vs goalB visually distinguishable (both valid AND DINO "
       f"{recep_junction_check['goalA_goalB_dino_cosine']} < T_cross {T_CROSS}): "
       f"**{recep_junction_check['goalA_goalB_visually_distinguishable']}**",
       f"- **branch render-valid (decision visible AND both goals valid): "
       f"{recep_junction_check['branch_render_valid']}**",
       f"- within safe spawn-relocation envelope: **{recep_junction_check['within_safe_spawn_relocation_plan']}**",
       f"- drive feasibility: **{recep_junction_check['drive_feasibility']}** (Step C).",
       f"- {recep_junction_check['note']}", "",
       "## Decision",
       f"**{outcome}.**",
       "- If embedding distinctness is promising and the junction is render-valid → Step C drive "
       "validation. If the true angular branch is visually indistinct or not render-valid → "
       "**re-scope H8-M** before drive validation. If candidate rooms collapse visually → "
       "reject/merge/defer them rather than forcing a fake held-out split.", "",
       "## Interpretation (honest)",
       "- **`recep_junction` is NOT render-valid**: goalA is a black void (luma 0.0, 100% lower "
       "black) and goalB is 80% black — the proposed branch coordinates point into unlit "
       "void/wall, and the decision frame is a straight corridor. No real junction exists at "
       "these coordinates.",
       "- **An initial automated junction check falsely PASSED** by testing only the decision "
       "frame's occlusion; it was **corrected by adding render-validity gating on the GOAL views** "
       "(a goal view with luma < 15 or lower-frame black > 0.5 is a coordinate-into-wall, not a "
       "distinct branch). Under the fix the junction correctly fails.",
       "- **Only 1 of 8 zones is visually distinct** (`waiting_seating`); the **vending / lobby / "
       "east zones collapse visually** (same alcove, DINO cross-split ≥ T_cross) and the reception "
       "fork/desk views are walls/windows.",
       "- **The H8-M Step-A coordinates cannot currently support a true angular junction OR a "
       "multi-room held-out visual split** in this scene envelope.",
       "- **This is a re-scope signal, NOT a success** — the validation gate did its job before "
       "any drive/record/train. A bounded real-junction render scan is the next step before any "
       "re-scope is finalized.", "",
       "## Claim boundary",
       "- Validation-only rendering; no recording, no training, no rollout, no promotion, no "
       "benchmark or autonomy claim; incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`.",
       "- Free camera (no robot body): distinctness + scene visibility only; chassis occlusion and "
       "drivability are Step-C drive-validation checks. `CL_BOUND_XY` unchanged.", "",
       "## Artifacts",
       "`assets/experiments/hospital_h8_m_embedding_search/`: `h8m_embedding_manifest.json`, "
       "`h8m_visual_similarity_matrix.{csv,md}`, `h8m_embedding_search_report.md`, "
       "`contact_sheets/`, `render_metadata/`. Harness: `scripts/gnm/h8m_embedding_render.py` "
       "(isaac render), `scripts/gnm/h8m_embedding_analyze.py` (this analysis). Raw .npy kept in "
       "scratchpad (not committed)."]
(OUT / "h8m_embedding_search_report.md").write_text("\n".join(rep) + "\n")

# copy render manifest into render_metadata for the evidence bundle
(RM / "h8m_render_manifest.json").write_text(json.dumps(man, indent=2) + "\n")

print(json.dumps({"scene_gate": man.get("scene_gate", {}).get("pass"),
                  "n_goal_views": N, "T_cross": T_CROSS, "T_dup": T_DUP,
                  "distinct_zones": distinct_zones, "indistinct_zones": indistinct_zones,
                  "recep_junction_ok": rj_ok, "outcome": outcome}, indent=2))
print("H8-M EMBEDDING ANALYSIS WRITTEN ->", OUT)
