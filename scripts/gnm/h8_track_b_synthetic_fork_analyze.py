"""H8-M Track B — SYNTHETIC_DIAGNOSTIC_ONLY fork RENDER-SCAN VALIDATION (gates 1-7 only).

Reads the synthetic-fork render (.npy views + sfork_scan_manifest.json) and evaluates ONLY the
render-scan validation gates:
  1 scene-load, 2 render-validity, 3 depth-openness, 4 open-floor guard,
  5 (input to) mandatory visual/contact-sheet verification, 6 embedding distinctness,
  7 action-angle separation.
It does NOT run drive-validation / recorded-mode / leakage audit / action-probe / training.

The designed branch pair is A=N (blue, STRAIGHT) vs B=W (green, TURN_LEFT_90), 90 deg apart. The
gate cascade (open-floor guard -> collinear guard -> action-angle -> distinctness) is applied to the
4 cardinal views of the `center` probe exactly as in the real-asset Track-B scans, so a synthetic
open-floor or collinear artifact would be caught the same way. Contact sheets are written for the
MANDATORY human visual verification (gate 5); this script records the automated verdict and the
final decision is confirmed only after that inspection.

Run: ~/miniforge3/envs/gnm_train/bin/python scripts/gnm/h8_track_b_synthetic_fork_analyze.py
"""
import csv, json, os, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import torch, timm

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
HANDOFF = Path(os.environ.get("H8_SFORK_HANDOFF", "/tmp/h8_sfork_npy"))
OUT = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_validation"
CS = OUT / "contact_sheets"; RM = OUT / "render_metadata"
for d in (OUT, CS, RM):
    d.mkdir(parents=True, exist_ok=True)

LUMA_MIN = 15.0
BLACK_MAX = 0.5
OPEN_MIN_DEPTH = 3.0
WALL_MAX_DEPTH = 2.0
OPEN_FLOOR_MIN_DEPTH = 4.0
MIN_SEP = 30.0
BRANCH_DISTINCT = 0.60
SID = "synthetic_diagnostic_fork"
DIRS = ["E", "N", "W", "S"]
DIR_DEG = {"E": 0.0, "N": 90.0, "W": 180.0, "S": 270.0}
DIR_COLOR = {"N": "blue/circle (branch A STRAIGHT)", "W": "green/triangle (branch B TURN_LEFT_90)",
             "E": "orange/square (distractor)", "S": "red/cross (approach)"}
_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)

man = json.loads((HANDOFF / "sfork_scan_manifest.json").read_text())
sc = man["scenes"][0]
views = sc["probes"][0]["views"]
named = sc.get("named_frames", {})
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
    return round(float((emb(a) @ emb(b).T).item()), 3)


def view_valid(v):
    return bool(v and not v.get("empty") and v.get("mean_luma", 0) >= LUMA_MIN
                and v.get("lower_frame_black_frac", 1) <= BLACK_MAX)


def branch_open(v):
    return bool(view_valid(v) and (v.get("median_depth_central_m") or 0.0) >= OPEN_MIN_DEPTH)


def ang_sep(a, b):
    d = abs(DIR_DEG[a] - DIR_DEG[b]) % 360
    return min(d, 360 - d)


depth = {d: (views.get(d, {}) or {}).get("median_depth_central_m") for d in DIRS}
luma = {d: (views.get(d, {}) or {}).get("mean_luma") for d in DIRS}
black = {d: (views.get(d, {}) or {}).get("lower_frame_black_frac") for d in DIRS}
opens = [d for d in DIRS if branch_open(views.get(d))]
all4 = [depth[d] for d in DIRS if depth.get(d) is not None]
open_floor = (len(all4) == 4 and min(all4) >= OPEN_FLOOR_MIN_DEPTH)
ns_open = branch_open(views.get("N")) and branch_open(views.get("S"))
ew_open = branch_open(views.get("E")) and branch_open(views.get("W"))

# designed branch pair A=N, B=W
gA, gB = "N", "W"
sep = ang_sep(gA, gB)
rN, rW = rgb_of(f"{SID}__center__N"), rgb_of(f"{SID}__center__W")
gAi, gBi = rgb_of(f"{SID}__goalA_img"), rgb_of(f"{SID}__goalB_img")
dino_center = dino_pair(rN, rW) if (rN is not None and rW is not None) else None
dino_goalimg = dino_pair(gAi, gBi) if (gAi is not None and gBi is not None) else None
dino = dino_goalimg if dino_goalimg is not None else dino_center

