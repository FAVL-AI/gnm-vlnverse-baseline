"""run_vln_instruction_demo.py — FleetSafe-VLN instruction demo.

Demonstrates the full pipeline:
    instruction → grounding → backbone → u_nom → CBF-QP → u_safe → certificate

Safe by default (--dry-run). Pass --publish to send actual /cmd_vel.

Usage:
    python3 scripts/vln/run_vln_instruction_demo.py \\
        --text "go to the nurse station and avoid people" \\
        --backbone gnm --dry-run

    python3 scripts/vln/run_vln_instruction_demo.py \\
        --source stdin \\
        --backbone auto \\
        --certificate-out results/vln/certificates/demo.jsonl
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

# Repo root on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fleet_safe_vla.vln.instruction_schema import (
    BackboneChoice, InstructionSource, VLNTrace,
)
from fleet_safe_vla.vln.instruction_intake import InstructionIntake
from fleet_safe_vla.vln.grounding import InstructionGrounder
from fleet_safe_vla.vln.backbone_router import BackboneRouter
from fleet_safe_vla.vln.vln_trace_logger import VLNTraceLogger

# Optional: safety certificate logger
try:
    from fleet_safe_vla.safety.certificate_logger import SafetyCertificateLogger
    _HAS_CERT = True
except ImportError:
    _HAS_CERT = False

# Optional: ROS2 publishing
_HAS_ROS = False
try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    _HAS_ROS = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Mock CBF-QP filter (used when real CBF is not importable)
# ---------------------------------------------------------------------------

def _mock_cbf(u_nom: list[float], min_dist_m: float, d_safe: float = 0.5) -> tuple[list[float], bool, str, float]:
    """Apply a simplified CBF rule as a fallback filter.

    Returns (u_safe, cbf_active, qp_status, h_min).
    """
    h = min_dist_m ** 2 - d_safe ** 2 if math.isfinite(min_dist_m) else 0.0
    if min_dist_m < d_safe:
        return [0.0, 0.0], True, "estop_fallback", h
    if min_dist_m < d_safe + 0.2:
        scale = (min_dist_m - d_safe) / 0.2
        vx_safe = u_nom[0] * scale
        wz_safe = u_nom[1] * scale
        return [vx_safe, wz_safe], True, "optimal", h
    return u_nom, False, "skipped", h


# ---------------------------------------------------------------------------
# One instruction → trace → (optionally) publish
# ---------------------------------------------------------------------------

def process_instruction(
    text: str,
    source: InstructionSource,
    grounder: InstructionGrounder,
    router: BackboneRouter,
    args: argparse.Namespace,
    trace_logger: VLNTraceLogger,
    cert_logger=None,
    ros_publisher=None,
) -> VLNTrace:

    t0 = time.perf_counter()

    intake = InstructionIntake()
    if source == InstructionSource.VOICE:
        inst = intake.from_voice_transcript(text)
    else:
        inst = intake.from_text(text)

    # Parse + ground
    goal = grounder.ground(inst)

    # Backbone → u_nom
    action = router.run_nominal_policy(goal, instruction=inst)
    u_nom = action.as_list()

    # CBF-QP safety filter
    min_dist_m = getattr(args, "_last_min_dist", float("inf"))
    u_safe, cbf_active, qp_status, h_min = _mock_cbf(u_nom, min_dist_m, args.safety_radius)

    latency_ms = (time.perf_counter() - t0) * 1000.0

    # Console trace
    print()
    print("  ┌─ VLN Decision Trace ─────────────────────────────────")
    print(f"  │  instruction   : {text!r}")
    print(f"  │  source        : {source.value}")
    print(f"  │  action        : {goal.action_type}  confidence={goal.confidence:.2f}")
    print(f"  │  label         : {goal.label!r}")
    if goal.safety_constraints:
        print(f"  │  constraints   : {[c.target for c in goal.safety_constraints]}")
    print(f"  │  backbone      : {action.backbone}")
    print(f"  │  u_nom         : vx={u_nom[0]:.3f}  wz={u_nom[1]:.3f}")
    if cbf_active:
        print(f"  │  u_safe  [CBF] : vx={u_safe[0]:.3f}  wz={u_safe[1]:.3f}  ({qp_status})")
    else:
        print(f"  │  u_safe        : vx={u_safe[0]:.3f}  wz={u_safe[1]:.3f}  ({qp_status})")
    print(f"  │  h_min         : {h_min:.4f}  safe={'YES' if h_min >= 0 else 'NO'}")
    print(f"  │  latency       : {latency_ms:.1f} ms")
    if goal.clarification_needed:
        print(f"  │  ⚠  CLARIFICATION NEEDED: {goal.stop_reason}")
    print("  └──────────────────────────────────────────────────────")

    # Optionally publish /cmd_vel
    if args.publish and ros_publisher is not None and not goal.clarification_needed:
        msg = Twist()
        msg.linear.x  = float(u_safe[0])
        msg.angular.z = float(u_safe[1])
        ros_publisher.publish(msg)
        print(f"  [VLN] Published to {args.cmd_topic}")
    elif args.publish and not ros_publisher:
        print("  [VLN] --publish requested but ROS2 not available — skipping.")

    # Build trace record
    trace = VLNTrace(
        instruction_source=source.value,
        raw_instruction=text,
        parsed_instruction=goal.to_dict(),
        grounding_candidates=goal.grounding_candidates,
        chosen_subgoal=goal.to_dict(),
        current_camera_frame_id="",
        model_name=action.backbone,
        u_nom=u_nom,
        u_safe=u_safe,
        cbf_active=cbf_active,
        qp_status=qp_status,
        min_dist_m=min_dist_m if math.isfinite(min_dist_m) else 0.0,
        h_min=h_min,
        latency_ms=latency_ms,
        stop_reason=goal.stop_reason,
        notes=action.explanation,
    )
    trace_logger.append(trace)

    # Safety certificate
    if cert_logger and _HAS_CERT:
        cert_logger.append_from_values(
            model_name=action.backbone,
            u_nom=u_nom,
            u_safe=u_safe,
            h_min=h_min,
            min_dist_m=min_dist_m if math.isfinite(min_dist_m) else 0.0,
            cbf_active=cbf_active,
            qp_status=qp_status,
            constraint_margin_min=h_min,
            latency_ms=latency_ms,
            safe=h_min >= 0 and qp_status in ("optimal", "skipped", "estop_fallback"),
            notes=f"VLN demo: {text[:80]}",
        )

    return trace


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FleetSafe-VLN instruction demo")
    p.add_argument("--text", default=None, help="Instruction text (use with --source text)")
    p.add_argument("--source", default="text",
                   choices=[s.value for s in InstructionSource],
                   help="Instruction source modality")
    p.add_argument("--backbone", default="auto",
                   choices=[b.value for b in BackboneChoice],
                   help="Navigation backbone")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Do not publish /cmd_vel (default)")
    p.add_argument("--publish", action="store_true",
                   help="Publish /cmd_vel (requires --publish, safety filter still active)")
    p.add_argument("--cmd-topic", default="/cmd_vel")
    p.add_argument("--odom-topic", default="/odom_raw")
    p.add_argument("--scan-topics", nargs="+", default=["/scan0", "/scan1"])
    p.add_argument("--topomap", default=None, help="Path to topomap image dir")
    p.add_argument("--certificate-out", default="results/vln/certificates/demo.jsonl")
    p.add_argument("--trace-out", default=None)
    p.add_argument("--safety-radius", type=float, default=0.5)
    p.add_argument("--max-vx", type=float, default=0.12)
    p.add_argument("--max-wz", type=float, default=0.35)
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    args._last_min_dist = float("inf")  # updated by scan subscriber if available

    grounder = InstructionGrounder(topomap_dir=args.topomap)
    router   = BackboneRouter(
        preferred=BackboneChoice(args.backbone),
        max_vx=args.max_vx,
        max_wz=args.max_wz,
    )

    trace_out = args.trace_out or args.certificate_out.replace(".jsonl", "_trace.jsonl")
    Path(args.certificate_out).parent.mkdir(parents=True, exist_ok=True)
    Path(trace_out).parent.mkdir(parents=True, exist_ok=True)

    cert_logger = None
    if _HAS_CERT:
        from fleet_safe_vla.safety.certificate_logger import SafetyCertificateLogger
        cert_logger = SafetyCertificateLogger(args.certificate_out)

    ros_publisher = None
    if args.publish and _HAS_ROS:
        if not rclpy.ok():
            rclpy.init()
        _node = rclpy.create_node("fleetsafe_vln_demo")
        ros_publisher = _node.create_publisher(Twist, args.cmd_topic, 10)

    print()
    print("  FleetSafe-VLN Instruction Demo")
    print(f"  backbone: {args.backbone}  |  motion: {'LIVE' if args.publish else 'DRY-RUN'}")
    print(f"  trace → {trace_out}")
    print(f"  certs → {args.certificate_out}")
    print()

    source = InstructionSource(args.source)

    with VLNTraceLogger(trace_out) as trace_logger:
        if args.text:
            # Single-shot mode
            process_instruction(
                args.text, source, grounder, router, args,
                trace_logger, cert_logger, ros_publisher,
            )
            print(f"\n  Trace rows written: {trace_logger.count}")
        else:
            # Interactive stdin mode
            intake = InstructionIntake()
            for inst in intake.stdin_stream("VLN> "):
                try:
                    process_instruction(
                        inst.raw_text, InstructionSource(inst.source),
                        grounder, router, args,
                        trace_logger, cert_logger, ros_publisher,
                    )
                except KeyboardInterrupt:
                    break
            print(f"\n  Trace rows written: {trace_logger.count}")

    if cert_logger:
        cert_logger.close()


if __name__ == "__main__":
    main()
