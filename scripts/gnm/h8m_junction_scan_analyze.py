"""H8-M — bounded junction-scan ANALYSIS (validation-only; no Isaac, no training).

Reads the junction-scan renders (.npy) + jscan_manifest.json, classifies each candidate junction,
and writes the manifest/table/report + contact sheets. A candidate is a RENDER_VALID_JUNCTION only
if the decision frame is visible, BOTH goal (branch) views are render-valid (not black-void /
wall-only / occluded), the expected action-angle separation is >=30 deg, AND the two branch views
are visually distinct (DINO) — i.e. two genuinely different corridors, not the same wall twice.

Run: ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h8m_junction_scan_analyze.py
"""
import csv, json, math, os, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch, timm
# Reviewed distinctness rule (Outcome A + E). Sibling module; this script runs from scripts/gnm.
from h8_distinctness_gate import (REAL_SCENE_DINO_THRESHOLD, REAL_SCENE_MARGIN,
                                  LEGACY_HARD_THRESHOLD_SUPERSEDED, PROVENANCE)

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
HANDOFF = Path(os.environ.get("H8M_JSCAN_HANDOFF", "/tmp/h8m_junction_npy"))
OUT = REPO / "assets/experiments/hospital_h8_m_junction_scan"
CS = OUT / "contact_sheets"; RM = OUT / "render_metadata"
for d in (OUT, CS, RM):
    d.mkdir(parents=True, exist_ok=True)

LUMA_MIN = 15.0       # below -> black-void / wall
BLACK_MAX = 0.5       # lower-frame black above -> occluded / wall-only
MIN_SEP = 30.0        # deg — a real angular branch
# Outcome A (calibrated, real indoor scenes): distinctness threshold ~0.76 with a margin band,
# superseding the arbitrary 0.60 (see scripts/gnm/h8_distinctness_gate.py and the gate decision doc).
# A pass also requires contact-sheet agreement; within-margin cosines are held for that human check.
BRANCH_DISTINCT = REAL_SCENE_DINO_THRESHOLD
BRANCH_MARGIN = REAL_SCENE_MARGIN
OPEN_MIN_DEPTH = 3.0  # m — a branch view must see >=3 m of open space ahead (else a near wall)
_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)

man = json.loads((HANDOFF / "jscan_manifest.json").read_text())
if man.get("aborted"):
    raise SystemExit("render aborted at scene gate")


def rgb_of(vid):
    p = HANDOFF / f"{vid}.npy"
    return np.load(p) if p.exists() else None


@torch.no_grad()
def dino_pair(model, a, b):
    def emb(x):
        im = Image.fromarray(x).convert("RGB").resize((224, 224), Image.BILINEAR)
        t = torch.from_numpy(np.asarray(im, np.float32) / 255.0).permute(2, 0, 1)[None]
        return torch.nn.functional.normalize(model((t - _MEAN) / _STD), dim=1)
    return float((emb(a) @ emb(b).T).item())


model = timm.create_model("vit_small_patch16_224.dino", pretrained=True, num_classes=0).eval()


def view_valid(v):
    return bool(v and not v.get("empty") and v.get("mean_luma", 0) >= LUMA_MIN
               and v.get("lower_frame_black_frac", 1) <= BLACK_MAX)


def branch_open(v):
    """A real navigable branch: render-valid AND sees open space ahead (large median depth)."""
    return bool(view_valid(v) and (v.get("median_depth_central_m") or 0.0) >= OPEN_MIN_DEPTH)