# ── gate cascade (same order as the real-asset scans) ─────────────────────────
if len(opens) >= 3 and not open_floor and (ns_open == ew_open) and sep >= MIN_SEP \
        and dino is not None and dino < BRANCH_DISTINCT:
    auto_cls = "RENDER_VALID_JUNCTION"
    auto_reason = "perpendicular depth-open divergent branches (N vs W), distinct"
elif open_floor:
    auto_cls = "OPEN_FLOOR_NOT_JUNCTION"
    auto_reason = f"all 4 cardinal depths >= {OPEN_FLOOR_MIN_DEPTH} m (open floor); needs gate-5 visual override"
elif ns_open != ew_open:
    auto_cls = "COLLINEAR_AISLE_NOT_JUNCTION"
    auto_reason = "only one through-axis fully open (straight aisle, not a cross)"
elif len(opens) < 3:
    auto_cls = "WALL_ONLY"
    auto_reason = f"<3 cardinal dirs depth-open (opens={opens})"
elif sep < MIN_SEP:
    auto_cls = "RENDER_VALID_BUT_VISUALLY_WEAK"
    auto_reason = f"branch sep {sep} deg < {MIN_SEP}"
else:
    auto_cls = "RENDER_VALID_BUT_VISUALLY_WEAK"
    auto_reason = f"branches not distinct (DINO {dino} >= {BRANCH_DISTINCT})"

# ── explicit gate PASS/FAIL table ─────────────────────────────────────────────
g2_valid = all(view_valid(named.get(k)) for k in ("decision", "goalA_img", "goalB_img")) \
    and view_valid(views.get("N")) and view_valid(views.get("W"))
g3_open = branch_open(views.get("N")) and branch_open(views.get("W"))
depth_exists = all((views.get(d, {}) or {}).get("median_depth_central_m") is not None for d in DIRS)
gates = [
    ("1_scene_load", bool(sc.get("scene_load_ok")),
     f"ref_authored={sc.get('ref_authored')} prims={sc.get('prim_count')} bbox={sc.get('world_bbox')}"),
    ("2_render_validity", bool(g2_valid),
     f"decision/goalA/goalB + center N/W all luma>={LUMA_MIN}, black<={BLACK_MAX}, non-empty; "
     f"depth_present={depth_exists}"),
    ("3_depth_openness", bool(g3_open),
     f"branch N depth={depth.get('N')} m, branch W depth={depth.get('W')} m (both >= {OPEN_MIN_DEPTH})"),
    ("4_open_floor_guard", (not open_floor),
     f"all-4 >= {OPEN_FLOOR_MIN_DEPTH} m? {open_floor} (guard passes when NOT open-floor); "
     f"depths E/N/W/S={[depth[d] for d in DIRS]}"),
    ("5_visual_verification", None,
     "MANDATORY human/contact-sheet inspection — recorded separately after this script; "
     "automated verdict must be confirmed by eye before RENDER_VALID_JUNCTION stands"),
    ("6_embedding_distinctness", (dino is not None and dino < BRANCH_DISTINCT),
     f"DINO cosine(goalA_img,goalB_img)={dino_goalimg}, cosine(centerN,centerW)={dino_center}; "
     f"threshold < {BRANCH_DISTINCT}"),
    ("7_action_angle", (sep >= MIN_SEP),
     f"branch A=N (STRAIGHT) vs B=W (TURN_LEFT_90): sep={sep} deg (>= {MIN_SEP}); different local actions"),
]
auto_gates_pass = all(p for _, p, _ in gates if p is not None)
outcome = ("SYNTHETIC_FORK_RENDER_VALID_PENDING_VISUAL_VERIFICATION_HOLD_FOR_REVIEW"
           if (auto_cls == "RENDER_VALID_JUNCTION" and auto_gates_pass)
           else "SYNTHETIC_FORK_RENDER_SCAN_FAILED_REVISE_GEOMETRY_OR_MARKERS")

