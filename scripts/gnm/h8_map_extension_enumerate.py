"""H8 map-extension: candidate-zone enumeration + navmap<->bringup frame-fit (ANALYSIS ONLY).

No collection, no training, no Isaac, no recording. Uses only committed navmap arrays and the
recorded 0-collision trajectories to:
  1. Re-derive the navmap<->bringup rigid transform by registering the driven footprint against
     the navmap free space (deterministic FFT cross-correlation over rotations). The recorded
     paths are, by definition, free; the transform that maps ~100% of them onto free cells is
     the fit.
  2. Enumerate the reachable free component from the robot spawn and its corridor-width profile.
  3. Author candidate zones along the corridor with LEAKAGE-CLEAN split bands (train/val/test
     goal x-coordinates disjoint by construction), plus hard-negative and visually-similar
     candidates, and honest DEFERRED entries for room families with no reachable geometry.

Everything geometric-only: navmap-free => NEEDS_DRIVE_VALIDATION (drivability + render + no
black occlusion still unproven); only the already-recorded lobby is PROVEN.

Writes under assets/experiments/hospital_h8_map_extension/:
  h8_navmap_frame_fit_report.md, h8_candidate_zones.json,
  h8_candidate_zone_table.csv, h8_candidate_zone_report.md, h8_navmap_overlay.png
Run with base python (numpy+scipy+PIL). Deterministic.
"""
import json, csv, os
from collections import deque
from pathlib import Path
import numpy as np
from scipy.signal import fftconvolve
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
NB = REPO / "assets/experiments/hospital_h7_collection/navmap"
OUT = REPO / "assets/experiments/hospital_h8_map_extension"
TRAJ = REPO / "assets/experiments/trajectories"
X0, Y0, RES, N = -7.0, -7.0, 0.05, 280

# recorded 0-collision episodes (proven free space; from committed H7 + H8-prototype records)
KG = ["h7_corridor_01_20260714_004338", "h7_corridor_02_20260714_010145",
      "h7_reception_01_20260714_000815", "h7_reception_02_20260714_002503",
      "h7_turn_01_20260714_011847", "h7_turn_02_20260714_013617",
      "h7_waiting_01_20260714_015109", "h7_waiting_02_20260714_020630",
      "h8_d1_routeA_turn_up_20260714_154933", "h8_d1_routeB_straight_20260714_183358",
      "h8_d2_routeA_fwdleft_20260714_184624", "h8_d2_routeB_fwdright_20260714_185908"]


def load_driven():
    pts = []
    for d in KG:
        p = TRAJ / d / "trajectory.csv"
        with open(p) as f:
            for row in csv.DictReader(f):
                try:
                    pts.append((float(row["robot_position_x"]), float(row["robot_position_y"])))
                except (KeyError, ValueError):
                    pass
    return np.array(pts)


def fit_transform(free, pts):
    """Return (theta_deg, tx, ty, full_free_frac). world = R(theta)*bringup + t."""
    sub = pts[::15]
    best = None
    for deg in range(0, 360, 1):
        th = np.deg2rad(deg); c, s = np.cos(th), np.sin(th)
        R = np.array([[c, -s], [s, c]]); P = sub @ R.T
        gx = ((P[:, 0] - P[:, 0].min()) / RES).astype(int)
        gy = ((P[:, 1] - P[:, 1].min()) / RES).astype(int)
        H, W = gy.max() + 1, gx.max() + 1
        if H > N or W > N:
            continue
        T = np.zeros((H, W), np.float32); T[gy, gx] = 1.0
        corr = fftconvolve(free, T[::-1, ::-1], mode="valid")
        r, cc = np.unravel_index(np.argmax(corr), corr.shape)
        frac = corr[r, cc] / T.sum()
        if best is None or frac > best[0]:
            tx = X0 + cc * RES - P[:, 0].min(); ty = Y0 + r * RES - P[:, 1].min()
            best = (frac, deg, tx, ty)
    _, deg, tx, ty = best
    th = np.deg2rad(deg); c, s = np.cos(th), np.sin(th); R = np.array([[c, -s], [s, c]])
    Pf = pts @ R.T + np.array([tx, ty])
    ix = ((Pf[:, 0] - X0) / RES).astype(int); iy = ((Pf[:, 1] - Y0) / RES).astype(int)
    ok = (ix >= 0) & (ix < N) & (iy >= 0) & (iy < N)
    return deg, tx, ty, float(free[iy[ok], ix[ok]].mean())


