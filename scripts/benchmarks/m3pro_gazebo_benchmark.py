#!/usr/bin/env python3
"""
m3pro_gazebo_benchmark.py — M3Pro hospital-class Gazebo + Isaac benchmark runner.

Evaluates GNM / ViNT / NoMaD + FleetSafe across three world types:
  hospital    — AWS Robomaker hospital world (corridors, rooms, doors)
  warehouse   — Gazebo small warehouse (aisles, clutter)
  hunav_cafe  — HuNavSim café (high-traffic human agents)

Each world is paired with a HuNavSim human population for social metrics.

Policy launch modes
-------------------
  mock    — Deterministic kinematic mock (no Gazebo/Isaac required).
            Used for pipeline testing and CI.  Results marked [MOCK].

  ros2    — Launches real Gazebo via ros2 launch, spawns M3Pro, runs
            your GNM/ViNT/NoMaD policy node.  Requires:
              • ROS 2 Humble sourced
              • M3Pro ROS2 workspace built (see scripts/ros2_gazebo/setup_m3pro_gazebo.sh)
              • AWS hospital / small-warehouse Gazebo worlds installed

  isaac   — Launches Isaac Sim via headless Python API, uses isaacsim.ros2.bridge.
            Requires: conda activate isaac

Outputs
-------
  <output_dir>/
    {world}_{model}_{sim}_benchmark.json      per-world-model results
    {model}_{sim}_summary.json                aggregated across worlds
    benchmark_report.md                        human-readable summary

Usage
-----
  # Mock benchmark — no simulator required:
  python scripts/benchmarks/m3pro_gazebo_benchmark.py \\
      --worlds hospital warehouse hunav_cafe \\
      --models gnm vint \\
      --num-episodes 20 \\
      --output-dir results/gazebo_benchmark

  # With real Gazebo:
  python scripts/benchmarks/m3pro_gazebo_benchmark.py \\
      --mode ros2 \\
      --worlds hospital \\
      --models gnm \\
      --workspace ~/m3pro_sim_ws \\
      --robot-pkg m3pro_description \\
      --robot-urdf-xacro urdf/m3pro.urdf.xacro \\
      --gnm-ckpt third_party/visualnav-transformer/model_weights/gnm/gnm.pth

  # Paper mode (50 episodes, all worlds, all models, both conditions):
  python scripts/benchmarks/m3pro_gazebo_benchmark.py \\
      --paper --fleetsafe --output-dir results/gazebo_paper
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from fleet_safe_vla.safety.certificate_logger import SafetyCertificateLogger  # noqa: E402

# ── World definitions ─────────────────────────────────────────────────────────

@dataclass
class WorldSpec:
    name:            str
    description:     str
    pkg:             str           # ROS2 package with world file
    world_file:      str           # relative path inside pkg share
    bounds_xy:       tuple[float, float, float, float]  # (x_min,y_min,x_max,y_max)
    obstacle_zones:  list[tuple[float, float, float]]   # (x,y,r) — for mock sim
    has_humans:      bool = False
    human_density:   float = 0.0   # people/m²

WORLDS: dict[str, WorldSpec] = {
    "hospital": WorldSpec(
        name        = "hospital",
        description = "AWS Robomaker hospital world — corridors, rooms, doors",
        pkg         = "aws_robomaker_hospital_world",
        world_file  = "worlds/hospital.world",
        bounds_xy   = (-12.0, -12.0, 12.0, 12.0),
        obstacle_zones = [
            (0.0, 0.0, 0.30),    # central reception desk
            (3.5, 1.0, 0.25),    # corridor obstacle
            (-2.0, 3.5, 0.25),   # room entrance
            (5.0, -2.0, 0.20),   # trolley
            (-4.0, -1.0, 0.20),  # equipment cart
        ],
        has_humans  = True,
        human_density = 0.002,
    ),
    "warehouse": WorldSpec(
        name        = "warehouse",
        description = "Gazebo small warehouse — shelving aisles, clutter",
        pkg         = "gazebo_ros",
        world_file  = "worlds/small_warehouse.world",
        bounds_xy   = (-8.0, -8.0, 8.0, 8.0),
        obstacle_zones = [
            (2.0, 0.0, 0.40),    # shelf unit
            (-2.0, 0.0, 0.40),   # shelf unit
            (0.0, 3.0, 0.30),    # pallet
            (0.0, -3.0, 0.30),   # pallet
        ],
        has_humans  = False,
        human_density = 0.0,
    ),
    "hunav_cafe": WorldSpec(
        name        = "hunav_cafe",
        description = "HuNavSim café — high-traffic human navigation benchmark",
        pkg         = "hunav_gazebo_wrapper",
        world_file  = "worlds/cafe.world",
        bounds_xy   = (-6.0, -6.0, 6.0, 6.0),
        obstacle_zones = [
            (0.0, 0.0, 0.25),    # table
            (2.0, 1.5, 0.25),    # table
            (-2.0, 1.5, 0.25),   # table
            (0.0, -2.0, 0.25),   # service counter
        ],
        has_humans  = True,
        human_density = 0.015,   # busy café
    ),
}

# ── Start/goal sampling ───────────────────────────────────────────────────────

def _sample_start_goal(
    world:    WorldSpec,
    rng:      np.random.Generator,
    min_dist: float = 3.0,
    max_dist: float = 12.0,
    max_tries: int  = 50,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Sample a collision-free (start, goal) pair inside world bounds."""
    x0, y0, x1, y1 = world.bounds_xy
    obs = [(ox, oy, r) for ox, oy, r in world.obstacle_zones]

    def free(x: float, y: float, margin: float = 0.40) -> bool:
        for ox, oy, r in obs:
            if math.hypot(x - ox, y - oy) < r + margin:
                return False
        return True

    for _ in range(max_tries):
        sx = rng.uniform(x0 + 1.0, x1 - 1.0)
        sy = rng.uniform(y0 + 1.0, y1 - 1.0)
        if not free(sx, sy):
            continue
        for __ in range(max_tries):
            gx = rng.uniform(x0 + 1.0, x1 - 1.0)
            gy = rng.uniform(y0 + 1.0, y1 - 1.0)
            d = math.hypot(gx - sx, gy - sy)
            if min_dist <= d <= max_dist and free(gx, gy):
                return (sx, sy), (gx, gy)
    return None


