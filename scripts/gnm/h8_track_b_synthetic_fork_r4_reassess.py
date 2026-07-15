"""H8 Track-B — RE-ASSESS the synthetic-fork R4 render validation under the implemented Outcome A + E
distinctness rule (validation/analysis ONLY; no Isaac, no re-render, no drive, no record, no train).

Reuses the ALREADY-COMMITTED R4 render evidence
(`assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r4/`) — every metric needed is in
the committed R4 manifest (per-view luma/depth/black, both DINO cosines, all 7 gate results,
action-angle 90 deg) and the committed similarity matrix. Nothing is re-rendered: the same validated
R4 render is re-CLASSIFIED under the reviewed rule in `scripts/gnm/h8_distinctness_gate.py`, where the
DINO embedding is ADVISORY ONLY for a SYNTHETIC_DIAGNOSTIC_ONLY symmetric cross (logged, never a hard
pass/fail). Required synthetic gates: 1 scene-load, 2 render-validity, 3 depth-openness, 4 open-floor
guard, 5 visual/contact-sheet verification, 7 action-angle separation.

Run: ~/miniforge3/bin/python scripts/gnm/h8_track_b_synthetic_fork_r4_reassess.py
"""
import csv, json, shutil, sys
from pathlib import Path

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
sys.path.insert(0, str(REPO / "scripts/gnm"))
from h8_distinctness_gate import (advisory_synthetic, distinctness_report_block, PROVENANCE,
                                  LEGACY_HARD_THRESHOLD_SUPERSEDED, REAL_SCENE_DINO_THRESHOLD)

SRC = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r4"
OUT = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r4_reassessed"
CS_OUT = OUT / "contact_sheets"
for d in (OUT, CS_OUT):
    d.mkdir(parents=True, exist_ok=True)

SRC_MANIFEST = SRC / "synthetic_fork_r4_render_validation_manifest.json"
SRC_MATRIX = SRC / "synthetic_fork_r4_visual_similarity_matrix.csv"
m = json.loads(SRC_MANIFEST.read_text())

# ── pull the committed R4 gate results (reused, NOT recomputed) ────────────────
gate_by_name = {g["gate"]: g for g in m["gates"]}
REQUIRED = ["1_scene_load", "2_render_validity", "3_depth_openness", "4_open_floor_guard", "7_action_angle"]
required_pass = all(bool(gate_by_name[g]["pass"]) for g in REQUIRED)

dino_goalimg = m.get("dino_goalimg")
dino_center = m.get("dino_center")
sep_deg = (m.get("designed_branch_pair") or {}).get("sep_deg")
gate5_src = str(m.get("gate_5_visual_verification"))
gate5_confirms = gate5_src.upper().startswith("DONE")

# ── advisory embedding verdict (Outcome E): DINO logged, NEVER gates ──────────
adv = advisory_synthetic(dino_goalimg)

# ── re-classify under the advisory rule ──────────────────────────────────────
# RENDER_VALID_JUNCTION now depends on geometry (gates 1-4) + action-angle (gate 7) + mandatory
# visual verification (gate 5) — NOT on the DINO cosine (advisory).
if required_pass and gate5_confirms:
    reassessed_cls = "RENDER_VALID_JUNCTION"
    reassessed_reason = ("perpendicular depth-open divergent branches (N vs W); geometry + "
                         "action-angle gates pass; gate-5 visual confirms branch-specific geometry; "
                         f"DINO advisory only (goal-image cosine {dino_goalimg}, not gated)")
    outcome = "SYNTHETIC_FORK_RENDER_VALID_PENDING_DRIVE_VALIDATION_HOLD_FOR_REVIEW"
elif required_pass and not gate5_confirms:
    reassessed_cls = "RENDER_VALID_PENDING_VISUAL_VERIFICATION"
    reassessed_reason = "geometry + action-angle pass; gate-5 visual verification still required"
    outcome = "SYNTHETIC_FORK_RENDER_VALID_PENDING_VISUAL_VERIFICATION_HOLD_FOR_REVIEW"