# ── contact sheets (gate 5 input) ─────────────────────────────────────────────
try:
    fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    fr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
except Exception:
    fb = fr = ImageFont.load_default()


def thumb(vid, size=(256, 192)):
    a = rgb_of(vid)
    return (Image.fromarray(a).convert("RGB").resize(size, Image.BILINEAR) if a is not None
            else Image.new("RGB", size, (35, 35, 35)))


# decision | goalA(N) | goalB(W) sheet + the two close goal images
tw, th = 256, 192
sheet = Image.new("RGB", (tw * 3 + 20, th + 44), "white"); dr = ImageDraw.Draw(sheet)
dr.text((6, 4), f"{SID} [{auto_cls}] sep={sep}deg DINO_goalimg={dino_goalimg} DINO_center={dino_center}",
        font=fb, fill="black")
for k, (role, vid, tag) in enumerate((("decision", f"{SID}__decision", "approach->junction"),
                                      ("goalA(N)", f"{SID}__center__N", "blue/circle STRAIGHT"),
                                      ("goalB(W)", f"{SID}__center__W", "green/triangle LEFT"))):
    im = thumb(vid, (tw, th)); sheet.paste(im, (6 + k * (tw + 4), 26))
    dr.text((6 + k * (tw + 4), 26 + th + 2), f"{role}: {tag}", font=fr, fill="#333")
    im.save(RM / f"{SID}__{role.replace('(', '_').replace(')', '')}.png")
sheet.save(CS / f"{SID}__decision_goalA_goalB.png")

# 4-cardinal sheet at center + close goal images
sheet2 = Image.new("RGB", (tw * 3 + 20, th * 2 + 60), "white"); d2 = ImageDraw.Draw(sheet2)
d2.text((6, 4), f"{SID} center 4-cardinal + close goal images  opens={opens} open_floor={open_floor} "
        f"ns_open={ns_open} ew_open={ew_open}", font=fb, fill="black")
grid = [("center N", f"{SID}__center__N"), ("center E", f"{SID}__center__E"),
        ("center W", f"{SID}__center__W"), ("center S", f"{SID}__center__S"),
        ("goalA_img", f"{SID}__goalA_img"), ("goalB_img", f"{SID}__goalB_img")]
for k, (lab, vid) in enumerate(grid):
    a, b = divmod(k, 3)
    im = thumb(vid, (tw, th)); sheet2.paste(im, (6 + b * (tw + 4), 26 + a * (th + 26)))
    dd = lab.split()[-1] if lab.startswith("center") else lab
    tag = DIR_COLOR.get(dd, "")
    d2.text((6 + b * (tw + 4), 26 + a * (th + 26) + th + 2),
            f"{lab} d={depth.get(dd) if lab.startswith('center') else '-'} {tag}", font=fr, fill="#222")
    im.save(RM / f"{SID}__{lab.replace(' ', '_')}.png")
sheet2.save(CS / f"{SID}__center_cardinal_and_goals.png")

# ── similarity matrix ─────────────────────────────────────────────────────────
sim = [("center:N", rgb_of(f"{SID}__center__N")), ("center:E", rgb_of(f"{SID}__center__E")),
       ("center:W", rgb_of(f"{SID}__center__W")), ("center:S", rgb_of(f"{SID}__center__S")),
       ("goalA_img", gAi), ("goalB_img", gBi)]
sim = [(lab, im) for lab, im in sim if im is not None]
labels = [s[0] for s in sim]; imgs = [s[1] for s in sim]
mat = [[1.0 if i == j else dino_pair(imgs[i], imgs[j]) for j in range(len(imgs))]
       for i in range(len(imgs))]
with open(OUT / "synthetic_fork_visual_similarity_matrix.csv", "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n"); w.writerow(["view"] + labels)
    for i, lab in enumerate(labels):
        w.writerow([lab] + mat[i])
mm = ["# Synthetic Fork Visual Similarity Matrix (DINO ViT-S/16 cosine)", "",
      f"Lower = more visually distinct. The designed goal branches (goalA_img blue vs goalB_img "
      f"green, and center:N vs center:W) should be < {BRANCH_DISTINCT}.", "",
      "| view | " + " | ".join(labels) + " |", "|" + "---|" * (len(labels) + 1)]
