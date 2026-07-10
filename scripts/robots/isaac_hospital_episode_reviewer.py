"""Isaac hospital episode reviewer — visual replay through the robot's eye.

Hospital episode review replays Isaac Sim simulation episodes through
the Yahboom front-facing RGB camera convention. It is visual review
evidence for internal simulation runs, not real-robot evidence.

Main evidence view: the Yahboom front RGB camera at the recorded poses.
A top-down debug map (trajectory trail, start/goal/contact markers,
red/amber/green zones) is rendered ONLY as a secondary overlay image.

CLI (isaac env, repo root):
    --list                          list reviewable episodes
    --episode <id> --replay         re-render front-camera frames along
                                    the recorded trajectory + export strip
    --episode <id> --export-strip   strip + manifest only (subset of replay)
    --episode <id> --live --checkpoint <ckpt>
                                    delegate a fresh live run to the
                                    episode runner (same safety envelope)
"""

import hashlib
import json
import pickle
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATASET = REPO / "datasets/isaac_hospital_imagenav_v0/unassigned"
TRAJ = REPO / "assets/experiments/trajectories"
HOSPITAL = ("https://omniverse-content-production.s3-us-west-2.amazonaws.com"
            "/Assets/Isaac/5.1/Isaac/Environments/Hospital/hospital.usd")
CLAIM = ("Hospital episode review replays Isaac Sim simulation episodes "
         "through the Yahboom front-facing RGB camera convention. It is "
         "visual review evidence for internal simulation runs, not "
         "real-robot evidence.")


def list_episodes():
    eps = []
    if DATASET.exists():
        for d in sorted(DATASET.iterdir()):
            m = d / "metadata.json"
            if m.exists():
                meta = json.loads(m.read_text())
                eps.append({"episode_id": d.name,
                            "goal_id": meta.get("goal_id"),
                            "n_frames": meta.get("n_frames"),
                            "source": "dataset"})
    return eps


def find_episode(ep_id):
    d = DATASET / ep_id
    if not (d / "metadata.json").exists():
        raise SystemExit(f"episode not found in dataset: {ep_id}")
    meta = json.loads((d / "metadata.json").read_text())
    src = REPO / meta["source_trajectory"] if meta.get("source_trajectory") \
        else None
    src_meta = json.loads((src / "episode_metadata.json").read_text()) \
        if src and (src / "episode_metadata.json").exists() else {}
    return d, meta, src_meta


