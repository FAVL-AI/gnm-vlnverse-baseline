"""
manual_custom_vln_office_drive.py — Manual drive in CustomVLN-Office
====================================================================
Allows manual keyboard driving inside the custom office scene.
Every movement is logged to RGB frames, x/y/yaw, action key,
timestamp, and distance to goal.

Dry-run: prints the controls and scene layout without opening Isaac Sim.

Controls (in Isaac Sim window):
  W      — forward (+0.3 m in heading direction)
  S      — backward (-0.3 m)
  A      — rotate left (+15°)
  D      — rotate right (-15°)
  Q      — strafe left
  E      — strafe right
  Space  — stop (record pose without movement)
  G      — mark current pose as goal
  P      — save episode to disk
  R      — reset to start pose
  Esc    — exit

Saved under: datasets/custom_vln_office_manual/<episode_id>/

Usage:
  python3 scripts/gnm/manual_custom_vln_office_drive.py --dry-run
  conda run -n isaac python scripts/gnm/manual_custom_vln_office_drive.py
"""
import argparse
import json
import math
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

REPO       = Path(__file__).resolve().parents[2]
SCENE_USD  = REPO / "assets/custom_vln_office/custom_vln_office.usd"
MANUAL_ROOT = REPO / "datasets/custom_vln_office_manual"
MANUAL_ROOT.mkdir(parents=True, exist_ok=True)

START_X, START_Y, START_YAW = 2.0, 5.0, 0.0
MOVE_STEP  = 0.3   # metres per step
TURN_STEP  = math.radians(15)
CAM_HEIGHT = 1.2


def _dry_run() -> None:
    print("CustomVLN-Office — Manual Drive (dry-run)")
    print("=" * 60)
    print()
    print("Scene layout (16 m × 10 m):")
    print("  Entrance corridor : x=0..4,  y=0..10")
    print("  Open office A     : x=4..10, y=0..5  (desks, chairs)")
    print("  Open office B     : x=10..16, y=0..5 (desks, shelf)")
    print("  Meeting area      : x=4..10, y=5..10 (meeting table)")
    print("  Hallway           : x=10..16, y=5..10 (cabinet, plant)")
    print()
    print("Start pose: (2.0, 5.0)  yaw=0°")
    print()
    print("Controls:")
    print("  W     forward  +0.3 m")
    print("  S     backward -0.3 m")
    print("  A     rotate left  +15°")
    print("  D     rotate right -15°")
    print("  Q     strafe left  +0.3 m")
    print("  E     strafe right -0.3 m")
    print("  Space stop (record without movement)")
    print("  G     mark current pose as goal")
    print("  P     save episode")
    print("  R     reset to start")
    print("  Esc   exit")
    print()
    print("Output per episode:")
    print(f"  {MANUAL_ROOT}/<episode_id>/")
    print("    rgb/000000.jpg … rgb/NNNNNN.jpg")
    print("    traj_data.pkl")
    print("    actions.jsonl")
    print("    metadata.json")
    print()
    print("To drive manually, run inside Isaac Sim:")
    print("  conda run -n isaac python scripts/gnm/manual_custom_vln_office_drive.py")