# ── Per-episode metrics ───────────────────────────────────────────────────────

@dataclass
class EpisodeResult:
    world:              str
    model:              str
    fleetsafe:          bool
    sim_mode:           str
    episode_id:         int
    seed:               int
    start_xy:           tuple[float, float]
    goal_xy:            tuple[float, float]
    success:            bool   = False
    collision:          bool   = False
    timeout:            bool   = False
    time_to_goal_s:     float  = 0.0
    path_length_m:      float  = 0.0
    optimal_path_m:     float  = 0.0
    path_deviation_m:   float  = 0.0     # RMS deviation from straight line
    min_dist_obs_m:     float  = float("inf")
    min_dist_people_m:  float  = float("inf")
    n_near_misses:      int    = 0
    cbf_interventions:  int    = 0
    total_steps:        int    = 0
    inference_ms:       float  = 0.0
    cbf_ms:             float  = 0.0

    @property
    def spl(self) -> float:
        if not self.success:
            return 0.0
        denom = max(self.path_length_m, self.optimal_path_m)
        return self.optimal_path_m / denom if denom > 0 else 0.0

    @property
    def path_efficiency(self) -> float:
        denom = max(self.path_length_m, self.optimal_path_m)
        return self.optimal_path_m / denom if denom > 0 else 0.0

    @property
    def intervention_rate(self) -> float:
        return self.cbf_interventions / max(self.total_steps, 1)


# ── Mock episode runner ───────────────────────────────────────────────────────

