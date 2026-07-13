"""Build labelled hospital target-scene frames + contact sheets from selected
candidate renders. gnm_train PIL. STRICT CLAIM BOUNDARY: every frame and sheet is
stamped 'Target hospital-scene render - not original H6 training/evaluation data',
and each contact sheet states it is an illustrative static-camera progression, not
a recorded navigation trajectory. Route labels are ROUTE-TYPE ILLUSTRATIONS, not
the original H6 split data. No image synthesis - only decode + banner text over
the real Isaac hospital.usd renders.
"""
import json, datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BASE = Path("/home/favl/robotics/gnm-vlnverse-baseline/assets/experiments/"
            "hospital_h2_collection_20260709")
CAND = BASE / "hospital_render_candidates"
OUT = BASE / "hospital_render_exports"
OUT.mkdir(parents=True, exist_ok=True)
DESK = Path("/home/favl/Desktop/h6_hospital_render_exports")
DESK.mkdir(parents=True, exist_ok=True)

FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
ASSET = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
         "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
# stronger warning required on every visual
WARN = "Target hospital-scene render — not original H6 training/evaluation data."

ROUTES = [
    {"key": "uturn", "id": "hospital_render_uturn",
     "illus": "u-turn route-type illustration — target hospital scene",
     "frames": {"start": "r04", "mid": "r01", "goal": "r02"}},
    {"key": "chain", "id": "hospital_render_chain",
     "illus": "chain route-type illustration — repaired route pattern",
     "frames": {"start": "r05", "mid": "r03", "goal": "r07"}},
    {"key": "compound", "id": "hospital_render_compound",
     "illus": "compound-turn route-type illustration — validation-style route pattern",
     "frames": {"start": "r12", "mid": "r08", "goal": "r11"}},
    {"key": "heldout", "id": "hospital_render_unseen",
     "illus": "unseen chain/u-turn route-type illustration — fresh-held-out-style pattern",
     "frames": {"start": "r14", "mid": "r16", "goal": "r09"}},
]
CONTEXT = [
    {"name": "ctx2", "id": "hospital_context_reception"},
    {"name": "ctx1", "id": "hospital_context_corridor"},
]

fb = lambda n: ImageFont.truetype(FB, n)
fr = lambda n: ImageFont.truetype(FR, n)


def labelled(cand_name, headline, frame_name, extra_note=None,
             height_str="robot height 0.35 m"):
    """Return a labelled PIL image (banner over the real hospital render)."""
    img = Image.open(CAND / f"cand_{cand_name}.png").convert("RGB")
    W, H = img.size
    BH = 132
    canvas = Image.new("RGB", (W, H + BH), (255, 255, 255))
    canvas.paste(img, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, H, W, H + BH], fill=(17, 17, 17))
    y = H + 8
    d.text((14, y), headline, fill=(255, 255, 255), font=fb(21)); y += 30
    d.text((14, y), f"frame: {frame_name}   ·   front RGB camera · {height_str}",
           fill=(215, 215, 215), font=fr(16)); y += 23
    d.text((14, y), f"real Isaac Sim 5.1 hospital.usd · 1280x720 · {cand_name}",
           fill=(180, 180, 180), font=fr(15)); y += 22
    d.text((14, y), extra_note or WARN, fill=(255, 210, 120), font=fb(16))
    return canvas


def contact(route):
    fr_defs = [("start", route["frames"]["start"]), ("mid", route["frames"]["mid"]),
               ("goal", route["frames"]["goal"])]
    tiles = [(f, c, Image.open(CAND / f"cand_{c}.png").convert("RGB")) for f, c in fr_defs]
    TW, TH = 420, 236
    pad, hdr, cap, ftr = 14, 66, 26, 60
    W = 3 * TW + 4 * pad
    H = hdr + TH + cap + ftr + 2 * pad
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 10), route["illus"], fill=(0, 0, 0), font=fb(22))
    d.text((pad, 42), "start → mid → goal   ·   real Isaac Sim 5.1 hospital.usd",
           fill=(60, 60, 60), font=fr(16))
    for i, (fname, cand, im) in enumerate(tiles):
        x = pad + i * (TW + pad); y = hdr + pad
        sheet.paste(im.resize((TW, TH)), (x, y))
        d.rectangle([x, y, x + TW, y + TH], outline=(0, 0, 0), width=1)
        d.text((x + 4, y + TH + 4), f"{fname}  ({cand})", fill=(0, 0, 0), font=fb(16))
    fy = hdr + pad + TH + cap + 6
    d.text((pad, fy), WARN, fill=(150, 90, 0), font=fb(15))
    d.text((pad, fy + 20),
           "route-type visual illustration — not the original H6 split data; static-camera "
           "progression, not a recorded trajectory. H6 metrics were collected in the "
           "procedural --scene stage, not here.", fill=(90, 90, 90), font=fr(13))
    return sheet


manifest = {"asset_path": ASSET, "asset_is_hospital_usd": True,
            "isaac_sim_version": "5.1.0.0", "resolution": [1280, 720],
            "robot_camera_height_m": 0.35, "synthetic": False, "placeholder": False,
            "warning_on_every_visual": WARN,
            "claim_boundary": ("These are TARGET-SCENE re-renders of the real Isaac hospital.usd "
                               "for the corrected deck and the next hospital run. Route labels are "
                               "route-TYPE illustrations, not the original H6 split data. They are "
                               "NOT the H6 training/evaluation frames (H6 ran in the procedural "
                               "--scene stage). They are static-camera views, not recorded trajectories."),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "routes": [], "context_renders": []}

for r in ROUTES:
    frames_out = {}
    for fname, cand in [("start", r["frames"]["start"]), ("mid", r["frames"]["mid"]),
                        ("goal", r["frames"]["goal"])]:
        im = labelled(cand, r["illus"], fname)
        fn = f"{r['id']}_{fname}.png"
        im.save(OUT / fn); im.save(DESK / fn)
        frames_out[fname] = {"file": fn, "candidate": cand}
    cs = contact(r)
    csn = f"{r['id']}_contact_sheet.png"
    cs.save(OUT / csn); cs.save(DESK / csn)
    manifest["routes"].append({"id": r["id"], "illustration_label": r["illus"],
                               "frames": frames_out, "contact_sheet": csn})
    print(f"built {r['id']}: 3 frames + {csn}")

for c in CONTEXT:
    note = ("hospital scene context render — not used as training/evaluation image "
            "(camera raised above robot height for overview)")
    headline = f"{c['id']}  ·  context overview"
    im = labelled(c["name"], headline, "context", extra_note=note,
                  height_str="raised camera ~1.4-1.5 m (above robot height)")
    fn = f"{c['id']}.png"
    im.save(OUT / fn); im.save(DESK / fn)
    manifest["context_renders"].append({"id": c["id"], "file": fn, "candidate": c["name"], "note": note})
    print(f"built {c['id']} (context)")

(OUT / "hospital_render_manifest.json").write_text(json.dumps(manifest, indent=2))
(DESK / "hospital_render_manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"\nDONE -> {OUT}\n     -> {DESK}")
