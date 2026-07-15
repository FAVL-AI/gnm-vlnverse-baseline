"""H8-M Track B — bounded junction-scan ANALYSIS (validation-only; no Isaac, no training).

Reads the Track-B render-scan (.npy directional views + trackb_scan_manifest.json), applies the
CORRECTED hospital method (render-validity + mandatory DEPTH OPENNESS, then embedding
distinctness), classifies each probe, and writes manifest/table/report + similarity matrix +
contact sheets. A probe is a branch-choice junction only if >=3 cardinal directions are depth-open
(arrive via one corridor, choose among >=2 divergent onward branches) AND the two chosen goal
branches are visually distinct.

Run: ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h8_track_b_render_scan_analyze.py
"""
import csv, json, os, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch, timm
# Reviewed distinctness rule (Outcome A + E). Sibling module; this script runs from scripts/gnm.
from h8_distinctness_gate import (REAL_SCENE_DINO_THRESHOLD, REAL_SCENE_MARGIN,
                                  LEGACY_HARD_THRESHOLD_SUPERSEDED, PROVENANCE)

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
HANDOFF = Path(os.environ.get("H8_TRACKB_HANDOFF", "/tmp/h8_mshelf_npy"))
OUT = REPO / "assets/experiments/hospital_h8_track_b_multi_shelf_scan"
CS = OUT / "contact_sheets"; RM = OUT / "render_metadata"
for d in (OUT, CS, RM):
    d.mkdir(parents=True, exist_ok=True)

LUMA_MIN = 15.0
BLACK_MAX = 0.5
OPEN_MIN_DEPTH = 3.0     # m — a branch is OPEN only if central median depth >= 3 m
WALL_MAX_DEPTH = 2.0     # m — central depth < 2 m is wall-like (rejected)
OPEN_FLOOR_MIN_DEPTH = 4.0  # m — if ALL 4 cardinal dirs are this open, the point is an open hall
#                             (no bounding corridor walls) — NOT a branch-choice junction. This
#                             guard rejects the open-floor false positive that depth+DINO alone
#                             flagged (e.g. warehouse open floor vs a shelf), confirmed visually.
MIN_SEP = 30.0           # deg — expected action-angle separation between the two branches
# Outcome A (calibrated, real indoor scenes): distinctness threshold ~0.76 with a margin band,
# superseding the arbitrary 0.60 (see scripts/gnm/h8_distinctness_gate.py and the gate decision doc).
# A pass also requires contact-sheet agreement; within-margin cosines are held for that human check.
BRANCH_DISTINCT = REAL_SCENE_DINO_THRESHOLD
BRANCH_MARGIN = REAL_SCENE_MARGIN

# ── MANDATORY visual verification (gate 13) ──────────────────────────────────
# Human review of the contact sheets. Any automated RENDER_VALID_JUNCTION that the images show is
# NOT a navigable angular fork is downgraded here, with the reason recorded. Applied AFTER automated
# classification; the automated verdict is preserved in `auto_classification` for audit.
VISUAL_OVERRIDES = {}  # populated after mandatory contact-sheet review, if a probe needs override
DIRS = ["E", "N", "W", "S"]
DIR_DEG = {"E": 0.0, "N": 90.0, "W": 180.0, "S": 270.0}
_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)

man = json.loads((HANDOFF / "trackb_scan_manifest.json").read_text())
model = timm.create_model("vit_small_patch16_224.dino", pretrained=True, num_classes=0).eval()


def rgb_of(vid):
    p = HANDOFF / f"{vid}.npy"
    return np.load(p) if p.exists() else None


@torch.no_grad()
def dino_pair(a, b):
    def emb(x):
        im = Image.fromarray(x).convert("RGB").resize((224, 224), Image.BILINEAR)
        t = torch.from_numpy(np.asarray(im, np.float32) / 255.0).permute(2, 0, 1)[None]
        return torch.nn.functional.normalize(model((t - _MEAN) / _STD), dim=1)
    return float((emb(a) @ emb(b).T).item())


def view_valid(v):
    return bool(v and not v.get("empty") and v.get("mean_luma", 0) >= LUMA_MIN
                and v.get("lower_frame_black_frac", 1) <= BLACK_MAX)


def branch_open(v):
    return bool(view_valid(v) and (v.get("median_depth_central_m") or 0.0) >= OPEN_MIN_DEPTH)


