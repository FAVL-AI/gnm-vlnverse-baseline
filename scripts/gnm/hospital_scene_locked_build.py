"""Build labelled PNGs + contact sheets for the gated hospital pilot pack from the
npy captured by hospital_front_camera_demo.py. gnm_train PIL. Every frame/sheet is
stamped 'Target hospital-scene render — not original H6 training/evaluation data'
and carries route label, split/use label, camera pose, robot pose, and asset path.
No image synthesis — decode + banner text over the real hospital.usd renders.
"""
import json
import datetime
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = Path("/home/favl/robotics/gnm-vlnverse-baseline/assets/experiments/"
            "hospital_h2_collection_20260709/hospital_scene_locked_exports")
DESK = Path("/home/favl/Desktop/hospital_scene_locked_exports")
DESK.mkdir(parents=True, exist_ok=True)
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
WARN = "Target hospital-scene render — not original H6 training/evaluation data."

pack = json.loads((BASE / "pilot_capture_poses.json").read_text())
ident = json.loads((BASE / "scene_identity_manifest.json").read_text())
ASSET = pack["asset_path"]
fb = lambda n: ImageFont.truetype(FB, n)
fr = lambda n: ImageFont.truetype(FR, n)


def load(af):
    return Image.fromarray(np.load(BASE / af), "RGB")


def labelled(img, route_label, use, frame_name, cpose, rpose):
    W, H = img.size
    BH = 150
    c = Image.new("RGB", (W, H + BH), (255, 255, 255)); c.paste(img, (0, 0))
    d = ImageDraw.Draw(c); d.rectangle([0, H, W, H + BH], fill=(17, 17, 17))
    y = H + 8
    d.text((14, y), f"{route_label}   ·   {frame_name}", fill=(255, 255, 255), font=fb(21)); y += 29
    d.text((14, y), f"{use}   ·   front RGB camera · robot height 0.35 m · 1280x720",
           fill=(215, 215, 215), font=fr(15)); y += 22
    d.text((14, y), f"camera (x={cpose['x']:.2f}, y={cpose['y']:.2f}, z={cpose['z']:.2f}, "
                    f"yaw={cpose['yaw_deg']}°)   robot (x={rpose['x']:.2f}, y={rpose['y']:.2f}, "
                    f"yaw={rpose['yaw_deg']}°)", fill=(180, 180, 180), font=fr(14)); y += 21
    d.text((14, y), "real Isaac Sim 5.1 hospital.usd", fill=(150, 150, 150), font=fr(14)); y += 20
    d.text((14, y), WARN, fill=(255, 210, 120), font=fb(15))
    return c


def contact(route_key, rdef):
    order = [f for f in ("start", "mid", "goal") if f in rdef["frames"]]
    tiles = [(f, load(rdef["frames"][f]["array_file"])) for f in order]
    TW, TH = 420, 236
    pad, hdr, cap, ftr = 14, 70, 26, 58
    W = len(tiles) * TW + (len(tiles) + 1) * pad
    Hs = hdr + TH + cap + ftr + 2 * pad
    sheet = Image.new("RGB", (W, Hs), (255, 255, 255)); d = ImageDraw.Draw(sheet)
    d.text((pad, 8), f"{rdef['label']}   ({route_key})", fill=(0, 0, 0), font=fb(23))
    d.text((pad, 40), f"{rdef['use']}   ·   start → mid → goal   ·   real Isaac Sim 5.1 hospital.usd",
           fill=(60, 60, 60), font=fr(15))
    for i, (fname, im) in enumerate(tiles):
        x = pad + i * (TW + pad); y = hdr + pad
        sheet.paste(im.resize((TW, TH)), (x, y))
        d.rectangle([x, y, x + TW, y + TH], outline=(0, 0, 0), width=1)
        d.text((x + 4, y + TH + 4), fname, fill=(0, 0, 0), font=fb(16))
    fy = hdr + pad + TH + cap + 6
    d.text((pad, fy), WARN, fill=(150, 90, 0), font=fb(15))
    d.text((pad, fy + 20), "gated pilot capture from the locked hospital scene "
           "(scene-identity gate PASS). Static-camera views, not a recorded trajectory.",
           fill=(90, 90, 90), font=fr(13))
    return sheet


out_manifest = {"asset_path": ASSET, "asset_is_hospital_usd": True,
                "isaac_sim_version": "5.1.0.0", "resolution": pack["resolution"],
                "robot_camera_height_m": pack["robot_camera_height_m"],
                "synthetic": False, "placeholder": False,
                "scene_identity_pass": ident["scene_identity_pass"],
                "scene_identity_checks": ident["checks"],
                "warning_on_every_visual": WARN,
                "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                "routes": []}

for rkey, rdef in pack["routes"].items():
    fout = {}
    for fname in [f for f in ("start", "mid", "goal") if f in rdef["frames"]]:
        fr_meta = rdef["frames"][fname]
        im = labelled(load(fr_meta["array_file"]), rdef["label"], rdef["use"], fname,
                      fr_meta["camera_pose"], fr_meta["robot_pose"])
        fn = f"{rkey}_{fname}.png"
        im.save(BASE / fn); im.save(DESK / fn)
        fout[fname] = {"file": fn, "camera_pose": fr_meta["camera_pose"],
                       "robot_pose": fr_meta["robot_pose"], "mean_luma": fr_meta["mean_luma"]}
    cs = contact(rkey, rdef); csn = f"{rkey}_contact_sheet.png"
    cs.save(BASE / csn); cs.save(DESK / csn)
    out_manifest["routes"].append({"route": rkey, "label": rdef["label"], "use": rdef["use"],
                                   "frames": fout, "contact_sheet": csn})
    print(f"built {rkey}: {len(fout)} frames + {csn}")

(BASE / "hospital_scene_locked_pack_manifest.json").write_text(json.dumps(out_manifest, indent=2))
(DESK / "hospital_scene_locked_pack_manifest.json").write_text(json.dumps(out_manifest, indent=2))
print(f"\nDONE -> {BASE}\n     -> {DESK}")