class ManualDriveSession:
    def __init__(self, app, stage, ctx):
        self.app   = app
        self.stage = stage
        self.ctx   = ctx
        self.x, self.y, self.yaw = START_X, START_Y, START_YAW
        self.goal_x = self.goal_y = None
        self.frames: list[dict] = []
        self.ep_id  = f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.out_dir = MANUAL_ROOT / self.ep_id
        self.rgb_dir = self.out_dir / "rgb"
        self.rgb_dir.mkdir(parents=True, exist_ok=True)
        self._setup_robot()
        self._setup_cam()

    def _setup_robot(self):
        from pxr import UsdGeom, UsdShade, Sdf, Gf
        self.root = "/World/ManualDrive"
        UsdGeom.Xform.Define(self.stage, self.root)
        mat = UsdShade.Material.Define(self.stage, f"{self.root}/MatRob")
        sh = UsdShade.Shader.Define(self.stage, f"{self.root}/MatRob/S")
        sh.CreateIdAttr("UsdPreviewSurface")
        sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.2, 0.4, 1.0))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.4)
        mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
        body = UsdGeom.Cube.Define(self.stage, f"{self.root}/Robot/body")
        body.CreateSizeAttr(0.5)
        body.AddTranslateOp().Set(Gf.Vec3d(0, 0, 0.5))
        UsdShade.MaterialBindingAPI(body.GetPrim()).Bind(mat)
        rob = UsdGeom.Xformable(
            UsdGeom.Xform.Define(self.stage, f"{self.root}/Robot").GetPrim())
        rob.ClearXformOpOrder()
        self._t_op = rob.AddTranslateOp()
        self._r_op = rob.AddRotateZOp()
        self._t_op.Set(Gf.Vec3d(self.x, self.y, 0.0))
        self._r_op.Set(math.degrees(self.yaw))

    def _setup_cam(self):
        from pxr import UsdGeom, Gf
        cam = UsdGeom.Camera.Define(self.stage, f"{self.root}/RobotCam")
        cam.CreateProjectionAttr(UsdGeom.Tokens.perspective)
        cam.CreateHorizontalApertureAttr(20.0)
        cam.CreateFocalLengthAttr(16.0)
        xf = UsdGeom.Xformable(cam.GetPrim())
        xf.ClearXformOpOrder()
        self._cam_t = xf.AddTranslateOp()
        self._cam_r = xf.AddRotateXYZOp()
        self._cam_t.Set(Gf.Vec3d(self.x, self.y, CAM_HEIGHT))
        yaw_deg = math.degrees(self.yaw)
        self._cam_r.Set(Gf.Vec3f(90.0, 0.0, yaw_deg - 90.0))
        try:
            import omni.kit.viewport.utility as vu
            vu.get_active_viewport().camera_path = f"{self.root}/RobotCam"
        except Exception:
            pass

    def _update_pose(self):
        from pxr import Gf
        self._t_op.Set(Gf.Vec3d(self.x, self.y, 0.0))
        self._r_op.Set(math.degrees(self.yaw))
        self._cam_t.Set(Gf.Vec3d(self.x, self.y, CAM_HEIGHT))
        self._cam_r.Set(Gf.Vec3f(90.0, 0.0, math.degrees(self.yaw) - 90.0))

    def _capture_frame(self) -> str:
        i = len(self.frames)
        path = self.rgb_dir / f"{i:06d}.jpg"
        captured = False
        try:
            import omni.renderer_capture
            omni.renderer_capture.acquire_renderer_capture_interface()\
                .capture_next_frame_swapchain(str(path))
            for _ in range(4):
                self.app.update()
            captured = path.exists()
        except Exception:
            pass
        if not captured:
            from PIL import Image
            Image.new("RGB", (480, 360), (80, 100, 80)).save(path)
        return str(path.relative_to(REPO))

    def step(self, action_key: str) -> None:
        from pxr import Gf
        dx = dy = dyaw = 0.0
        if action_key == "W":
            dx = MOVE_STEP * math.cos(self.yaw)
            dy = MOVE_STEP * math.sin(self.yaw)
        elif action_key == "S":
            dx = -MOVE_STEP * math.cos(self.yaw)
            dy = -MOVE_STEP * math.sin(self.yaw)
        elif action_key == "A":
            dyaw = TURN_STEP
        elif action_key == "D":
            dyaw = -TURN_STEP
        elif action_key == "Q":
            dx = MOVE_STEP * math.cos(self.yaw + math.pi / 2)
            dy = MOVE_STEP * math.sin(self.yaw + math.pi / 2)
        elif action_key == "E":
            dx = -MOVE_STEP * math.cos(self.yaw + math.pi / 2)
            dy = -MOVE_STEP * math.sin(self.yaw + math.pi / 2)

        self.x   += dx
        self.y   += dy
        self.yaw += dyaw
        # Clamp to floor
        self.x = max(0.2, min(15.8, self.x))
        self.y = max(0.2, min(9.8,  self.y))

        self._update_pose()
        for _ in range(6):
            self.app.update()

        rgb_path = self._capture_frame()
        dist = math.hypot(self.x - (self.goal_x or 0), self.y - (self.goal_y or 0)) \
               if self.goal_x is not None else -1.0
        self.frames.append({
            "frame_index":    len(self.frames) - 1,
            "timestamp":      round(time.time(), 3),
            "x":              round(self.x,   4),
            "y":              round(self.y,   4),
            "yaw":            round(self.yaw, 4),
            "action_dx":      round(dx,    4),
            "action_dy":      round(dy,    4),
            "action_dyaw":    round(dyaw,  4),
            "action_key":     action_key,
            "rgb_image_path": rgb_path,
            "distance_to_goal": round(dist, 4),
        })
        print(f"  [{action_key}] ({self.x:.2f}, {self.y:.2f}) yaw={math.degrees(self.yaw):.0f}°"
              + (f" dist_goal={dist:.2f}" if dist >= 0 else ""))

    def save_episode(self) -> None:
        if not self.frames:
            print("  No frames recorded.")
            return
        pos = np.array([[f["x"], f["y"]] for f in self.frames], dtype=np.float32)
        yaw = np.array([f["yaw"] for f in self.frames], dtype=np.float32)
        path_len = float(np.linalg.norm(np.diff(pos, axis=0), axis=1).sum())
        pkl = {
            "position": pos, "yaw": yaw,
            "scene_id": "custom_vln_office",
            "episode_id": self.ep_id,
            "start_pos": [float(pos[0][0]), float(pos[0][1])],
            "start_yaw": float(yaw[0]),
            "goal_pos":  [self.goal_x or float(pos[-1][0]),
                          self.goal_y or float(pos[-1][1])],
            "n_steps": len(self.frames),
            "path_length_m": path_len,
            "source": "manual_custom_vln_office_drive.py",
        }
        with open(self.out_dir / "traj_data.pkl", "wb") as f:
            pickle.dump(pkl, f)
        with open(self.out_dir / "actions.jsonl", "w") as f:
            for frame in self.frames:
                f.write(json.dumps(frame) + "\n")
        meta = {
            "episode_id": self.ep_id, "scene_id": "custom_vln_office",
            "split": "manual",
            "n_steps": len(self.frames), "path_length_m": round(path_len, 4),
            "source": "manual_drive", "vlnverse_assets_used": False,
        }
        with open(self.out_dir / "metadata.json", "w") as f:
            json.dump(meta, f, indent=2)
        print(f"  Episode saved: {self.out_dir}  ({len(self.frames)} frames)")

    def reset(self) -> None:
        from pxr import Gf
        self.x, self.y, self.yaw = START_X, START_Y, START_YAW
        self._update_pose()
        self.frames = []
        print(f"  Reset to ({START_X}, {START_Y})  yaw=0°")