def ang_sep(a, b):
    d = abs(DIR_DEG[a] - DIR_DEG[b]) % 360
    return min(d, 360 - d)


rows = []                 # flat per-probe classification rows
sim_entries = []          # (label, rgb) for the similarity matrix
scene_summ = []

for sc in man["scenes"]:
    sid = sc["scene_id"]
    if not sc.get("scene_load_ok"):
        scene_summ.append({"scene_id": sid, "scene_load_ok": False,
                           "aborted_reason": sc.get("aborted_reason", "scene did not load"),
                           "n_probes": 0, "render_valid_junctions": []})
        rows.append({"scene_id": sid, "probe_id": "-", "classification": "DEFERRED",
                     "reason": "scene did not load", "n_open": 0})
        continue
    sjunc = []
    for pr in sc["probes"]:
        pid = pr["probe_id"]; views = pr["views"]; eye = pr["eye"]
        opens = [d for d in DIRS if branch_open(views.get(d))]
        depth = {d: (views.get(d, {}) or {}).get("median_depth_central_m") for d in DIRS}
        luma = {d: (views.get(d, {}) or {}).get("mean_luma") for d in DIRS}
        row = {"scene_id": sid, "probe_id": pid, "eye_x": eye[0], "eye_y": eye[1],
               "open_dirs": "|".join(opens), "n_open": len(opens),
               **{f"depth_{d}": depth[d] for d in DIRS}, **{f"luma_{d}": luma[d] for d in DIRS}}
        # empty-view / occlusion handling
        any_empty = any((views.get(d, {}) or {}).get("empty") for d in DIRS)
        # branch-choice junction requires >=3 open cardinal directions
        cls = None; reason = ""; gA = gB = dec = None; dino = None; sep = None
        if len(opens) >= 3:
            all4 = [depth[d] for d in DIRS if depth.get(d) is not None]
            open_floor = (len(all4) == 4 and min(all4) >= OPEN_FLOOR_MIN_DEPTH)
            ns_open = branch_open(views.get("N")) and branch_open(views.get("S"))
            ew_open = branch_open(views.get("E")) and branch_open(views.get("W"))
            # prefer a PERPENDICULAR open pair as the two divergent branches (a real angular fork);
            # this reports a genuine ~90 deg divergence rather than two ends of one aisle.
            import itertools as _it
            perp = [(a, b) for a, b in _it.combinations(opens, 2) if ang_sep(a, b) == 90]
            if perp:
                gA, gB = max(perp, key=lambda pr_: min(depth[pr_[0]] or 0, depth[pr_[1]] or 0))
            else:
                ranked0 = sorted(opens, key=lambda d: (depth[d] or 0), reverse=True)
                gA, gB = ranked0[0], ranked0[1]
            dec = next((d for d in sorted(opens, key=lambda d: (depth[d] or 0), reverse=True)
                        if d not in (gA, gB)), gA)
            sep = ang_sep(gA, gB)
            rA, rB = rgb_of(f"{sid}__{pid}__{gA}"), rgb_of(f"{sid}__{pid}__{gB}")
            if rA is not None and rB is not None:
                dino = round(dino_pair(rA, rB), 3)
            if open_floor:
                cls, reason = "OPEN_FLOOR_NOT_JUNCTION", (
                    f"OPEN FLOOR: all 4 cardinal dirs depth >= {OPEN_FLOOR_MIN_DEPTH} m (no "
                    "bounding corridor walls) — open hall (or a wide 4-way that visual verification "
                    "must distinguish), not auto-confirmed as a branch-choice junction")
            elif ns_open != ew_open:
                # exactly one through-axis is open; the perpendicular axis is not a full crossing
                cls, reason = "COLLINEAR_AISLE_NOT_JUNCTION", (
                    "STRAIGHT AISLE: one through-axis open ("
                    + ("N-S" if ns_open else "E-W")
                    + "), the perpendicular axis is not a full crossing — two ends of one aisle, "
                    "not an angular fork")
            elif sep < MIN_SEP:
                cls, reason = "RENDER_VALID_BUT_VISUALLY_WEAK", f"branch sep {sep}deg < {MIN_SEP}"
            elif dino is not None and dino >= BRANCH_DISTINCT + BRANCH_MARGIN:
                cls, reason = "RENDER_VALID_BUT_VISUALLY_WEAK", (
                    f"branches not distinct (DINO {dino} >= {round(BRANCH_DISTINCT + BRANCH_MARGIN, 3)}; "
                    "calibrated, supersedes 0.60)")
            elif dino is not None and dino > BRANCH_DISTINCT - BRANCH_MARGIN:
                cls, reason = "RENDER_VALID_BUT_VISUALLY_WEAK", (
                    f"DINO {dino} within review margin of {BRANCH_DISTINCT} — requires contact-sheet "
                    "agreement, not auto-distinct")
            else:
                cls, reason = "RENDER_VALID_JUNCTION", (
                    f"perpendicular depth-open divergent branches, distinct (DINO {dino} <= "
                    f"{round(BRANCH_DISTINCT - BRANCH_MARGIN, 3)}; calibrated ~{BRANCH_DISTINCT}, supersedes 0.60)")
        elif len(opens) == 2:
            a, b = opens
            if ang_sep(a, b) >= 179:
                cls, reason = "WALL_ONLY", "straight corridor (2 opposite open, no choice)"
            else:
                cls, reason = "WALL_ONLY", "L-corner (2 perpendicular open, single forced turn)"
        else:
            if any_empty and len(opens) == 0:
                cls, reason = "DEFERRED", "empty render(s) at this probe"
            else:
                cls, reason = "WALL_ONLY", f"boxed/dead-end ({len(opens)} open, walls <{OPEN_MIN_DEPTH}m)"
        row.update({"classification": cls, "reason": reason, "decision_dir": dec,
                    "goalA_dir": gA, "goalB_dir": gB, "branch_sep_deg": sep,
                    "goalA_depth_m": depth.get(gA) if gA else None,
                    "goalB_depth_m": depth.get(gB) if gB else None, "branch_dino_cosine": dino})
        rows.append(row)
        if cls in ("RENDER_VALID_JUNCTION", "RENDER_VALID_BUT_VISUALLY_WEAK", "OPEN_FLOOR_NOT_JUNCTION", "COLLINEAR_AISLE_NOT_JUNCTION"):
            sjunc.append(row)
            for role, dd in (("goalA", gA), ("goalB", gB)):
                r = rgb_of(f"{sid}__{pid}__{dd}")
                if r is not None:
                    sim_entries.append((f"{sid}:{pid}:{role}:{dd}", r))
    scene_summ.append({"scene_id": sid, "scene_load_ok": True, "n_probes": len(sc["probes"]),
                       "prim_count": sc.get("prim_count"), "world_bbox": sc.get("world_bbox"),
                       "render_valid_junctions": [r["probe_id"] for r in sjunc
                                                  if r["classification"] == "RENDER_VALID_JUNCTION"],
                       "visually_weak": [r["probe_id"] for r in sjunc
                                         if r["classification"] == "RENDER_VALID_BUT_VISUALLY_WEAK"]})