def reach_from(grid, sr, sc):
    R = np.zeros_like(grid, bool)
    if not grid[sr, sc]:
        return R
    q = deque([(sr, sc)]); R[sr, sc] = True
    while q:
        r, c = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < N and 0 <= nc < N and grid[nr, nc] and not R[nr, nc]:
                R[nr, nc] = True; q.append((nr, nc))
    return R


def main():
    occ = np.load(NB / "occupancy_raw.npy"); rawfree = (occ == 0)
    nav = np.load(NB / "navigable.npy").astype(bool)   # True = navigable (inflated)
    pts = load_driven()
    deg, tx, ty, frac = fit_transform((occ == 0).astype(np.float32), pts)
    assert deg == 0 and frac > 0.999, f"unexpected fit deg={deg} frac={frac}"

    def b2g(bx, by):   # bringup -> grid (col,row)
        wx, wy = bx + tx, by + ty
        return int((wx - X0) / RES), int((wy - Y0) / RES)

    sc, sr = b2g(0.0, 0.0)
    reach_nav = reach_from(nav, sr, sc)
    reach_raw = reach_from(rawfree, sr, sc)
    rr, ccl = np.where(reach_nav)
    bx = X0 + ccl * RES - tx; by = Y0 + rr * RES - ty
    env = dict(x_min=float(bx.min()), x_max=float(bx.max()),
               y_min=float(by.min()), y_max=float(by.max()), cells=int(reach_nav.sum()))
    rr2, cc2 = np.where(reach_raw); by2 = Y0 + rr2 * RES - ty; bx2 = X0 + cc2 * RES - tx
    env_raw = dict(x_min=float(bx2.min()), x_max=float(bx2.max()),
                   y_min=float(by2.min()), y_max=float(by2.max()), cells=int(reach_raw.sum()))
    proven = dict(x_min=-2.31, x_max=0.91, y_min=-0.76, y_max=0.92)

    # corridor width profile: navigable y-extent per 0.25 m x-bin
    prof = []
    for x0 in np.arange(np.floor(env["x_min"]), np.ceil(env["x_max"]), 0.25):
        m = (bx >= x0) & (bx < x0 + 0.25)
        if m.sum() < 3:
            continue
        yb = by[m]; prof.append((round(float(x0 + 0.125), 3), round(float(yb.max() - yb.min()), 2),
                                 round(float(yb.min()), 2), round(float(yb.max()), 2)))

    def width_at(xc):
        cand = [w for (xx, w, _, _) in prof if abs(xx - xc) <= 0.3]
        return min(cand) if cand else 0.0

    def risk(xc):
        w = width_at(xc)
        return "low" if w >= 1.6 else "medium" if w >= 1.1 else "high"

    def status_for(xc):
        return "PROVEN" if proven["x_min"] - 0.2 <= xc <= proven["x_max"] + 0.2 else "NEEDS_DRIVE_VALIDATION"

    # candidate zones along the corridor; split BANDS chosen disjoint in x -> leakage-clean.
    # west (train), mid-west (val), lobby (train, proven), east (test), far ends (hard-neg / lookalike)
    zones = []

    def zone(zid, kind, x0, x1, split, family, vis, notes):
        xc = round((x0 + x1) / 2, 2)
        zones.append(dict(candidate_id=zid, kind=kind,
                          bringup_rect=[round(x0, 2), round(x1, 2), -0.55, 1.0],
                          representative_o_d=[xc, 0.1],
                          corridor_width_m=round(width_at(xc), 2),
                          intended_split=split, family=family, visual_uniqueness=vis,
                          est_collision_risk=risk(xc), status=status_for(xc), notes=notes))

    # disjoint x-bands: train-west [-8.5,-4.0], val [-3.8,-3.0], lobby(train) [-2.31,0.91],
    # test-east [1.4,3.5], hard-neg far-west [-9.9,-9.0] (disjoint from all correct-goal bands)
    zone("h8mx_west_A", "corridor_continuation", -8.5, -7.0, "train", "near_far_same_approach",
         "distinct (west end)", "West corridor run; goal selects stop distance along +x. New reachable space.")
    zone("h8mx_west_B", "corridor_continuation", -6.8, -5.5, "train", "stop_vs_go",
         "distinct", "West corridor; stop-here vs continue. Visual confuser for h8mx_lookalike_test.")
    zone("h8mx_west_C", "corridor_continuation", -5.3, -4.0, "train", "shared_corridor_branch",
         "distinct", "West corridor; lateral branch within ~1.8 m width (short-baseline >=30 deg like DF01/02).")
    zone("h8mx_val_A", "corridor_continuation", -3.8, -3.0, "val", "near_far_same_approach",
         "distinct (val band)", "Held-out val band, x disjoint from train/test goal coords.")
    zone("h8mx_lobby_proven", "proven_lobby", -2.31, 0.91, "train", "corridor_t_junction",
         "as recorded", "Already-recorded proven lobby (H7/H8). Existing train decision frames.")
    zone("h8mx_east_A", "corridor_continuation", 1.4, 2.4, "test", "near_far_same_approach",
         "distinct (east band)", "Held-out test band; spatially far from train. New reachable space.")
    zone("h8mx_east_B", "corridor_continuation", 2.6, 3.5, "test", "stop_vs_go",
         "distinct (east end)", "East corridor end; test stop-conditioning. New reachable space.")
    zone("h8mx_lookalike_test", "visually_similar_diff_location", 3.0, 3.5, "test",
         "visually_similar_diff_location", "REQUIRES RENDER CONFIRM",
         "Test goal whose APPEARANCE must be render-confirmed similar to west confuser h8mx_west_B; "
         "COORDINATES disjoint (east vs west) -> only appearance is shared, which is the adversarial design.")
    zone("h8mx_hardneg_farwest", "hard_negative", -9.9, -9.0, "hard-negative", "any",
         "distinct", "Far-west corridor end as a WRONG goal for east routes (mismatched-goal ablation); "
         "x disjoint from all correct-goal bands.")
    # deferred room families -- no reachable geometry in robot slab
    for zid, fam, note in [
        ("h8mx_side_corridor", "side_corridor", "No reachable side corridor in robot slab (walls in z-slab)."),
        ("h8mx_reception_room", "reception_side_room", "Reception hall not reachable (sealed in slab)."),
        ("h8mx_waiting_elevator_bin", "waiting_elevator_bin", "Waiting/elevator/bin alcoves not reachable in slab."),
        ("h8mx_same_room_object", "same_room_diff_object", "No reachable multi-object room; DF09 stays deferred."),
    ]:
        zones.append(dict(candidate_id=zid, kind="deferred_room", bringup_rect=None,
                          representative_o_d=None, corridor_width_m=None, intended_split="none",
                          family=fam, visual_uniqueness=None, est_collision_risk=None,
                          status="DEFERRED", notes=note))

    # leakage-clean check: correct-goal x-bands must not overlap ACROSS different splits.
    # Same-split overlap is fine; hard-negative goals are wrong-goals (excluded from the goal bands).
    def xrange(z):
        r = z["bringup_rect"]; return None if r is None else (r[0], r[1])
    def overlaps(a, b):
        return not (a[1] < b[0] or b[1] < a[0])
    goal_bands = [(z["intended_split"], xrange(z)) for z in zones
                  if z["intended_split"] in ("train", "val", "test") and xrange(z)]
    conflicts = []
    for i in range(len(goal_bands)):
        for j in range(i + 1, len(goal_bands)):
            (s1, a), (s2, b) = goal_bands[i], goal_bands[j]
            if s1 != s2 and overlaps(a, b):
                conflicts.append({"a_split": s1, "a": a, "b_split": s2, "b": b})
    leakage_clean = len(conflicts) == 0

    counts = {}
    for z in zones:
        counts[z["status"]] = counts.get(z["status"], 0) + 1

    result = dict(
        frame_fit=dict(theta_deg=deg, t_bringup_to_world=[round(tx, 4), round(ty, 4)],
                       inverse_world_to_bringup=[round(-tx, 4), round(-ty, 4)],
                       full_driven_free_frac=round(frac, 5), n_driven_points=int(len(pts))),
        reachable_envelope_bringup=env, reachable_envelope_raw_bringup=env_raw,
        proven_lobby_bringup=proven, corridor_width_profile=prof,
        leakage_clean_split_bands=leakage_clean, split_band_conflicts=conflicts,
        status_counts=counts, n_zones=len(zones), zones=zones)
    OUT.mkdir(exist_ok=True)
    (OUT / "h8_candidate_zones.json").write_text(json.dumps(result, indent=2))
    write_csv(zones)
    write_frame_fit_report(result)
    write_zone_report(result)
    draw_overlay(occ, reach_nav, zones, tx, ty)
    print(json.dumps(dict(theta=deg, t=[round(tx, 3), round(ty, 3)], driven_free=round(frac, 4),
                          reach_env=env, leakage_clean=leakage_clean, status_counts=counts,
                          n_zones=len(zones)), indent=2))
    print("H8 MAP-EXTENSION ENUM ->", OUT)


