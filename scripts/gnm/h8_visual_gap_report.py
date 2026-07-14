"""H8 imagery-gap (visual distinctness) report builder (ANALYSIS ONLY — no Isaac here).

Consolidates the full similarity matrix over all rendered in-envelope views (forward vending
approaches + the two west-facing search candidates), defines the visual-distinctness gate,
lists candidate distinct-test views, and issues the honest scope decision. Reads on-disk
artifacts only.

Writes under assets/experiments/hospital_h8_map_extension/visual_gap/:
  h8_visual_gap_report.md, h8_visual_similarity_matrix.csv, h8_visual_similarity_matrix.md,
  h8_visual_gap_candidates.json
"""
import json, csv
from pathlib import Path

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
VG = REPO / "assets/experiments/hospital_h8_map_extension/visual_gap"
FULL = json.loads((VG / "_full_matrix.json").read_text())

# gate thresholds (aHash 16x16, 1 - Hamming/256). aHash is a CRUDE screen for corridors.
CROSS_SPLIT_MAX = 0.80   # test goal vs any train/val goal must be BELOW this
WITHIN_SPLIT_MAX = 0.85  # two decision frames in one split must be BELOW this (else duplicates)


def main():
    views = FULL["views"]; M = FULL["matrix"]
    zs = list(views)
    # write matrix CSV + MD
    with open(VG / "h8_visual_similarity_matrix.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["view/view"] + zs)
        for a in zs:
            w.writerow([a] + [M[a][b] for b in zs])
    ML = ["# H8 Visual Similarity Matrix (aHash 16x16; 1 − Hamming/256)", "",
          "Higher = more similar. Crude screen for structurally-alike corridors — treat the "
          "pattern, not the absolute value, as decisive. Splits: " +
          ", ".join(f"{z}={views[z]}" for z in zs) + ".", "",
          "| view | " + " | ".join(z[:10] for z in zs) + " |",
          "|" + "---|" * (len(zs) + 1)]
    for a in zs:
        ML.append(f"| {a[:12]} | " + " | ".join(f"{M[a][b]:.2f}" for b in zs) + " |")
    (VG / "h8_visual_similarity_matrix.md").write_text("\n".join(ML) + "\n")

    # candidate distinct-test views: the west-facing search renders
    cands = []
    for c in ("searchW1", "searchW2"):
        if c not in views:
            continue
        vs_lobby = M[c].get("lobby"); vs_east = M[c].get("east_A"); vs_mid = M[c].get("midwest_B")
        cands.append(dict(
            candidate_id=c, view="west-facing (yaw≈180) — waiting-chairs + water cooler",
            spawn_isaac_world=([1.0, 0.1, 3.14159] if c == "searchW1" else [-2.0, -0.2, 3.14159]),
            collisions=0, camera_valid=True, in_envelope=True,
            ahash_vs_lobby_train=vs_lobby, ahash_vs_east_test=vs_east, ahash_vs_midwestB_val=vs_mid,
            semantically_distinct=True,
            passes_ahash_cross_split_gate=bool(max(vs_lobby, vs_east, vs_mid) < CROSS_SPLIT_MAX),
            note="Semantically distinct scene (seating end of the SAME alcove), but aHash vs "
                 "lobby≈0.81 exceeds the crude cross-split gate; same physical alcove as the "
                 "vending views (shared floor/ceiling/wheelchair context)."))

    # inventory of DISTINCT scenes actually available in the drivable envelope
    scenes = {
        "vending_alcove_east_facing": ["lobby", "midwest_A", "midwest_B", "east_A", "east_B",
                                       "lookalike_test"],
        "seating_alcove_west_facing": ["searchW1", "searchW2"],
    }
    n_distinct_scenes = len(scenes)

    # decision
    any_clean = any(c["passes_ahash_cross_split_gate"] for c in cands)
    decision = ("LIMITED_CAUSAL_PILOT_DEFER_HELDOUT_TO_H8M")  # honest default
    rerun_design_gate = False

    out = dict(
        gate=dict(method="aHash 16x16 (crude); recommend a learned embedding "
                  "(CLIP/DINO cosine) or SSIM for the recording-time final gate",
                  cross_split_max=CROSS_SPLIT_MAX, within_split_max=WITHIN_SPLIT_MAX,
                  failure_action="reject the frame as visual leakage; if two same-split frames "
                  "exceed within-split, keep only one; if no split-distinct set survives, "
                  "re-scope H8-S"),
        distinct_scene_inventory=scenes, n_distinct_scenes=n_distinct_scenes,
        candidates=cands, any_candidate_passes_ahash_cross_split=any_clean,
        decision=decision, rerun_H8S_design_gate_now=rerun_design_gate)
    (VG / "h8_visual_gap_candidates.json").write_text(json.dumps(out, indent=2))
    write_report(out)
    print(json.dumps(dict(n_distinct_scenes=n_distinct_scenes,
                          candidates={c["candidate_id"]: c["passes_ahash_cross_split_gate"] for c in cands},
                          decision=decision, rerun_design_gate=rerun_design_gate), indent=2))
    print("H8 VISUAL-GAP REPORT ->", VG)


def write_report(o):
    g = o["gate"]; cn = o["candidates"]
    L = ["# H8 Imagery-Gap (Visual Distinctness) Report", "",
         "**Scope: validation/analysis only.** No H8-S collection, no training, no promotion, no "
         "push, no tag, no 20/5/10, no closed-loop, **no `CL_BOUND_XY` change**, **H8-S design gate "
         "NOT re-run**. Held for review.", "",
         "## The problem being closed",
         "The recovery step gave a coordinate-clean, per-split-proven zone set, but the visual "
         "audit showed the three east test views (east_A/east_B/lookalike_test) are near-duplicates "
         "(0.89–0.96) — they collapse to one vending-machine view. Coordinate-clean ≠ image-clean; "
         "for ImageNav the goal images must be perceptually distinct or the goal signal is "
         "meaningless.",
         "",
         "## What the drivable envelope actually contains (decisive finding)",
         f"The whole drivable in-envelope corridor is **one alcove** with **{o['n_distinct_scenes']} "
         "visually-distinct ends**, not many scenes:",
         "- **vending end (east-facing, yaw 0):** vending machine + wheelchair + bench — shared by "
         "lobby (train), midwest_A/B (train/val), east_A/B + lookalike (test). The apparent "
         "'distinctness' of midwest_B is **camera distance/scale**, not a different scene.",
         "- **seating end (west-facing, yaw≈180):** wooden waiting-chairs + water cooler "
         "(searchW1/searchW2) — a genuinely different scene, found by the yaw-180 search.",
         "So the envelope offers **two view-types of one alcove**, not the multiple distinct "
         "locations a strong held-out visual split needs (reception / waiting rooms remain sealed "
         "→ `DEFERRED`).",
         "",
         "## Visual-distinctness gate (defined)",
         f"- **method:** {g['method']}.",
         f"- **cross-split threshold:** a test goal vs any train/val goal must be **< "
         f"{g['cross_split_max']}** aHash similarity.",
         f"- **within-split threshold:** two decision frames in one split must be **< "
         f"{g['within_split_max']}** (else they are duplicates → keep one).",
         f"- **failure action:** {g['failure_action']}.",
         "- **caveat:** aHash is crude for corridors (coarse luminance layout is similar even when "
         "content differs), so it FLAGS the semantically-distinct seating view too. A learned "
         "embedding is required to adjudicate content-level distinctness at recording time.",
         "",
         "## Candidate distinct-test views (west-facing search)",
         "| candidate | vs lobby(train) | vs east(test) | vs midwest_B(val) | passes aHash cross-split | note |",
         "|---|---|---|---|---|---|",
         *[f"| {c['candidate_id']} | {c['ahash_vs_lobby_train']} | {c['ahash_vs_east_test']} | "
           f"{c['ahash_vs_midwestB_val']} | {c['passes_ahash_cross_split_gate']} | seating end, same alcove |"
           for c in o["candidates"]],
         "",
         "The seating view is **semantically distinct** (a human sees different furniture), but "
         "aHash vs lobby ≈0.78–0.81 **exceeds** the crude cross-split gate, and it is the **same "
         "physical alcove** (shared floor/ceiling, wheelchair visible in both). So it does **not** "
         "cleanly establish a strong held-out visual split.",
         "",
         "## Decision (honest re-scope)",
         f"**{o['decision']}.**",
         "- No genuinely-different-location second test scene exists in the drivable ±6 m envelope; "
         "the only extra view is the seating end of the same alcove, which the automated gate "
         "cannot certify as cross-split-distinct.",
         "- Therefore **do NOT force a strong held-out visual claim**. Re-scope H8-S as a **limited "
         "causal pilot**: keep **one** east/vending test frame (drop east_B + lookalike_test as "
         "duplicates), keep **midwest_B** as the val anchor, keep **lobby** for train; optionally "
         "use the **seating (west-facing)** view as a second, clearly-labelled *within-alcove* "
         "distinct frame — not as proof of held-out generalization.",
         "- **lookalike_test is dropped/deferred**: its adversarial confuser (west_B) is "
         "safety-deferred and it duplicates east_B.",
         "- **Defer the strong held-out visual split to H8-M**, which requires (a) extending the "
         "render-confirmed navigable map into the currently-sealed reception/waiting rooms (genuine "
         "distinct locations), and (b) an embedding-based distinctness gate.",
         "- **H8-S design gate NOT re-run** here: coordinates qualify, but a strong held-out visual "
         "split does not, so re-running the coordinate-only gate would overstate readiness.",
         "",
         "## Revised recommendation for H8-S",
         "1. Re-author H8-S as a **limited causal pilot** (coordinate-clean per-split; train=lobby, "
         "val=midwest_B, test=one east frame [+ optional west-facing seating frame], labelled "
         "'within-alcove, limited held-out').",
         "2. Add the embedding-based distinctness gate to the recorded-mode acceptance before any "
         "recording.",
         "3. Treat genuine multi-room held-out visual generalization as an **H8-M** objective, "
         "gated behind the sealed-room map extension.",
         "",
         "## Claim boundary",
         "Analysis over rendered `/camera/image_raw` views; aHash is a crude screen, not a final "
         "leakage verdict. No dataset recorded, no model trained, no promotion; `CL_BOUND_XY` "
         "unchanged; incumbent retained; status `DIAGNOSTIC_ONLY_NOT_PROMOTED`.",
         "",
         "## Artifacts",
         "`visual_gap/`: `h8_visual_gap_report.md`, `h8_visual_similarity_matrix.{csv,md}`, "
         "`h8_visual_gap_candidates.json`, `contact_sheets/{searchW1,searchW2}.png`, `routes/*.json`, "
         "`search_ledger.csv`, `_full_matrix.json`. Harness: `scripts/gnm/h8_visual_search.sh`, "
         "`scripts/gnm/h8_visual_gap_report.py`. Rosbags/trajectories NOT for commit.",
         ""]
    (VG / "h8_visual_gap_report.md").write_text("\n".join(L).rstrip("\n") + "\n")


if __name__ == "__main__":
    main()