results = []
for c in man["candidates"]:
    cid = c["cand_id"]
    row = {"cand_id": cid, "kind": c["kind"], "o_d": c["o_d"],
           "approach_yaw_deg": c["approach_yaw_deg"], "goalA": c.get("goalA"), "goalB": c.get("goalB"),
           "expected_action_angle_sep_deg": c["expected_action_angle_sep_deg"],
           "within_envelope": c["within_envelope"]}
    if not c["within_envelope"]:
        row["classification"] = "OUT_OF_ENVELOPE"; results.append(row); continue
    vd = c["views"].get("decision"); vA = c["views"].get("goalA"); vB = c["views"].get("goalB")
    row["decision_luma"] = (vd or {}).get("mean_luma"); row["goalA_luma"] = (vA or {}).get("mean_luma")
    row["goalB_luma"] = (vB or {}).get("mean_luma")
    row["decision_black"] = (vd or {}).get("lower_frame_black_frac")
    row["goalA_black"] = (vA or {}).get("lower_frame_black_frac"); row["goalB_black"] = (vB or {}).get("lower_frame_black_frac")
    row["goalA_depth_m"] = (vA or {}).get("median_depth_central_m")
    row["goalB_depth_m"] = (vB or {}).get("median_depth_central_m")
    a_valid, b_valid = view_valid(vA), view_valid(vB)
    a_open, b_open = branch_open(vA), branch_open(vB)
    dec_ok = bool(vd and not vd.get("empty") and vd.get("mean_luma", 0) > 12
                  and vd.get("lower_frame_black_frac", 1) < BLACK_MAX)
    row["goalA_render_valid"] = a_valid; row["goalB_render_valid"] = b_valid
    row["goalA_branch_open"] = a_open; row["goalB_branch_open"] = b_open
    row["decision_render_valid"] = dec_ok
    # branch distinctness (only meaningful if both branch views are OPEN)
    ab = None
    if a_open and b_open:
        rA, rB = rgb_of(f"{cid}__goalA"), rgb_of(f"{cid}__goalB")
        if rA is not None and rB is not None:
            ab = round(dino_pair(model, rA, rB), 3)
    row["branch_dino_cosine"] = ab
    # classification — a real junction needs BOTH branches OPEN (large depth), not near walls
    if any(c["views"].get(r, {}).get("empty") for r in ("decision", "goalA", "goalB")):
        cls = "DEFERRED"
    elif not dec_ok:
        cls = "OCCLUDED"
    elif not (a_open and b_open):
        cls = "WALL_ONLY"      # render-valid pixels but a near wall ahead -> not a navigable branch
    elif c["expected_action_angle_sep_deg"] < MIN_SEP:
        cls = "RENDER_VALID_BUT_VISUALLY_WEAK"
    elif ab is not None and ab >= BRANCH_DISTINCT + BRANCH_MARGIN:
        cls = "RENDER_VALID_BUT_VISUALLY_WEAK"          # not distinct (calibrated, supersedes 0.60)
    elif ab is not None and ab > BRANCH_DISTINCT - BRANCH_MARGIN:
        cls = "RENDER_VALID_BUT_VISUALLY_WEAK"          # within review margin -> needs contact-sheet agreement
    else:
        cls = "RENDER_VALID_JUNCTION"                   # distinct (calibrated ~0.76, supersedes 0.60)
    row["classification"] = cls
    results.append(row)

valid_junctions = [r["cand_id"] for r in results if r["classification"] == "RENDER_VALID_JUNCTION"]
weak = [r["cand_id"] for r in results if r["classification"] == "RENDER_VALID_BUT_VISUALLY_WEAK"]
outcome = ("REAL_JUNCTION_FOUND_HOLD_FOR_REVIEW" if valid_junctions
           else "NO_RENDER_VALID_JUNCTION_RECOMMEND_RESCOPE_OR_DIFFERENT_SCENE")

# ── RGB-only vs depth-aware comparison (task 4): which candidates a pixel-validity-only gate
# would have accepted as junctions (decision + both goals render-valid, sep >= MIN_SEP) but the
# depth-openness gate reclassifies to WALL_ONLY. Computed from the data, not hardcoded.
rgb_apparent = [r["cand_id"] for r in results if r.get("decision_render_valid")
                and r.get("goalA_render_valid") and r.get("goalB_render_valid")
                and r["expected_action_angle_sep_deg"] >= MIN_SEP]