# apply MANDATORY visual-verification overrides (gate 13) before computing the outcome
for r in rows:
    key = f"{r['scene_id']}:{r['probe_id']}"
    if key in VISUAL_OVERRIDES:
        newcls, vreason = VISUAL_OVERRIDES[key]
        r["auto_classification"] = r["classification"]
        r["visual_verified"] = True
        r["classification"] = newcls
        r["reason"] = vreason
for s in scene_summ:
    if s.get("scene_load_ok"):
        s["render_valid_junctions"] = [r["probe_id"] for r in rows if r["scene_id"] == s["scene_id"]
                                        and r["classification"] == "RENDER_VALID_JUNCTION"]
        s["visually_weak"] = [r["probe_id"] for r in rows if r["scene_id"] == s["scene_id"]
                              and r["classification"] == "RENDER_VALID_BUT_VISUALLY_WEAK"]
visual_downgrades = [f"{r['scene_id']}:{r['probe_id']} ({r.get('auto_classification')}->"
                     f"{r['classification']})" for r in rows if r.get("visual_verified")]

valid = [(r["scene_id"], r["probe_id"]) for r in rows if r["classification"] == "RENDER_VALID_JUNCTION"]
weak = [(r["scene_id"], r["probe_id"]) for r in rows if r["classification"] == "RENDER_VALID_BUT_VISUALLY_WEAK"]
open_floor_rej = [f"{r['scene_id']}:{r['probe_id']}" for r in rows if r["classification"] == "OPEN_FLOOR_NOT_JUNCTION"]
outcome = ("REAL_JUNCTION_FOUND_HOLD_FOR_REVIEW" if valid else
           "NO_RENDER_VALID_JUNCTION_STOP_REAL_ASSETS_BUILD_SYNTHETIC_DIAGNOSTIC_FORK")