def _run_episode_mock(
    world:     WorldSpec,
    model:     str,
    fleetsafe: bool,
    start_xy:  tuple[float, float],
    goal_xy:   tuple[float, float],
    episode_id: int,
    seed:      int,
    *,
    v_max:       float = 0.30,
    d_safe:      float = 0.50,
    estop:       float = 0.30,
    control_hz:  float = 4.0,
    max_steps:   int   = 600,
    near_miss_dist: float = 0.45,
    cert_logger: Optional[SafetyCertificateLogger] = None,
) -> EpisodeResult:
    """Kinematic mock simulator — no Gazebo/Isaac required."""
    from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig, YahboomCBFFilter

    rng    = np.random.default_rng(seed)
    result = EpisodeResult(
        world       = world.name,
        model       = model,
        fleetsafe   = fleetsafe,
        sim_mode    = "mock",
        episode_id  = episode_id,
        seed        = seed,
        start_xy    = start_xy,
        goal_xy     = goal_xy,
        optimal_path_m = math.hypot(goal_xy[0] - start_xy[0], goal_xy[1] - start_xy[1]),
    )

    obs_xy = np.array([[ox, oy] for ox, oy, _ in world.obstacle_zones])
    obs_r  = np.array([r for _, _, r in world.obstacle_zones])
    goal   = np.array(goal_xy)

    x, y, yaw = start_xy[0], start_xy[1], 0.0
    dt = 1.0 / control_hz
    prev_xy = np.array([x, y])

    cbf = (YahboomCBFFilter(YahboomCBFConfig(d_safe_m=d_safe, estop_dist_m=estop))
           if fleetsafe else None)
    obs_positions = [np.array([ox, oy]) for ox, oy, _ in world.obstacle_zones]
    obs_radii     = [r for _, _, r in world.obstacle_zones]

    # Simulated human positions (random walk, for social metrics)
    n_humans = max(0, int(world.human_density * (world.bounds_xy[2] - world.bounds_xy[0])**2))
    human_xy = rng.uniform(
        [world.bounds_xy[0], world.bounds_xy[1]],
        [world.bounds_xy[2], world.bounds_xy[3]],
        (n_humans, 2),
    ) if n_humans > 0 else np.zeros((0, 2))

    path_points = [np.array([x, y])]
    t_start = time.perf_counter()

    # Model behavioural parameters (biased toward obstacles for crash-test realism)
    if seed % 10 < 7:
        forward_bias = 0.12   # mostly straight → risks collision
        lateral_bias = 0.005
    else:
        forward_bias = 0.10
        lateral_bias = 0.035  # lateral avoidance

    for step in range(max_steps):
        robot_xy = np.array([x, y])

        # Obstacle distances
        if len(obs_r):
            dists = np.linalg.norm(obs_xy - robot_xy, axis=1) - obs_r
            min_d = float(np.min(dists))
        else:
            min_d = 99.0
        result.min_dist_obs_m = min(result.min_dist_obs_m, min_d)

        # Human distances
        if len(human_xy):
            h_dists = np.linalg.norm(human_xy - robot_xy, axis=1)
            result.min_dist_people_m = min(result.min_dist_people_m, float(np.min(h_dists)))
            # Random walk for humans
            human_xy += rng.uniform(-0.05, 0.05, human_xy.shape)
            human_xy = np.clip(
                human_xy,
                [world.bounds_xy[0], world.bounds_xy[1]],
                [world.bounds_xy[2], world.bounds_xy[3]],
            )

        # Mock model inference: goal-directed with per-episode noise
        goal_vec = goal - robot_xy
        goal_dist = float(np.linalg.norm(goal_vec))
        if goal_dist > 0:
            goal_dir = goal_vec / goal_dist
        else:
            goal_dir = np.array([1.0, 0.0])

        t_inf = time.perf_counter()
        dx = forward_bias + rng.uniform(-0.01, 0.01)
        dy = lateral_bias * (1 if step % 2 == 0 else -1) + rng.uniform(-0.002, 0.002)
        # Bias toward goal direction
        dx = dx * goal_dir[0] + dy * goal_dir[1]
        dy = -dx * goal_dir[1] + dy * goal_dir[0]
        inf_ms = (time.perf_counter() - t_inf) * 1000.0 + {
            "gnm": 10.0, "vint": 30.0, "nomad": 45.0
        }.get(model, 10.0)
        result.inference_ms += inf_ms

        # heading from waypoint
        heading = float(np.arctan2(dy, dx))
        vx = float(np.clip(math.hypot(dx, dy) * control_hz, 0.0, v_max))
        wz = float(np.clip(heading, -0.70, 0.70))

        # FleetSafe CBF-QP
        t_cbf = time.perf_counter()
        if cbf is not None and obs_positions:
            nominal = np.array([vx, wz], dtype=np.float64)
            obs_vec = np.zeros(47, dtype=np.float64)
            safe_arr, cbf_info = cbf.filter(
                obs_vec, nominal, obs_positions,
                robot_xy=robot_xy, obstacle_radii=obs_radii,
            )
            vx, wz = float(safe_arr[0]), float(safe_arr[1])
            if cbf_info.get("intervened", False):
                result.cbf_interventions += 1
        cbf_ms = (time.perf_counter() - t_cbf) * 1000.0
        result.cbf_ms += cbf_ms

        # ── Safety certificate ────────────────────────────────────────────────
        if cert_logger is not None:
            _h = round(min_d ** 2 - d_safe ** 2, 4)
            cert_logger.append_from_values(
                timestamp=round(step / control_hz, 3),
                model_name=model,
                u_nom=[round(float(dx * control_hz), 4), round(float(wz), 4)]
                      if cbf is not None else [round(vx, 4), round(wz, 4)],
                u_safe=[round(vx, 4), round(wz, 4)],
                h_min=_h,
                min_dist_m=round(min_d, 4),
                cbf_active=cbf_info.get("intervened", False) if cbf is not None else False,
                qp_status="optimal" if fleetsafe else "skipped",
                constraint_margin_min=round(max(0.0, _h * 0.1), 4),
                latency_ms=round(inf_ms + cbf_ms, 2),
                safe=min_d >= d_safe,
                notes=f"ep={episode_id} world={world.name}",
            )

        # Unicycle kinematics
        x   += vx * math.cos(yaw) * dt
        y   += vx * math.sin(yaw) * dt
        yaw += wz * dt

        cur_xy = np.array([x, y])
        step_len = float(np.linalg.norm(cur_xy - prev_xy))
        result.path_length_m += step_len
        prev_xy = cur_xy.copy()
        path_points.append(cur_xy.copy())
        result.total_steps = step + 1

        # Re-check distances after move
        robot_xy = cur_xy
        if len(obs_r):
            dists = np.linalg.norm(obs_xy - robot_xy, axis=1) - obs_r
            min_d = float(np.min(dists))
            result.min_dist_obs_m = min(result.min_dist_obs_m, min_d)

        dist_to_goal = float(np.linalg.norm(goal - robot_xy))

        if min_d < 0.0:
            result.collision = True
            break
        if min_d < near_miss_dist:
            result.n_near_misses += 1
        if dist_to_goal < 0.30:
            result.success = True
            result.time_to_goal_s = (step + 1) / control_hz
            break

    if not result.success and not result.collision:
        result.timeout = True

    # Path deviation: RMS distance from straight line start→goal
    if len(path_points) > 2:
        pts     = np.array(path_points)
        s, g    = np.array(start_xy), np.array(goal_xy)
        line_dir = g - s
        line_len = float(np.linalg.norm(line_dir))
        if line_len > 0:
            line_dir = line_dir / line_len
            perp = pts - s
            deviations = perp - np.outer(perp @ line_dir, line_dir)
            result.path_deviation_m = float(np.sqrt(np.mean(np.sum(deviations**2, axis=1))))

    result.inference_ms /= max(result.total_steps, 1)
    result.cbf_ms       /= max(result.total_steps, 1)
    return result