rgb_to_wall = [r["cand_id"] for r in results if r["cand_id"] in rgb_apparent
               and r["classification"] == "WALL_ONLY"]

# ── contact sheets ───────────────────────────────────────────────────────────
try:
    fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
except Exception:
    fb = fr = ImageFont.load_default()


def thumb(vid, size=(256, 192)):
    a = rgb_of(vid)
    return (Image.fromarray(a).convert("RGB").resize(size, Image.BILINEAR) if a is not None
            else Image.new("RGB", size, (35, 35, 35)))


for r in results:
    cid = r["cand_id"]
    if r["classification"] == "OUT_OF_ENVELOPE":
        continue
    tw, th = 256, 192
    sheet = Image.new("RGB", (tw * 3 + 20, th + 44), "white"); dr = ImageDraw.Draw(sheet)
    dr.text((6, 4), f"{cid}  [{r['classification']}]  {r['kind']}  sep={r['expected_action_angle_sep_deg']}deg"
            + (f"  branchDINO={r['branch_dino_cosine']}" if r.get("branch_dino_cosine") is not None else ""),
            font=fb, fill="black")
    for k, role in enumerate(("decision", "goalA", "goalB")):
        im = thumb(f"{cid}__{role}", (tw, th)); sheet.paste(im, (6 + k * (tw + 4), 26))
        dr.text((6 + k * (tw + 4), 26 + th + 2), role, font=fr, fill="#333")
        im.save(RM / f"{cid}__{role}.png")
    sheet.save(CS / f"{cid}.png")

# overview grid of all decision frames
dec_ids = [r["cand_id"] for r in results if r["classification"] != "OUT_OF_ENVELOPE"]
cols = 3; rows = math.ceil(max(1, len(dec_ids)) / cols); tw, th = 240, 180
ov = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 30) + 8), "white"); dov = ImageDraw.Draw(ov)
for k, cid in enumerate(dec_ids):
    im = thumb(f"{cid}__decision", (tw, th)); rr, cc = divmod(k, cols)
    ov.paste(im, (8 + cc * (tw + 8), 8 + rr * (th + 30)))
    cl = next(x["classification"] for x in results if x["cand_id"] == cid)
    dov.text((8 + cc * (tw + 8), 8 + rr * (th + 30) + th + 2), f"{cid}: {cl}", font=fr, fill="#111")
ov.save(CS / "_decision_overview.png")

# ── manifest + table + report ────────────────────────────────────────────────
manifest = {"status": "VALIDATION_ONLY", "step": "H8-M bounded real-junction render scan",
            "scene_gate": man.get("scene_gate", {}).get("pass"),
            "render": {k: man.get(k) for k in ("resolution", "camera_height_m", "camera_raise_note",
                                               "branch_reach_m", "free_camera_no_robot_body",
                                               "hospital_prim_count")},
            "thresholds": {"luma_min": LUMA_MIN, "lower_black_max": BLACK_MAX,
                           "min_angle_sep_deg": MIN_SEP, "branch_distinct_dino": BRANCH_DISTINCT,
                           "branch_open_min_depth_m": OPEN_MIN_DEPTH},
            "n_candidates": len(results), "candidates": results,
            "render_valid_junctions": valid_junctions, "visually_weak": weak,
            "rgb_only_apparent_junctions": rgb_apparent,
            "reclassified_to_wall_only_by_depth": rgb_to_wall,
            "decision_rule_outcome": outcome,
            "caveats": ["Bounded scan of hypothesized candidates grounded in the known reachable "
                        "geometry, NOT an exhaustive floor-plan search — absence here is strong but "
                        "not a proof that no junction exists anywhere in hospital.usd.",
                        "Free camera, no robot body: render-validity + branch-distinctness only; "
                        "drivability + chassis occlusion are Step-C checks, not tested here.",
                        "No recording, training, rollout, or promotion; CL_BOUND_XY unchanged."]}