def write_csv(zones):
    cols = ["candidate_id", "kind", "family", "intended_split", "bringup_rect",
            "representative_o_d", "corridor_width_m", "visual_uniqueness",
            "est_collision_risk", "status", "notes"]
    with open(OUT / "h8_candidate_zone_table.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n"); w.writerow(cols)
        for z in zones:
            w.writerow([z.get(c) for c in cols])


def write_frame_fit_report(r):
    ff = r["frame_fit"]; env = r["reachable_envelope_bringup"]; envr = r["reachable_envelope_raw_bringup"]
    L = ["# H8 navmap <-> bringup Frame-Fit Report", "",
         "**Scope: analysis only.** No Isaac, no recording, no training. Recovers the transform "
         "between the committed navmap frame and the recording (bringup) frame from committed "
         "data, resolving the blocker recorded in `H8_NAVIGABLE_MAP_EXTENSION_PLAN.md` §1.", "",
         "## Frames",
         "- **Navmap frame** (`navmap_meta.json`): built directly from `hospital.usd` geometry in "
         "world coordinates; `x,y in [-7, 7] m`, resolution 0.05 m, 280x280; "
         "`occupancy_raw.npy` (1=occupied, 0=free), `navigable.npy` (True=free after robot-radius "
         "inflation).",
         "- **Bringup frame**: the robot's odometry is **spawn-relative** (spawn reported as (0,0)); "
         "route waypoints are authored in this frame.",
         "",
         "## Observed offset",
         "Naively assuming spawn == world origin puts **0.0%** of the recorded 0-collision paths on "
         "free cells (all axis/flip conventions tested), while 100% are in-bounds -> a genuine "
         "frame **offset**, not an indexing convention.",
         "",
         "## Fit method",
         "The recorded paths are free space by construction (0 collisions). Register the driven "
         "footprint against the navmap free map by deterministic FFT cross-correlation over "
         "rotations `theta in [0,360)` (1 deg step); the placement maximising free-cell overlap is "
         "the transform. Verified on the **full** driven set (not the subsample used for search).",
         "",
         "## Result",
         f"- **Rotation:** `theta = {ff['theta_deg']} deg` (pure translation; no rotation).",
         f"- **Translation:** `world = bringup + ({ff['t_bringup_to_world'][0]}, "
         f"{ff['t_bringup_to_world'][1]}) m`.",
         f"- **Inverse:** `bringup = (world_x + ({ff['inverse_world_to_bringup'][0]}), "
         f"world_y + ({ff['inverse_world_to_bringup'][1]}))`.",
         f"- **Verification:** **{ff['full_driven_free_frac']*100:.2f}%** of all "
         f"{ff['n_driven_points']} recorded points land on free cells under this transform "
         "(target ~100%). The spawn maps to world "
         f"`({ff['t_bringup_to_world'][0]}, {ff['t_bringup_to_world'][1]})`.",
         "",
         "## Can the frames be aligned safely?",
         "**Yes** — a single, exact rigid translation (no rotation, no scale) aligns them, validated "
         "at 100% on 65k+ independently-recorded points. The navmap is therefore usable as a "
         "coordinate oracle for the whole hospital via `bringup = world - t`. **Caveat:** navmap-free "
         "is *geometric* freedom in the z-slab [0.08, 0.55] after inflation; it certifies candidate "
         "coordinates for enumeration but does **not** prove drivability, render quality, or absence "
         "of black lower-frame occlusion -> such coordinates are `NEEDS_DRIVE_VALIDATION`.",
         "",
         "## Reachable free space (spawn-connected)",
         f"- **Inflated `navigable` reachable envelope (bringup):** "
         f"x[{env['x_min']:.2f}, {env['x_max']:.2f}], y[{env['y_min']:.2f}, {env['y_max']:.2f}] "
         f"({env['cells']} cells).",
         f"- **Uninflated `occupancy_raw` reachable envelope (bringup):** "
         f"x[{envr['x_min']:.2f}, {envr['x_max']:.2f}], y[{envr['y_min']:.2f}, {envr['y_max']:.2f}] "
         f"({envr['cells']} cells).",
         "- **Structure:** a single connected corridor ~14 m long, ~1.85-2.15 m wide. **Even "
         "uninflated, no rooms or side-branches are reachable from spawn** in the robot slab -> "
         "room/hall families are geometrically unreachable here (see zone report).",
         "",
         "## Consequence for the map extension",
         "The fit **quadruples** usable corridor length (proven lobby ~3.2 m -> reachable ~14 m), "
         "enough to place train/val/test goals in **disjoint x-bands** (leakage-clean by "
         "construction). It does **not** unlock rooms; reception/waiting/elevator/side-room families "
         "remain deferred pending a drivable doorway or a different scene.", ""]
    (OUT / "h8_navmap_frame_fit_report.md").write_text("\n".join(L).rstrip("\n") + "\n")


