"""ROS 2 bridge bring-up for the articulated Yahboom M3 Pro (Phase 2, R2).

Loads the imported articulated USD on a physics ground plane, builds the
ROS 2 OmniGraph (clock, /odom, /tf, /cmd_vel -> wheel velocities), then runs
a self-contained acceptance test: publishes a forward twist on /cmd_vel via
the system ROS 2 Humble CLI and asserts the robot actually translates.

The four mecanum wheels are driven as a differential pair approximation
(left = fl+rl, right = fr+rr): correct for the vx/wz commands GNM-style
policies emit; lateral vy is not actuated (matches Phase 2 scope).

Run (system ROS 2 must be sourced so the bridge links against it):
    source /opt/ros/humble/setup.bash && \
        ~/miniforge3/envs/isaac/bin/python -u scripts/robots/m3pro_ros2_bringup.py
"""

from isaacsim import SimulationApp

app = SimulationApp({"headless": True, "width": 1280, "height": 720})

import math
import sys
import numpy as np
import subprocess
import time
from pathlib import Path

from isaacsim.core.utils.extensions import enable_extension

enable_extension("isaacsim.ros2.bridge")
app.update()
app.update()

import omni.graph.core as og
import omni.timeline
import omni.usd
from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics

REPO = Path(__file__).resolve().parents[2]
ROBOT_USD = REPO / "assets/robots/yahboom_m3_pro/yahboom_m3pro.usd"
WHEEL_JOINTS = ["fl_wheel_joint", "fr_wheel_joint",
                "rl_wheel_joint", "rr_wheel_joint"]
WHEEL_RADIUS = 0.048
TRACK_WIDTH = 0.170

ctx = omni.usd.get_context()
ctx.new_stage()
app.update()
stage = ctx.get_stage()
world = UsdGeom.Xform.Define(stage, "/World")
stage.SetDefaultPrim(world.GetPrim())
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)

UsdPhysics.Scene.Define(stage, "/World/physicsScene")
UsdLux.DomeLight.Define(stage, "/World/Dome").CreateIntensityAttr(1000.0)

ground = UsdGeom.Cube.Define(stage, "/World/Ground")
ground.CreateSizeAttr(1.0)
UsdGeom.XformCommonAPI(ground).SetScale(Gf.Vec3f(40, 40, 0.1))
UsdGeom.XformCommonAPI(ground).SetTranslate(Gf.Vec3d(0, 0, -0.05))
UsdPhysics.CollisionAPI.Apply(ground.GetPrim())

robot = stage.DefinePrim("/World/M3Pro")
robot.GetReferences().AddReference(str(ROBOT_USD))
UsdGeom.XformCommonAPI(UsdGeom.Xformable(robot)).SetTranslate(
    Gf.Vec3d(0, 0, 0.005))
app.update()

ROBOT_PATH = "/World/M3Pro"
ARTIC_ROOT = "/World/M3Pro/base_footprint"