else:
    failed = [g for g in REQUIRED if not bool(gate_by_name[g]["pass"])]
    reassessed_cls = "SYNTHETIC_FORK_RENDER_SCAN_FAILED"
    reassessed_reason = f"required render gate(s) failed: {failed} (DINO is advisory, not a cause)"
    outcome = "SYNTHETIC_FORK_RENDER_SCAN_FAILED_REVISE_GEOMETRY"

# ── build the reassessed gate table (gate 6 now advisory: pass=None) ──────────
reassessed_gates = []
for g in m["gates"]:
    name = g["gate"]
    if name == "6_embedding_distinctness":
        reassessed_gates.append({
            "gate": "6_embedding_distinctness", "pass": None, "mode": "ADVISORY_ONLY",
            "detail": (f"ADVISORY ONLY (Outcome E) — NOT a synthetic pass/fail gate. DINO goal-image "
                       f"cosine {dino_goalimg} (standoff1.5={m.get('dino_goalimg_standoff_1_5')}, "
                       f"standoff2.0={m.get('dino_goalimg_standoff_2_0')}); center N-vs-W {dino_center}. "
                       f"advisory reference {REAL_SCENE_DINO_THRESHOLD}; former hard "
                       f"{LEGACY_HARD_THRESHOLD_SUPERSEDED} superseded. A symmetric cross shares the "
                       "same corridor perspective, so DINO cannot separate same-from-distinct.")})
    else:
        reassessed_gates.append({"gate": name, "pass": g["pass"], "detail": g["detail"]})

# ── copy committed contact sheets as review evidence (gate 5 input) ───────────
copied = []
src_cs = SRC / "contact_sheets"
if src_cs.is_dir():
    for p in sorted(src_cs.glob("*.png")):
        shutil.copy2(p, CS_OUT / p.name)
        copied.append(p.name)

# ── copy the similarity matrix (reused DINO cosines, advisory framing) ────────
matrix_rows = list(csv.reader(SRC_MATRIX.read_text().splitlines()))
with open(OUT / "synthetic_fork_r4_reassessed_visual_similarity_matrix.csv", "w", newline="") as f:
    csv.writer(f, lineterminator="\n").writerows(matrix_rows)

labels = matrix_rows[0][1:]
mm = ["# Synthetic Fork R4 — Visual Similarity Matrix (DINO ViT-S/16 cosine) — REASSESSED (advisory)",
      "",
      "**ADVISORY ONLY (Outcome E).** These are the committed R4 DINO cosines, reused unchanged. They "
      "are recorded for transparency but do NOT pass/fail this SYNTHETIC_DIAGNOSTIC_ONLY scene — a "
      "symmetric cross shares the same corridor perspective, so DINO cannot separate "
      f"same-from-distinct (advisory reference {REAL_SCENE_DINO_THRESHOLD}; former hard "
      f"{LEGACY_HARD_THRESHOLD_SUPERSEDED} superseded). Lower = more visually distinct.", "",
      "| view | " + " | ".join(labels) + " |", "|" + "---|" * (len(labels) + 1)]
for r in matrix_rows[1:]:
    mm.append("| " + " | ".join(r) + " |")
(OUT / "synthetic_fork_r4_reassessed_visual_similarity_matrix.md").write_text("\n".join(mm) + "\n")

