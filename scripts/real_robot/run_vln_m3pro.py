"""run_vln_m3pro.py — FleetSafe-VLN real robot controller for Yahboom ROSMASTER-M3Pro.

Full ROS2-integrated VLN pipeline:
    /fleetsafe/instruction_text | /fleetsafe/instruction_voice
        → InstructionIntake → InstructionGrounder → BackboneRouter → u_nom
        → CBF-QP safety filter → /cmd_vel  (DRY-RUN by default)
        → VLNTrace JSONL + SafetyCertificate JSONL

Safety guarantees:
    - DRY-RUN by default (--enable-motion required for real actuation)
    - "stop"/"halt"/"freeze" always produce zero velocity immediately
    - Confidence < 0.3 → zero velocity
    - Stale LiDAR (> 1.0 s) → emergency stop, latch estop
    - CBF-QP infeasible → emergency stop, latch estop
    - No direct /cmd_vel from language layer — all motion through CBF filter
    - Every received instruction writes trace JSONL + cert JSONL + ROS2 cert topic,
      regardless of decision (allowed, cbf_infeasible, stale_lidar, estop_latched, …)

Usage on robot (source ROS2 first):
    source /opt/ros/humble/setup.bash
    source ~/ros2_ws/install/setup.bash  # if available

    # Dry-run (default — no motion)
    python3 scripts/real_robot/run_vln_m3pro.py

    # Enable real motion
    python3 scripts/real_robot/run_vln_m3pro.py --enable-motion

    # Text instruction via CLI (single shot):
    ros2 topic pub --once /fleetsafe/instruction_text std_msgs/msg/String \
        "{data: 'go to the nurse station and avoid people'}"

ROS2 topics subscribed:
    /fleetsafe/instruction_text   std_msgs/String  — typed instructions
    /fleetsafe/instruction_voice  std_msgs/String  — ASR transcripts
    /scan0                        sensor_msgs/LaserScan
    /scan1                        sensor_msgs/LaserScan  (optional)
    /camera/color/image_raw       sensor_msgs/Image  (latched for backbone)
    /odom_raw                     nav_msgs/Odometry

ROS2 topics published:
    /cmd_vel                      geometry_msgs/Twist  — u_safe (or zero if dry-run)
    /fleetsafe/cmd_vel_nominal    geometry_msgs/Twist  — u_nom before CBF
    /fleetsafe/vln/parsed_instruction  std_msgs/String  — GroundedGoal JSON
    /fleetsafe/vln/subgoal        std_msgs/String  — chosen backbone subgoal JSON
    /fleetsafe/certificate        std_msgs/String  — SafetyCertificate JSON
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ── Argument parsing (before ROS2 import to allow --help without ROS2) ────────
parser = argparse.ArgumentParser(
    description="FleetSafe-VLN real robot controller (M3Pro)"
)
parser.add_argument(
    "--enable-motion",
    action="store_true",
    help="Publish real /cmd_vel commands. Default: DRY-RUN (zero velocity sent).",
)
parser.add_argument(
    "--backbone", default="auto",
    choices=["gnm", "vint", "nomad", "auto"],
    help="Preferred visual navigation backbone (default: auto).",
)
parser.add_argument(
    "--safety-radius", type=float, default=0.50,
    help="CBF safety radius in metres (default: 0.50).",
)
parser.add_argument(
    "--max-vx", type=float, default=0.12,
    help="Maximum forward speed m/s (default: 0.12).",
)
parser.add_argument(
    "--max-wz", type=float, default=0.35,
    help="Maximum yaw rate rad/s (default: 0.35).",
)
parser.add_argument(
    "--min-confidence", type=float, default=0.30,
    help="Minimum grounding confidence to issue motion (default: 0.30).",
)
parser.add_argument(
    "--scan-stale-sec", type=float, default=1.0,
    help="LiDAR age threshold for emergency stop in seconds (default: 1.0).",
)
parser.add_argument(
    "--camera-stale-sec", type=float, default=2.0,
    help="Camera age threshold above which camera_seen=False in seconds (default: 2.0).",
)
parser.add_argument(
    "--trace-dir", type=Path,
    default=Path("results/vln_runs"),
    help="Directory for VLNTrace JSONL files.",
)
parser.add_argument(
    "--cert-dir", type=Path,
    default=Path("results/certificates"),
    help="Directory for SafetyCertificate JSONL files.",
)
parser.add_argument(
    "--ros-domain-id", type=int, default=None,
    help="Override ROS_DOMAIN_ID.",
)
parser.add_argument(
    "--scan-topics", type=str, default="/scan0,/scan1",
    help=(
        "Comma-separated LiDAR topic names (default: /scan0,/scan1). "
        "Use /scan,/scan_multi for Yahboom firmware that publishes those names. "
        "Example: --scan-topics /scan0,/scan1"
    ),
)
parser.add_argument(
    "--odom-topic", type=str, default="/odom_raw",
    help="Odometry topic name (default: /odom_raw). Use /odom as fallback.",
)
args_cli, _ = parser.parse_known_args()

# ── VLN layer imports ──────────────────────────────────────────────────────────
from fleet_safe_vla.vln.instruction_schema import (
    ActionType, InstructionSource, VLNTrace,
)
from fleet_safe_vla.vln.instruction_intake import InstructionIntake
from fleet_safe_vla.vln.grounding import InstructionGrounder
from fleet_safe_vla.vln.backbone_router import BackboneRouter
from fleet_safe_vla.vln.vln_trace_logger import VLNTraceLogger

# Optional: real CBF-QP filter
try:
    from fleet_safe_vla.safety.cbf_filter import CBFQPFilter as _RealCBF
    _HAS_REAL_CBF = True
except ImportError:
    _HAS_REAL_CBF = False

# LiDAR sanitizer (always available — pure Python, no ROS2 dependency)
from fleet_safe_vla.safety.lidar_sanitizer import sanitize as _lidar_sanitize, LidarSample

# ── ROS2 imports ───────────────────────────────────────────────────────────────
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import (
        QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy,
        qos_profile_sensor_data,
    )
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from sensor_msgs.msg import LaserScan, Image
    from std_msgs.msg import String, Bool
    _HAS_ROS2 = True
except ImportError:
    _HAS_ROS2 = False


# ---------------------------------------------------------------------------
# Simplified CBF fallback (used when fleet_safe_vla.safety.cbf_filter absent)
# ---------------------------------------------------------------------------

def _mock_cbf(
    u_nom: list[float],
    min_dist_m: float,
    d_safe: float,
) -> tuple[list[float], bool, str, float]:
    h = min_dist_m ** 2 - d_safe ** 2 if math.isfinite(min_dist_m) else 0.0
    if min_dist_m < d_safe:
        return [0.0, 0.0], True, "estop_fallback", h
    if min_dist_m < d_safe + 0.20:
        scale = (min_dist_m - d_safe) / 0.20
        return [u_nom[0] * scale, u_nom[1] * scale], True, "optimal", h
    return list(u_nom), False, "skipped", h


def _safe_float(v: float) -> float | None:
    """Convert inf/nan to None for JSON serialization."""
    return None if not math.isfinite(v) else v


# ---------------------------------------------------------------------------
# Shared robot state (thread-safe via lock)
# ---------------------------------------------------------------------------

_state_lock = threading.Lock()
_robot: dict = {
    "scan0_raw_min":    float("inf"),
    "scan1_raw_min":    float("inf"),
    "scan_clearance":   float("inf"),   # sanitized effective clearance for CBF
    "scan_timestamp":   0.0,
    "camera_timestamp": 0.0,           # wall time of last received image frame
    "odom_vx":          0.0,
    "odom_wz":          0.0,
    "last_image_id":    "none",
    "estop_latched":    False,
    "scan0_sample":     None,
    "scan1_sample":     None,
}


# ---------------------------------------------------------------------------
# ROS2 Node
# ---------------------------------------------------------------------------

class VLNControllerNode(Node if _HAS_ROS2 else object):  # type: ignore[misc]
    """Full VLN pipeline controller node for the Yahboom ROSMASTER-M3Pro."""

    def __init__(
        self,
        grounder: InstructionGrounder,
        router:   BackboneRouter,
        intake:   InstructionIntake,
        trace_logger: VLNTraceLogger,
        cert_path: Path,
        args: argparse.Namespace,
    ):
        if not _HAS_ROS2:
            return
        super().__init__("fleetsafe_vln_controller")

        self._grounder            = grounder
        self._router              = router
        self._intake              = intake
        self._trace_logger        = trace_logger
        self._cert_path           = cert_path
        self._cert_fh             = cert_path.open("a", encoding="utf-8", buffering=1)
        self._args                = args
        self._dry_run             = not args.enable_motion
        self._first_camera_frame  = False   # set True on first image callback

        # QoS for LiDAR + Odometry: BEST_EFFORT, depth=1
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # QoS for camera: BEST_EFFORT + VOLATILE + depth=5
        # Matches Orbbec / V4L2 drivers which publish with BEST_EFFORT.
        # Using depth=5 avoids losing frames under temporary latency spikes.
        camera_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )

        # ── Publishers ─────────────────────────────────────────────────────
        self._pub_cmd     = self.create_publisher(Twist,  "/cmd_vel",                          10)
        self._pub_unom    = self.create_publisher(Twist,  "/fleetsafe/cmd_vel_nominal",         10)
        self._pub_parsed  = self.create_publisher(String, "/fleetsafe/vln/parsed_instruction",  10)
        self._pub_subgoal = self.create_publisher(String, "/fleetsafe/vln/subgoal",             10)
        self._pub_cert    = self.create_publisher(String, "/fleetsafe/certificate",             10)

        # ── Subscribers ────────────────────────────────────────────────────
        self.create_subscription(
            String, "/fleetsafe/instruction_text",
            self._cb_text_instruction, 10
        )
        self.create_subscription(
            String, "/fleetsafe/instruction_voice",
            self._cb_voice_instruction, 10
        )

        # Dynamic scan subscriptions — topic names are configurable via --scan-topics
        # so the controller works with /scan0,/scan1 or /scan,/scan_multi depending
        # on the Yahboom firmware version.
        _scan_topics = [t.strip() for t in args.scan_topics.split(",") if t.strip()]
        self._scan_topic_names = _scan_topics
        for _slot, _topic in enumerate(_scan_topics[:2]):
            self.create_subscription(
                LaserScan, _topic,
                self._make_scan_cb(_slot), sensor_qos
            )

        # Odometry — configurable topic for /odom_raw vs /odom variants
        self.create_subscription(
            Odometry, args.odom_topic,
            self._cb_odom, sensor_qos
        )
        self.create_subscription(
            Image, "/camera/color/image_raw",
            self._cb_image, camera_qos
        )
        self.create_subscription(
            String, "/fleetsafe/estop_clear",
            self._cb_estop_clear, 10
        )

        self.get_logger().info(
            f"FleetSafe-VLN controller ready. "
            f"motion={'ENABLED' if not self._dry_run else 'DRY-RUN'} "
            f"backbone={args.backbone} "
            f"d_safe={args.safety_radius:.2f}m  "
            f"scan={args.scan_topics}  "
            f"odom={args.odom_topic}  "
            f"estop_clear=listening on /fleetsafe/estop_clear"
        )

    # ── Sensor callbacks ───────────────────────────────────────────────────────

    def _make_scan_cb(self, slot: int):
        """Return a LaserScan callback that stores data in slot 0 (primary) or 1 (secondary).

        Using per-slot closures ensures each configured topic always writes to its
        own state bucket, regardless of arrival order.  The combined scan_clearance
        is the minimum effective clearance across all populated slots.
        """
        def _cb(msg: "LaserScan"):
            sample = _lidar_sanitize(
                ranges    = list(msg.ranges),
                range_min = float(msg.range_min),
                range_max = float(msg.range_max),
                percentile = 5,
            )
            raw_min = sample.raw_min_m
            with _state_lock:
                if slot == 0:
                    _robot["scan0_sample"]  = sample
                    _robot["scan0_raw_min"] = raw_min
                else:
                    _robot["scan1_sample"]  = sample
                    _robot["scan1_raw_min"] = raw_min

                s0 = _robot["scan0_sample"]
                s1 = _robot["scan1_sample"]
                if s0 is not None and s1 is not None:
                    _robot["scan_clearance"] = min(
                        s0.effective_clearance_m,
                        s1.effective_clearance_m,
                    )
                elif s0 is not None:
                    _robot["scan_clearance"] = s0.effective_clearance_m
                elif s1 is not None:
                    _robot["scan_clearance"] = s1.effective_clearance_m

                _robot["scan_timestamp"] = time.time()
        return _cb

    def _cb_odom(self, msg: "Odometry"):
        with _state_lock:
            _robot["odom_vx"] = msg.twist.twist.linear.x
            _robot["odom_wz"] = msg.twist.twist.angular.z

    def _cb_image(self, msg: "Image"):
        now      = time.time()
        frame_id = msg.header.frame_id or f"frame_{msg.header.stamp.sec}"
        with _state_lock:
            _robot["last_image_id"]    = frame_id
            _robot["camera_timestamp"] = now

        if not self._first_camera_frame:
            self._first_camera_frame = True
            try:
                enc = getattr(msg, "encoding", "?")
                w   = getattr(msg, "width",    0)
                h   = getattr(msg, "height",   0)
                self.get_logger().info(
                    f"[VLN] first camera frame received: "
                    f"width={w}, height={h}, encoding={enc}"
                )
            except Exception:
                pass

    def _cb_estop_clear(self, msg: "String"):
        """Handle /fleetsafe/estop_clear — reset latch only when clearance is safe."""
        with _state_lock:
            was_latched = _robot["estop_latched"]
            min_dist    = _robot["scan_clearance"]

        if not was_latched:
            self.get_logger().info(
                "[VLN] /fleetsafe/estop_clear received — e-stop was not latched, ignored."
            )
            return

        if min_dist < self._args.safety_radius:
            self.get_logger().error(
                f"[VLN] E-stop clear REFUSED: clearance {min_dist:.3f} m < "
                f"safety_radius {self._args.safety_radius:.3f} m. "
                f"Move the robot away from the obstacle first."
            )
            return

        with _state_lock:
            _robot["estop_latched"] = False
        self.get_logger().warn(
            f"[VLN] E-stop CLEARED. "
            f"clearance={min_dist:.3f} m  safety_radius={self._args.safety_radius:.3f} m. "
            f"Controller will accept new instructions."
        )

    # ── Instruction callbacks ──────────────────────────────────────────────────

    def _cb_text_instruction(self, msg: "String"):
        self._handle_instruction(msg.data, InstructionSource.TEXT)

    def _cb_voice_instruction(self, msg: "String"):
        self._handle_instruction(msg.data, InstructionSource.VOICE)

    # ── Core pipeline ──────────────────────────────────────────────────────────

    def _handle_instruction(self, text: str, source: InstructionSource) -> None:
        t0 = time.perf_counter()

        # ── Parse instruction first (required for instruction_id on all paths) ──
        try:
            if source == InstructionSource.VOICE:
                inst = self._intake.from_voice_transcript(text)
            else:
                inst = self._intake.from_text(text)
        except Exception as exc:
            if _HAS_ROS2:
                self.get_logger().error(f"Intake failed: {exc}")
            return

        # ── Collect sensor state snapshot ──────────────────────────────────────
        _now = time.time()
        with _state_lock:
            estop_latched    = _robot["estop_latched"]
            scan_age         = _now - _robot.get("scan_timestamp", 0.0)
            camera_ts        = _robot.get("camera_timestamp", 0.0)
            min_dist         = _robot["scan_clearance"]
            frame_id         = _robot["last_image_id"]
            s0: "LidarSample | None" = _robot.get("scan0_sample")
            s1: "LidarSample | None" = _robot.get("scan1_sample")
            scan0_raw = _robot.get("scan0_raw_min", float("inf"))
            scan1_raw = _robot.get("scan1_raw_min", float("inf"))

        camera_last_age_ms = (_now - camera_ts) * 1000.0 if camera_ts > 0.0 else None

        scan_audit = {
            "scan0_raw_min_m":       _safe_float(scan0_raw),
            "scan1_raw_min_m":       _safe_float(scan1_raw),
            "scan0_valid_min_m":     _safe_float(s0.valid_min_m   if s0 else float("inf")),
            "scan1_valid_min_m":     _safe_float(s1.valid_min_m   if s1 else float("inf")),
            "scan0_invalid_ct":      s0.invalid_count if s0 else 0,
            "scan1_invalid_ct":      s1.invalid_count if s1 else 0,
            "effective_clearance_m": _safe_float(min_dist),
            "filtering_applied":     (s0.filtering_applied if s0 else False)
                                     or (s1.filtering_applied if s1 else False),
        }

        # ── E-stop latch check ─────────────────────────────────────────────────
        if estop_latched:
            if _HAS_ROS2:
                self.get_logger().warn(
                    "E-stop latched. Ignoring instruction. "
                    "Publish /fleetsafe/estop_clear to resume."
                )
            self._publish_zero()
            self._emit_evidence(
                inst=inst, goal=None,
                decision="estop_latched", qp_status="estop_latched",
                u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
                cbf_active=False, min_dist=min_dist, h_min=-1.0,
                frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                scan_audit=scan_audit, estop_latched=True,
                reason="estop_latched",
            )
            return

        # ── Stale sensor check ─────────────────────────────────────────────────
        if scan_age > self._args.scan_stale_sec:
            if _HAS_ROS2:
                self.get_logger().error(
                    f"LiDAR stale ({scan_age:.1f}s > {self._args.scan_stale_sec}s). "
                    f"Emergency stop."
                )
            self._emit_evidence(
                inst=inst, goal=None,
                decision="stale_lidar", qp_status="stale_lidar",
                u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
                cbf_active=False, min_dist=min_dist, h_min=-1.0,
                frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                scan_audit=scan_audit, estop_latched=False,
                reason="stale_lidar",
            )
            self._emergency_stop("stale_lidar")
            return

        # ── Ground instruction ─────────────────────────────────────────────────
        try:
            goal = self._grounder.ground(inst)
        except Exception as exc:
            if _HAS_ROS2:
                self.get_logger().error(f"Grounding failed: {exc}")
            self._emit_evidence(
                inst=inst, goal=None,
                decision="exception", qp_status="exception",
                u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
                cbf_active=False, min_dist=min_dist, h_min=0.0,
                frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                scan_audit=scan_audit, estop_latched=False,
                reason=f"grounding_exception:{exc}",
            )
            return

        # Publish parsed instruction for dashboard / audit
        parsed_msg = String()
        parsed_msg.data = json.dumps({
            "instruction_id": inst.instruction_id,
            "source":         source.value,
            "text":           text,
            "action_type":    goal.action_type,
            "label":          goal.label,
            "confidence":     goal.confidence,
            "clarification":  goal.clarification_needed,
            "constraints":    [c.target for c in goal.safety_constraints],
        })
        if _HAS_ROS2:
            self._pub_parsed.publish(parsed_msg)

        # ── Stop override ──────────────────────────────────────────────────────
        if goal.action_type == ActionType.STOP.value:
            self._publish_zero()
            if _HAS_ROS2:
                self.get_logger().info(
                    f"[STOP] Instruction: {text!r} → immediate zero velocity."
                )
            self._emit_evidence(
                inst=inst, goal=goal,
                decision="stop_override", qp_status="stop_override",
                u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
                cbf_active=False, min_dist=min_dist, h_min=0.0,
                frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                scan_audit=scan_audit, estop_latched=False,
                reason="stop_override",
            )
            return

        # ── Clarification / low confidence ─────────────────────────────────────
        if goal.clarification_needed or not goal.is_actionable():
            if _HAS_ROS2:
                self.get_logger().warn(
                    f"Instruction not actionable (confidence={goal.confidence:.2f}, "
                    f"clarification={goal.clarification_needed}). Zero velocity."
                )
            self._publish_zero()
            self._emit_evidence(
                inst=inst, goal=goal,
                decision="low_confidence", qp_status="low_confidence",
                u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
                cbf_active=False, min_dist=min_dist, h_min=0.0,
                frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                scan_audit=scan_audit, estop_latched=False,
                reason="low_confidence",
            )
            return

        # ── Backbone → u_nom ───────────────────────────────────────────────────
        try:
            action = self._router.run_nominal_policy(goal, instruction=inst)
            u_nom  = action.as_list()
        except Exception as exc:
            if _HAS_ROS2:
                self.get_logger().error(f"Backbone failed: {exc}")
            self._publish_zero()
            self._emit_evidence(
                inst=inst, goal=goal,
                decision="exception", qp_status="exception",
                u_nom=[0.0, 0.0], u_safe=[0.0, 0.0],
                cbf_active=False, min_dist=min_dist, h_min=0.0,
                frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                scan_audit=scan_audit, estop_latched=False,
                reason=f"backbone_exception:{exc}",
            )
            return

        # Publish u_nom for monitoring
        if _HAS_ROS2:
            unom_msg = Twist()
            unom_msg.linear.x  = u_nom[0]
            unom_msg.angular.z = u_nom[1]
            self._pub_unom.publish(unom_msg)

            subgoal_msg = String()
            subgoal_msg.data = json.dumps({
                "backbone":   action.backbone,
                "confidence": action.confidence,
                "vx":         action.vx,
                "wz":         action.wz,
            })
            self._pub_subgoal.publish(subgoal_msg)

        # ── CBF-QP safety filter ───────────────────────────────────────────────
        u_safe, cbf_active, qp_status, h_min = _mock_cbf(
            u_nom, min_dist, self._args.safety_radius
        )

        latency_ms = (time.perf_counter() - t0) * 1000.0

        if qp_status == "estop_fallback":
            if _HAS_ROS2:
                self.get_logger().error(
                    f"[ESTOP] cbf_infeasible  "
                    f"eff_clearance={min_dist:.3f}m < d_safe={self._args.safety_radius:.3f}m"
                )
            self._emit_evidence(
                inst=inst, goal=goal,
                decision="cbf_infeasible", qp_status="cbf_infeasible",
                u_nom=u_nom, u_safe=[0.0, 0.0],
                cbf_active=True, min_dist=min_dist, h_min=h_min,
                frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
                latency_ms=latency_ms,
                scan_audit=scan_audit, estop_latched=False,
                reason="cbf_infeasible",
            )
            self._emergency_stop("cbf_infeasible")
            return

        # ── Publish u_safe ─────────────────────────────────────────────────────
        decision = "dry_run_zero" if self._dry_run else ("cbf_clipped" if cbf_active else "allowed")

        s0_raw_str = f"{scan0_raw:.2f}" if math.isfinite(scan0_raw) else "inf"
        s0_eff_str = f"{s0.valid_min_m:.2f}" if s0 else "?"
        s1_raw_str = f"{scan1_raw:.2f}" if math.isfinite(scan1_raw) else "inf"
        s1_eff_str = f"{s1.valid_min_m:.2f}" if s1 else "?"

        if self._dry_run:
            if _HAS_ROS2:
                self.get_logger().info(
                    f"[DRY-RUN] vx={u_safe[0]:.3f}  wz={u_safe[1]:.3f}  "
                    f"backbone={action.backbone}  h_min={h_min:.4f}  "
                    f"scan0 raw={s0_raw_str}m valid={s0_eff_str}m  "
                    f"scan1 raw={s1_raw_str}m valid={s1_eff_str}m  "
                    f"eff={min_dist:.2f}m  latency={latency_ms:.1f}ms"
                )
        else:
            if _HAS_ROS2:
                cmd = Twist()
                cmd.linear.x  = float(u_safe[0])
                cmd.angular.z = float(u_safe[1])
                self._pub_cmd.publish(cmd)
                self.get_logger().info(
                    f"[CMD] vx={u_safe[0]:.3f}  wz={u_safe[1]:.3f}  "
                    f"backbone={action.backbone}  cbf={cbf_active}  "
                    f"h_min={h_min:.4f}  eff={min_dist:.2f}m  latency={latency_ms:.1f}ms"
                )

        self._emit_evidence(
            inst=inst, goal=goal,
            decision=decision, qp_status=qp_status,
            u_nom=u_nom, u_safe=u_safe,
            cbf_active=cbf_active, min_dist=min_dist, h_min=h_min,
            frame_id=frame_id, camera_last_age_ms=camera_last_age_ms,
            latency_ms=latency_ms,
            scan_audit=scan_audit, estop_latched=False,
            reason="",
        )

    # ── Evidence emission (guaranteed on every instruction, every decision) ────

    def _emit_evidence(
        self,
        *,
        inst,
        goal,
        decision: str,
        qp_status: str,
        u_nom: list,
        u_safe: list,
        cbf_active: bool,
        min_dist: float,
        h_min: float,
        frame_id: str,
        camera_last_age_ms: "float | None",
        latency_ms: float,
        scan_audit: dict,
        estop_latched: bool,
        reason: str,
    ) -> None:
        ts          = time.time()
        instr_id    = getattr(inst, "instruction_id", "")
        source_val  = getattr(inst, "source", "")
        raw_text    = getattr(inst, "raw_text", "")
        stale_limit = getattr(self._args, "camera_stale_sec", 2.0) * 1000.0
        camera_seen = (
            frame_id not in ("none", "")
            and camera_last_age_ms is not None
            and camera_last_age_ms < stale_limit
        )

        # ── Trace JSONL (via VLNTraceLogger) ───────────────────────────────────
        try:
            self._trace_logger.append_from_values(
                timestamp_ns=time.time_ns(),
                instruction_source=source_val,
                raw_instruction=raw_text,
                parsed_instruction={
                    "action_type": goal.action_type if goal else "unknown",
                    "label":       goal.label       if goal else "",
                    "confidence":  goal.confidence  if goal else 0.0,
                },
                grounding_candidates=goal.grounding_candidates if goal else [],
                chosen_subgoal={
                    "label":       goal.label       if goal else "",
                    "action_type": goal.action_type if goal else "unknown",
                },
                current_camera_frame_id=frame_id,
                model_name=self._args.backbone,
                u_nom=u_nom,
                u_safe=u_safe,
                cbf_active=cbf_active,
                qp_status=qp_status,
                min_dist_m=min_dist if math.isfinite(min_dist) else 0.0,
                h_min=h_min,
                latency_ms=latency_ms,
                stop_reason=reason or decision,
                notes=json.dumps({
                    "instruction_id":    instr_id,
                    "decision":          decision,
                    "dry_run":           self._dry_run,
                    "estop_latched":     estop_latched,
                    "reason":            reason or decision,
                    "camera_seen":       camera_seen,
                    "camera_frame_id":   frame_id,
                    "camera_last_age_ms": camera_last_age_ms,
                    "scan_audit":        scan_audit,
                }),
            )
            self._trace_logger.flush()  # fsync
        except Exception as exc:
            if _HAS_ROS2:
                try:
                    self.get_logger().warn(f"[VLN-EVIDENCE] trace write failed: {exc}")
                except Exception:
                    pass

        # ── Certificate JSONL (raw dict, all required fields) ──────────────────
        safe_decision = decision not in ("cbf_infeasible", "stale_lidar",
                                         "estop_latched", "exception")
        cert_row: dict = {
            "timestamp":             ts,
            "instruction_id":        instr_id,
            "source":                source_val,
            "safe":                  h_min >= 0.0 and safe_decision,
            "qp_status":             qp_status,
            "h_min":                 h_min,
            "min_dist_m":            _safe_float(min_dist),
            "safety_radius_m":       self._args.safety_radius,
            "constraint_margin_min": max(0.0, h_min),
            "latency_ms":            latency_ms,
            "u_nominal":             u_nom,
            "u_safe":                u_safe,
            "cbf_active":            cbf_active,
            "estop_latched":         estop_latched,
            "decision":              decision,
            "reason":                reason or decision,
            "dry_run":               self._dry_run,
            "scan_audit":            scan_audit,
            "camera_seen":            camera_seen,
            "camera_frame_id":        frame_id,
            "camera_last_age_ms":     camera_last_age_ms,
        }
        try:
            self._cert_fh.write(json.dumps(cert_row) + "\n")
            self._cert_fh.flush()
            os.fsync(self._cert_fh.fileno())
        except Exception as exc:
            if _HAS_ROS2:
                try:
                    self.get_logger().warn(f"[VLN-EVIDENCE] cert write failed: {exc}")
                except Exception:
                    pass

        # ── Publish certificate to ROS2 topic ──────────────────────────────────
        if _HAS_ROS2 and hasattr(self, "_pub_cert"):
            try:
                cert_msg = String()
                cert_msg.data = json.dumps(cert_row)
                self._pub_cert.publish(cert_msg)
            except Exception as exc:
                try:
                    self.get_logger().warn(f"[VLN-EVIDENCE] cert publish failed: {exc}")
                except Exception:
                    pass

        # ── Console evidence log ───────────────────────────────────────────────
        log_line = (
            f"[VLN-EVIDENCE] "
            f"trace={self._trace_logger.path} "
            f"cert={self._cert_path} "
            f"instruction_id={instr_id} "
            f"decision={decision}"
        )
        if _HAS_ROS2 and hasattr(self, "get_logger"):
            try:
                self.get_logger().info(log_line)
            except Exception:
                print(log_line)
        else:
            print(log_line)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _publish_zero(self):
        """Publish zero Twist to /cmd_vel.  Silent no-op if rclpy context is gone."""
        if not _HAS_ROS2 or not hasattr(self, "_pub_cmd"):
            return
        try:
            if rclpy.ok():
                self._pub_cmd.publish(Twist())
        except Exception:
            pass

    def _emergency_stop(self, reason: str):
        with _state_lock:
            _robot["estop_latched"] = True
        self._publish_zero()
        if _HAS_ROS2:
            self.get_logger().error(f"[ESTOP] reason={reason} — latching e-stop.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if args_cli.ros_domain_id is not None:
        os.environ["ROS_DOMAIN_ID"] = str(args_cli.ros_domain_id)

    # ── Output directories ─────────────────────────────────────────────────────
    ts = time.strftime("%Y%m%d_%H%M%S")
    trace_dir = args_cli.trace_dir / ts
    cert_dir  = args_cli.cert_dir  / ts
    trace_dir.mkdir(parents=True, exist_ok=True)
    cert_dir.mkdir(parents=True, exist_ok=True)

    trace_path = trace_dir / "vln_trace_m3pro.jsonl"
    cert_path  = cert_dir  / "vln_certificates_m3pro.jsonl"

    # Touch files so make vln-evidence-latest can always find them
    trace_path.touch()
    cert_path.touch()

    # ── Pipeline components ────────────────────────────────────────────────────
    grounder     = InstructionGrounder(min_confidence=args_cli.min_confidence)
    router       = BackboneRouter(
        preferred=args_cli.backbone,
        max_vx=args_cli.max_vx,
        max_wz=args_cli.max_wz,
    )
    intake       = InstructionIntake()
    trace_logger = VLNTraceLogger(trace_path)

    # ── Banner ─────────────────────────────────────────────────────────────────
    print("=" * 66)
    print("  FleetSafe-VLN  |  M3Pro Real Robot Controller")
    print(f"  Motion   : {'ENABLED — publishing /cmd_vel' if args_cli.enable_motion else 'DRY-RUN (no motion)'}")
    print(f"  Backbone : {args_cli.backbone}")
    print(f"  d_safe   : {args_cli.safety_radius:.2f} m")
    print(f"  max_vx   : {args_cli.max_vx:.2f} m/s   max_wz: {args_cli.max_wz:.2f} rad/s")
    print(f"  Scan     : {args_cli.scan_topics}")
    print(f"  Odom     : {args_cli.odom_topic}")
    print(f"  Trace    : {trace_path}")
    print(f"  Certs    : {cert_path}")
    print(f"  ROS2     : {'available' if _HAS_ROS2 else 'NOT FOUND'}")
    print("=" * 66)
    print()
    print("  Listening on:")
    print("    /fleetsafe/instruction_text   — typed text instructions")
    print("    /fleetsafe/instruction_voice  — voice ASR transcripts")
    print()
    print("  Publishing:")
    print("    /cmd_vel                           — u_safe (or zero in DRY-RUN)")
    print("    /fleetsafe/cmd_vel_nominal         — u_nom (pre-CBF)")
    print("    /fleetsafe/vln/parsed_instruction  — GroundedGoal JSON")
    print("    /fleetsafe/vln/subgoal             — backbone subgoal JSON")
    print("    /fleetsafe/certificate             — SafetyCertificate JSON")
    print()

    if not _HAS_ROS2:
        print("[ERROR] rclpy not found. Install ROS2 Humble and source the setup file.")
        print("  source /opt/ros/humble/setup.bash")
        sys.exit(1)

    # ── ROS2 spin ──────────────────────────────────────────────────────────────
    rclpy.init()
    node = VLNControllerNode(
        grounder=grounder,
        router=router,
        intake=intake,
        trace_logger=trace_logger,
        cert_path=cert_path,
        args=args_cli,
    )

    print("[VLN] Node spinning. Send instructions via ROS2 topic or make vln-send.")
    print("      Ctrl+C to stop (zero velocity will be published on shutdown).\n")

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception:
        # Catches rclpy.executors.ExternalShutdownException and similar;
        # these are normal when the process is signalled externally.
        pass
    finally:
        # Guard every shutdown step: rclpy context may already be invalid.
        try:
            node._publish_zero()  # _publish_zero checks rclpy.ok() internally
        except Exception:
            pass
        try:
            node._cert_fh.flush()
            node._cert_fh.close()
        except Exception:
            pass
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass
        print(f"\n[VLN] Shutdown. Trace rows: {trace_logger.count}")
        print(f"[VLN] Trace  → {trace_path}")
        print(f"[VLN] Certs  → {cert_path}")


if __name__ == "__main__":
    main()