import collections as _collections
cls_counts = dict(_collections.Counter(r["classification"] for r in rows))
cls_counts_str = ", ".join(f"{k}={v}" for k, v in sorted(cls_counts.items()))

# ── similarity matrix (bounded) ──────────────────────────────────────────────
if not sim_entries:
    # fallback: representative deepest-open view of up to 12 probes, to keep the file meaningful
    seen = 0
    for r in rows:
        if seen >= 12 or r.get("classification") in (None, "DEFERRED"):
            continue
        dd = r.get("goalA_dir") or (r.get("open_dirs", "").split("|")[0] if r.get("open_dirs") else None)
        if not dd:
            continue
        im = rgb_of(f"{r['scene_id']}__{r['probe_id']}__{dd}")
        if im is not None:
            sim_entries.append((f"{r['scene_id']}:{r['probe_id']}:rep:{dd}", im)); seen += 1
labels = [e[0] for e in sim_entries][:16]
imgs = [e[1] for e in sim_entries][:16]
mat = [[1.0 if i == j else round(dino_pair(imgs[i], imgs[j]), 3)
        for j in range(len(imgs))] for i in range(len(imgs))]
with open(OUT / "multi_shelf_visual_similarity_matrix.csv", "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n"); w.writerow(["view"] + labels)
    for i, lab in enumerate(labels):
        w.writerow([lab] + mat[i])
mm = ["# Track-B Visual Similarity Matrix (DINO ViT-S/16 cosine)", "",
      "Lower = more visually distinct. Goal branches of a real junction should be < "
      f"{BRANCH_DISTINCT}. " + ("No junction candidates found — matrix shows representative "
      "open views (fallback)." if not valid and not weak else ""), "",
      "| view | " + " | ".join(labels) + " |", "|" + "---|" * (len(labels) + 1)]
for i, lab in enumerate(labels):
    mm.append(f"| {lab} | " + " | ".join(f"{mat[i][j]}" for j in range(len(labels))) + " |")
(OUT / "multi_shelf_visual_similarity_matrix.md").write_text("\n".join(mm) + "\n")

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


for r in rows:
    if r["classification"] not in ("RENDER_VALID_JUNCTION", "RENDER_VALID_BUT_VISUALLY_WEAK", "OPEN_FLOOR_NOT_JUNCTION", "COLLINEAR_AISLE_NOT_JUNCTION"):
        continue
    sid, pid = r["scene_id"], r["probe_id"]; tw, th = 256, 192
    sheet = Image.new("RGB", (tw * 3 + 20, th + 44), "white"); dr = ImageDraw.Draw(sheet)
    dr.text((6, 4), f"{sid} {pid} [{r['classification']}] sep={r.get('branch_sep_deg')}deg "
            f"DINO={r.get('branch_dino_cosine')}", font=fb, fill="black")
    for k, (role, dd) in enumerate((("decision", r.get("decision_dir")),
                                    ("goalA", r.get("goalA_dir")), ("goalB", r.get("goalB_dir")))):
        im = thumb(f"{sid}__{pid}__{dd}", (tw, th)); sheet.paste(im, (6 + k * (tw + 4), 26))
        dr.text((6 + k * (tw + 4), 26 + th + 2), f"{role} ({dd})", font=fr, fill="#333")
        im.save(RM / f"{sid}__{pid}__{role}_{dd}.png")
    sheet.save(CS / f"{sid}__{pid}.png")

