"""Convert the hospital candidate .npy arrays -> PNGs + a single labelled montage
grid for inspection. Run with the gnm_train env PIL (the isaac-env PIL crashes on
PNG save). No image synthesis — only decode + downscale + text labels."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path("/home/favl/robotics/gnm-vlnverse-baseline/assets/experiments/"
           "hospital_h2_collection_20260709/hospital_render_candidates")
FONT_P = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
poses = json.loads((OUT / "candidate_poses.json").read_text())
by_name = {c["name"]: c for c in poses["candidates"]}

npys = sorted(OUT.glob("cand_*.npy"))
thumbs = []
for p in npys:
    name = p.stem.replace("cand_", "")
    arr = np.load(p)
    img = Image.fromarray(arr, "RGB")
    img.save(OUT / f"cand_{name}.png")            # full-res PNG for later selection
    c = by_name.get(name, {})
    eye = c.get("eye"); tgt = c.get("target"); luma = c.get("mean_luma")
    thumbs.append((name, img.copy(), eye, tgt, luma))

# montage grid
COLS = 4
TW, TH = 320, 180
pad, labh = 8, 34
rows = (len(thumbs) + COLS - 1) // COLS
MW = COLS * TW + (COLS + 1) * pad
MH = rows * (TH + labh) + (rows + 1) * pad
montage = Image.new("RGB", (MW, MH), (245, 245, 245))
draw = ImageDraw.Draw(montage)
try:
    font = ImageFont.truetype(FONT_P, 15)
    fs = ImageFont.truetype(FONT_P, 12)
except Exception:
    font = fs = ImageFont.load_default()

for i, (name, img, eye, tgt, luma) in enumerate(thumbs):
    r, c = divmod(i, COLS)
    x = pad + c * (TW + pad)
    y = pad + r * (TH + labh + pad)
    montage.paste(img.resize((TW, TH)), (x, y))
    draw.text((x + 2, y + TH + 2), f"{name}  luma={luma}", fill=(0, 0, 0), font=font)
    if eye and tgt:
        draw.text((x + 2, y + TH + 18),
                  f"eye({eye[0]:.1f},{eye[1]:.1f},{eye[2]:.2f})->tgt({tgt[0]:.1f},{tgt[1]:.1f})",
                  fill=(60, 60, 60), font=fs)

montage.save(OUT / "candidates_montage.png")
print(f"wrote {len(thumbs)} PNGs + candidates_montage.png ({MW}x{MH}) -> {OUT}")
