"""Top-down H7 route-review overlay: plot the 8 planned routes against ground truth
(the smoke episode's actual collision-free driven path) + the render-confirmed pilot
points. Risk-coloured. PIL (gnm_train). Honest: feature zones are approximate from
renders and labelled as such.
"""
import json, csv
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
RDIR = REPO / "assets/experiments/hospital_h7_collection/routes"
REPORTS = REPO / "assets/experiments/hospital_h7_collection/reports"
REPORTS.mkdir(parents=True, exist_ok=True)
# the 3 collision-free driven paths (ground truth): smoke + 2 +y valchecks
TRAJ = REPO / "assets/experiments/trajectories"
DRIVEN_CSVS = ([TRAJ / "h7_reception_01_smoke_20260713_231058/trajectory.csv"] +
               sorted(TRAJ.glob("h7_valcheck_*/trajectory.csv")))

# render-confirmed robot-height pilot camera positions (each rendered clear floor)
PILOT_PTS = [(-2.6, -0.8), (-0.8, -0.2), (1.2, 0.0), (-1.5, 0.0), (0.2, 0.0), (2.0, 0.0),
             (0.0, 1.0), (1.2, 0.4), (1.4, -0.6), (-2.2, 1.4), (0.0, 0.6), (1.6, -0.2)]

RISK = {  # (split, risk, confirmation, landmarks) — after +y drive-validation
    "h7_reception_01": ("train", "LOW", "drive-CONFIRMED (smoke, 0 contacts)",
                        "reception desk, wheelchair, vending, corridor opening"),
    "h7_reception_02": ("val", "LOW", "drive-covered (within 0-contact envelope, x<=1.0, y<=0.4)",
                        "reception desk, wheelchair, open floor"),
    "h7_corridor_01": ("train", "LOW", "drive-covered (y=0 line inside reception_01 path; goal trimmed x=1.0)",
                       "corridor walls, floor, ceiling lights"),
    "h7_corridor_02": ("val", "LOW", "drive-covered (y=0.6 bracketed by driven y=0 & y=0.8; goal trimmed x=1.0)",
                       "corridor, doors"),
    "h7_turn_01": ("train", "LOW", "drive-CONFIRMED (valcheck, 0 contacts)",
                   "wall corner, T-junction, bin"),
    "h7_turn_02": ("test", "LOW", "drive-covered (mirror of turn_01; points within driven envelope)",
                   "wall corner, T-junction, bin"),
    "h7_waiting_01": ("train", "LOW", "drive-CONFIRMED (valcheck, 0 contacts)",
                      "waiting tables, glass doorway, bin"),
    "h7_waiting_02": ("test", "LOW", "drive-covered (within waiting_01/reception_01 envelope)",
                      "waiting tables, glass doorway, bin"),
}
RCOL = {"LOW": (30, 150, 40), "MEDIUM": (210, 120, 0), "HIGH": (200, 30, 30)}

routes = {p.stem: json.loads(p.read_text()) for p in sorted(RDIR.glob("h7_*.json"))
          if p.stem != "h7_routes_manifest"}

driven_paths = []
for cpath in DRIVEN_CSVS:
    if not cpath.exists():
        continue
    pts = []
    with open(cpath) as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i % 20 == 0:
                try:
                    pts.append((float(row["robot_position_x"]), float(row["robot_position_y"])))
                except Exception:
                    pass
    if pts:
        driven_paths.append(pts)

# canvas / world transform
XMIN, XMAX, YMIN, YMAX = -3.3, 2.7, -1.7, 1.9
SCALE = 150
ML, MT = 60, 60
W = int((XMAX - XMIN) * SCALE) + 2 * ML
H = int((YMAX - YMIN) * SCALE) + 2 * MT + 40
img = Image.new("RGB", (W, H), (255, 255, 255))
d = ImageDraw.Draw(img)
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
fb = lambda n: ImageFont.truetype(FB, n)
fr = lambda n: ImageFont.truetype(FR, n)


def px(x, y):
    return ML + (x - XMIN) * SCALE, MT + (YMAX - y) * SCALE


# approximate feature caution (from renders — NOT surveyed)
vb_x, _ = px(1.8, 0)
d.rectangle([vb_x, MT, W - ML, MT + (YMAX - YMIN) * SCALE], fill=(252, 240, 240))
d.text((vb_x + 4, MT + 6), "≈ vending / wheelchair\n(approx from renders — avoid)",
       fill=(180, 90, 90), font=fr(12))

# grid
for gx in range(-3, 3):
    x, _ = px(gx, 0); d.line([(x, MT), (x, MT + (YMAX - YMIN) * SCALE)], fill=(230, 230, 230))
    d.text((x + 2, MT + 2), f"x={gx}", fill=(150, 150, 150), font=fr(11))
for gy in range(-1, 2):
    _, y = px(0, gy); d.line([(ML, y), (W - ML, y)], fill=(230, 230, 230))
    d.text((ML + 2, y + 2), f"y={gy}", fill=(150, 150, 150), font=fr(11))

# proven-clear driven paths (ground truth): 3 collision-free drives
for path in driven_paths:
    d.line([px(*p) for p in path], fill=(120, 210, 130), width=9)
# render-confirmed pilot points
for (x, y) in PILOT_PTS:
    cx, cy = px(x, y)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(60, 170, 70), outline=(0, 90, 0))

# origin / robot spawn
ox, oy = px(0, 0)
d.ellipse([ox - 6, oy - 6, ox + 6, oy + 6], outline=(0, 0, 200), width=2)
d.text((ox + 7, oy - 16), "spawn (0,0)", fill=(0, 0, 200), font=fb(12))

# planned routes
for rid, r in routes.items():
    col = RCOL[RISK[rid][1]]
    pts = [px(x, y) for x, y in r["waypoints"]]
    d.line(pts, fill=col, width=3)
    sx, sy = pts[0]; gx, gy = pts[-1]
    d.ellipse([sx - 6, sy - 6, sx + 6, sy + 6], fill=(255, 255, 255), outline=col, width=3)
    d.rectangle([gx - 6, gy - 6, gx + 6, gy + 6], fill=col, outline=(0, 0, 0))
    mx, my = pts[len(pts) // 2]
    d.text((mx + 6, my - 6), rid.replace("h7_", ""), fill=col, font=fb(12))

# legend
ly = MT + (YMAX - YMIN) * SCALE + 8
d.text((ML, ly), "● render-confirmed pt   ━ 3 proven driven paths (0 contacts)   "
       "○ start  ■ goal   GREEN=LOW", fill=(40, 40, 40), font=fr(13))
d.text((ML, ly + 18), "Robot spawns at (0,0) and drives waypoints in WORLD coords. "
       "Feature zones approximate from renders, not surveyed.", fill=(110, 110, 110), font=fr(12))

img.save(REPORTS / "h7_route_review_overlay.png")

# coordinate table (json + csv)
table = []
for rid, r in routes.items():
    split, risk, conf, lm = RISK[rid]
    table.append({"route_id": rid, "family": r["route_type"], "variant": rid[-2:],
                  "split_target": split, "risk": risk, "confirmation": conf,
                  "start": r["waypoints"][0], "mid": r["waypoints"][1], "goal": r["waypoints"][-1],
                  "waypoints": r["waypoints"], "landmarks": lm})
(REPORTS / "h7_route_review_table.json").write_text(json.dumps(table, indent=2))
print("wrote overlay + table ->", REPORTS)
for t in table:
    print(f"  {t['route_id']:16s} {t['family']:20s} {t['split_target']:5s} {t['risk']:6s} "
          f"start{t['start']} mid{t['mid']} goal{t['goal']}")
