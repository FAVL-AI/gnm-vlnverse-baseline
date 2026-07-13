#!/usr/bin/env python3
"""Export REAL H6 front-camera PNG evidence (start / mid / final + contact sheet)
with visible provenance labels, for the professor deck.

Source = the actual converted front-RGB frames (Yahboom front camera, 640x480,
converted from the recorded rosbags) under datasets/isaac_hospital_h6/. NO
synthetic images, NO placeholders. If a source frame is missing the script stops
and reports the exact path.

Labels are drawn from the committed recording ledger (episode_id, route_type,
split, route_completed, contacts, max_contact_streak) — not invented.
"""
import json, shutil, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
COL = REPO / "assets/experiments/hospital_h2_collection_20260709"
OUT = COL / "h6_front_camera_exports"
DESKTOP = Path("/home/favl/Desktop/h6_front_camera_exports")
LEDGER = json.loads((COL / "h6_recording_ledger.json").read_text())
LED = {r["episode_label"]: r for r in LEDGER}

FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# episode_label -> (dataset subdir, timestamped dir, route_type label, split, use)
EPISODES = [
    ("h6rec_h6_uturn_01_a", "train", "h6rec_h6_uturn_01_a_20260712_195504",
     "uturn", "train", "train"),
    ("h6rec_h6_chain_01_a", "train", "h6rec_h6_chain_01_a_20260712_202208",
     "chain (repaired in-bounds)", "train", "train"),
    ("h6rec_h6_compound_01_a", "val", "h6rec_h6_compound_01_a_20260712_220936",
     "compound_turn", "validation", "validation"),
    ("h6rec_h6_chain_02_a", "test_h6hard", "h6rec_h6_chain_02_a_20260712_230437",
     "chain", "fresh held-out", "held-out"),
]
CAM = "front RGB camera, 640x480"


def font(bold, sz):
    return ImageFont.truetype(FONT_B if bold else FONT_R, sz)