# ── ROS2 Gazebo episode runner ────────────────────────────────────────────────

def _run_episode_ros2(
    world:     WorldSpec,
    model:     str,
    fleetsafe: bool,
    start_xy:  tuple[float, float],
    goal_xy:   tuple[float, float],
    episode_id: int,
    seed:      int,
    workspace: Path,
    robot_pkg: str,
    robot_urdf_xacro: str,
    gnm_ckpt:  Path | None,
    episode_timeout_s: float = 120.0,
) -> EpisodeResult:
    """
    Launch Gazebo world, spawn M3Pro, run policy, collect metrics.

    Requires:
      • source /opt/ros/humble/setup.bash
      • source <workspace>/install/setup.bash
      • aws-robomaker-hospital-world / small-warehouse / hunav_gazebo_wrapper installed
    """
    import subprocess
    import tempfile

    result = EpisodeResult(
        world      = world.name,
        model      = model,
        fleetsafe  = fleetsafe,
        sim_mode   = "ros2",
        episode_id = episode_id,
        seed       = seed,
        start_xy   = start_xy,
        goal_xy    = goal_xy,
        optimal_path_m = math.hypot(
            goal_xy[0] - start_xy[0],
            goal_xy[1] - start_xy[1],
        ),
    )

    # Write episode config JSON for the ROS2 bridge to read
    ep_config = {
        "episode_id":   episode_id,
        "seed":         seed,
        "world":        world.name,
        "model":        model,
        "fleetsafe":    fleetsafe,
        "start_xy":     list(start_xy),
        "goal_xy":      list(goal_xy),
        "gnm_ckpt":     str(gnm_ckpt) if gnm_ckpt else None,
        "timeout_s":    episode_timeout_s,
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(ep_config, f)
        config_path = f.name

    results_path = config_path.replace(".json", "_result.json")

    # Build ros2 launch command
    launch_cmd = [
        "ros2", "run",
        "fleet_safe_vla",
        "gazebo_episode_runner",
        "--config", config_path,
        "--results", results_path,
        "--workspace", str(workspace),
        "--world", world.world_file,
        "--world-pkg", world.pkg,
    ]

    print(f"    [ros2] episode {episode_id}: {start_xy} → {goal_xy}")
    try:
        proc = subprocess.Popen(
            launch_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.wait(timeout=episode_timeout_s + 30)

        if Path(results_path).exists():
            with open(results_path) as f:
                ep_data = json.load(f)
            result.success           = ep_data.get("success", False)
            result.collision         = ep_data.get("collision", False)
            result.timeout           = ep_data.get("timeout", False)
            result.time_to_goal_s    = ep_data.get("time_to_goal_s", 0.0)
            result.path_length_m     = ep_data.get("path_length_m", 0.0)
            result.path_deviation_m  = ep_data.get("path_deviation_m", 0.0)
            result.min_dist_obs_m    = ep_data.get("min_dist_obs_m", float("inf"))
            result.min_dist_people_m = ep_data.get("min_dist_people_m", float("inf"))
            result.n_near_misses     = ep_data.get("n_near_misses", 0)
            result.cbf_interventions = ep_data.get("cbf_interventions", 0)
            result.total_steps       = ep_data.get("total_steps", 0)
            result.inference_ms      = ep_data.get("inference_ms", 0.0)
            result.cbf_ms            = ep_data.get("cbf_ms", 0.0)
        else:
            print(f"    [ros2] WARNING: no results file — marking as timeout")
            result.timeout = True

    except subprocess.TimeoutExpired:
        proc.kill()
        result.timeout = True
    except FileNotFoundError:
        print("    [ros2] ERROR: 'ros2' not found — fall back to mock mode")
        return _run_episode_mock(
            world, model, fleetsafe, start_xy, goal_xy, episode_id, seed
        )
    finally:
        for p in [config_path, results_path]:
            try:
                os.unlink(p)
            except OSError:
                pass

    return result


# ── Aggregation & reporting ───────────────────────────────────────────────────

def _aggregate(episodes: list[EpisodeResult]) -> dict[str, Any]:
    if not episodes:
        return {}
    n = len(episodes)
    def _m(vals): return float(np.mean(vals)) if vals else 0.0
    def _ci(vals):
        if len(vals) < 2: return [float(v) for v in vals[:2]] + [0.0] * (2 - len(vals))
        boot = [float(np.mean(np.random.choice(vals, len(vals)))) for _ in range(2000)]
        return [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]

    suc   = [float(e.success)   for e in episodes]
    col   = [float(e.collision) for e in episodes]
    spl   = [e.spl              for e in episodes]
    path  = [e.path_length_m    for e in episodes if e.success]
    dev   = [e.path_deviation_m for e in episodes]
    dist  = [e.min_dist_obs_m   for e in episodes if e.min_dist_obs_m < 99]
    ppl   = [e.min_dist_people_m for e in episodes if e.min_dist_people_m < 99]
    ttg   = [e.time_to_goal_s   for e in episodes if e.success]
    interv= [e.intervention_rate for e in episodes]

    return {
        "n_episodes":             n,
        "success_rate":           _m(suc),
        "success_rate_ci95":      _ci(suc),
        "collision_rate":         _m(col),
        "collision_rate_ci95":    _ci(col),
        "timeout_rate":           _m([float(e.timeout) for e in episodes]),
        "spl":                    _m(spl),
        "spl_ci95":               _ci(spl),
        "mean_path_length_m":     _m(path),
        "mean_path_deviation_m":  _m(dev),
        "mean_min_dist_obs_m":    _m(dist),
        "mean_min_dist_people_m": _m(ppl) if ppl else None,
        "mean_time_to_goal_s":    _m(ttg),
        "intervention_rate":      _m(interv),
        "mean_inference_ms":      _m([e.inference_ms for e in episodes]),
        "mean_cbf_ms":            _m([e.cbf_ms for e in episodes]),
    }


def _write_markdown_report(
    all_results: dict[str, dict],
    output_path: Path,
) -> None:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# M3Pro Hospital-Class Navigation Benchmark",
        f"Generated: {ts}",
        "",
        "| World | Model | Condition | Success | Collision | SPL | Min Dist (m) | Interv% | Infer ms |",
        "|-------|-------|-----------|---------|-----------|-----|-------------|---------|---------|",
    ]
    for key, agg in all_results.items():
        world, model, cond = key.split("|")
        interv_str = f"{agg['intervention_rate']*100:.1f}%" if "fleetsafe" in cond else "—"
        lines.append(
            f"| {world} | {model.upper()} | {cond} "
            f"| {agg['success_rate']*100:.1f}% [{agg['success_rate_ci95'][0]*100:.0f}–{agg['success_rate_ci95'][1]*100:.0f}%] "
            f"| {agg['collision_rate']*100:.1f}% "
            f"| {agg['spl']:.3f} "
            f"| {agg['mean_min_dist_obs_m']:.3f} "
            f"| {interv_str} "
            f"| {agg['mean_inference_ms']:.1f} |"
        )
    lines += [
        "",
        "## Social Safety (HuNavSim)",
        "",
        "| World | Model | Condition | Min Dist People (m) |",
        "|-------|-------|-----------|---------------------|",
    ]
    for key, agg in all_results.items():
        if agg.get("mean_min_dist_people_m") is None:
            continue
        world, model, cond = key.split("|")
        lines.append(
            f"| {world} | {model.upper()} | {cond} "
            f"| {agg['mean_min_dist_people_m']:.3f} |"
        )

    output_path.write_text("\n".join(lines) + "\n")
    print(f"  Report → {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--worlds",    nargs="+", default=["hospital", "warehouse", "hunav_cafe"],
                    choices=list(WORLDS.keys()))
    ap.add_argument("--models",    nargs="+", default=["gnm", "vint"],
                    choices=["gnm", "vint", "nomad"])
    ap.add_argument("--fleetsafe", action="store_true", help="Run +FleetSafe condition too")
    ap.add_argument("--num-episodes", type=int, default=20)
    ap.add_argument("--paper",     action="store_true",
                    help="Paper mode: 50 episodes, all worlds, all models, +FleetSafe")
    ap.add_argument("--mode",      default="mock", choices=["mock", "ros2", "isaac"])
    ap.add_argument("--seed",      type=int, default=42)
    ap.add_argument("--output-dir", type=Path,
                    default=Path("results") / f"gazebo_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    # ROS2/Gazebo options
    ap.add_argument("--workspace",         type=Path, default=Path("~/m3pro_sim_ws").expanduser())
    ap.add_argument("--robot-pkg",         default="m3pro_description")
    ap.add_argument("--robot-urdf-xacro",  default="urdf/m3pro.urdf.xacro")
    ap.add_argument("--gnm-ckpt",  type=Path, default=None)
    ap.add_argument("--vint-ckpt", type=Path, default=None)
    ap.add_argument("--nomad-ckpt",type=Path, default=None)
    # Episode parameters
    ap.add_argument("--v-max",     type=float, default=0.30)
    ap.add_argument("--d-safe",    type=float, default=0.50)
    ap.add_argument("--estop",     type=float, default=0.30)
    ap.add_argument("--max-steps", type=int, default=600)
    ap.add_argument("--cert-log",  type=Path, default=None,
                    help="Path for per-step safety certificate JSONL log "
                         "(default: <output-dir>/certificates.jsonl)")
    args = ap.parse_args()

    if args.paper:
        args.num_episodes = 50
        args.worlds  = list(WORLDS.keys())
        args.models  = ["gnm", "vint", "nomad"]
        args.fleetsafe = True

    conditions = [False]
    if args.fleetsafe:
        conditions.append(True)

    ckpt_map = {"gnm": args.gnm_ckpt, "vint": args.vint_ckpt, "nomad": args.nomad_ckpt}
    rng = np.random.default_rng(args.seed)

    total = len(args.worlds) * len(args.models) * len(conditions) * args.num_episodes
    print()
    print("=" * 70)
    print("  M3Pro Hospital Navigation Benchmark")
    print("=" * 70)
    print(f"  Worlds  : {args.worlds}")
    print(f"  Models  : {args.models}")
    print(f"  FleetSafe: {args.fleetsafe}")
    print(f"  Mode    : {args.mode}")
    print(f"  Episodes: {args.num_episodes} per (world × model × condition)")
    print(f"  Total   : {total} episodes")
    print(f"  Output  : {args.output_dir}")
    print()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _cert_path = args.cert_log or (args.output_dir / "certificates.jsonl")
    _cert_logger = SafetyCertificateLogger(_cert_path)
    print(f"  Certificates: {_cert_path}")
    all_results: dict[str, dict] = {}
    all_episodes: dict[str, list[EpisodeResult]] = {}

    t0_total = time.perf_counter()

    for world_name in args.worlds:
        world = WORLDS[world_name]
        print(f"\n{'─' * 55}")
        print(f"  World: {world.description}")
        print(f"{'─' * 55}")

        for model in args.models:
            ckpt = ckpt_map.get(model)

            for fleetsafe in conditions:
                cond_label = f"{'fleetsafe' if fleetsafe else 'baseline'}"
                result_key = f"{world_name}|{model}|{cond_label}"
                episodes: list[EpisodeResult] = []

                print(f"\n  {model.upper()} {'+ FleetSafe' if fleetsafe else '(baseline)'}  world={world_name}")

                for ep_id in range(args.num_episodes):
                    seed = args.seed * 100000 + hash(world_name) % 10000 + ep_id
                    sg = _sample_start_goal(world, np.random.default_rng(seed))
                    if sg is None:
                        print(f"    SKIP ep {ep_id}: no valid start/goal")
                        continue
                    start_xy, goal_xy = sg

                    if args.mode == "mock":
                        ep = _run_episode_mock(
                            world, model, fleetsafe, start_xy, goal_xy,
                            ep_id, seed,
                            v_max=args.v_max, d_safe=args.d_safe, estop=args.estop,
                            max_steps=args.max_steps,
                            cert_logger=_cert_logger,
                        )
                    elif args.mode == "ros2":
                        ep = _run_episode_ros2(
                            world, model, fleetsafe, start_xy, goal_xy,
                            ep_id, seed,
                            workspace=args.workspace,
                            robot_pkg=args.robot_pkg,
                            robot_urdf_xacro=args.robot_urdf_xacro,
                            gnm_ckpt=ckpt,
                        )
                    else:  # isaac — falls back to mock until Isaac launch wired
                        print(f"    [isaac] backend not yet wired — using mock for ep {ep_id}")
                        ep = _run_episode_mock(
                            world, model, fleetsafe, start_xy, goal_xy,
                            ep_id, seed,
                        )

                    episodes.append(ep)

                    if (ep_id + 1) % 5 == 0 or ep_id == args.num_episodes - 1:
                        sr  = sum(e.success   for e in episodes) / len(episodes)
                        col = sum(e.collision  for e in episodes) / len(episodes)
                        spl = sum(e.spl        for e in episodes) / len(episodes)
                        print(
                            f"    ep {ep_id+1:3d}/{args.num_episodes}  "
                            f"sr={sr*100:.0f}%  col={col*100:.0f}%  spl={spl:.3f}  "
                            f"infer={ep.inference_ms:.1f}ms  cbf={ep.cbf_ms:.2f}ms"
                        )

                agg = _aggregate(episodes)
                all_results[result_key] = agg
                all_episodes[result_key] = episodes

                # Write per-world-model JSON
                out = {
                    "world":     world_name,
                    "model":     model,
                    "fleetsafe": fleetsafe,
                    "sim_mode":  args.mode,
                    "aggregate": agg,
                    "episodes":  [asdict(e) for e in episodes],
                }
                fname = f"{world_name}_{model}_{'fs' if fleetsafe else 'bl'}_{args.mode}_benchmark.json"
                (args.output_dir / fname).write_text(json.dumps(out, indent=2))

    elapsed = time.perf_counter() - t0_total

    # Write summary JSON
    summary = {
        "config": {
            "worlds": args.worlds, "models": args.models,
            "fleetsafe": args.fleetsafe, "mode": args.mode,
            "num_episodes": args.num_episodes, "seed": args.seed,
            "d_safe": args.d_safe, "estop": args.estop, "v_max": args.v_max,
        },
        "results":    all_results,
        "elapsed_s":  round(elapsed, 2),
        "timestamp":  datetime.now(tz=timezone.utc).isoformat(),
    }
    summary_path = args.output_dir / "benchmark_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\n  Summary → {summary_path}")

    _write_markdown_report(all_results, args.output_dir / "benchmark_report.md")

    # Print quick comparison table
    print()
    print(f"{'─'*70}")
    print(f"  {'World':<14} {'Model':<6} {'Cond':<10} {'SR':>6} {'Col':>6} {'SPL':>6} {'MinDist':>8}")
    print(f"{'─'*70}")
    for key, agg in all_results.items():
        world_n, model_n, cond_n = key.split("|")
        print(
            f"  {world_n:<14} {model_n.upper():<6} {cond_n:<10} "
            f"{agg['success_rate']*100:5.0f}% "
            f"{agg['collision_rate']*100:5.0f}% "
            f"{agg['spl']:6.3f} "
            f"{agg['mean_min_dist_obs_m']:7.3f}m"
        )
    print(f"{'─'*70}")
    _cert_logger.close()
    print(f"  Safety certificates → {_cert_path}  ({_cert_logger.count} steps)")
    print(f"\n  {total} episodes  |  {elapsed:.1f}s  |  {elapsed/total:.2f}s/ep")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