keys = og.Controller.Keys
og.Controller.edit(
    {"graph_path": "/World/ROS2Graph", "evaluator_name": "execution"},
    {
        keys.CREATE_NODES: [
            ("tick", "omni.graph.action.OnPlaybackTick"),
            ("rosCtx", "isaacsim.ros2.bridge.ROS2Context"),
            ("simTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
            ("clockPub", "isaacsim.ros2.bridge.ROS2PublishClock"),
            ("twistSub", "isaacsim.ros2.bridge.ROS2SubscribeTwist"),
            ("breakLin", "omni.graph.nodes.BreakVector3"),
            ("breakAng", "omni.graph.nodes.BreakVector3"),
            ("diff", "isaacsim.robot.wheeled_robots.DifferentialController"),
            ("idxL", "omni.graph.nodes.ArrayIndex"),
            ("idxR", "omni.graph.nodes.ArrayIndex"),
            ("wheelCmd", "omni.graph.nodes.ConstructArray"),
            ("odom", "isaacsim.core.nodes.IsaacComputeOdometry"),
            ("odomPub", "isaacsim.ros2.bridge.ROS2PublishOdometry"),
            ("tfPub", "isaacsim.ros2.bridge.ROS2PublishRawTransformTree"),
        ],
        keys.SET_VALUES: [
            ("twistSub.inputs:topicName", "cmd_vel"),
            ("diff.inputs:wheelRadius", WHEEL_RADIUS),
            ("diff.inputs:wheelDistance", TRACK_WIDTH),
            ("diff.inputs:maxLinearSpeed", 1.0),
            ("diff.inputs:maxAngularSpeed", 4.0),
            ("diff.inputs:maxWheelSpeed", 25.0),
            ("idxL.inputs:index", 0),
            ("idxR.inputs:index", 1),
            ("wheelCmd.inputs:arraySize", 4),
            ("odomPub.inputs:odomFrameId", "odom"),
            ("odomPub.inputs:chassisFrameId", "base_footprint"),
            ("tfPub.inputs:parentFrameId", "odom"),
            ("tfPub.inputs:childFrameId", "base_footprint"),
        ],
        keys.CONNECT: [
            ("tick.outputs:tick", "clockPub.inputs:execIn"),
            ("tick.outputs:tick", "twistSub.inputs:execIn"),
            ("tick.outputs:tick", "odom.inputs:execIn"),
            ("rosCtx.outputs:context", "clockPub.inputs:context"),
            ("rosCtx.outputs:context", "twistSub.inputs:context"),
            ("rosCtx.outputs:context", "odomPub.inputs:context"),
            ("rosCtx.outputs:context", "tfPub.inputs:context"),
            ("simTime.outputs:simulationTime", "clockPub.inputs:timeStamp"),
            ("simTime.outputs:simulationTime", "odomPub.inputs:timeStamp"),
            ("simTime.outputs:simulationTime", "tfPub.inputs:timeStamp"),
            ("twistSub.outputs:execOut", "diff.inputs:execIn"),
            ("twistSub.outputs:linearVelocity", "breakLin.inputs:tuple"),
            ("twistSub.outputs:angularVelocity", "breakAng.inputs:tuple"),
            ("breakLin.outputs:x", "diff.inputs:linearVelocity"),
            ("breakAng.outputs:z", "diff.inputs:angularVelocity"),
            ("diff.outputs:velocityCommand", "idxL.inputs:array"),
            ("diff.outputs:velocityCommand", "idxR.inputs:array"),
            ("idxL.outputs:value", "wheelCmd.inputs:input0"),
            ("odom.outputs:execOut", "odomPub.inputs:execIn"),
            ("odom.outputs:execOut", "tfPub.inputs:execIn"),
            ("odom.outputs:position", "odomPub.inputs:position"),
            ("odom.outputs:orientation", "odomPub.inputs:orientation"),
            ("odom.outputs:linearVelocity", "odomPub.inputs:linearVelocity"),
            ("odom.outputs:angularVelocity", "odomPub.inputs:angularVelocity"),
            ("odom.outputs:position", "tfPub.inputs:translation"),
            ("odom.outputs:orientation", "tfPub.inputs:rotation"),
        ],
    },
)

# ConstructArray only ships with input0; add the remaining slots and wire
# them as left/right pairs: [fl, fr, rl, rr] = [L, R, L, R].
wheel_node = og.get_node_by_path("/World/ROS2Graph/wheelCmd")
for i in (1, 2, 3):
    og.Controller.create_attribute(
        wheel_node, f"inputs:input{i}", og.Type(og.BaseDataType.DOUBLE))
og.Controller.connect("/World/ROS2Graph/idxR.outputs:value",
                      "/World/ROS2Graph/wheelCmd.inputs:input1")
og.Controller.connect("/World/ROS2Graph/idxL.outputs:value",
                      "/World/ROS2Graph/wheelCmd.inputs:input2")
og.Controller.connect("/World/ROS2Graph/idxR.outputs:value",
                      "/World/ROS2Graph/wheelCmd.inputs:input3")

stage.GetPrimAtPath("/World/ROS2Graph/odom").GetRelationship(
    "inputs:chassisPrim").SetTargets([ARTIC_ROOT])
print("[graph] ROS2 graph built")

# --- Camera publisher -----------------------------------------------------
# The URDF import creates the camera_link frame but no Camera prim. Author
# an RGB camera under it: rotateXYZ (90, 0, -90) points the USD camera's
# forward (-Z) along the robot's +X with up = +Z.
CAM_PRIM = f"{ROBOT_PATH}/camera_link/rgb_camera"
cam = UsdGeom.Camera.Define(stage, CAM_PRIM)
cam.CreateFocalLengthAttr(18.0)
cam.CreateClippingRangeAttr(Gf.Vec2f(0.02, 10000.0))
UsdGeom.XformCommonAPI(cam).SetRotate(Gf.Vec3f(90.0, 0.0, -90.0))

import omni.replicator.core as rep

render_product = rep.create.render_product(CAM_PRIM, (640, 480))
rp_path = render_product.path if hasattr(render_product, "path") \
    else str(render_product)

og.Controller.edit("/World/ROS2Graph", {
    keys.CREATE_NODES: [
        ("camHelper", "isaacsim.ros2.bridge.ROS2CameraHelper"),
    ],
    keys.SET_VALUES: [
        ("camHelper.inputs:renderProductPath", rp_path),
        ("camHelper.inputs:type", "rgb"),
        ("camHelper.inputs:topicName", "camera/image_raw"),
        ("camHelper.inputs:frameId", "camera_link"),
    ],
    keys.CONNECT: [
        ("/World/ROS2Graph/tick.outputs:tick", "camHelper.inputs:execIn"),
        ("/World/ROS2Graph/rosCtx.outputs:context", "camHelper.inputs:context"),
    ],
})
print(f"[camera] /camera/image_raw publisher configured (rp={rp_path})")

try:
    og.Controller.edit("/World/ROS2Graph", {
        keys.CREATE_NODES: [
            ("camInfo", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
        ],
        keys.SET_VALUES: [
            ("camInfo.inputs:renderProductPath", rp_path),
            ("camInfo.inputs:topicName", "camera/camera_info"),
            ("camInfo.inputs:frameId", "camera_link"),
        ],
        keys.CONNECT: [
            ("/World/ROS2Graph/tick.outputs:tick", "camInfo.inputs:execIn"),
            ("/World/ROS2Graph/rosCtx.outputs:context", "camInfo.inputs:context"),
        ],
    })
    print("[camera] /camera/camera_info publisher configured")
except Exception as e:
    print(f"[camera] camera_info deferred (node wiring failed): {e}")

from isaacsim.core.api import SimulationContext
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.types import ArticulationAction

sim = SimulationContext(physics_dt=1.0 / 60.0, rendering_dt=1.0 / 60.0,
                        stage_units_in_meters=1.0)
arti = SingleArticulation(ARTIC_ROOT, name="m3pro")
sim.initialize_physics()
arti.initialize()
sim.play()
for _ in range(60):
    sim.step(render=False)
print(f"[init] dof names: {list(arti.dof_names)}")


def robot_xyz():
    pos, _ = arti.get_world_pose()
    return float(pos[0]), float(pos[1]), float(pos[2])


# --- Probe 1: direct joint-velocity actuation, no ROS involved -----------
px0, py0, pz0 = robot_xyz()
action = ArticulationAction(
    joint_velocities=[6.25, 6.25, 6.25, 6.25],
    joint_indices=[arti.get_dof_index(j) for j in WHEEL_JOINTS])
for _ in range(240):
    arti.apply_action(action)
    sim.step(render=False)
px1, py1, pz1 = robot_xyz()
direct = math.hypot(px1 - px0, py1 - py0)
print(f"[probe] direct-drive displacement over 4 s: {direct:.3f} m "
      f"(z {pz0:.3f}->{pz1:.3f}); wheel vel now: "
      f"{arti.get_joint_velocities()}")
arti.apply_action(ArticulationAction(
    joint_velocities=[0.0] * 4,
    joint_indices=[arti.get_dof_index(j) for j in WHEEL_JOINTS]))
for _ in range(60):
    sim.step(render=False)


# The Isaac process env poisons the ROS 2 CLI (python 3.10) with the
# conda env's PYTHONPATH / LD_LIBRARY_PATH, so run every CLI call in a
# scrubbed environment.
import os

def ros_cli(cmd, **kw):
    return subprocess.run(
        ["env", "-i", f"HOME={os.environ['HOME']}",
         "PATH=/usr/bin:/bin:/usr/local/bin",
         "bash", "-c", f"source /opt/ros/humble/setup.bash && {cmd}"],
        capture_output=True, text=True, **kw)


ros_cli("ros2 daemon stop || true")
res = ros_cli("timeout 15 ros2 topic list --no-daemon --spin-time 5")
print(f"[test] topics visible to system ROS 2:\n{res.stdout}"
      + (f"[test] CLI stderr: {res.stderr.strip()[:300]}" if res.returncode else ""))

pub = None
if "--gnm-control" not in sys.argv:
    pub = subprocess.Popen(
    ["env", "-i", f"HOME={os.environ['HOME']}",
     "PATH=/usr/bin:/bin:/usr/local/bin",
     "bash", "-c",
     "source /opt/ros/humble/setup.bash && "
     "ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist "
     "'{linear: {x: 0.3}}'"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Let the ROS 2 CLI publisher finish its slow cold start (imports + DDS
# discovery) before measuring, pumping frames so the graph is live.
for _ in range(240):
    sim.step(render=(_ % 3 == 0))
x0, y0, z0 = robot_xyz()

# --- Mandatory per-step trajectory logging (every live episode) ----------
import sys
from datetime import datetime as _dt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from trajectory_logger import TrajectoryLogger

CL_MODE = "--gnm-control" in sys.argv
_prefix = "gnm_closed_loop" if CL_MODE else "manual_arc"
EPISODE_ID = f"{_prefix}_{_dt.now():%Y%m%d_%H%M%S}"
EPISODE_TOPICS = ["/camera/image_raw", "/camera/camera_info", "/odom",
                  "/tf", "/clock", "/cmd_vel"]
from gnm_shadow import SHADOW_FIELDS as _SF
CL_FIELDS = [
    "gnm_control_enabled", "gnm_action_raw_linear_velocity",
    "gnm_action_raw_angular_velocity", "gnm_action_clipped_linear_velocity",
    "gnm_action_clipped_angular_velocity", "action_clipped",
    "watchdog_state", "emergency_stop_triggered", "stop_reason",
]
traj_log = TrajectoryLogger(
    EPISODE_ID, REPO,
    policy_mode="gnm_closed_loop" if CL_MODE else "manual_cmd_vel",
    extra_fields=_SF + (CL_FIELDS if CL_MODE else []))

bag_proc = None
bag_path = None
if "--episode" in sys.argv:
    bag_path = REPO / "assets/experiments/rosbags" / EPISODE_ID
    bag_proc = subprocess.Popen(
        ["env", "-i", f"HOME={os.environ['HOME']}",
         "PATH=/usr/bin:/bin:/usr/local/bin",
         "bash", "-c",
         "source /opt/ros/humble/setup.bash && "
         f"ros2 bag record -o {bag_path} " + " ".join(EPISODE_TOPICS)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(120):
        sim.step(render=(_ % 3 == 0))
    print(f"[episode] {EPISODE_ID}: rosbag recording to {bag_path}")


shadow = None
rgb_annot = None
if "--episode" in sys.argv or "--shadow-gnm" in sys.argv or "--gnm-control" in sys.argv:
    import omni.replicator.core as _rep
    from gnm_shadow import GNMShadow, SHADOW_FIELDS
    rgb_annot = _rep.AnnotatorRegistry.get_annotator("rgb")
    rgb_annot.attach(render_product)
    shadow = GNMShadow(
        REPO,
        REPO / "assets/deck/tracka_goal_observation.jpg",
        device="cuda")
    print(f"[shadow] GNM shadow inference active (model="
          f"{shadow.latest['shadow_gnm_model_path']}); "
          "no /cmd_vel control — scripted controller drives")


def robot_pose_yaw():
    pos, quat = arti.get_world_pose()
    w, qx, qy, qz = (float(v) for v in quat)
    yaw = math.atan2(2.0 * (w * qz + qx * qy),
                     1.0 - 2.0 * (qy * qy + qz * qz))
    return float(pos[0]), float(pos[1]), float(pos[2]), yaw

if CL_MODE:
    # ── GNM closed-loop bounded smoke episode ────────────────────────────
    # First time GNM has control authority: short, bounded, clamped,
    # watchdog-protected, explicit zeroing. Control-authority milestone
    # only — the fixed goal image is not scene-aligned, so no
    # navigation-quality claim.
    CL_LIN_MAX, CL_ANG_MAX = 0.20, 0.40
    CL_BOUND_XY = 6.0
    CL_Z_DRIFT_MAX = 0.05
    CL_FAIL_MAX = 10
    CL_STEPS = 480          # 8 s of sim time at 60 Hz
    CL_WATCHDOG_S = 0.5     # sim seconds without fresh inference -> zero

    publish_ok = True
    try:
        og.Controller.edit("/World/ROS2Graph", {
            keys.CREATE_NODES: [
                ("cmdPub", "isaacsim.ros2.bridge.ROS2Publisher")],
            keys.SET_VALUES: [
                ("cmdPub.inputs:messagePackage", "geometry_msgs"),
                ("cmdPub.inputs:messageSubfolder", "msg"),
                ("cmdPub.inputs:messageName", "Twist"),
                ("cmdPub.inputs:topicName", "cmd_vel"),
            ],
            keys.CONNECT: [
                ("/World/ROS2Graph/tick.outputs:tick", "cmdPub.inputs:execIn"),
                ("/World/ROS2Graph/rosCtx.outputs:context",
                 "cmdPub.inputs:context"),
            ]})
        for _ in range(10):
            app.update()
        _node = og.get_node_by_path("/World/ROS2Graph/cmdPub")
        _in = [a.get_name() for a in _node.get_attributes()
               if a.get_name().startswith("inputs:")]
        _lin = next(a for a in _in if a.lower().endswith("linear:x"))
        _ang = next(a for a in _in if a.lower().endswith("angular:z"))
        print(f"[cl] cmd publisher ready (fields {_lin}, {_ang})")

        def publish_cmd(vx, wz):
            og.Controller.set(
                og.Controller.attribute(f"/World/ROS2Graph/cmdPub.{_lin}"),
                float(vx))
            og.Controller.set(
                og.Controller.attribute(f"/World/ROS2Graph/cmdPub.{_ang}"),
                float(wz))
    except Exception as e:
        publish_ok = False
        print(f"[cl] cmd publisher unavailable ({e}); applying without "
              "/cmd_vel mirror")

        def publish_cmd(vx, wz):
            pass

    cl_wheels = [arti.get_dof_index(j) for j in WHEEL_JOINTS]

    def apply_cmd(vx, wz):
        wl = (vx - wz * TRACK_WIDTH / 2.0) / WHEEL_RADIUS
        wr = (vx + wz * TRACK_WIDTH / 2.0) / WHEEL_RADIUS
        arti.apply_action(ArticulationAction(
            joint_velocities=[wl, wr, wl, wr], joint_indices=cl_wheels))

    publish_cmd(0.0, 0.0)
    # Warm the camera and fill the GNM context buffer before authority.
    for _ in range(60):
        sim.step(render=True)
        _f = rgb_annot.get_data()
        if _f is not None and getattr(_f, "size", 0) > 0:
            shadow.add_frame(np.asarray(_f)[:, :, :3].copy())
    shadow.infer()

    _, _, z0_cl, _ = robot_pose_yaw()
    estop = False
    stop_reason = None
    watchdog_state = "armed"
    last_ok_sim = sim.current_time
    clipped_count = 0
    applied_nonzero = 0

    def cl_log(i, wd, vraw, wraw, vappl, wappl, clipped, note=""):
        px_, py_, pz_, pyaw_ = robot_pose_yaw()
        od_l = og.Controller.get("/World/ROS2Graph/odom.outputs:linearVelocity")
        od_a = og.Controller.get("/World/ROS2Graph/odom.outputs:angularVelocity")
        extra = dict(shadow.latest)
        extra.update({
            "actual_controller": "gnm_closed_loop",
            "actual_linear_velocity_cmd": round(vappl, 6),
            "actual_angular_velocity_cmd": round(wappl, 6),
            "gnm_control_enabled": True,
            "gnm_action_raw_linear_velocity":
                round(vraw, 6) if vraw is not None else None,
            "gnm_action_raw_angular_velocity":
                round(wraw, 6) if wraw is not None else None,
            "gnm_action_clipped_linear_velocity": round(vappl, 6),
            "gnm_action_clipped_angular_velocity": round(wappl, 6),
            "action_clipped": clipped,
            "watchdog_state": wd,
            "emergency_stop_triggered": estop,
            "stop_reason": stop_reason,
        })
        traj_log.log_step(
            step_idx=i, sim_time=sim.current_time,
            x=px_, y=py_, z=pz_, yaw=pyaw_,
            linear_cmd=vappl, angular_cmd=wappl,
            odom_lin=float(od_l[0]) if od_l is not None else 0.0,
            odom_ang=float(od_a[2]) if od_a is not None else 0.0,
            image_timestamp=sim.current_time,
            stop_signal=None,
            safety_state="emergency_stop" if estop else
            ("hold" if wd.startswith("triggered") else "nominal"),
            notes=note, extra=extra)
        return px_, py_, pz_

    print(f"[cl] GNM control authority granted: {CL_STEPS/60:.0f}s bounded "
          f"episode, |v|<={CL_LIN_MAX}, |w|<={CL_ANG_MAX}, "
          f"XY bounds +/-{CL_BOUND_XY}m")
    for i in range(CL_STEPS):
        render = (i % 3 == 0)
        sim.step(render=render)
        if render:
            _f = rgb_annot.get_data()
            if _f is not None and getattr(_f, "size", 0) > 0:
                shadow.add_frame(np.asarray(_f)[:, :, :3].copy())
                shadow.infer()
                if shadow.latest["shadow_gnm_status"] == "ok":
                    last_ok_sim = sim.current_time

        raw = shadow.raw_cmd()
        px_, py_, pz_, _ = robot_pose_yaw()
        if abs(px_) > CL_BOUND_XY or abs(py_) > CL_BOUND_XY:
            estop, stop_reason = True, "left_xy_bounds"
        elif abs(pz_ - z0_cl) > CL_Z_DRIFT_MAX:
            estop, stop_reason = True, "z_drift_exceeded"
        elif shadow.failures > CL_FAIL_MAX:
            estop, stop_reason = True, "inference_failure_count"
        elif raw is not None and any(
                math.isnan(v) or math.isinf(v) for v in raw):
            estop, stop_reason = True, "nan_inf_action"
        elif raw is not None and (abs(raw[0]) > CL_LIN_MAX * 5
                                  or abs(raw[1]) > CL_ANG_MAX * 5):
            estop, stop_reason = True, "action_gross_bounds"

        if estop:
            publish_cmd(0.0, 0.0)
            apply_cmd(0.0, 0.0)
            watchdog_state = "estop_zeroed"
            cl_log(i, watchdog_state,
                   raw[0] if raw else None, raw[1] if raw else None,
                   0.0, 0.0, False, note=f"emergency stop: {stop_reason}")
            print(f"[cl] EMERGENCY STOP at step {i}: {stop_reason}")
            break

        wd_age = sim.current_time - last_ok_sim
        if raw is None:
            watchdog_state = "warmup_zero"
            vraw = wraw = None
            vappl = wappl = 0.0
            clipped = False
        elif wd_age > CL_WATCHDOG_S:
            watchdog_state = "triggered_stale_inference"
            vraw, wraw = raw
            vappl = wappl = 0.0
            clipped = False
        else:
            watchdog_state = "armed"
            vraw, wraw = raw
            vappl = max(-CL_LIN_MAX, min(CL_LIN_MAX, vraw))
            wappl = max(-CL_ANG_MAX, min(CL_ANG_MAX, wraw))
            clipped = (vappl != vraw) or (wappl != wraw)
            clipped_count += int(clipped)

        publish_cmd(vappl, wappl)
        apply_cmd(vappl, wappl)
        if abs(vappl) > 1e-6 or abs(wappl) > 1e-6:
            applied_nonzero += 1
        cl_log(i, watchdog_state, vraw, wraw, vappl, wappl, clipped)

    # ── Explicit zeroing + verification hold ────────────────────────────
    publish_cmd(0.0, 0.0)
    apply_cmd(0.0, 0.0)
    hx, hy, _, _ = robot_pose_yaw()
    for h in range(120):    # 2 s of sim time
        sim.step(render=(h % 3 == 0))
        publish_cmd(0.0, 0.0)
        cl_log(CL_STEPS + h, "zeroed_hold", None, None, 0.0, 0.0, False,
               note="post-episode zero hold")
    hx2, hy2, _, _ = robot_pose_yaw()
    hold_disp = math.hypot(hx2 - hx, hy2 - hy)
    print(f"[cl] zero-hold displacement over 2 s: {hold_disp:.4f} m")

    if bag_proc is not None:
        bag_proc.terminate()
        try:
            bag_proc.wait(timeout=15)
        except Exception:
            bag_proc.kill()

    cl_meta = shadow.summary()
    cl_meta.update({
        "closed_loop": True,
        "cl_limits": {"lin_max_ms": CL_LIN_MAX, "ang_max_rads": CL_ANG_MAX,
                      "xy_bound_m": CL_BOUND_XY,
                      "z_drift_max_m": CL_Z_DRIFT_MAX,
                      "watchdog_s": CL_WATCHDOG_S},
        "cl_steps_commanded": CL_STEPS,
        "cl_applied_nonzero_steps": applied_nonzero,
        "cl_clipped_steps": clipped_count,
        "cl_emergency_stop": estop,
        "cl_stop_reason": stop_reason,
        "cl_cmd_vel_mirror_published": publish_ok,
        "cl_zero_hold_displacement_m": round(hold_disp, 5),
        "cl_scope_note": (
            "control-authority smoke only: bounded, clamped, watchdog-"
            "protected; fixed non-scene goal image, no navigation-quality "
            "claim"),
    })
    meta = traj_log.finalize(
        scene_path="procedural bring-up stage (physics ground plane)",
        robot_asset=ROBOT_USD.relative_to(REPO),
        rosbag_path=bag_path.relative_to(REPO) if bag_path else None,
        command_profile=(f"GNM closed loop, clamped to {CL_LIN_MAX} m/s "
                         f"/ {CL_ANG_MAX} rad/s"),
        topics_recorded=EPISODE_TOPICS if bag_path else [],
        extra_meta=cl_meta)
    print(f"[cl] episode finalised: {traj_log.dir}")
    print(f"[cl] steps={meta['steps_logged']} dist={meta['total_distance_m']}m"
          f" z_drift={meta['max_abs_z_drift_m']}m estop={estop} "
          f"reason={stop_reason} clipped={clipped_count} "
          f"nonzero={applied_nonzero}")
    sim.stop()
    app.close()
    raise SystemExit(0)

wheel_idx = [arti.get_dof_index(j) for j in WHEEL_JOINTS]
t_before = sim.current_time
for i in range(800):
    # Full-frame updates pump the ROS graph; physics-only steps actually
    # integrate. Interleave so both happen.
    sim.step(render=(i % 3 == 0))
    cmd = og.Controller.get("/World/ROS2Graph/diff.outputs:velocityCommand")
    if cmd is not None and len(cmd) == 2:
        l, r = float(cmd[0]), float(cmd[1])
        arti.apply_action(ArticulationAction(
            joint_velocities=[l, r, l, r], joint_indices=wheel_idx))
    px, py, pz, pyaw = robot_pose_yaw()
    tw_lin = og.Controller.get("/World/ROS2Graph/twistSub.outputs:linearVelocity")
    tw_ang = og.Controller.get("/World/ROS2Graph/twistSub.outputs:angularVelocity")
    od_lin = og.Controller.get("/World/ROS2Graph/odom.outputs:linearVelocity")
    od_ang = og.Controller.get("/World/ROS2Graph/odom.outputs:angularVelocity")
    if shadow is not None and i % 3 == 0:
        frame = rgb_annot.get_data()
        if frame is not None and getattr(frame, "size", 0) > 0:
            shadow.add_frame(np.asarray(frame)[:, :, :3].copy())
            shadow.infer()
    actual_lin = float(tw_lin[0]) if tw_lin is not None else 0.0
    actual_ang = float(tw_ang[2]) if tw_ang is not None else 0.0
    extra = None
    if shadow is not None:
        extra = dict(shadow.latest)
        extra.update({
            "actual_controller": "scripted_cmd_vel",
            "actual_linear_velocity_cmd": round(actual_lin, 6),
            "actual_angular_velocity_cmd": round(actual_ang, 6),
        })
    traj_log.log_step(
        step_idx=i, sim_time=sim.current_time,
        x=px, y=py, z=pz, yaw=pyaw,
        linear_cmd=actual_lin,
        angular_cmd=actual_ang,
        odom_lin=float(od_lin[0]) if od_lin is not None else 0.0,
        odom_ang=float(od_ang[2]) if od_ang is not None else 0.0,
        image_timestamp=sim.current_time,
        stop_signal=None, safety_state="nominal",
        extra=extra)
print(f"[debug] sim time advanced {sim.current_time - t_before:.2f} s during ROS phase")

odom_probe = og.Controller.get("/World/ROS2Graph/odom.outputs:position")
print(f"[debug] odom node position now: {odom_probe}")
lin = og.Controller.get("/World/ROS2Graph/twistSub.outputs:linearVelocity")
wheels = og.Controller.get("/World/ROS2Graph/diff.outputs:velocityCommand")
print(f"[debug] twist received by graph: {lin}; wheel commands: {wheels}")

if pub is not None:
    pub.terminate()
x1, y1, z1 = robot_xyz()
moved = math.hypot(x1 - x0, y1 - y0)
print(f"[test] displacement after ~13 s of 0.3 m/s forward twist: "
      f"{moved:.3f} m (start=({x0:.3f},{y0:.3f},{z0:.3f}) end=({x1:.3f},{y1:.3f},{z1:.3f}))")

odom_sample = ros_cli("timeout 8 ros2 topic echo --once /odom "
                      "--field pose.pose.position").stdout.strip()
print(f"[test] /odom sample:\n{odom_sample}")

verdict = "PASS" if moved > 0.5 else "FAIL"
print(f"[test] ACCEPTANCE {verdict}: robot {'moved' if moved > 0.5 else 'did not move enough'}")

if bag_proc is not None:
    bag_proc.terminate()
    try:
        bag_proc.wait(timeout=15)
    except Exception:
        bag_proc.kill()
meta = traj_log.finalize(
    scene_path="procedural bring-up stage (physics ground plane)",
    robot_asset=ROBOT_USD.relative_to(REPO),
    rosbag_path=bag_path.relative_to(REPO) if bag_path else None,
    command_profile="external ros2 CLI: 0.3 m/s forward twist at 20 Hz",
    topics_recorded=EPISODE_TOPICS if bag_path else [],
    extra_meta=shadow.summary() if shadow is not None else None)
if shadow is not None:
    print(f"[shadow] frames={shadow.frames_received} attempts={shadow.attempts} "
          f"ok={shadow.successes} fail={shadow.failures} "
          f"mean_lat={sum(shadow.latencies_ms)/len(shadow.latencies_ms):.1f}ms"
          if shadow.latencies_ms else "[shadow] no successful inferences")
print(f"[episode] trajectory log finalised: {traj_log.dir}")
print(f"[episode] steps={meta['steps_logged']} dist={meta['total_distance_m']}m "
      f"z_drift={meta['max_abs_z_drift_m']}m sim_dur={meta['sim_duration_s']}s")

import sys
if "--hold" in sys.argv:
    # Zero the wheels first or the robot keeps its last velocity targets
    # and eventually drives off the edge of the test ground.
    arti.apply_action(ArticulationAction(
        joint_velocities=[0.0] * 4, joint_indices=wheel_idx))
    print("[hold] sim stays up for external DDS probing; kill to stop")
    i = 0
    while True:
        sim.step(render=(i % 3 == 0))
        i += 1

sim.stop()
app.close()