def frames(ep_dir):
    js = sorted(ep_dir.glob("*.jpg"), key=lambda p: int(p.stem))
    if not js:
        print(f"STOP: no real frames found under {ep_dir}", file=sys.stderr)
        sys.exit(3)
    n = len(js)
    return js, {"start": (0, js[0]), "mid": (n // 2, js[n // 2]),
                "final": (n - 1, js[-1])}, n


def meta_lines(label, rtype, split, use, n, idx, role):
    r = LED[label]
    return [
        f"episode_id: {r['episode_dir'].split('/')[-1]}",
        f"route_type: {rtype}   |   split: {split}   |   training use: {use}",
        f"route_completed={r.get('route_completed')}   |   contacts="
        f"{r.get('total_collision_count')}   |   max_contact_streak={r.get('max_contact_streak')}",
        f"{CAM}   |   frame {idx}/{n-1} ({role})   |   scripted-expert, converted from rosbag",
    ]


def labelled(src_jpg, label, rtype, split, use, n, idx, role, dst):
    im = Image.open(src_jpg).convert("RGB")
    W, H = im.size  # 640x480
    banner = 132
    canvas = Image.new("RGB", (W, H + banner), (18, 18, 22))
    canvas.paste(im, (0, 0))
    d = ImageDraw.Draw(canvas)
    # role tag (top-left, on image)
    tag = f"{role.upper()}"
    d.rectangle([0, 0, 8 + d.textlength(tag, font=font(True, 22)), 30], fill=(0, 0, 0))
    d.text((6, 3), tag, font=font(True, 22), fill=(255, 214, 10))
    # banner
    y = H + 8
    d.text((10, y), f"{label}", font=font(True, 19), fill=(255, 255, 255)); y += 26
    for ln in meta_lines(label, rtype, split, use, n, idx, role):
        d.text((10, y), ln, font=font(False, 14), fill=(210, 210, 214)); y += 22
    canvas.save(dst)


def contact_sheet(label, rtype, split, use, roles, n, dst):
    tw, th = 384, 288
    pad, gap, header, rolebar, footer = 20, 14, 58, 26, 78
    W = pad * 2 + tw * 3 + gap * 2
    H = header + th + rolebar + footer
    cv = Image.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(cv)
    d.text((pad, 12), f"{label}", font=font(True, 22), fill=(255, 255, 255))
    d.text((pad, 38), f"{rtype}   |   split: {split}   |   training use: {use}",
           font=font(False, 15), fill=(255, 214, 10))
    x = pad
    for role in ("start", "mid", "final"):
        idx, jpg = roles[role]
        thumb = Image.open(jpg).convert("RGB").resize((tw, th))
        cv.paste(thumb, (x, header))
        rl = f"{role.upper()}  ·  frame {idx}/{n-1}"
        d.text((x + 4, header + th + 4), rl, font=font(True, 15), fill=(230, 230, 234))
        x += tw + gap
    r = LED[label]
    fy = header + th + rolebar + 6
    d.text((pad, fy),
           f"route_completed={r.get('route_completed')}   |   contacts={r.get('total_collision_count')}"
           f"   |   max_contact_streak={r.get('max_contact_streak')}",
           font=font(False, 14), fill=(210, 210, 214))
    d.text((pad, fy + 22), f"{CAM}   |   scripted-expert demonstration, converted from recorded rosbag "
           "(no synthetic frames)", font=font(False, 14), fill=(160, 160, 166))
    cv.save(dst)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest, episodes_meta = [], {}
    for label, sub, dirname, rtype, split, use in EPISODES:
        ep_dir = REPO / "datasets/isaac_hospital_h6" / sub / dirname
        if not ep_dir.is_dir():
            print(f"STOP: missing episode dir {ep_dir}", file=sys.stderr); sys.exit(3)
        js, roles, n = frames(ep_dir)
        r = LED[label]
        episodes_meta[label] = {
            "episode_id": r["episode_dir"].split("/")[-1],
            "route_type": rtype, "split": split, "training_use": use,
            "route_completed": r.get("route_completed"),
            "contacts": r.get("total_collision_count"),
            "max_contact_streak": r.get("max_contact_streak"),
            "camera": CAM + " (Yahboom front, Isaac Sim)", "n_frames": n,
        }
        for role in ("start", "mid", "final"):
            idx, jpg = roles[role]
            dst = OUT / f"{label}_{role}.png"
            labelled(jpg, label, rtype, split, use, n, idx, role, dst)
            manifest.append({"file": dst.name, "episode_label": label,
                             "episode_id": r["episode_dir"].split("/")[-1],
                             "frame_role": role,
                             "source_frame": jpg.relative_to(REPO).as_posix(),
                             "frame_index": idx, "n_frames": n, "route_type": rtype,
                             "split": split, "training_use": use, "camera": CAM,
                             "route_completed": r.get("route_completed"),
                             "contacts": r.get("total_collision_count"),
                             "max_contact_streak": r.get("max_contact_streak"),
                             "synthetic": False})
        cs = OUT / f"{label}_contact_sheet.png"
        contact_sheet(label, rtype, split, use, roles, n, cs)
        manifest.append({"file": cs.name, "episode_label": label,
                         "episode_id": r["episode_dir"].split("/")[-1],
                         "frame_role": "contact_sheet",
                         "frames": {rr: roles[rr][0] for rr in roles}, "n_frames": n,
                         "route_type": rtype, "split": split, "training_use": use,
                         "camera": CAM, "route_completed": r.get("route_completed"),
                         "contacts": r.get("total_collision_count"),
                         "max_contact_streak": r.get("max_contact_streak"),
                         "synthetic": False})
        print(f"[h6-frames] {label}: start/mid/final + contact sheet "
              f"(n={n}, frames {roles['start'][0]}/{roles['mid'][0]}/{roles['final'][0]})")
    (OUT / "h6_front_camera_exports_manifest.json").write_text(json.dumps(
        {"source": "datasets/isaac_hospital_h6 converted front-RGB frames (real, 640x480)",
         "synthetic": False,
         "fields_recorded": ["episode_id", "route_type", "split", "frame_role",
                             "route_completed", "contacts", "max_contact_streak",
                             "camera", "training_use"],
         "episodes": episodes_meta, "exports": manifest}, indent=2))
    # copy to Desktop for easy access
    DESKTOP.mkdir(parents=True, exist_ok=True)
    for p in OUT.glob("*.png"):
        shutil.copy2(p, DESKTOP / p.name)
    shutil.copy2(OUT / "h6_front_camera_exports_manifest.json",
                 DESKTOP / "h6_front_camera_exports_manifest.json")
    print(f"[h6-frames] {len(list(OUT.glob('*.png')))} PNGs -> {OUT.relative_to(REPO)}")
    print(f"[h6-frames] copied to {DESKTOP}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