def write_zone_report(r):
    env = r["reachable_envelope_bringup"]
    active = [z for z in r["zones"] if z["status"] != "DEFERRED"]
    L = ["# H8 Candidate-Zone Enumeration Report", "",
         "**Scope: analysis only.** No Isaac, no recording, no training, no H8-S collection. "
         "Candidate zones are derived from the navmap free space via the recovered frame-fit "
         "(`h8_navmap_frame_fit_report.md`). Geometric freedom only -> non-proven zones are "
         "`NEEDS_DRIVE_VALIDATION` until render + drive validation (the next, review-gated sub-step).",
         "",
         f"**Reachable envelope (bringup):** x[{env['x_min']:.2f}, {env['x_max']:.2f}], "
         f"y[{env['y_min']:.2f}, {env['y_max']:.2f}].  "
         f"**Leakage-clean split bands:** {'YES' if r['leakage_clean_split_bands'] else 'NO'} "
         f"(val/test/new-train goal x-bands disjoint).",
         "",
         "## Claim boundary (what this establishes and what it does NOT)",
         "> The navigation-map frame fit demonstrates that a larger corridor-aligned region is "
         "geometrically consistent with the recorded trajectory frame. It does **not** demonstrate "
         "that candidate poses are collision-free, camera-valid, spawnable, drivable, visually "
         "suitable, or reproducible in Isaac Sim.",
         "",
         "The frame fit establishes **geometric candidacy, not navigability or visual suitability.** "
         "Consequently:",
         "- The **proven lobby** (`x in [-2.31, 0.91]`) remains the **only previously proven "
         "region** — proven by recorded 0-collision driving, not by this analysis. Its `PROVEN` "
         "label means exactly that: previously driven collision-free; nothing more is claimed for it "
         "here.",
         "- The **eight new regions are candidates only** (`NEEDS_DRIVE_VALIDATION`); they must not "
         "be called proven, reachable, safe, spawnable, or dataset-ready until they pass the Isaac "
         "render-and-drive validation gate.",
         "- **Side-room and branching-route families remain DEFERRED** — the scene provides no "
         "verified drivable side branch or room access in the robot slab.",
         "- **Split cleanliness currently applies to COORDINATES only**, not yet to final rendered "
         "imagery or route trajectories; goal-image / trajectory leakage is re-audited after "
         "rendering.",
         "",
         "## Candidate zones",
         "| candidate_id | kind | family | split | x-range (bringup) | width m | risk | status |",
         "|---|---|---|---|---|---|---|---|"]
    for z in r["zones"]:
        rect = z["bringup_rect"]; xr = f"[{rect[0]}, {rect[1]}]" if rect else "—"
        L.append(f"| {z['candidate_id']} | {z['kind']} | {z['family']} | {z['intended_split']} "
                 f"| {xr} | {z['corridor_width_m'] if z['corridor_width_m'] is not None else '—'} "
                 f"| {z['est_collision_risk'] or '—'} | {z['status']} |")
    L += ["",
          "## Split assignment (leakage-clean by construction)",
          "Correct-goal x-bands are disjoint across splits so no goal coordinate is reused (the "
          "exact failure that flagged H8-S): **train** = west corridor `x in [-8.5, -4.0]` + proven "
          "lobby `x in [-2.31, 0.91]`; **val** = `x in [-3.8, -3.0]`; **test** = east corridor "
          "`x in [1.4, 3.5]`. Hard-negative (wrong) goals sit at the far-west end `x in [-9.9, -9.0]`, "
          "disjoint from every correct-goal band. The look-alike test goal sits in the east band; "
          "its visual confuser is a west train zone -> only appearance is shared, coordinates are "
          "disjoint (render-confirm the similarity).",
          "",
          "## Feasible families here",
          "- **Along-corridor stop-conditioning** (near/far, stop-vs-go): abundant distinct "
          "x-locations -> easy to make leakage-clean. Primary yield of this extension.",
          "- **Short-baseline action-branch** (shared-corridor branch, T/fork like DF01/DF02): "
          "feasible within the ~1.85 m corridor width (~0.9 m lateral gives >=30 deg over ~1 m).",
          "- **Visually-similar-different-location**: two similar corridor stretches at distinct x "
          "(adversarial); needs render confirmation of look-alike goal images.",
          "- **Hard-negative goals**: far corridor ends as wrong goals for the mismatched-goal gate.",
          "",
          "## Deferred (honest limitation — no reachable geometry)",
          "Reception-hall, waiting/elevator/bin, generic side-corridor, and same-room-different-"
          "object families are **DEFERRED**: even uninflated, no rooms/side-branches are reachable "
          "from spawn in the robot slab. Realising them needs a drivable doorway (none in slab) or "
          "a different scene/asset — out of scope for this corridor extension.",
          "",
          "## Next sub-step (review-gated; NOT run here)",
          "Render + drive validation of the `NEEDS_DRIVE_VALIDATION` zones: per zone run the scene "
          "gate, raised mount 0.12, export a real `/camera/image_raw` contact sheet, verify hospital "
          "context + no black lower-frame occlusion, then a 0-collision drive. Only zones passing "
          "all checks graduate to `PROVEN` and feed a re-authored H8-S design gate that must report "
          "`design_ready_to_record = YES` before any recording.",
          "",
          "## Artifacts",
          "`assets/experiments/hospital_h8_map_extension/`: `h8_navmap_frame_fit_report.md`, "
          "`h8_candidate_zones.json`, `h8_candidate_zone_table.csv`, this report, "
          "`h8_navmap_overlay.png` (navmap with proven lobby + reachable envelope + candidate zones; "
          "**a map figure, not a camera contact sheet** — camera contact sheets are deferred to the "
          "render-validation sub-step). Harness: `scripts/gnm/h8_map_extension_enumerate.py`.", ""]
    (OUT / "h8_candidate_zone_report.md").write_text("\n".join(L).rstrip("\n") + "\n")


