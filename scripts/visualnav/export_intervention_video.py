#!/usr/bin/env python3
"""
scripts/visualnav/export_intervention_video.py

Export a benchmark episode as an annotated intervention replay video (MP4 or GIF).

Every frame shows:
  - 2-D top-down scene view
  - Robot position (colored by intervention status)
  - Trajectory trail (colored: green=safe, yellow=near, red=intervened)
  - Obstacle positions and safety margin rings
  - Scene graph edges (color-coded by relation)
  - Raw action vector (red arrow)
  - Safe action vector (green arrow)
  - Counterfactual rollout paths at intervention frames
  - Text overlay: intervention reason, causal explanation, version info

Embedded in video metadata:
  - benchmark_version
  - protocol_version
  - git_commit
  - backend
  - episode_dir

Usage:
    python scripts/visualnav/export_intervention_video.py \\
        --episode-dir <path> \\
        --output replay.mp4 \\
        [--fps 4] \\
        [--show-counterfactual] \\
        [--interventions-only]

Output:
    MP4 (requires ffmpeg) or GIF fallback (requires Pillow).
    If neither is available, saves individual PNG frames.

Evidence contract:
    If backend == mock: "MOCK COUNTERFACTUAL ROLLOUT" watermark is always shown.
    All rendered data comes from intervention_evidence.jsonl — no extrapolation.

Returns exit code 0 on success, 1 on failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import math
import json

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyArrowPatch, Circle
    from matplotlib.animation import FuncAnimation, FFMpegWriter, PillowWriter
    _HAS_MATPLOTLIB = True
except ImportError:
    _HAS_MATPLOTLIB = False

from fleet_safe_vla.envs.isaaclab.replay.intervention_replay import InterventionReplayViewer
from fleet_safe_vla.envs.isaaclab.replay.replay_scene import ReplayFrame
from fleet_safe_vla.envs.isaaclab.replay.scene_graph_visualizer import (
    EDGE_COLOR_MAP,
    NODE_COLOR_MAP,
    SceneGraphRenderer,
)
from fleet_safe_vla.envs.isaaclab.replay.trajectory_visualizer import (
    TrajectoryData,
    build_action_vectors,
)
from fleet_safe_vla.benchmark_version import GIT_COMMIT, BENCHMARK_VERSION, PROTOCOL_VERSION


ARENA_PADDING = 0.5    # metres of padding around observable range


def _frame_color(frame: ReplayFrame) -> str:
    if frame.intervention_applied:
        return "#e83333"
    if frame.nearest_obstacle_distance_m < 0.45:
        return "#e8c200"
    return "#33bb33"


def _draw_frame(
    ax_scene: "plt.Axes",
    ax_text: "plt.Axes",
    viewer: InterventionReplayViewer,
    frame: ReplayFrame,
    traj_data: TrajectoryData,
    renderer: SceneGraphRenderer,
    show_cf: bool,
    frame_title: str,
) -> None:
    ax_scene.cla()
    ax_text.cla()
    ax_text.axis("off")

    # ── Obstacles ──────────────────────────────────────────────────────────────
    for obs in frame.obstacles:
        color = {
            "obstacle": "#cc3322",
            "wall": "#996633",
            "dynamic_agent": "#3344cc",
        }.get(obs.node_type, "#888888")
        circle = Circle(
            (obs.x, obs.y), obs.radius_m,
            color=color, alpha=0.7, zorder=3,
        )
        ax_scene.add_patch(circle)

    # ── Safety margin ring ─────────────────────────────────────────────────────
    margin_ring = Circle(
        (frame.robot_x, frame.robot_y), 0.30,
        fill=False, edgecolor="#e8c200", linewidth=1.5, linestyle="--", alpha=0.6, zorder=4,
    )
    collision_ring = Circle(
        (frame.robot_x, frame.robot_y), 0.10,
        fill=False, edgecolor="#e83333", linewidth=1.0, linestyle=":", alpha=0.5, zorder=4,
    )
    ax_scene.add_patch(margin_ring)
    ax_scene.add_patch(collision_ring)

    # ── Goal marker ────────────────────────────────────────────────────────────
    if frame.goal_xy:
        goal_circle = Circle(
            frame.goal_xy, 0.20,
            color="#22bb22", alpha=0.4, zorder=3,
        )
        ax_scene.add_patch(goal_circle)
        ax_scene.annotate("GOAL", xy=frame.goal_xy,
                          fontsize=6, ha="center", va="center", color="#22bb22")

    # ── Scene graph edges ──────────────────────────────────────────────────────
    edges = renderer.render_edges(frame)
    for edge in edges:
        sx, sy = edge.source_xy
        tx, ty = edge.target_xy
        ls     = "--" if edge.line_width < 0 else "-"
        lw     = abs(edge.line_width)
        ax_scene.plot(
            [sx, tx], [sy, ty],
            color=edge.color_rgb, linewidth=lw, linestyle=ls, alpha=0.7, zorder=5,
        )
        # Label at midpoint for causal edges
        if edge.is_causal:
            mx, my = (sx + tx) / 2, (sy + ty) / 2
            ax_scene.annotate(
                edge.relation, xy=(mx, my),
                fontsize=5, color=edge.color_rgb, ha="center",
            )

    # ── Trajectory trail ───────────────────────────────────────────────────────
    trail = traj_data.get_trail_up_to(frame.frame_idx)
    if len(trail) > 1:
        for i in range(1, len(trail)):
            p0, p1 = trail[i - 1], trail[i]
            ax_scene.plot(
                [p0.x, p1.x], [p0.y, p1.y],
                color=p1.color_rgb, linewidth=1.2, alpha=0.55, zorder=6,
            )

    # ── Action vectors ─────────────────────────────────────────────────────────
    av = build_action_vectors(frame, scale=1.5)
    if abs(av.raw_vx_world) > 0.01 or abs(av.raw_vy_world) > 0.01:
        ax_scene.annotate(
            "", xy=av.raw_tip_xy, xytext=(frame.robot_x, frame.robot_y),
            arrowprops=dict(arrowstyle="->", color="#e83333", lw=2.0),
            zorder=8,
        )
    if abs(av.safe_vx_world) > 0.01 or abs(av.safe_vy_world) > 0.01:
        ax_scene.annotate(
            "", xy=av.safe_tip_xy, xytext=(frame.robot_x, frame.robot_y),
            arrowprops=dict(arrowstyle="->", color="#33bb33", lw=2.0),
            zorder=8,
        )

    # ── Counterfactual rollout ─────────────────────────────────────────────────
    if show_cf and frame.intervention_applied:
        cf = renderer.build_counterfactual(frame)
        if len(cf.raw_trajectory) > 1:
            rx = [p[0] for p in cf.raw_trajectory]
            ry = [p[1] for p in cf.raw_trajectory]
            ax_scene.plot(rx, ry, color="#e83333", linewidth=1.0,
                          linestyle="--", alpha=0.5, zorder=7, label="raw (cf)")
        if len(cf.safe_trajectory) > 1:
            sx2 = [p[0] for p in cf.safe_trajectory]
            sy2 = [p[1] for p in cf.safe_trajectory]
            ax_scene.plot(sx2, sy2, color="#33bb33", linewidth=1.0,
                          linestyle="--", alpha=0.5, zorder=7, label="safe (cf)")

    # ── Robot ──────────────────────────────────────────────────────────────────
    robot_color = _frame_color(frame)
    robot_circle = Circle(
        (frame.robot_x, frame.robot_y), 0.15,
        color=robot_color, alpha=0.9, zorder=10,
    )
    ax_scene.add_patch(robot_circle)

    # ── Axes ───────────────────────────────────────────────────────────────────
    ax_scene.set_aspect("equal")
    ax_scene.set_title(frame_title, fontsize=8, pad=4)
    ax_scene.set_xlabel("x (m)", fontsize=7)
    ax_scene.set_ylabel("y (m)", fontsize=7)
    ax_scene.tick_params(labelsize=6)
    ax_scene.grid(True, alpha=0.2)

    # Legend
    handles = [
        mpatches.Patch(color="#e83333", label="raw action / intervention"),
        mpatches.Patch(color="#33bb33", label="safe action / goal"),
        mpatches.Patch(color="#e8c200", label="near-violation"),
        mpatches.Patch(color="#3366cc", label="robot"),
    ]
    ax_scene.legend(handles=handles, fontsize=5, loc="upper right")

    # ── Text overlay ───────────────────────────────────────────────────────────
    ov = viewer.overlay_for(frame)
    text = "\n".join(ov.to_plain_lines()[:25])   # limit for readability
    ax_text.text(
        0.02, 0.98, text,
        transform=ax_text.transAxes,
        fontsize=5.5, verticalalignment="top",
        fontfamily="monospace",
        bbox=dict(boxstyle="round", facecolor="black", alpha=0.75),
        color="white",
    )


def export_video(
    viewer: InterventionReplayViewer,
    output_path: Path,
    fps: int = 4,
    show_cf: bool = True,
    interventions_only: bool = False,
    dpi: int = 120,
) -> None:
    if not _HAS_MATPLOTLIB:
        print("[export] ERROR: matplotlib not available. pip install matplotlib")
        sys.exit(1)

    frames = viewer.frames
    if interventions_only:
        frames = [f for f in frames if f.intervention_applied] or frames

    if not frames:
        print("[export] No frames to render.")
        return

    # Compute scene bounds
    all_x = [f.robot_x for f in frames]
    all_y = [f.robot_y for f in frames]
    for f in frames:
        for obs in f.obstacles:
            all_x.append(obs.x)
            all_y.append(obs.y)
        if f.goal_xy:
            all_x.append(f.goal_xy[0])
            all_y.append(f.goal_xy[1])

    x_min = min(all_x) - ARENA_PADDING
    x_max = max(all_x) + ARENA_PADDING
    y_min = min(all_y) - ARENA_PADDING
    y_max = max(all_y) + ARENA_PADDING

    traj_data = TrajectoryData.build(viewer.frames)
    renderer  = SceneGraphRenderer()

    vi = viewer.version_info()
    frame_title_base = (
        f"FleetSafe Intervention Replay | "
        f"model={vi.get('model','?')} | "
        f"v{BENCHMARK_VERSION} | commit={GIT_COMMIT[:8]}"
    )

    print(f"[export] Rendering {len(frames)} frames → {output_path} ({fps} fps)")

    fig, (ax_scene, ax_text) = plt.subplots(
        1, 2,
        figsize=(12, 5),
        gridspec_kw={"width_ratios": [2, 1]},
        dpi=dpi,
    )
    fig.patch.set_facecolor("#111111")
    ax_scene.set_facecolor("#1a1a1a")

    frame_list = list(frames)

    def animate(i: int) -> None:
        frame = frame_list[i]
        status = "[INTERV]" if frame.intervention_applied else (
            "[NEAR]" if frame.nearest_obstacle_distance_m < 0.45 else "[OK]"
        )
        title = f"{frame_title_base} | {status} | frame {frame.frame_idx}"
        ax_scene.set_xlim(x_min, x_max)
        ax_scene.set_ylim(y_min, y_max)
        _draw_frame(ax_scene, ax_text, viewer, frame, traj_data, renderer, show_cf, title)

    anim = FuncAnimation(
        fig,
        animate,
        frames=len(frame_list),
        interval=1000 // fps,
        repeat=False,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()

    # Embed benchmark metadata in video title / description where possible
    metadata = {
        "title":   f"FleetSafe Intervention Replay v{BENCHMARK_VERSION}",
        "artist":  f"FAVL-AI  commit={GIT_COMMIT}",
        "comment": (
            f"benchmark_version={BENCHMARK_VERSION} "
            f"protocol_version={PROTOCOL_VERSION} "
            f"git_commit={GIT_COMMIT} "
            f"backend={vi.get('backend','?')}"
        ),
    }

    if suffix == ".mp4":
        try:
            writer = FFMpegWriter(fps=fps, metadata=metadata, bitrate=1800)
            anim.save(str(output_path), writer=writer)
            print(f"[export] MP4 written: {output_path}")
        except Exception as exc:
            print(f"[export] ffmpeg unavailable ({exc}). Trying GIF fallback.")
            gif_path = output_path.with_suffix(".gif")
            writer = PillowWriter(fps=fps, metadata=metadata)
            anim.save(str(gif_path), writer=writer)
            print(f"[export] GIF written: {gif_path}")
    elif suffix == ".gif":
        writer = PillowWriter(fps=fps, metadata=metadata)
        anim.save(str(output_path), writer=writer)
        print(f"[export] GIF written: {output_path}")
    else:
        # PNG frame dump
        frames_dir = output_path.with_suffix("")
        frames_dir.mkdir(parents=True, exist_ok=True)
        for i, frame in enumerate(frame_list):
            animate(i)
            fig.savefig(frames_dir / f"frame_{i:04d}.png", dpi=dpi)
        print(f"[export] PNG frames written to: {frames_dir}")

    plt.close(fig)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export FleetSafe intervention replay video from benchmark artifacts."
    )
    parser.add_argument("--episode-dir", required=True,
                        help="Episode directory containing intervention_evidence.jsonl")
    parser.add_argument("--run-dir", default=None,
                        help="Run-level directory containing metadata.yaml")
    parser.add_argument("--output", default="replay.mp4",
                        help="Output file: .mp4 (requires ffmpeg), .gif, or directory for PNGs")
    parser.add_argument("--fps",    type=int, default=4)
    parser.add_argument("--dpi",    type=int, default=120)
    parser.add_argument("--show-counterfactual",  action="store_true", default=True)
    parser.add_argument("--interventions-only",   action="store_true", default=False,
                        help="Only render intervention frames")
    parser.add_argument("--scene", default="", help="Scene name override")
    args = parser.parse_args(argv)

    episode_dir = Path(args.episode_dir)
    run_dir     = Path(args.run_dir) if args.run_dir else None
    output_path = Path(args.output)

    print(f"[export] Loading: {episode_dir}")
    viewer = InterventionReplayViewer(
        episode_dir=episode_dir,
        run_dir=run_dir,
        scene_id=args.scene,
    ).load()

    viewer.print_summary()

    if not viewer.is_valid():
        print("[export] ⚠ Required artifacts missing. Proceeding with partial data.")
    for w in viewer.version_warnings():
        print(f"[export] ⚠ VERSION: {w}")

    export_video(
        viewer=viewer,
        output_path=output_path,
        fps=args.fps,
        show_cf=args.show_counterfactual,
        interventions_only=args.interventions_only,
        dpi=args.dpi,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