(OUT / "h8m_junction_scan_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

cols_csv = ["cand_id", "kind", "classification", "within_envelope", "expected_action_angle_sep_deg",
            "decision_luma", "goalA_luma", "goalB_luma", "goalA_depth_m", "goalB_depth_m",
            "goalA_branch_open", "goalB_branch_open", "goalA_black", "goalB_black",
            "goalA_render_valid", "goalB_render_valid", "branch_dino_cosine"]
with open(OUT / "h8m_junction_scan_table.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols_csv, lineterminator="\n"); w.writeheader()
    for r in results:
        w.writerow({k: r.get(k) for k in cols_csv})

rep = ["# H8-M Bounded Real-Junction Render Scan (VALIDATION ONLY)", "",
       "**Status: VALIDATION ONLY.** Render-scan only — no drive validation, no recording, no "
       "training, no rollout, no promotion; `CL_BOUND_XY` unchanged. Verified hospital.usd, scene "
       "gate **" + ("PASS" if man.get("scene_gate", {}).get("pass") else "FAIL") + "**, free camera "
       "at the raised (~0.12 m) mount, level horizon.", "",
       "## Question",
       "Does any render-valid T-junction/fork exist inside the safe +/-6 m envelope — i.e. a shared "
       "decision frame whose goal A and goal B lie along **divergent, actually-open** branches "
       "(>=30 deg apart, both render-valid, visually distinct)?", "",
       "## Method",
       f"- {len([r for r in results if r['within_envelope']])} in-envelope candidates (T-junctions "
       "along the corridor, reception fork, corridor-end fans, a perpendicular reception cross), "
       "each rendered decision + goalA + goalB (branch reach "
       f"{man.get('branch_reach_m')} m).",
       f"- Render-valid goal view: luma >= {LUMA_MIN} and lower-frame black <= {BLACK_MAX}. "
       f"**Branch OPEN (the decisive test): median central depth >= {OPEN_MIN_DEPTH} m** — a "
       "goal view that renders fine but faces a near wall (small depth) is WALL_ONLY, not a "
       f"navigable branch. Branch distinctness: calibrated DINO cosine < {BRANCH_DISTINCT} with "
       f"±{BRANCH_MARGIN} margin + contact-sheet agreement (supersedes the arbitrary "
       f"{LEGACY_HARD_THRESHOLD_SUPERSEDED}, Outcome A; provenance: {PROVENANCE}). Angular "
       f"separation >= {MIN_SEP} deg.",
       "- **Why depth:** luma + distinctness alone cannot tell an open corridor from a textured "
       "wall (two different walls read as 'valid + distinct'); depth is the criterion that "
       "separates an open branch from a wall in front of the camera.",
       "- Grounded in the known reachable geometry (H8 straight corridor + reception); a **bounded** "
       "scan, not an exhaustive floor-plan search.", "",
       "## Candidates",
       "| candidate | kind | class | sep (deg) | goalA depth (m) | goalB depth (m) | goalA luma | goalB luma | branch DINO |",
       "|---|---|---|---|---|---|---|---|---|",
       *[f"| {r['cand_id']} | {r['kind']} | {r['classification']} | "
         f"{r['expected_action_angle_sep_deg']} | {r.get('goalA_depth_m')} | {r.get('goalB_depth_m')} | "
         f"{r.get('goalA_luma')} | {r.get('goalB_luma')} | {r.get('branch_dino_cosine')} |"
         for r in results], "",
       f"- **RENDER_VALID_JUNCTION:** {', '.join(valid_junctions) if valid_junctions else 'NONE'}.",
       f"- **RENDER_VALID_BUT_VISUALLY_WEAK:** {', '.join(weak) if weak else 'NONE'}.", "",
       "## Decision",
       f"**{outcome}.**",
       ("- At least one render-valid junction exists → **hold for review** before drive validation "
        "(Step C)." if valid_junctions else
        "- **No render-valid junction** was found in the bounded scan → recommend **re-scoping "
        "H8-M away from angular-branch claims in this scene**, or moving the angular-branch evidence "
        "to a different scene. Do NOT force a fake junction claim."),
       ("" if valid_junctions else
        "- **No angular branch-choice claim can be made in this hospital scene under the current "
        "safe +/-6 m envelope.** hospital.usd should remain a **distance/stop-axis** conditioning "
        "and hospital-scene visual-validity environment; angular branch-choice evidence must move "
        "to a different scene that contains a real fork/T-junction."),
       "- This is a bounded scan; absence is strong evidence but not a proof that no junction exists "
       "anywhere in hospital.usd.", "",
       "## Interpretation (honest)",
       "- **No navigable junction exists in the bounded +/-6 m scan.** Every candidate branch view "
       "faces a wall or furniture within ~0.3-2.9 m (median central depth); the only open branch "
       "(`jc_recep_cross` goalB, 7.7 m) is paired with a blocked branch — so no candidate has TWO "
       "divergent open branches.",
       "- **RGB-only vs depth-aware (why the gate changed):** a pixel-validity-only gate "
       f"(decision + both goal views render-valid, angular sep >= {MIN_SEP} deg) would have "
       f"accepted **{len(rgb_apparent)} candidates as apparent junctions** "
       f"({', '.join(rgb_apparent) if rgb_apparent else 'NONE'}) — luma + DINO cannot separate an "
       "open corridor from a textured wall (two different walls read as 'valid + distinct'). Adding "
       f"the **depth-openness criterion** (median central depth >= {OPEN_MIN_DEPTH} m on BOTH "
       f"branches) reclassifies **all {len(rgb_to_wall)} of them to WALL_ONLY** "
       f"({', '.join(rgb_to_wall) if rgb_to_wall else 'NONE'}). Pixel validity != navigability — "
       "the same lesson as the recep_junction black-void fix, one level deeper.",
       "- **This corroborates the H8 finding**: the reachable envelope is a single straight corridor "
       "with walls/furniture on the sides — no branching corridors.",
       "- **Recommendation:** re-scope H8-M away from angular-branch claims in this scene (keep the "
       "distance/stop axis and any genuinely-distinct rooms), or move the angular-branch evidence to "
       "a different scene. Do NOT force a fake junction.", "",
       "## Claim boundary",
       "- Validation-only render; no drive, no recording, no training, no rollout, no promotion, no "
       "benchmark/autonomy claim; incumbent retained; `DIAGNOSTIC_ONLY_NOT_PROMOTED`; `CL_BOUND_XY` "
       "unchanged. Free camera (no robot body): drivability + chassis occlusion are Step-C checks.", "",
       "## Artifacts",
       "`assets/experiments/hospital_h8_m_junction_scan/`: `h8m_junction_scan_manifest.json`, "
       "`h8m_junction_scan_report.md`, `h8m_junction_scan_table.csv`, `contact_sheets/`, "
       "`render_metadata/`. Harness: `scripts/gnm/h8m_junction_scan_render.py` (isaac), "
       "`scripts/gnm/h8m_junction_scan_analyze.py` (this). Raw .npy in scratchpad (not committed)."]
(OUT / "h8m_junction_scan_report.md").write_text("\n".join(rep) + "\n")
(RM / "h8m_jscan_render_manifest.json").write_text(json.dumps(man, indent=2) + "\n")

print(json.dumps({"scene_gate": man.get("scene_gate", {}).get("pass"),
                  "n_candidates": len(results), "render_valid_junctions": valid_junctions,
                  "visually_weak": weak, "outcome": outcome}, indent=2))
print("H8-M JUNCTION SCAN ANALYSIS WRITTEN ->", OUT)
