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
print(f"[debug] sim time advanced {sim.current_time - t_before:.2f} s during ROS phase")

odom_probe = og.Controller.get("/World/ROS2Graph/odom.outputs:position")
print(f"[debug] odom node position now: {odom_probe}")
lin = og.Controller.get("/World/ROS2Graph/twistSub.outputs:linearVelocity")
wheels = og.Controller.get("/World/ROS2Graph/diff.outputs:velocityCommand")
print(f"[debug] twist received by graph: {lin}; wheel commands: {wheels}")

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