for i, lab in enumerate(labels):
    mm.append(f"| {lab} | " + " | ".join(f"{mat[i][j]}" for j in range(len(labels))) + " |")
(OUT / "synthetic_fork_visual_similarity_matrix.md").write_text("\n".join(mm) + "\n")

# ── manifest + table + report ─────────────────────────────────────────────────
manifest = {"label": "SYNTHETIC_DIAGNOSTIC_ONLY", "status": "VALIDATION_ONLY_GATES_1_7",
            "scene": SID, "asset_path": sc.get("asset_path"), "scene_load_ok": sc.get("scene_load_ok"),
            "prim_count": sc.get("prim_count"), "world_bbox": sc.get("world_bbox"),
            "thresholds": {"luma_min": LUMA_MIN, "lower_black_max": BLACK_MAX,
                           "branch_open_min_depth_m": OPEN_MIN_DEPTH,
                           "open_floor_reject_min_depth_m": OPEN_FLOOR_MIN_DEPTH,
                           "min_branch_sep_deg": MIN_SEP, "branch_distinct_dino": BRANCH_DISTINCT},
            "center_depths_m": depth, "center_luma": luma, "center_lower_black_frac": black,
            "opens": opens, "open_floor": open_floor, "ns_open": ns_open, "ew_open": ew_open,
            "designed_branch_pair": {"A": "N", "B": "W", "sep_deg": sep},
            "dino_goalimg": dino_goalimg, "dino_center": dino_center,
            "auto_classification": auto_cls, "auto_reason": auto_reason,
            "gates": [{"gate": g, "pass": p, "detail": d} for g, p, d in gates],
            "gates_1_4_6_7_auto_pass": auto_gates_pass,
            "gate_5_visual_verification": "PENDING_HUMAN_CONTACT_SHEET_INSPECTION",
            "decision_rule_outcome": outcome,
            "named_frames": named, "center_views": views,
            "gates_not_run": ["drive_validation", "recorded_mode", "leakage_audit",
                              "action_probe", "training"],
            "claim_boundary": ["SYNTHETIC_DIAGNOSTIC_ONLY", "not hospital evidence",
                               "not real-scene evidence", "not benchmark evidence", "not promotion",
                               "not full ImageNav evidence", "not SOTA", "no autonomy claim",
                               "no training authorization", "CL_BOUND_XY unchanged"]}