def replay(ep_id, out_root, with_video=False):
    d, meta, src_meta = find_episode(ep_id)
    t = pickle.loads((d / "traj_data.pkl").read_bytes())
    pos, yaw = t["position"], t["yaw"]

    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True})
    import numpy as np
    import omni.replicator.core as rep
    import omni.usd
    from PIL import Image, ImageDraw
    from pxr import Gf, UsdGeom, UsdLux

    ctx = omni.usd.get_context()
    ctx.open_stage(HOSPITAL)
    stage = ctx.get_stage()
    UsdLux.DomeLight.Define(stage, "/World_extra/dome").CreateIntensityAttr(800)
    cam = UsdGeom.Camera.Define(stage, "/World_extra/cam")
    t_op = cam.AddTranslateOp()
    r_op = cam.AddRotateXYZOp()
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 10000))
    rp = rep.create.render_product("/World_extra/cam", (640, 480))
    annot = rep.AnnotatorRegistry.get_annotator("rgb")
    annot.attach(rp)

    def render_at(x, y, th, z=0.35, down=False):
        t_op.Set(Gf.Vec3d(float(x), float(y), z))
        if down:
            r_op.Set(Gf.Vec3f(0.0, 0.0, 0.0))
        else:
            r_op.Set(Gf.Vec3f(90.0, 0.0, float(np.degrees(th)) - 90.0))
        arr = np.zeros(())
        for _ in range(14):
            rep.orchestrator.step(rt_subframes=3)
            arr = np.array(annot.get_data())
            if arr.ndim == 3 and arr.size and float(arr[..., :3].mean()) > 1.0:
                break
        return arr[..., :3].astype("uint8")

    out = out_root / ep_id
    out.mkdir(parents=True, exist_ok=True)
    idxs = list(range(0, len(pos), max(1, len(pos) // 40)))
    frames = []
    for i in idxs:
        frames.append(render_at(pos[i][0], pos[i][1], yaw[i]))
    Image.fromarray(frames[0]).save(out / "start_state.png")
    Image.fromarray(frames[-1]).save(out / "final_current_state.png")
    goal_png = d / "goal.png"
    if goal_png.exists():
        Image.open(goal_png).convert("RGB").save(out / "goal_state.png")
        gimg = np.array(Image.open(goal_png).convert("RGB").resize((640, 480)))
    else:
        gimg = frames[-1]
    strip = np.concatenate(
        [np.array(Image.fromarray(f).resize((320, 240)))
         for f in (frames[0], frames[-1])] +
        [np.array(Image.fromarray(gimg).resize((320, 240)))], axis=1)
    Image.fromarray(strip).save(out / "start_current_goal_strip.png")

    # secondary top-down DEBUG view with trail + zone overlay (not evidence)
    cx, cy = float(pos[:, 0].mean()), float(pos[:, 1].mean())
    dbg = render_at(cx, cy, 0.0, z=9.0, down=True)
    im = Image.fromarray(dbg)
    dr = ImageDraw.Draw(im)
    span = 14.0
    def w2p(x, y):
        return (int((x - cx) / span * 640 + 320),
                int((cy - y) / span * 480 * (640 / 480) + 240))
    zones_f = REPO / "assets/datasets/isaac_hospital_navgen_v0/safety_zones.json"
    if zones_f.exists():
        colors = {"red": (255, 60, 60), "amber": (255, 190, 40),
                  "green": (70, 200, 70)}
        for z in json.loads(zones_f.read_text())["zones"]:
            if z["zone"] == "green":
                continue
            pts = [w2p(px, py) for px, py in z["polygon"]]
            dr.polygon(pts, outline=colors[z["zone"]], width=3)
    for i in range(1, len(pos)):
        dr.line([w2p(*pos[i - 1]), w2p(*pos[i])], fill=(80, 160, 255), width=2)
    dr.ellipse([*(v - 6 for v in w2p(*pos[0])),
                *(v + 6 for v in w2p(*pos[0]))], outline=(0, 255, 0), width=3)
    dr.ellipse([*(v - 6 for v in w2p(*pos[-1])),
                *(v + 6 for v in w2p(*pos[-1]))], outline=(255, 0, 255), width=3)
    im.save(out / "debug_topdown_overlay.png")

    telemetry = {"final_distance_to_goal_m": src_meta.get(
                     "final_distance_to_goal_m"),
                 "min_distance_to_goal_m": src_meta.get(
                     "min_distance_to_goal_m"),
                 "path_length_m": src_meta.get("total_distance_m"),
                 "stop_reason": src_meta.get("cl_stop_reason"),
                 "estop": src_meta.get("cl_emergency_stop"),
                 "watchdog": src_meta.get("cl_watchdog_timeout_s")}
    (out / "telemetry_summary.json").write_text(json.dumps(telemetry, indent=2))
    (out / "contact_summary.json").write_text(json.dumps(
        {"collision_reporting": src_meta.get("collision_reporting"),
         "episode_had_collision": src_meta.get("episode_had_collision"),
         "total_collision_count": src_meta.get("total_collision_count"),
         "first_collision_step": src_meta.get("first_collision_step")},
        indent=2))
    manifest = {"episode_id": ep_id, "goal_id": meta.get("goal_id"),
                "frames_rerendered": len(frames),
                "main_view": "Yahboom front-facing RGB camera (re-rendered "
                             "at recorded poses)",
                "debug_view": "secondary top-down overlay (trail, start/"
                              "goal markers, red/amber zone outlines) — "
                              "NOT primary evidence",
                "claim_boundary": CLAIM}
    (out / "review_manifest.json").write_text(json.dumps(manifest, indent=2))
    (out / "review_notes.md").write_text(
        f"# Review — {ep_id}\n\n{CLAIM}\n\nMain view: front RGB. Strip: "
        "start | final current | goal. Debug top-down overlay is secondary."
        f"\n\nTelemetry: {json.dumps(telemetry)}\n")
    app.close()
    print(f"review exported: {out}")


def main():
    args = sys.argv[1:]
    if "--list" in args:
        for e in list_episodes():
            print(f"{e['episode_id']}  goal={e['goal_id']}  "
                  f"frames={e['n_frames']}")
        return
    ep = args[args.index("--episode") + 1]
    from datetime import date
    out_root = (REPO / f"assets/experiments/hospital_episode_review_"
                f"{date.today().strftime('%Y%m%d')}")
    if "--live" in args:
        ck = args[args.index("--checkpoint") + 1]
        _, meta, _ = find_episode(ep)
        subprocess.run(
            ["/home/favl/miniforge3/envs/isaac/bin/python", "-u",
             "scripts/robots/m3pro_ros2_bringup.py", "--gnm-control",
             "--episode", "--collision-report", "--scene", "hospital",
             "--policy-ckpt", ck, "--goal-id", meta["goal_id"],
             "--episode-name", f"review_live_{ep[:24]}", "--steps", "900",
             "--experiment-id", "episode_review",
             "--condition", "review_live_run"], cwd=REPO, check=True)
        return
    replay(ep, out_root)


if __name__ == "__main__":
    main()