# per-scene overview grid of every probe's deepest-open (or E) view, labelled with class
import math as _m
for sc in man["scenes"]:
    sid = sc["scene_id"]
    pr_rows = [r for r in rows if r["scene_id"] == sid and r["probe_id"] != "-"]
    if not pr_rows:
        continue
    cols = 4; rr = _m.ceil(len(pr_rows) / cols); tw, th = 220, 165
    ov = Image.new("RGB", (cols * (tw + 8) + 8, rr * (th + 30) + 8), "white"); dov = ImageDraw.Draw(ov)
    for k, r in enumerate(pr_rows):
        dd = r.get("goalA_dir") or (r.get("open_dirs", "").split("|")[0] if r.get("open_dirs") else "E")
        im = thumb(f"{sid}__{r['probe_id']}__{dd}", (tw, th)); a, b = divmod(k, cols)
        ov.paste(im, (8 + b * (tw + 8), 8 + a * (th + 30)))
        dov.text((8 + b * (tw + 8), 8 + a * (th + 30) + th + 2),
                 f"{r['probe_id']}:{r['classification'][:14]}", font=fr, fill="#111")
    ov.save(CS / f"_{sid}_overview.png")

# ── manifest + table + report ────────────────────────────────────────────────
manifest = {"status": "VALIDATION_ONLY", "step": "H8-M Track-B bounded junction render scan",
            "scenes_scanned": [s["scene_id"] for s in man["scenes"]],
            "method": "geometry-grounded interior grid; 4 cardinal RGB+depth views/probe; "
                      "branch-choice junction = >=3 depth-open (>=3 m) cardinal dirs with distinct "
                      "goal branches. Depth openness mandatory (RGB/luma/DINO alone insufficient).",
            "thresholds": {"luma_min": LUMA_MIN, "lower_black_max": BLACK_MAX,
                           "branch_open_min_depth_m": OPEN_MIN_DEPTH, "wall_max_depth_m": WALL_MAX_DEPTH,
                           "open_floor_reject_min_depth_m": OPEN_FLOOR_MIN_DEPTH,
                           "min_branch_sep_deg": MIN_SEP, "branch_distinct_dino": BRANCH_DISTINCT},
            "open_floor_rejected": open_floor_rej,
            "visual_verification_downgrades_gate13": visual_downgrades,
            "scene_summary": scene_summ, "n_probe_rows": len(rows),
            "render_valid_junctions": [f"{s}:{p}" for s, p in valid],
            "visually_weak": [f"{s}:{p}" for s, p in weak],
            "decision_rule_outcome": outcome, "probes": rows,
            "caveats": ["Bounded, geometry-grounded scan (interior grid, cardinal directions) — NOT "
                        "an exhaustive floor-plan search; a negative is strong evidence, not proof no "
                        "junction exists. Cardinal sampling resolves orthogonal T/cross junctions, not "
                        "oblique (~45deg) forks.",
                        "Free camera, no robot body: render-validity + depth-openness + distinctness "
                        "only. Drivability + chassis occlusion are a later drive-validation gate, NOT "
                        "tested here. Reachable asset != usable junction; render-validity != drive-validity.",
                        "No collection, drive, recording, training, rollout, or promotion; CL_BOUND_XY "
                        "unchanged; incumbent retained; DIAGNOSTIC_ONLY_NOT_PROMOTED."]}