(OUT / "synthetic_fork_render_validation_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

with open(OUT / "synthetic_fork_render_validation_table.csv", "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["gate", "pass", "detail"])
    for g, p, d in gates:
        w.writerow([g, ("PENDING" if p is None else p), d])
    w.writerow([])
    w.writerow(["view", "luma", "lower_black_frac", "median_depth_central_m", "open>=3m"])
    for d in DIRS:
        w.writerow([f"center_{d}", luma.get(d), black.get(d), depth.get(d), branch_open(views.get(d))])
    for k in ("decision", "goalA_img", "goalB_img"):
        v = named.get(k, {})
        w.writerow([k, v.get("mean_luma"), v.get("lower_frame_black_frac"),
                    v.get("median_depth_central_m"), ""])

rep = [
    "# H8-M Track-B SYNTHETIC_DIAGNOSTIC_ONLY Fork — Render-Scan Validation (Gates 1-7)", "",
    "**Status: VALIDATION ONLY — render-scan gates 1-7.** No drive-validation, no recorded-mode, no "
    "leakage audit, no action-probe, no training. Free camera at the raised (~0.12 m) robot-eye "
    "mount, level horizon. `CL_BOUND_XY` unchanged.", "",
    "> **SYNTHETIC_DIAGNOSTIC_ONLY.** This tests whether the *authored* junction satisfies the "
    "render-valid angular branch-choice requirements. It is not hospital, real-scene, benchmark, or "
    "SOTA evidence, and authorizes no training.", "",
    "## Scene",
    f"- `{SID}` — asset `{sc.get('asset_path')}`",
    f"- scene_load_ok={sc.get('scene_load_ok')}, prims={sc.get('prim_count')}, "
    f"world_bbox={sc.get('world_bbox')}",
    f"- Designed 4-way cross: branch A=N (blue/circle, STRAIGHT), branch B=W (green/triangle, "
    f"TURN_LEFT_90); E=distractor (orange), S=approach (red). Divergence A-B = {sep} deg.", "",
    "## Gate results (1-7)",
    "| gate | pass | detail |",
    "|---|---|---|",
    *[f"| {g} | {'PENDING (human)' if p is None else p} | {d} |" for g, p, d in gates], "",
    f"- **Automated gates (1,2,3,4,6,7) all pass:** {auto_gates_pass}.",
    f"- **Automated classification of the N-vs-W branch pair:** `{auto_cls}` — {auto_reason}.",
    "- **Gate 5 (mandatory visual/contact-sheet verification):** PENDING human inspection of "
    "`contact_sheets/` — the automated verdict does not stand until confirmed by eye.", "",
    "## Per-view depth / luma (center probe)",
    "| view | luma | lower_black_frac | median_depth_m | open>=3m | intended cue |",
    "|---|---|---|---|---|---|",
    *[f"| center {d} | {luma.get(d)} | {black.get(d)} | {depth.get(d)} | {branch_open(views.get(d))} "
      f"| {DIR_COLOR.get(d)} |" for d in DIRS],
    f"| open_floor(all4>=4m) | {open_floor} | | | | ns_open={ns_open} ew_open={ew_open} |", "",
    "## Embedding distinctness",
    f"- DINO cosine(goalA_img blue, goalB_img green) = **{dino_goalimg}** (threshold < {BRANCH_DISTINCT}).",
    f"- DINO cosine(center N, center W) = **{dino_center}**.", "",
    "## Decision",
    f"**{outcome}.**",
    ("- Automated gates 1-4,6,7 pass and the N-vs-W pair classifies RENDER_VALID_JUNCTION — **hold "
     "for human visual verification (gate 5), then hold for review before any drive-validation.** "
     "Render-validity is NOT drive-validity." if auto_cls == "RENDER_VALID_JUNCTION" and auto_gates_pass
     else "- The render scan did NOT confirm a render-valid junction — **revise the synthetic scene "
     "geometry / visual markers before any drive-validation.** Do not proceed to training."),
    "- Do not start training. Do not claim benchmark or real-scene evidence.", "",
    "## Gates intentionally NOT run",
    "- drive-validation, recorded-mode, leakage audit, action-probe, training — deferred to a later, "
    "separately-approved stage after gates 1-7 pass and are reviewed.", "",
    "## Claim boundary",
    "- SYNTHETIC_DIAGNOSTIC_ONLY; not hospital evidence; not real-scene evidence; not benchmark "
    "evidence; not promotion; not full goal-conditioned ImageNav evidence; not SOTA; no autonomy "
    "claim; no training authorization; `CL_BOUND_XY` unchanged.",
    "- One cross is not enough for a leakage-safe train/val/test split; future training requires a "
    "family of at least 6 disjoint junction instances.", "",
    "## Artifacts",
    "`assets/experiments/hospital_h8_track_b_synthetic_fork_validation/`: "
    "`synthetic_fork_render_validation_manifest.json`, `synthetic_fork_render_validation_table.csv`, "
    "`synthetic_fork_render_validation_report.md`, `synthetic_fork_visual_similarity_matrix.{csv,md}`, "
    "`contact_sheets/`, `render_metadata/`. Harness: "
    "`scripts/gnm/h8_track_b_synthetic_fork_render.py` (isaac), "
    "`scripts/gnm/h8_track_b_synthetic_fork_analyze.py` (this). Raw .npy in scratchpad (not committed).",
]
(OUT / "synthetic_fork_render_validation_report.md").write_text("\n".join(rep) + "\n")
(RM / "sfork_render_scan_render_manifest.json").write_text(json.dumps(man, indent=2) + "\n")

print(json.dumps({"scene_load_ok": sc.get("scene_load_ok"), "opens": opens,
                  "open_floor": open_floor, "ns_open": ns_open, "ew_open": ew_open,
                  "depths": depth, "dino_goalimg": dino_goalimg, "dino_center": dino_center,
                  "auto_classification": auto_cls, "auto_gates_pass": auto_gates_pass,
                  "outcome": outcome}, indent=2))
print("SYNTHETIC FORK RENDER-SCAN VALIDATION WRITTEN ->", OUT)
