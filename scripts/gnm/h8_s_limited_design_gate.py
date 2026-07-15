"""H8-S LIMITED_CAUSAL_PILOT design gate (DESIGN ONLY — no Isaac, no recording, no training).

Validates the re-scoped 3-frame limited pilot (train=lobby, val=midwest_B, test=east_A) from
labels/geometry + the committed aHash visual matrix, BEFORE any recording. Checks:
  1. coordinate split clean (o_d + goal coords disjoint across splits),
  2. no reused goal coordinates,
  3. stop-distance separations (report; flag frames below stop_min),
  4. visual distinctness classified honestly: acceptable-for-LIMITED-pilot vs strong-held-out,
  5. LIMITED_CAUSAL_PILOT labelled; no strong-held-out / multi-room / full-ImageNav claim,
  6. standard metrics + diagnostics planned.

Reads  assets/experiments/hospital_h8_s_limited_pilot/h8sl_decision_frames.json
       assets/experiments/hospital_h8_map_extension/visual_gap/_full_matrix.json
Writes (same dir): h8sl_design_manifest.json, h8sl_acceptance_results.json,
                   h8sl_design_gate_report.md
Run with base python (stdlib only).
"""
import json, math, itertools
from pathlib import Path

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
DIR = REPO / "assets/experiments/hospital_h8_s_limited_pilot"
MATRIX = REPO / "assets/experiments/hospital_h8_map_extension/visual_gap/_full_matrix.json"
STRONG_HELDOUT_MAX = 0.60   # aHash cross-split below this would allow a STRONG held-out claim
LIMITED_OK_MAX = 0.90       # above this even a limited pilot is untenable (identical views)
# zone (split anchor) -> matrix key
ZONE_KEY = {"lobby": "lobby", "midwest_B": "midwest_B", "east_A": "east_A"}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def main():
    d = json.loads((DIR / "h8sl_decision_frames.json").read_text())
    mat = json.loads(MATRIX.read_text())["matrix"]
    frames = d["decision_frames"]
    stop_min = d["stop_min_m"]

    # per-frame stop separations + confirmed-range containment
    fr_out = []
    for f in frames:
        o = f["o_d"]; A = f["goalA"]["coord"]; B = f["goalB"]["coord"]
        dA, dB = dist(o, A), dist(o, B); sep = abs(dA - dB)
        lo, hi = f["drive_confirmed_range"]
        contained = all(lo - 1e-6 <= c[0] <= hi + 1e-6 for c in (o, A, B))
        fr_out.append({**f, "goal_dist_A_m": round(dA, 3), "goal_dist_B_m": round(dB, 3),
                       "stop_separation_m": round(sep, 3), "meets_stop_min": sep >= stop_min,
                       "coords_in_confirmed_range": contained})

    # coordinate disjointness across splits
    split_coords = {}
    for f in frames:
        for c in (f["o_d"], f["goalA"]["coord"], f["goalB"]["coord"]):
            split_coords.setdefault(f["split"], set()).add(tuple(c))
    reused = []
    for (s1, c1), (s2, c2) in itertools.combinations(split_coords.items(), 2):
        inter = c1 & c2
        if inter:
            reused.append({"splits": [s1, s2], "coords": [list(x) for x in inter]})
    # x-band disjointness
    bands = {s: (min(x for x, _ in cs), max(x for x, _ in cs)) for s, cs in split_coords.items()}
    band_overlaps = []
    for (s1, b1), (s2, b2) in itertools.combinations(bands.items(), 2):
        if not (b1[1] < b2[0] or b2[1] < b1[0]):
            band_overlaps.append({"splits": [s1, s2], "bands": [b1, b2]})
    coords_clean = not reused and not band_overlaps

    # visual distinctness: cross-split aHash between the split anchor zones
    splits = {f["split"]: f["zone"] for f in frames}
    cross = []
    for (s1, z1), (s2, z2) in itertools.combinations(splits.items(), 2):
        k1, k2 = ZONE_KEY[z1], ZONE_KEY[z2]
        cross.append({"splits": [s1, s2], "zones": [z1, z2], "ahash": mat[k1][k2]})
    max_cross = max(c["ahash"] for c in cross)
    if max_cross <= STRONG_HELDOUT_MAX:
        vis_class = "STRONG_HELDOUT_CAPABLE"
    elif max_cross <= LIMITED_OK_MAX:
        vis_class = "LIMITED_PILOT_ONLY"
    else:
        vis_class = "UNACCEPTABLE_NEAR_IDENTICAL"
    vis_ok_for_limited = vis_class == "LIMITED_PILOT_ONLY"

    labelled_limited = d.get("status") == "LIMITED_CAUSAL_PILOT"
    no_strong_claim = all(x in d.get("not_claimed", []) for x in
                          ["strong held-out visual benchmark",
                           "multi-room/cross-location generalization",
                           "full goal-conditioned ImageNav"])
    metrics_ok = set(["TL", "NE", "SR", "OSR", "SPL", "nDTW", "CR"]).issubset(d["planned_metrics"])
    diag_ok = all(k in " ".join(d["planned_diagnostics"]) for k in
                  ["action-probe", "goal-sensitivity", "mismatched-goal", "distinctness", "leakage"])

    checks = {
        "coordinate_split_clean": coords_clean,
        "no_reused_goal_coordinates": not reused,
        "x_bands_disjoint": not band_overlaps,
        "visual_distinctness_ok_for_limited_pilot": vis_ok_for_limited,
        "labelled_LIMITED_CAUSAL_PILOT": labelled_limited,
        "no_strong_heldout_or_multiroom_or_full_imagenav_claim": no_strong_claim,
        "standard_metrics_planned": metrics_ok,
        "diagnostics_planned": diag_ok,
        "CL_BOUND_XY_unchanged": d["safety"]["unchanged"],
    }
    gate_pass = all(checks.values())

    results = {
        "status": "LIMITED_CAUSAL_PILOT", "gate_pass": gate_pass, "checks": checks,
        "visual": {"classification": vis_class, "max_cross_split_ahash": max_cross,
                   "cross_pairs": cross, "strong_heldout_threshold": STRONG_HELDOUT_MAX,
                   "note": "aHash is crude; a STRONG held-out claim needs an embedding gate at H8-M."},
        "coordinate_bands": {s: [round(b[0], 2), round(b[1], 2)] for s, b in bands.items()},
        "reused_coordinates": reused, "x_band_overlaps": band_overlaps,
        "decision_frames": fr_out,
        "frames_below_stop_min": [f["frame_id"] for f in fr_out if not f["meets_stop_min"]],
    }
    (DIR / "h8sl_acceptance_results.json").write_text(json.dumps(results, indent=2))
    manifest = {**d, "computed": results}
    (DIR / "h8sl_design_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_report(d, results)
    print(json.dumps({"gate_pass": gate_pass, "visual_class": vis_class,
                      "max_cross_ahash": max_cross, "coords_clean": coords_clean,
                      "frames_below_stop_min": results["frames_below_stop_min"],
                      "checks": checks}, indent=2))
    print("H8-S LIMITED DESIGN GATE ->", DIR)


def write_report(d, r):
    c = r["checks"]; v = r["visual"]
    L = ["# H8-S Limited Causal Pilot — Design-Gate Report", "",
         "**Status: `LIMITED_CAUSAL_PILOT`.** Design gate only — no recording, no training, no "
         "promotion, no push, no tag, no 20/5/10, no closed-loop, no H8-M sealed-room validation, "
         "`CL_BOUND_XY` unchanged. Held for review.", "",
         f"**Gate: {'PASS' if r['gate_pass'] else 'FAIL'}** for the re-scoped 3-frame limited pilot.",
         "",
         "## Not claimed (honest boundary)",
         "This pilot is **NOT** a strong held-out visual benchmark, **NOT** multi-room / "
         "cross-location generalization, **NOT** full goal-conditioned ImageNav. All goal images are "
         "the same vending alcove at different scales; it tests only whether the objective makes "
         "behaviour respond to the goal on a small, real, coordinate-clean set.",
         "",
         "## Split & decision frames (drive-validated coordinates)",
         "| frame | split | zone | o_d | near→far goals | stop-sep m | in confirmed range |",
         "|---|---|---|---|---|---|---|"]
    for f in r["decision_frames"]:
        L.append(f"| {f['frame_id']} | {f['split']} | {f['zone']} | {f['o_d']} | "
                 f"{f['goalA']['coord']}→{f['goalB']['coord']} | "
                 f"{f['stop_separation_m']}{'' if f['meets_stop_min'] else ' ⚠<min'} | "
                 f"{f['coords_in_confirmed_range']} |")
    L += ["",
          f"Coordinate bands (disjoint): {r['coordinate_bands']}.",
          (f"**Note:** frames below stop_min ({d['stop_min_m']} m): "
           f"{r['frames_below_stop_min']} — the east test frame's confirmed drivable range is short "
           "(1.4–2.11 m), so its near/far stop separation is modest; acceptable for a LIMITED pilot, "
           "flagged, not a strong benchmark." if r["frames_below_stop_min"]
           else "All frames meet the stop-min separation."),
          "",
          "## Coordinate cleanliness",
          f"- coordinate split clean: **{c['coordinate_split_clean']}**.",
          f"- no reused goal coordinates across splits: **{c['no_reused_goal_coordinates']}** "
          f"(reused: {r['reused_coordinates'] or 'none'}).",
          f"- x-bands disjoint: **{c['x_bands_disjoint']}** (overlaps: {r['x_band_overlaps'] or 'none'}).",
          "",
          "## Visual distinctness (for a LIMITED pilot, not a benchmark)",
          f"- classification: **{v['classification']}** — max cross-split aHash "
          f"**{v['max_cross_split_ahash']}** (strong-held-out would need ≤ {v['strong_heldout_threshold']}).",
          "- cross-split pairs: " + ", ".join(f"{p['splits'][0]}~{p['splits'][1]}={p['ahash']}"
                                              for p in v["cross_pairs"]) + ".",
          "- All goals are the same alcove at different scales, so the gate certifies visual "
          "distinctness **only as adequate for a limited pilot**; a strong held-out visual split "
          "requires the embedding gate + sealed-room extension (H8-M).",
          "",
          "## Honest-label & scope checks",
          f"- labelled LIMITED_CAUSAL_PILOT: **{c['labelled_LIMITED_CAUSAL_PILOT']}**.",
          f"- no strong-held-out / multi-room / full-ImageNav claim: "
          f"**{c['no_strong_heldout_or_multiroom_or_full_imagenav_claim']}**.",
          f"- `CL_BOUND_XY` unchanged: **{c['CL_BOUND_XY_unchanged']}**.",
          "",
          "## Planned metrics & diagnostics",
          f"- metrics: {', '.join(d['planned_metrics'])} (planned: **{c['standard_metrics_planned']}**).",
          f"- diagnostics: {', '.join(d['planned_diagnostics'])} (planned: **{c['diagnostics_planned']}**).",
          "",
          "## Dropped / deferred",
          *[f"- **{k}**: {vv}" for k, vv in d["dropped_or_deferred"].items()],
          "",
          "## Decision",
          ("**Design gate PASSES for the limited pilot.** Coordinates are clean and disjoint, no "
           "goal-coordinate reuse, visual distinctness is honestly classified as LIMITED-only, and "
           "the design is labelled and scoped as a limited causal pilot. Recording is **not** "
           "authorised here — a recorded-mode gate + the standard diagnostics come next, on review."
           if r["gate_pass"] else
           "**Design gate FAILS** — see failing checks above; do not record."),
          "- Strong held-out visual generalization remains an **H8-M** objective "
          "(`H8_M_SEALED_ROOM_MAP_EXTENSION_PLAN.md`).",
          "",
          "## Artifacts",
          "`assets/experiments/hospital_h8_s_limited_pilot/`: `h8sl_decision_frames.json` (design "
          "input), `h8sl_design_manifest.json`, `h8sl_acceptance_results.json`, this report. "
          "Harness: `scripts/gnm/h8_s_limited_design_gate.py`.", ""]
    (DIR / "h8sl_design_gate_report.md").write_text("\n".join(L).rstrip("\n") + "\n")


if __name__ == "__main__":
    main()
