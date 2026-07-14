"""Build the H7 camera-view review deliverables from the variant renders:
per-option contact sheets, a 3-option comparison grid, and per-variant metrics.
system python3 (numpy/PIL). No training.
"""
import json, csv
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

COLL = Path("assets/experiments/hospital_h7_collection")
D = COLL / "camera_review_npy"
OUT = COLL / "camera_option_contact_sheets"; OUT.mkdir(parents=True, exist_ok=True)
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
bold = lambda n: ImageFont.truetype(FB, n)
reg = lambda n: ImageFont.truetype(FR, n)
man = json.load(open(D / "camera_review_manifest.json"))

# report label -> rendered variant key (data showed 105=up, 75=down)
OPTIONS = {"current": ("current", "level (90,0,-90) — as recorded in H7 pilot"),
           "pitch_up": ("pitch_dn", "upward pitch ~15° (105,0,-90)"),
           "raise_mount": ("raise_z", "raised mount +0.12 m, level")}
ROUTES = ["reception_01", "turn_01"]
FRAMES = ["start", "mid", "goal"]


def load(route, frame, vkey):
    p = D / f"{route}__{frame}__{vkey}.npy"
    return np.load(p) if p.exists() else None


def black_pct(a):
    lum = a.astype(float).mean(axis=2)
    return round(float((lum < 5).mean() * 100), 1)


# per-variant metrics
metrics = []
for label, (vkey, desc) in OPTIONS.items():
    vals = []
    for rt in ROUTES:
        for fr in FRAMES:
            a = load(rt, fr, vkey)
            if a is not None:
                vals.append(black_pct(a))
    metrics.append({"option": label, "config": desc, "mean_black_pct": round(np.mean(vals), 1),
                    "mean_usable_pct": round(100 - np.mean(vals), 1)})
with open(COLL / "reports/h7_camera_view_metrics.csv", "a", newline="") as f:
    w = csv.writer(f); w.writerow([]); w.writerow(["--- camera OPTION comparison (robot+hospital renders) ---"])
    w.writerow(["option", "config", "mean_black_pct", "mean_usable_pct"])
    for m in metrics:
        w.writerow([m["option"], m["config"], m["mean_black_pct"], m["mean_usable_pct"]])


def frame_img(a, tag, sub):
    im = Image.fromarray(a, "RGB"); W, Hh = im.size
    c = Image.new("RGB", (W, Hh + 42), (255, 255, 255)); c.paste(im, (0, 0))
    d = ImageDraw.Draw(c); d.rectangle([0, Hh, W, Hh + 42], fill=(20, 20, 30))
    d.text((6, Hh + 3), tag, fill=(255, 255, 255), font=bold(15))
    d.text((6, Hh + 22), sub, fill=(180, 200, 220), font=reg(12))
    return c


# per-option contact sheet (2 routes x 3 frames)
for label, (vkey, desc) in OPTIONS.items():
    tiles = []
    for rt in ROUTES:
        for fr in FRAMES:
            a = load(rt, fr, vkey)
            if a is not None:
                tiles.append(frame_img(a, f"{rt} · {fr}", f"black {black_pct(a)}%"))
    if not tiles:
        continue
    TW, TH = tiles[0].size
    cols, pad, hdr = 3, 10, 54
    rows = (len(tiles) + cols - 1) // cols
    W = cols * TW + (cols + 1) * pad; Hs = hdr + rows * TH + (rows + 1) * pad
    s = Image.new("RGB", (W, Hs), (255, 255, 255)); d = ImageDraw.Draw(s)
    mb = next(m["mean_black_pct"] for m in metrics if m["option"] == label)
    d.text((pad, 8), f"H7 camera option: {label}   ({desc})", fill=(0, 0, 0), font=bold(20))
    d.text((pad, 32), f"real hospital.usd + robot · mean black {mb}% · recorded-equivalent front RGB",
           fill=(40, 90, 40), font=reg(13))
    for i, t in enumerate(tiles):
        r, cc = divmod(i, cols)
        s.paste(t, (pad + cc * (TW + pad), hdr + pad + r * (TH + pad)))
    s.save(OUT / f"h7_camera_{label}_contact_sheet.png")

# 3-option comparison grid: rows=options, cols=4 sample poses
SAMPLES = [("reception_01", "start"), ("reception_01", "goal"), ("turn_01", "start"), ("turn_01", "goal")]
cellW, cellH = 320, 240
pad, hdr, rowlab = 8, 48, 150
gW = rowlab + len(SAMPLES) * cellW + (len(SAMPLES) + 1) * pad
gH = hdr + len(OPTIONS) * cellH + (len(OPTIONS) + 1) * pad
g = Image.new("RGB", (gW, gH), (255, 255, 255)); d = ImageDraw.Draw(g)
d.text((pad, 8), "H7 front-camera options — current vs pitch-up vs raised mount "
       "(real hospital.usd + robot)", fill=(0, 0, 0), font=bold(19))
for ci, (rt, fr) in enumerate(SAMPLES):
    x = rowlab + pad + ci * (cellW + pad)
    d.text((x + 4, hdr - 16), f"{rt} · {fr}", fill=(0, 0, 0), font=bold(13))
for ri, (label, (vkey, desc)) in enumerate(OPTIONS.items()):
    y = hdr + pad + ri * (cellH + pad)
    mb = next(m["mean_black_pct"] for m in metrics if m["option"] == label)
    d.text((6, y + cellH // 2 - 14), f"{label}\nblack {mb}%", fill=(0, 0, 0), font=bold(14))
    for ci, (rt, fr) in enumerate(SAMPLES):
        a = load(rt, fr, vkey)
        x = rowlab + pad + ci * (cellW + pad)
        if a is not None:
            g.paste(Image.fromarray(a, "RGB").resize((cellW, cellH)), (x, y))
            d.rectangle([x, y, x + cellW, y + cellH], outline=(0, 0, 0))
g.save(OUT / "h7_camera_options_comparison.png")
print("metrics:", metrics)
print("wrote option sheets + comparison ->", OUT)
