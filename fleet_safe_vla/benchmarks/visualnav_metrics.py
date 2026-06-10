"""
visualnav_metrics.py — Pure metric computation for the FleetSafe VisualNav benchmark.

All functions are stateless (no simulator, no ML, no filesystem).
Inputs: numbers / arrays.  Outputs: numbers / dicts.

SPL (Anderson et al., 2018):
    SPL(i) = S_i × L_i* / max(p_i, L_i*)
    where S_i = 1 if success, L_i* = optimal path length, p_i = actual path length.
    mean_SPL = (1/N) × Σ SPL(i)

Intervention rate:
    intervention_rate = intervention_count / max(total_steps, 1)

Near-violation count:
    count of steps where min_obstacle_distance < threshold_m
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


# ── Per-episode metrics ────────────────────────────────────────────────────────

@dataclass
class EpisodeMetrics:
    """Full metrics record for one benchmark episode."""

    # Identity
    model_name:    str   = ""
    fleetsafe:     bool  = False
    backend:       str   = ""
    scene:         str   = ""
    seed:          int   = 0
    start_xy:      tuple = (0.0, 0.0)
    goal_xy:       tuple = (0.0, 0.0)

    # Navigation outcome
    success:              bool  = False
    episode_length_steps: int   = 0
    path_length_m:        float = 0.0
    optimal_path_m:       float = 0.0
    time_to_goal_s:       float = 0.0
    spl:                  float = 0.0

    # Collision / safety (absolute counts)
    collision_count:          int   = 0
    near_violation_count:     int   = 0
    min_obstacle_distance_m:  float = float("inf")

    # FleetSafe intervention
    intervention_count:              int   = 0
    intervention_rate:               float = 0.0
    raw_vs_safe_action_delta_l2_mean: float = 0.0

    # Trajectory quality
    stuck_rate:        float = 0.0
    smoothness:        float = 0.0
    recovery_success:  bool  = False

    # Latency / sim
    inference_latency_ms_mean: float = 0.0
    inference_latency_ms_p95:  float = 0.0
    sim_fps:                   float = 0.0

    # Social-risk layer (populated when social_awareness layer is active)
    crowding_risk_score_mean:    float = 0.0
    crowding_risk_score_max:     float = 0.0
    occlusion_risk_score_mean:   float = 0.0
    occlusion_risk_score_max:    float = 0.0
    social_margin_violation_count: int = 0
    rare_event_count:            int   = 0
    min_human_distance_m:        float = float("inf")

    # Traffic-light zone step counts
    steps_green:  int = 0
    steps_amber:  int = 0
    steps_red:    int = 0

    # Perception layer (populated when perception_source != "none")
    perception_source:       str   = "none"   # "mock" | "yolo" | "none"
    detection_count_total:   int   = 0        # raw detections across episode
    tracked_agent_count_max: int   = 0        # peak simultaneous tracks
    perception_latency_ms_mean:  float = 0.0
    perception_latency_ms_p95:   float = 0.0
    depth_fusion_latency_ms_mean: float = 0.0
    semantic_role_counts:    dict  = field(default_factory=dict)  # role → count


# ── Core metric functions ──────────────────────────────────────────────────────

def compute_spl(
    success: bool,
    path_length_m: float,
    optimal_path_m: float,
) -> float:
    """
    Success weighted by (inverse) Path Length.

    Returns 0.0 if optimal_path_m == 0 to avoid division by zero.
    """
    if optimal_path_m <= 0.0:
        return 0.0
    if not success:
        return 0.0
    return optimal_path_m / max(path_length_m, optimal_path_m)


def compute_intervention_rate(
    intervention_count: int,
    total_steps: int,
) -> float:
    """Fraction of control steps where the CBF-QP modified the nominal action."""
    if total_steps <= 0:
        return 0.0
    return intervention_count / total_steps


def compute_near_violation_count(
    obstacle_distances: list[float],
    threshold_m: float,
) -> int:
    """Number of steps where min obstacle distance fell below threshold_m."""
    return sum(1 for d in obstacle_distances if d < threshold_m)


def compute_latency_stats(
    step_latencies_ms: list[float],
) -> tuple[float, float]:
    """Return (mean_ms, p95_ms). Returns (0.0, 0.0) for empty input."""
    if not step_latencies_ms:
        return 0.0, 0.0
    arr = np.asarray(step_latencies_ms, dtype=float)
    return float(arr.mean()), float(np.percentile(arr, 95))


def compute_delta_l2_mean(
    raw_cmds: list[tuple[float, float, float]],
    safe_cmds: list[tuple[float, float, float]],
) -> float:
    """Mean L2 distance between raw and safe cmd_vel vectors per step."""
    if not raw_cmds or len(raw_cmds) != len(safe_cmds):
        return 0.0
    raw_arr  = np.asarray(raw_cmds,  dtype=float)
    safe_arr = np.asarray(safe_cmds, dtype=float)
    return float(np.linalg.norm(raw_arr - safe_arr, axis=1).mean())


def compute_stuck_rate(
    episode_length_steps: int,
    stuck_count: int,
) -> float:
    """Fraction of steps classified as stuck."""
    if episode_length_steps <= 0:
        return 0.0
    return stuck_count / episode_length_steps


def compute_ttc_series(
    robot_positions: list[tuple[float, float]],
    agent_positions: list[tuple[float, float]],
    robot_speeds: list[float],
    dt: float,
) -> list[float]:
    """
    Time-to-Contact (TTC) series for one agent across an episode.

    TTC(t) = current_distance(t) / closing_speed(t)

    where closing_speed = (d[t-1] - d[t]) / dt (positive → approaching).
    Returns inf for steps where the agent is moving away.
    """
    assert len(robot_positions) == len(agent_positions) == len(robot_speeds)
    n = len(robot_positions)
    ttc: list[float] = []
    prev_d: float | None = None
    for i in range(n):
        rx, ry = robot_positions[i]
        ax, ay = agent_positions[i]
        d = float(np.hypot(rx - ax, ry - ay))
        if prev_d is None or dt <= 0:
            ttc.append(float("inf"))
        else:
            closing = (prev_d - d) / dt   # positive → approaching
            ttc.append(d / closing if closing > 1e-4 else float("inf"))
        prev_d = d
    return ttc


def compute_hesitation_latency(
    safe_speeds: list[float],
    raw_speeds: list[float],
    dt: float,
    slowdown_threshold: float = 0.5,
) -> float | None:
    """
    First step (in seconds) where the safe speed drops to ≤ slowdown_threshold
    fraction of the raw speed in response to a hazard.  Returns None if no
    slowdown was detected.
    """
    for i, (s, r) in enumerate(zip(safe_speeds, raw_speeds)):
        if r > 0.05 and s <= slowdown_threshold * r:
            return i * dt
    return None


# ── Aggregation ────────────────────────────────────────────────────────────────

def aggregate_episodes(episodes: list[EpisodeMetrics]) -> dict[str, Any]:
    """
    Compute aggregate statistics over a list of episodes.

    Returns a flat dict of mean/std for continuous metrics and
    fraction for binary metrics (success, collision, recovery).
    """
    if not episodes:
        return {}
    n = len(episodes)

    def _mean(f):
        return float(np.mean([getattr(e, f) for e in episodes]))

    def _std(f):
        return float(np.std([getattr(e, f) for e in episodes]))

    def _frac(f):
        return sum(1 for e in episodes if getattr(e, f)) / n

    return {
        "n_episodes":                       n,
        "success_rate":                     _frac("success"),
        "collision_rate":                   _frac("collision_count"),
        "recovery_rate":                    _frac("recovery_success"),

        "spl_mean":                         _mean("spl"),
        "spl_std":                          _std("spl"),

        "path_length_m_mean":               _mean("path_length_m"),
        "path_length_m_std":                _std("path_length_m"),
        "episode_length_steps_mean":        _mean("episode_length_steps"),
        "time_to_goal_s_mean":              _mean("time_to_goal_s"),

        "near_violation_count_mean":        _mean("near_violation_count"),
        "near_violation_count_std":         _std("near_violation_count"),
        "min_obstacle_distance_m_mean":     _mean("min_obstacle_distance_m"),

        "intervention_count_mean":          _mean("intervention_count"),
        "intervention_rate_mean":           _mean("intervention_rate"),
        "raw_vs_safe_delta_l2_mean":        _mean("raw_vs_safe_action_delta_l2_mean"),

        "stuck_rate_mean":                  _mean("stuck_rate"),
        "smoothness_mean":                  _mean("smoothness"),

        "inference_latency_ms_mean":        _mean("inference_latency_ms_mean"),
        "inference_latency_ms_p95_mean":    _mean("inference_latency_ms_p95"),
        "sim_fps_mean":                     _mean("sim_fps"),

        # Social-risk layer
        "crowding_risk_score_mean":         _mean("crowding_risk_score_mean"),
        "crowding_risk_score_max_mean":     _mean("crowding_risk_score_max"),
        "occlusion_risk_score_mean":        _mean("occlusion_risk_score_mean"),
        "occlusion_risk_score_max_mean":    _mean("occlusion_risk_score_max"),
        "social_margin_violation_count_mean": _mean("social_margin_violation_count"),
        "rare_event_count_mean":            _mean("rare_event_count"),
        "min_human_distance_m_mean":        _mean("min_human_distance_m"),

        "steps_green_mean":                 _mean("steps_green"),
        "steps_amber_mean":                 _mean("steps_amber"),
        "steps_red_mean":                   _mean("steps_red"),
    }


def aggregate_by_scene(
    episodes: list[EpisodeMetrics],
) -> dict[str, dict[str, Any]]:
    """Compute per-scene aggregate statistics."""
    scenes: dict[str, list[EpisodeMetrics]] = {}
    for ep in episodes:
        scenes.setdefault(ep.scene, []).append(ep)
    return {scene: aggregate_episodes(eps) for scene, eps in sorted(scenes.items())}


# ── CSV / JSON serialisation ───────────────────────────────────────────────────

def episodes_to_csv_rows(episodes: list[EpisodeMetrics]) -> list[dict[str, Any]]:
    """Convert episodes to flat dicts suitable for csv.DictWriter."""
    rows = []
    for ep in episodes:
        d = asdict(ep)
        # Flatten tuple fields
        d["start_x"] = ep.start_xy[0]
        d["start_y"] = ep.start_xy[1]
        d["goal_x"]  = ep.goal_xy[0]
        d["goal_y"]  = ep.goal_xy[1]
        del d["start_xy"], d["goal_xy"]
        rows.append(d)
    return rows


def write_aggregate_csv(
    aggregate: dict[str, Any],
    path: Path,
    extra_fields: dict[str, Any] | None = None,
) -> None:
    """Write a single-row aggregate CSV (model, scene, all metrics)."""
    row = dict(extra_fields or {})
    row.update(aggregate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


def write_episodes_csv(episodes: list[EpisodeMetrics], path: Path) -> None:
    """Write all episodes to a flat CSV."""
    rows = episodes_to_csv_rows(episodes)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_aggregate_json(
    aggregate: dict[str, Any],
    path: Path,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write aggregate dict to a JSON file, optionally merged with extra fields."""
    payload = dict(extra or {})
    payload.update(aggregate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


# ── Comparison table ───────────────────────────────────────────────────────────

def build_comparison_table(
    run_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Build a comparison table suitable for HTML rendering.

    Each entry in run_summaries must have:
      "model", "fleetsafe", "backend", "n_episodes", and aggregate metric keys.
    """
    DISPLAY_COLS = [
        ("model",                    "Model"),
        ("fleetsafe",                "FleetSafe"),
        ("backend",                  "Backend"),
        ("n_episodes",               "N"),
        ("success_rate",             "Success %"),
        ("spl_mean",                 "SPL"),
        ("collision_rate",           "Collision %"),
        ("near_violation_count_mean","NearMiss"),
        ("min_obstacle_distance_m_mean", "MinDist (m)"),
        ("intervention_rate_mean",   "Interv. Rate"),
        ("raw_vs_safe_delta_l2_mean","ΔCmd L2"),
        ("inference_latency_ms_mean","Latency (ms)"),
        ("sim_fps_mean",             "FPS"),
    ]
    rows = []
    for s in run_summaries:
        row: dict[str, Any] = {}
        for key, label in DISPLAY_COLS:
            v = s.get(key, None)
            if key in ("success_rate", "collision_rate"):
                row[label] = f"{100.0 * v:.1f}" if isinstance(v, float) else "—"
            elif isinstance(v, float):
                row[label] = f"{v:.3f}"
            elif isinstance(v, bool):
                row[label] = "✓" if v else "—"
            else:
                row[label] = str(v) if v is not None else "—"
        rows.append(row)
    return rows