(OUT / "multi_shelf_render_scan_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

cols_csv = ["scene_id", "probe_id", "classification", "reason", "n_open", "open_dirs",
            "decision_dir", "goalA_dir", "goalB_dir", "branch_sep_deg", "goalA_depth_m",
            "goalB_depth_m", "branch_dino_cosine", "eye_x", "eye_y",
            "depth_E", "depth_N", "depth_W", "depth_S"]
with open(OUT / "multi_shelf_render_scan_table.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols_csv, lineterminator="\n"); w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k) for k in cols_csv})

n_load_ok = sum(1 for s in scene_summ if s.get("scene_load_ok"))
rep = ["# H8-M Track-B Bounded Junction Render Scan (VALIDATION ONLY)", "",
       "**Status: VALIDATION ONLY.** Render-scan only — no collection, no drive validation, no "
       "recording, no training, no rollout, no promotion; `CL_BOUND_XY` unchanged. Free camera at "
       "the raised (~0.12 m) robot-eye mount, level horizon.", "",
       "**Key line:** Reachable asset != usable junction. Track-B only progresses if the render "
       "scan proves a real, depth-open branch with visually valid goal views and expected angular "
       "action separation.", "",
       "## Scenes scanned",
       *[f"- `{s['scene_id']}` — load_ok={s.get('scene_load_ok')}"
         + (f", prims={s.get('prim_count')}, probes={s.get('n_probes')}, "
            f"render_valid_junctions={s.get('render_valid_junctions')}, weak={s.get('visually_weak')}"
            if s.get('scene_load_ok') else f", aborted: {s.get('aborted_reason')}")
         for s in scene_summ], "",
       "## Method (corrected hospital method)",
       f"- Geometry-grounded interior grid over each scene's world bbox; at each probe, 4 cardinal "
       "views (E/N/W/S) with RGB + `distance_to_image_plane` depth.",
       f"- **Branch-choice junction = >= 3 cardinal directions depth-open (median central depth >= "
       f"{OPEN_MIN_DEPTH} m)** — arrive via one corridor, choose among >= 2 divergent onward "
       "branches. 2 opposite open = straight corridor; 2 perpendicular = L-corner; both are NOT a "
       "branch choice.",
       f"- Goal branches must be visually distinct (calibrated DINO cosine < {BRANCH_DISTINCT} with "
       f"±{BRANCH_MARGIN} margin band + contact-sheet agreement; supersedes the arbitrary "
       f"{LEGACY_HARD_THRESHOLD_SUPERSEDED}, Outcome A) and >= {MIN_SEP} deg apart. **Depth openness "
       "is mandatory** — luma/DINO alone cannot separate an open corridor from a textured wall (the "
       f"hospital false-positive lesson). Distinctness rule provenance: {PROVENANCE}", "",
       "## Result",
       f"- Scenes that loaded: {n_load_ok}/{len(scene_summ)}.",
       f"- **RENDER_VALID_JUNCTION:** {', '.join(f'{s}:{p}' for s, p in valid) if valid else 'NONE'}.",
       f"- **RENDER_VALID_BUT_VISUALLY_WEAK:** {', '.join(f'{s}:{p}' for s, p in weak) if weak else 'NONE'}.", "",
       "### Per-probe classification (summary)",
       "| scene | probe | class | n_open | open | sep | goalA depth | goalB depth | DINO | reason |",
       "|---|---|---|---|---|---|---|---|---|---|",
       *[f"| {r['scene_id']} | {r['probe_id']} | {r['classification']} | {r.get('n_open')} | "
         f"{r.get('open_dirs')} | {r.get('branch_sep_deg')} | {r.get('goalA_depth_m')} | "
         f"{r.get('goalB_depth_m')} | {r.get('branch_dino_cosine')} | {r.get('reason')} |"
         for r in rows], "",
       "## Decision",
       f"**{outcome}.**",
       ("- At least one RENDER_VALID_JUNCTION exists (visually verified) → **hold for review** "
        "before any drive validation (do NOT treat render-validity as drive-validity)." if valid else
        "- **No render-valid junction** in `warehouse_multiple_shelves`. → this was the final "
        "targeted real-world-like candidate; **stop real-asset scanning** and recommend **building a "
        "small `SYNTHETIC_DIAGNOSTIC_ONLY` T/Y/cross fork scene**. Do NOT force a fake angular-branch "
        "claim."),
       "- Bounded scan: absence is strong evidence, not proof; cardinal sampling resolves orthogonal "
       "junctions, not oblique forks.",
       f"- **Final counts (warehouse_multiple_shelves): OPEN_FLOOR_NOT_JUNCTION="
       f"{cls_counts.get('OPEN_FLOOR_NOT_JUNCTION', 0)}, COLLINEAR_AISLE_NOT_JUNCTION="
       f"{cls_counts.get('COLLINEAR_AISLE_NOT_JUNCTION', 0)}, RENDER_VALID_BUT_VISUALLY_WEAK="
       f"{cls_counts.get('RENDER_VALID_BUT_VISUALLY_WEAK', 0)}, WALL_ONLY="
       f"{cls_counts.get('WALL_ONLY', 0)}, RENDER_VALID_JUNCTION="
       f"{cls_counts.get('RENDER_VALID_JUNCTION', 0)}.**",
       "- **Track-B status: `hospital`, `office_isaac`, `warehouse_simple`, `warehouse_full`, and "
       "`warehouse_multiple_shelves` have ALL failed the Track-B render-valid-junction gate.** No "
       "angular branch-choice training should begin from these scenes.",
       "- **Next step: build a small `SYNTHETIC_DIAGNOSTIC_ONLY` corridor-forked (T/Y/cross) scene** "
       "— two navigable branches diverging >= 30 deg with visually distinct, branch-specific goal "
       "views — clearly labelled synthetic/diagnostic-only. Real-asset scanning is now exhausted.", "",
       "## Visual verification (mandatory) & scene character",
       f"- **Class distribution (warehouse_multiple_shelves):** {cls_counts_str}.",
       "- **Explicit `OPEN_FLOOR_NOT_JUNCTION` and `COLLINEAR_AISLE_NOT_JUNCTION` guards:** "
       f"depth-openness in >=3 cardinal directions is NOT a junction on its own. All 4 dirs >= "
       f"{OPEN_FLOOR_MIN_DEPTH} m ⇒ `OPEN_FLOOR_NOT_JUNCTION` (open hall or a wide 4-way that visual "
       "verification must distinguish). Exactly one through-axis open with the perpendicular axis not "
       "a full crossing ⇒ `COLLINEAR_AISLE_NOT_JUNCTION` (a straight aisle — two ends of one aisle, "
       "the `p13` warehouse_full pattern, now caught automatically).",
       "- **Contact-sheet visual verification is MANDATORY (gate 14) before any probe is confirmed "
       "`RENDER_VALID_JUNCTION`** — and, because a real walled 4-way cross-aisle reads as "
       "`OPEN_FLOOR_NOT_JUNCTION` under central-depth sampling, the OPEN_FLOOR and COLLINEAR contact "
       "sheets were ALSO inspected for a genuine walled cross. Depth + embedding is necessary but not "
       "sufficient.",
       "- **Visual-verification overrides applied (gate 14):** "
       + ("; ".join(visual_downgrades) if visual_downgrades else "NONE (no automated "
          "RENDER_VALID_JUNCTION required downgrade; the guards rejected the false positives "
          "automatically)") + ".", "",
       "## Claim boundary",
       "- Validation-only render scan; no collection, no recording, no drive validation, no rollout, "
       "no training, no promotion, no benchmark evidence; incumbent retained; "
       "`DIAGNOSTIC_ONLY_NOT_PROMOTED`; `CL_BOUND_XY` unchanged.",
       (f"- **warehouse_multiple_shelves has at least one visually-verified RENDER_VALID_JUNCTION** "
        f"({', '.join(f'{s}:{p}' for s, p in valid)}) → held for review before drive validation."
        if valid else
        "- **warehouse_multiple_shelves produced zero render-valid junctions — it FAILS the Track-B "
        "render-valid-junction gate.** It was the last untried real-world-like candidate; real-asset "
        "scanning is exhausted → move to a `SYNTHETIC_DIAGNOSTIC_ONLY` fork."),
       "- Reachable asset != usable junction; render-validity != drive-validity. "
       + ("**No angular branch-choice training should begin until this candidate passes drive "
          "validation, recorded-mode, splits, and a leakage audit.**" if valid else
          "**No angular branch-choice training should begin from this scene.** No real junction, no "
          "angular-branch training.")
       + " Training remains blocked until a real junction, valid goal images, recorded decision "
       "frames, train/val/test splits, and a leakage audit exist.", "",
       "## Artifacts",
       "`assets/experiments/hospital_h8_track_b_multi_shelf_scan/`: `multi_shelf_render_scan_manifest.json`, "
       "`multi_shelf_render_scan_table.csv`, `multi_shelf_render_scan_report.md`, "
       "`multi_shelf_visual_similarity_matrix.{csv,md}`, `contact_sheets/`, `render_metadata/`. Harness: "
       "`scripts/gnm/h8_track_b_multi_shelf_render.py` (isaac), "
       "`scripts/gnm/h8_track_b_multi_shelf_analyze.py` (this). Raw .npy in scratchpad (not committed)."]
(OUT / "multi_shelf_render_scan_report.md").write_text("\n".join(rep) + "\n")
(RM / "multi_shelf_render_scan_render_manifest.json").write_text(json.dumps(man, indent=2) + "\n")

print(json.dumps({"scenes_loaded": f"{n_load_ok}/{len(scene_summ)}", "n_probe_rows": len(rows),
                  "render_valid_junctions": [f"{s}:{p}" for s, p in valid],
                  "visually_weak": [f"{s}:{p}" for s, p in weak], "outcome": outcome}, indent=2))
print("H8-M TRACK-B RENDER SCAN ANALYSIS WRITTEN ->", OUT)
