"""Export H7 RAISED-MOUNT front-camera contact sheets from the ACTUAL recorded
/camera/image_raw stream in each h7r_ episode's rosbag (NOT re-renders). start /
current / goal frames + a labelled contact sheet per episode. Same builder as the
original H7 frames tool, retargeted to the raised-mount pilot (camera +0.12 m,
level horizon) and its own collection dir. system python3 (rosbags + numpy + PIL).
"""
import sys, json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from rosbags.highlevel import AnyReader
from rosbags.typesys import Stores, get_typestore

TS = get_typestore(Stores.ROS2_HUMBLE)

REPO = Path("/home/favl/robotics/gnm-vlnverse-baseline")
TRAJ = REPO / "assets/experiments/trajectories"
BAGS = REPO / "assets/experiments/rosbags"
OUT = REPO / "assets/experiments/hospital_h7_raise_collection/exports"
OUT.mkdir(parents=True, exist_ok=True)
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
fb = lambda n: ImageFont.truetype(FB, n)
fr = lambda n: ImageFont.truetype(FR, n)

PREFIX = "h7r_"
_BASE_SPLIT = {"reception_01": "train", "corridor_01": "train", "turn_01": "train",
               "waiting_01": "train", "reception_02": "val", "corridor_02": "val",
               "turn_02": "test", "waiting_02": "test"}
SPLIT = {PREFIX + k: v for k, v in _BASE_SPLIT.items()}
EPS = list(SPLIT)
TOPIC = "/camera/image_raw"


def decode(msg):
    h, w, enc = msg.height, msg.width, (msg.encoding or "rgb8").lower()
    ch = {"rgb8": 3, "bgr8": 3, "rgba8": 4, "bgra8": 4, "mono8": 1}.get(enc, 3)
    a = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    a = a[:h * (msg.step or w * ch)].reshape(h, -1)[:, :w * ch].reshape(h, w, ch)
    if enc.startswith("bgr"):
        a = a[..., ::-1][..., :3]
    return np.ascontiguousarray(a[..., :3])


def three_frames(bagdir):
    with AnyReader([bagdir], default_typestore=TS) as r:
        conns = [c for c in r.connections if c.topic == TOPIC]
        n = sum(1 for _ in r.messages(connections=conns))
        if n == 0:
            return None, 0
        targets = {0: "start", n // 2: "current", n - 1: "goal"}
        got = {}
        with AnyReader([bagdir], default_typestore=TS) as r2:
            conns2 = [c for c in r2.connections if c.topic == TOPIC]
            for i, (conn, ts, raw) in enumerate(r2.messages(connections=conns2)):
                if i in targets:
                    got[targets[i]] = decode(r2.deserialize(raw, conn.msgtype))
                if i >= n - 1:
                    break
        return got, n


def label(img_arr, ep, split, route_type, frame, eid):
    im = Image.fromarray(img_arr, "RGB")
    W, H = im.size
    BH = 96
    c = Image.new("RGB", (W, H + BH), (255, 255, 255)); c.paste(im, (0, 0))
    d = ImageDraw.Draw(c); d.rectangle([0, H, W, H + BH], fill=(16, 40, 20))
    d.text((10, H + 6), f"{ep}  ·  {route_type}  ·  {frame}", fill=(255, 255, 255), font=fb(17))
    d.text((10, H + 30), f"split={split} · RECORDED /camera/image_raw frame · {W}x{H}",
           fill=(200, 230, 205), font=fr(14))
    d.text((10, H + 52), f"real Isaac hospital.usd · scene-gate PASS · camera +0.12 m (level) · {eid}",
           fill=(150, 200, 160), font=fr(13))
    d.text((10, H + 72), "H7 raised-mount recorded frame — actual front-RGB camera stream "
           "(not a re-render).", fill=(150, 220, 255), font=fb(13))
    return c


def contact_sheet(frames, ep, split, route_type):
    order = [f for f in ("start", "current", "goal") if f in frames]
    tiles = [(f, Image.fromarray(frames[f], "RGB")) for f in order]
    TW, TH = 426, 320
    pad, hdr, cap, ftr = 12, 58, 24, 46
    W = len(tiles) * TW + (len(tiles) + 1) * pad
    H = hdr + TH + cap + ftr + 2 * pad
    s = Image.new("RGB", (W, H), (255, 255, 255)); d = ImageDraw.Draw(s)
    d.text((pad, 8), f"{ep}   ·   {route_type}   ·   split={split}", fill=(0, 0, 0), font=fb(21))
    d.text((pad, 34), "RECORDED front-RGB /camera/image_raw — start → current → goal "
           "(real hospital.usd, camera +0.12 m level, scene-gate PASS)", fill=(30, 90, 40), font=fr(14))
    for i, (fn, im) in enumerate(tiles):
        x = pad + i * (TW + pad); y = hdr + pad
        s.paste(im.resize((TW, TH)), (x, y))
        d.rectangle([x, y, x + TW, y + TH], outline=(0, 0, 0), width=1)
        d.text((x + 4, y + TH + 4), fn, fill=(0, 0, 0), font=fb(16))
    fy = hdr + pad + TH + cap + 4
    d.text((pad, fy), "H7 raised-mount recorded frames — actual camera stream, not a re-render. "
           "Distinct from procedural-stage H6.", fill=(30, 90, 40), font=fb(13))
    return s


index = []
only = sys.argv[1] if len(sys.argv) > 1 else None
for ep in EPS:
    if only and ep != only:
        continue
    dirs = sorted(TRAJ.glob(f"{ep}_20*"))
    if not dirs:
        print(f"{ep}: NO trajectory dir"); continue
    eid = dirs[-1].name
    meta = json.loads((dirs[-1] / "episode_metadata.json").read_text())
    route_type = meta.get("route_id", ep)
    bagdir = BAGS / eid
    if not bagdir.exists():
        print(f"{ep}: NO bag {bagdir}"); continue
    frames, n = three_frames(bagdir)
    if not frames:
        print(f"{ep}: 0 image_raw messages"); continue
    split = SPLIT[ep]
    saved = {}
    for fn, arr in frames.items():
        lab = label(arr, ep, split, route_type, fn, eid)
        p = OUT / f"{ep}_{fn}.png"; lab.save(p); saved[fn] = p.name
    cs = contact_sheet(frames, ep, split, route_type)
    csn = f"{ep}_contact_sheet.png"; cs.save(OUT / csn)
    index.append({"episode": ep, "episode_id": eid, "split": split, "route_type": route_type,
                  "image_raw_msgs": n, "frames": saved, "contact_sheet": csn,
                  "source": "recorded /camera/image_raw (not a re-render)"})
    print(f"{ep}: {n} frames -> start/current/goal + {csn}")

(OUT / "h7r_contact_sheets_index.json").write_text(json.dumps(index, indent=2))
print(f"\nwrote {len(index)} contact sheets -> {OUT}")