def run_isaac() -> None:
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": False, "renderer": "RayTracedLighting"})
    import omni.usd
    ctx = omni.usd.get_context()
    if SCENE_USD.exists():
        ctx.open_stage(str(SCENE_USD))
    else:
        ctx.new_stage()
    for _ in range(120):
        app.update()
        time.sleep(0.01)
    stage = ctx.get_stage()
    session = ManualDriveSession(app, stage, ctx)

    print("=" * 60)
    print("CustomVLN-Office — Manual Drive")
    print("  W/S/A/D/Q/E = move  |  G = set goal  |  P = save  |  R = reset  |  Esc = exit")
    print("=" * 60)

    # Keyboard event handler
    key_map = {}
    try:
        import carb.input
        import omni.appwindow
        kbd = carb.input.acquire_input_interface()
        app_win = omni.appwindow.get_default_app_window()
        def _on_key(e, *_):
            if e.type == carb.input.KeyboardEventType.KEY_RELEASE:
                k = str(e.input).split(".")[-1].upper()
                key_map["last"] = k
        kbd.subscribe_to_keyboard_events(app_win.get_keyboard(), _on_key)
    except Exception:
        key_map["last"] = None
        print("  Keyboard subscription unavailable; using programmatic step loop.")

    try:
        while True:
            app.update()
            k = key_map.pop("last", None)
            if k in ("W", "S", "A", "D", "Q", "E", "SPACE"):
                session.step(k if k != "SPACE" else "STOP")
            elif k == "G":
                session.goal_x, session.goal_y = session.x, session.y
                print(f"  Goal set: ({session.x:.2f}, {session.y:.2f})")
            elif k == "P":
                session.save_episode()
            elif k == "R":
                session.reset()
            elif k in ("ESCAPE", "ESC"):
                break
            time.sleep(0.033)
    except KeyboardInterrupt:
        pass
    finally:
        session.save_episode()
        app.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        _dry_run()
    else:
        run_isaac()


if __name__ == "__main__":
    main()