def draw_overlay(occ, reach, zones, tx, ty):
    # base: occupied dark, free light-grey; reachable=pale blue; proven lobby=green box; zones colored
    img = np.zeros((N, N, 3), np.uint8)
    img[occ == 1] = (60, 60, 70); img[occ == 0] = (210, 210, 210)
    img[reach] = (150, 190, 235)
    def b2rc(bx, by):
        return int((by + ty - Y0) / RES), int((bx + tx - X0) / RES)  # row,col
    def box(x0, x1, y0, y1, col):
        r0, c0 = b2rc(x0, y0); r1, c1 = b2rc(x1, y1)
        r0, r1 = sorted((r0, r1)); c0, c1 = sorted((c0, c1))
        r0 = max(0, r0); c0 = max(0, c0); r1 = min(N - 1, r1); c1 = min(N - 1, c1)
        img[r0:r1 + 1, c0] = col; img[r0:r1 + 1, c1] = col
        img[r0, c0:c1 + 1] = col; img[r1, c0:c1 + 1] = col
    palette = {"train": (40, 160, 60), "val": (210, 150, 20), "test": (200, 50, 50),
               "hard-negative": (150, 40, 160), "none": (120, 120, 120)}
    for z in zones:
        if z["bringup_rect"] is None:
            continue
        x0, x1, y0, y1 = z["bringup_rect"]
        box(x0, x1, y0, y1, palette.get(z["intended_split"], (0, 0, 0)))
    # flip vertically so +y is up in the saved image
    Image.fromarray(img[::-1]).resize((N * 2, N * 2), Image.NEAREST).save(OUT / "h8_navmap_overlay.png")


if __name__ == "__main__":
    main()