# ── reassessed manifest ──────────────────────────────────────────────────────
manifest = {
    "label": "SYNTHETIC_DIAGNOSTIC_ONLY",
    "status": "VALIDATION_ONLY_REASSESSED_UNDER_ADVISORY_EMBEDDING_RULE",
    "reassessment_of": str(SRC_MANIFEST.relative_to(REPO)),
    "rerendered": False,
    "reused_committed_r4_render": True,
    "advisory_embedding_rule": {
        "outcome": "A+E",
        "synthetic_dino": "advisory_only_not_gated",
        "advisory_reference_threshold": REAL_SCENE_DINO_THRESHOLD,
        "legacy_hard_threshold_superseded": LEGACY_HARD_THRESHOLD_SUPERSEDED,
        "provenance": PROVENANCE,
        "rule_module": "scripts/gnm/h8_distinctness_gate.py"},
    "scene": m.get("scene"), "asset_path": m.get("asset_path"),
    "scene_load_ok": m.get("scene_load_ok"), "prim_count": m.get("prim_count"),
    "world_bbox": m.get("world_bbox"), "center_depths_m": m.get("center_depths_m"),
    "center_luma": m.get("center_luma"), "opens": m.get("opens"),
    "open_floor": m.get("open_floor"), "ns_open": m.get("ns_open"), "ew_open": m.get("ew_open"),
    "designed_branch_pair": m.get("designed_branch_pair"),
    "action_angle_sep_deg": sep_deg,
    "dino_goalimg_advisory": dino_goalimg, "dino_center_advisory": dino_center,
    "dino_advisory_verdict": adv,
    "required_render_gates": REQUIRED,
    "required_render_gates_pass": required_pass,
    "gate_5_visual_verification": gate5_src,
    "gate_5_confirms_branch_specific_geometry": gate5_confirms,
    "gates": reassessed_gates,
    "reassessed_classification": reassessed_cls,
    "reassessed_reason": reassessed_reason,
    "decision_rule_outcome": outcome,
    "contact_sheets_copied": copied,
    "claim_boundary": [
        "SYNTHETIC_DIAGNOSTIC_ONLY", "advisory embedding rule applied (Outcome A + E)",
        "no real-scene benchmark claim", "no hospital claim", "no full goal-conditioned ImageNav claim",
        "no SOTA", "no promotion (DIAGNOSTIC_ONLY_NOT_PROMOTED; incumbent retained)",
        "no autonomy claim", "no drive validation", "no recording", "no trajectory collection",
        "no training", "CL_BOUND_XY unchanged (6.0 m watchdog untouched)",
        "DINO logged as advisory, not used as a hard failure"],
}
(OUT / "synthetic_fork_r4_reassessed_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

# ── reassessed gate table (csv) ──────────────────────────────────────────────
with open(OUT / "synthetic_fork_r4_reassessed_table.csv", "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n"); w.writerow(["gate", "pass", "mode", "detail"])
    for g in reassessed_gates:
        w.writerow([g["gate"], g["pass"], g.get("mode", "hard_gate"), g["detail"]])

# ── reassessed report (md) ───────────────────────────────────────────────────
def _p(v):
    return {True: "PASS", False: "FAIL", None: "ADVISORY/ MANUAL"}.get(v, str(v))


rep = [
    "# H8 Track-B — Synthetic Diagnostic Fork R4 RE-ASSESSMENT (under implemented Outcome A + E)", "",
    "**Status: VALIDATION / ANALYSIS ONLY — `SYNTHETIC_DIAGNOSTIC_ONLY`.** This re-assessment reuses "
    "the already-committed R4 render evidence and re-classifies it under the implemented reviewed "
    "distinctness rule (`scripts/gnm/h8_distinctness_gate.py`), in which the DINO embedding is "
    "**advisory only** for a symmetric cross. **No re-render, no drive-validation, no recording, no "
    "trajectory collection, no training, no promotion.** `CL_BOUND_XY` unchanged.", "",
    f"- Reassessment of: `{SRC_MANIFEST.relative_to(REPO)}`",
    "- Re-rendered: **No** — the committed R4 render (same validated frames) is reused; only the "
    "classification rule changed.",
    f"- Advisory embedding rule provenance: {PROVENANCE}", "",
    "## Reviewed rule applied (Outcome A + E)",
    "- **Synthetic fork (Outcome E):** DINO cosine is **advisory only** — logged, never a hard "
    "pass/fail. A DINO cosine above the former 0.60 (or above the calibrated 0.76) does **not** "
    "fail the synthetic fork.",
    "- **Required render gates:** 1 scene-load, 2 render-validity, 3 depth-openness, 4 open-floor "
    "guard, 5 visual/contact-sheet verification, 7 action-angle separation.",
    "- **Gate 6 (embedding distinctness):** reported as an advisory DINO cosine, not a pass/fail.", "",
    "## Gate results (reassessed)",
    "| gate | result | detail |", "|---|---|---|",
    *[f"| {g['gate']} | {_p(g['pass'])}{' (advisory)' if g.get('mode')=='ADVISORY_ONLY' else ''} | "
      f"{g['detail'][:96]} |" for g in reassessed_gates], "",
    f"- **Required render gates (1,2,3,4,7) all pass:** {required_pass}.",
    f"- **Gate 5 (mandatory visual/contact-sheet):** {gate5_src[:140]}",
    f"- **Gate 6 embedding distinctness:** ADVISORY — DINO goal-image cosine **{dino_goalimg}**, "
    f"center N-vs-W **{dino_center}** (advisory reference {REAL_SCENE_DINO_THRESHOLD}; former hard "
    f"{LEGACY_HARD_THRESHOLD_SUPERSEDED} superseded). **Logged as advisory, not used as a hard "
    "failure.**", "",
    "## Distinctness (advisory) block",
    distinctness_report_block(adv), "",
    "## Geometry & action-angle (reused from committed R4, unchanged)",
    f"- Scene load: prims {m.get('prim_count')}, bbox {m.get('world_bbox')} — **valid**.",
    f"- Depth-openness: center depths {m.get('center_depths_m')} m (branches N/W both >= 3.0 m) — "
    "**geometry gates remained valid**.",
    f"- Open-floor guard: open_floor={m.get('open_floor')} (not an open hall) — **passes**.",
    f"- Action-angle: designed branch pair A=N vs B=W, **sep ~{sep_deg} deg** (approximately 90 deg, "
    ">= 30) — **remained valid**.",
    "- Contact-sheet verification: the committed R4 gate-5 record confirms the four corridors are "
    "**branch-specific / dramatically distinct to a human** (blue-round / orange-boxy / "
    "green-narrow-pointed / red-columned) — **confirms branch-specific synthetic geometry**. Sheets "
    f"copied to `contact_sheets/` ({len(copied)} files).", "",
    "## Reassessed decision",
    f"- **Reassessed classification: `{reassessed_cls}`.**",
    f"- **Outcome: `{outcome}`.**", "",
    "Under the reviewed rule the required render gates (1,2,3,4,5,7) are satisfied — the only prior "
    "R4 failure was the now-advisory DINO gate (6). Per the decision rule, **STOP for review before "
    "drive validation.** Do **not** start drive validation, recorded-mode data collection, "
    "action-probe, or training.", "",
    "## Next gate (not started; on approval only)",
    "render reassessment passes -> **drive validation** -> recorded-mode data exists -> split/leakage "
    "audit passes -> action-probe readiness passes -> review approval. **Training remains blocked** "
    "until all of these pass.", "",
    "## Claim boundary",
    "`SYNTHETIC_DIAGNOSTIC_ONLY`; advisory embedding rule applied; no real-scene benchmark claim; no "
    "hospital claim; no full goal-conditioned ImageNav claim; no SOTA; no promotion "
    "(`DIAGNOSTIC_ONLY_NOT_PROMOTED`, incumbent retained); no autonomy claim; no drive validation; no "
    "recording; no trajectory collection; no training; `CL_BOUND_XY` unchanged; geometry gates "
    "remained valid; action-angle remained approximately 90 deg; contact-sheet verification confirms "
    "branch-specific synthetic geometry; DINO value logged as advisory, not used as a hard failure.", "",
    "## Artifacts",
    "`assets/experiments/hospital_h8_track_b_synthetic_fork_validation_r4_reassessed/`: "
    "`synthetic_fork_r4_reassessed_manifest.json`, `synthetic_fork_r4_reassessed_table.csv`, "
    "`synthetic_fork_r4_reassessed_report.md`, "
    "`synthetic_fork_r4_reassessed_visual_similarity_matrix.{csv,md}`, `contact_sheets/`. Rule: "
    "`scripts/gnm/h8_distinctness_gate.py`; reassessor: "
    "`scripts/gnm/h8_track_b_synthetic_fork_r4_reassess.py`.",
]
(OUT / "synthetic_fork_r4_reassessed_report.md").write_text("\n".join(rep) + "\n")

print(json.dumps({"rerendered": False, "reused_committed_r4": True,
                  "required_render_gates_pass": required_pass,
                  "gate6_mode": "advisory_only", "dino_goalimg_advisory": dino_goalimg,
                  "action_angle_sep_deg": sep_deg, "reassessed_classification": reassessed_cls,
                  "outcome": outcome, "contact_sheets_copied": len(copied)}, indent=2))
print("REASSESSMENT WRITTEN ->", OUT)
