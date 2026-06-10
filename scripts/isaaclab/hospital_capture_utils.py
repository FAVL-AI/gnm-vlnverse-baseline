"""
hospital_capture_utils.py — Pure-Python utilities for run_hospital.py capture mode.

NO Isaac Sim / omni dependency — fully importable in test environments.
All functions that write files accept an explicit log_dir argument.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# ── Hospital floor-plan geometry (mirrors hospital_scene_builder.py) ──────────

# (x_min, x_max, y_min, y_max, RGB 0-1, label)
HOSPITAL_ZONES = [
    (-10.0, -2.0,  2.0,  8.0, (0.20, 0.40, 0.80), "ICU"),
    ( -2.0,  2.0,  2.0,  8.0, (0.55, 0.55, 0.60), "Nurse Station"),
    (  2.0, 10.0,  2.0,  8.0, (0.20, 0.65, 0.65), "Pharmacy"),
    (-10.0, 10.0, -1.5,  2.0, (0.95, 0.92, 0.82), "Emergency Corridor"),
    (-10.0, 10.0, -8.0, -1.5, (0.40, 0.65, 0.45), "Waiting Room"),
]

# Walls: [(x0, y0, x1, y1), ...]  -- boundary + interior dividers
HOSPITAL_WALLS = [
    (-10, -8, -10, 8),  (-10, 8,  10, 8),
    ( 10,  8, 10, -8),  ( 10, -8, -10, -8),
    (-10,  2,  10,  2),  (-10, -1.5, 10, -1.5),
    ( -2,  2,  -2,  8),  (  2,  2,   2,  8),
]

# ── Pedestrian scenario waypoints ─────────────────────────────────────────────

SCENARIO_WAYPOINTS: dict[str, list[tuple[float, float]]] = {
    "none":          [],
    "crossing":      [(-4.0, 0.0), (4.0, 0.0)],
    "occlusion":     [(-3.0, 1.5), (3.0, 1.5), (-3.0, -1.5), (3.0, -1.5)],
    "congestion":    [(-5, 0), (-3, 1), (-1, -1), (1, 0), (3, 1), (5, -1)],
    "yield":         [(-4.0, 0.0), (0.0, 0.0), (4.0, 0.0)],
    "corridor_rush": [(-6, i * 0.5) for i in range(-3, 5)],
}

SCENARIO_AGENT_COUNTS: dict[str, int] = {
    "none":          0,
    "crossing":      1,
    "occlusion":     2,
    "congestion":    6,
    "yield":         2,
    "corridor_rush": 8,
}

# ── Sensor degradation parser ─────────────────────────────────────────────────

DEGRADE_DEFAULTS: dict[str, Any] = {
    "motion_blur":        0,
    "low_light":          0,
    "lidar_dropout_rate": 0,
    "camera_packet_loss": 0,
    "latency_jitter_ms":  0,
    "depth_corruption":   False,
}

_DEGRADE_ALIASES: dict[str, str] = {
    "lidar_dropout":  "lidar_dropout_rate",
    "packet_loss":    "camera_packet_loss",
    "latency_jitter": "latency_jitter_ms",
    "blur":           "motion_blur",
}


def parse_degrade(spec: str) -> dict:
    """
    Parse 'motion_blur=30,lidar_dropout=10,depth_corruption' into a config dict.

    >>> parse_degrade("")["motion_blur"]
    0
    >>> parse_degrade("motion_blur=40,depth_corruption")["motion_blur"]
    40.0
    >>> parse_degrade("motion_blur=40,depth_corruption")["depth_corruption"]
    True
    >>> parse_degrade("lidar_dropout=15")["lidar_dropout_rate"]
    15.0
    """
    config = dict(DEGRADE_DEFAULTS)
    if not spec.strip():
        return config
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            key, _, val = token.partition("=")
            key = _DEGRADE_ALIASES.get(key.strip().lower().replace("-", "_"),
                                       key.strip().lower().replace("-", "_"))
            if key in config:
                config[key] = float(val)
        else:
            key = _DEGRADE_ALIASES.get(token.lower().replace("-", "_"),
                                       token.lower().replace("-", "_"))
            if key in config:
                config[key] = True
    return config


# ── Capture status writers ────────────────────────────────────────────────────

def write_viewport_status(log_dir: Path, status: str) -> None:
    """Write viewport_status.txt. Called unconditionally at end of run."""
    (log_dir / "viewport_status.txt").write_text(status + "\n")


def write_capture_status(
    log_dir: Path,
    *,
    scene: str,
    scenario: str,
    isaac_runtime: str,
    usd_asset: str,
    screenshot: str,
    procedural_preview: str,
    method: str,
    timestamp: str,
    isaac_version: str,
) -> dict:
    """
    Write capture_status.json with evidence-ledger fields.
    Returns the dict that was written.

    Evidence values follow the taxonomy:
      RECORDED  — artifact exists and was produced in this run
      MISSING   — attempted but not produced
      NOT_RUN   — --capture not passed; no attempt made
    """
    status = {
        "isaac_runtime":      isaac_runtime,
        "usd_asset":          usd_asset,
        "screenshot":         screenshot,
        "procedural_preview": procedural_preview,
        "scene":              scene,
        "scenario":           scenario,
        "method":             method,
        "timestamp":          timestamp,
        "isaac_version":      isaac_version,
    }
    (log_dir / "capture_status.json").write_text(json.dumps(status, indent=2))
    return status


def write_photoreal_status(
    log_dir: Path,
    *,
    render_status: str,
    usd_loaded: bool,
    usd_path: str | None,
    screenshot_path: str | None,
    method: str,
    scene: str,
    scenario: str,
    timestamp: str,
    isaac_version: str,
) -> None:
    """Write photoreal_status.json (read by the dashboard backend)."""
    payload = {
        "status":         render_status,
        "usd_loaded":     usd_loaded,
        "usd_path":       usd_path,
        "screenshot":     screenshot_path,
        "capture_method": method,
        "scene":          scene,
        "scenario":       scenario,
        "timestamp":      timestamp,
        "isaac_version":  isaac_version,
    }
    (log_dir / "photoreal_status.json").write_text(json.dumps(payload, indent=2))


# ── Procedural floor-plan preview ─────────────────────────────────────────────

def write_procedural_preview(
    log_dir: Path,
    scene: str,
    scenario: str,
    isaac_version: str = "unknown",
    usd_available: bool | None = None,
    isaac_runtime: str = "RECORDED",
) -> Path | None:
    """
    Render a matplotlib floor-plan of the procedural hospital scene to
    logs/<run>/procedural_preview.png.

    Works without Isaac Sim, GPU, or a display (uses Agg backend).
    Returns the Path on success, None if matplotlib is unavailable.
    """
    try:
        import matplotlib  # type: ignore
        matplotlib.use("Agg")  # headless, no DISPLAY required
        import matplotlib.pyplot as plt  # type: ignore
        import matplotlib.patches as patches  # type: ignore
    except ImportError:
        return None

    fig, ax = plt.subplots(figsize=(14, 9))
    fig.patch.set_facecolor("#111827")
    ax.set_facecolor("#111827")

    # ── Draw zones ──────────────────────────────────────────────────────────
    for x0, x1, y0, y1, rgb, label in HOSPITAL_ZONES:
        rect = patches.Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            linewidth=0,
            facecolor=rgb,
            alpha=0.55,
        )
        ax.add_patch(rect)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(cx, cy, label,
                ha="center", va="center",
                color="white", fontsize=8,
                fontfamily="monospace", fontweight="bold", alpha=0.85)

    # ── Draw walls ──────────────────────────────────────────────────────────
    for x0, y0, x1, y1 in HOSPITAL_WALLS:
        ax.plot([x0, x1], [y0, y1], color="#e5e7eb", linewidth=1.4, alpha=0.7)

    # ── Draw pedestrian waypoints ────────────────────────────────────────────
    waypoints = SCENARIO_WAYPOINTS.get(scenario, [])
    scenario_color = "#f87171"  # red-400
    for i, (wx, wy) in enumerate(waypoints):
        ax.scatter(wx, wy, s=120, color=scenario_color, zorder=6,
                   edgecolors="white", linewidths=0.8)
        ax.text(wx + 0.35, wy + 0.35, f"P{i+1}",
                color=scenario_color, fontsize=7,
                fontfamily="monospace", fontweight="bold", zorder=7)

    if waypoints and len(waypoints) > 1:
        xs = [w[0] for w in waypoints]
        ys = [w[1] for w in waypoints]
        ax.plot(xs, ys, "--", color=scenario_color, linewidth=0.8, alpha=0.5, zorder=5)

    # ── Robot start position ─────────────────────────────────────────────────
    ax.scatter(0, 0, s=200, color="#34d399", marker="^", zorder=8,
               edgecolors="white", linewidths=1.0, label="Robot start")
    ax.text(0.4, -0.6, "Robot", color="#34d399",
            fontsize=7, fontfamily="monospace", fontweight="bold")

    # ── Annotations ─────────────────────────────────────────────────────────
    ax.set_xlim(-11.5, 11.5)
    ax.set_ylim(-9.5, 9.5)
    ax.set_aspect("equal")
    ax.tick_params(colors="#6b7280", labelsize=7)
    for spine in ax.spines.values():
        spine.set_edgecolor("#374151")

    title = f"FleetSafe Hospital  ·  {scene.replace('hospital_', '').replace('_', ' ').title()}"
    if scenario != "none":
        title += f"  ·  scenario: {scenario.replace('_', ' ')}"
    ax.set_title(title, color="#f9fafb", fontsize=10,
                 fontfamily="monospace", pad=10)

    # Auto-detect USD if not provided
    if usd_available is None:
        try:
            _usd_path = (
                log_dir.parents[2]
                / "fleet_safe_vla" / "envs" / "isaaclab" / "hospital" / "assets" / "hospital_world.usd"
            )
            usd_available = _usd_path.exists() and _usd_path.stat().st_size > 1000
        except (IndexError, Exception):
            usd_available = False

    usd_label = "FOUND" if usd_available else "MISSING"
    note_lines = [
        f"Procedural scene  ·  Isaac runtime: {isaac_runtime}  ·  photoreal USD: {usd_label}",
        f"Isaac {isaac_version}  ·  do not claim: photoreal hospital complete",
    ]
    ax.text(0, -9.1, "\n".join(note_lines),
            ha="center", va="top", color="#6b7280",
            fontsize=6.5, fontfamily="monospace",
            transform=ax.transData)

    # Legend
    legend_elements = [
        patches.Patch(facecolor=(0.20, 0.40, 0.80), alpha=0.7, label="ICU"),
        patches.Patch(facecolor=(0.55, 0.55, 0.60), alpha=0.7, label="Nurse Station"),
        patches.Patch(facecolor=(0.20, 0.65, 0.65), alpha=0.7, label="Pharmacy"),
        patches.Patch(facecolor=(0.95, 0.92, 0.82), alpha=0.7, label="Corridor"),
        patches.Patch(facecolor=(0.40, 0.65, 0.45), alpha=0.7, label="Waiting Room"),
    ]
    if waypoints:
        import matplotlib.lines as mlines  # type: ignore
        legend_elements.append(
            mlines.Line2D([], [], color=scenario_color, marker="o",
                          markersize=6, label=f"Pedestrian ({scenario})")
        )
    legend = ax.legend(
        handles=legend_elements,
        loc="upper right",
        fontsize=6.5,
        facecolor="#1f2937",
        edgecolor="#374151",
        labelcolor="white",
    )

    out = log_dir / "procedural_preview.png"
    plt.savefig(str(out), dpi=150, bbox_inches="tight",
                facecolor="#111827", edgecolor="none")
    plt.close(fig)
    return out


# ── Latest-symlink helper ─────────────────────────────────────────────────────

def update_latest_symlink(log_dir: Path) -> None:
    """Point logs/hospital_benchmark/latest → this run's directory.

    Uses a relative symlink (just the dir name) so the repo is portable.
    """
    latest = log_dir.parent / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        # Relative target: just the run dir name, resolved from latest's parent
        latest.symlink_to(log_dir.name, target_is_directory=True)
    except Exception as e:
        print(f"[capture_utils] WARNING: could not update latest symlink: {e}")
