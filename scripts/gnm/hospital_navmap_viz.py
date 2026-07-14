"""Visualize the hospital occupancy map: inflate by robot radius, keep only the
lobby-connected navigable region, and render a metre-gridded PNG so driving routes
can be read off measured free floor. gnm_train env (numpy/PIL; scipy optional).
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

NAV = Path("/home/favl/robotics/gnm-vlnverse-baseline/assets/experiments/"
           "hospital_h7_collection/navmap")
meta = json.loads((NAV / "navmap_meta.json").read_text())
occ = np.load(NAV / "occupancy_raw.npy")
X0, Y0, RES = meta["x_min"], meta["y_min"], meta["res_m"]
NY, NX = occ.shape
ROBOT_R = 0.28                                   # radius + margin (m)
r_cells = int(round(ROBOT_R / RES))


def dilate(mask, r):
    try:
        from scipy.ndimage import binary_dilation, iterate_structure, generate_binary_structure
        st = iterate_structure(generate_binary_structure(2, 1), r)
        return binary_dilation(mask, structure=st)
    except Exception:
        out = mask.copy()
        for _ in range(r):
            s = out.copy()
            s[1:, :] |= out[:-1, :]; s[:-1, :] |= out[1:, :]
            s[:, 1:] |= out[:, :-1]; s[:, :-1] |= out[:, 1:]
            out = s
        return out


infl = dilate(occ.astype(bool), r_cells)
free = ~infl


def cell(x, y):
    return int((x - X0) / RES), int((y - Y0) / RES)


# lobby-connected component via BFS from origin (0,0)
def connected_from(x, y):
    ix, iy = cell(x, y)
    comp = np.zeros_like(free, dtype=bool)
    if not (0 <= ix < NX and 0 <= iy < NY and free[iy, ix]):
        # snap to nearest free cell
        fy, fx = np.where(free)
        if len(fx) == 0:
            return comp
        d = (fx - ix) ** 2 + (fy - iy) ** 2
        k = int(np.argmin(d)); ix, iy = fx[k], fy[k]
    stack = [(iy, ix)]; comp[iy, ix] = True
    while stack:
        cy, cx = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = cy + dy, cx + dx
            if 0 <= nx < NX and 0 <= ny < NY and free[ny, nx] and not comp[ny, nx]:
                comp[ny, nx] = True; stack.append((ny, nx))
    return comp


nav = connected_from(0.0, 0.0)
np.save(NAV / "navigable.npy", nav)

# --- render PNG (upscale, y-up) ---
SC = 3
img = np.full((NY, NX, 3), 255, np.uint8)
img[occ.astype(bool)] = (35, 35, 35)                       # hard geometry
img[infl & ~occ.astype(bool)] = (150, 150, 150)            # inflation margin
img[nav] = (235, 245, 255)                                 # navigable (lobby-connected)
img[free & ~nav] = (205, 230, 205)                         # free but disconnected
im = Image.fromarray(img[::-1], "RGB").resize((NX * SC, NY * SC), Image.NEAREST)
d = ImageDraw.Draw(im)
try:
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    fb = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
except Exception:
    f = fb = ImageFont.load_default()


def px(x, y):                                              # world -> image px (y-up)
    ix, iy = (x - X0) / RES, (y - Y0) / RES
    return ix * SC, (NY - iy) * SC


for m in range(int(meta["x_min"]), int(meta["x_max"]) + 1):
    x, _ = px(m, 0); d.line([(x, 0), (x, NY * SC)], fill=(220, 220, 220), width=1)
    d.text((x + 2, 4), f"x={m}", fill=(120, 120, 120), font=f)
for m in range(int(meta["y_min"]), int(meta["y_max"]) + 1):
    _, y = px(0, m); d.line([(0, y), (NX * SC, y)], fill=(220, 220, 220), width=1)
    d.text((4, y + 2), f"y={m}", fill=(120, 120, 120), font=f)
ox, oy = px(0, 0)
d.ellipse([ox - 5, oy - 5, ox + 5, oy + 5], outline=(200, 0, 0), width=2)
d.text((ox + 6, oy - 16), "origin", fill=(200, 0, 0), font=fb)
im.save(NAV / "navmap_overlay.png")

ys, xs = np.where(nav)
if len(xs):
    bx = (xs.min() * RES + X0, xs.max() * RES + X0)
    by = (ys.min() * RES + Y0, ys.max() * RES + Y0)
else:
    bx = by = (0, 0)
print(f"inflated by {r_cells} cells ({ROBOT_R} m). navigable cells={int(nav.sum())} "
      f"area={nav.sum()*RES*RES:.1f} m^2  bbox x{bx} y{by}")
print(f"-> {NAV/'navmap_overlay.png'}")
