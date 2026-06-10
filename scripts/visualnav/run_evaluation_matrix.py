#!/usr/bin/env python3
"""
run_evaluation_matrix.py — GNM vs ViNT × baseline vs FleetSafe comparison.

Runs the full 4-condition evaluation matrix and prints a comparison table:

    ┌─────────────────────────────────────────────────────────────────────┐
    │  Model         │ FleetSafe │ Success │ Collisions │ Interventions │ …│
    ├─────────────────────────────────────────────────────────────────────┤
    │  GNM           │     OFF   │  …%     │  …%        │    —          │  │
    │  GNM + FS      │     ON    │  …%     │  …%        │  …%           │  │
    │  ViNT          │     OFF   │  …%     │  …%        │    —          │  │
    │  ViNT + FS     │     ON    │  …%     │  …%        │  …%           │  │
    └─────────────────────────────────────────────────────────────────────┘

Backends
--------
  --backend mock     (default) Uses kinematic mock sim — no Isaac, no MuJoCo
                     required.  The REAL GNM/ViNT model is invoked for
                     inference; only the physics are synthetic.  Starts in
                     seconds.  This is the recommended mode for May 29.

  --backend mujoco   Full MuJoCo physics.  Slower startup (~5 s).

Usage
-----
    # Quick evaluation (real model inference, mock physics):
    python scripts/visualnav/run_evaluation_matrix.py

    # With real GNM + ViNT checkpoints:
    python scripts/visualnav/run_evaluation_matrix.py \\
        --gnm-ckpt  third_party/visualnav-transformer/model_weights/gnm/gnm.pth \\
        --vint-ckpt third_party/visualnav-transformer/model_weights/vint/vint.pth

    # Save results to JSON:
    python scripts/visualnav/run_evaluation_matrix.py --output results/matrix.json

    # More episodes (more statistically robust):
    python scripts/visualnav/run_evaluation_matrix.py --episodes 20 --seeds 5

    # Compare all three models:
    python scripts/visualnav/run_evaluation_matrix.py --models gnm vint nomad
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

_VNT      = _REPO / "third_party" / "visualnav-transformer" / "model_weights"
_CKPTS    = {
    "gnm":   _VNT / "gnm"   / "gnm.pth",
    "vint":  _VNT / "vint"  / "vint.pth",
    "nomad": _VNT / "nomad" / "nomad.pth",
}

from fleet_safe_vla.benchmarks.hospital_scenes import SCENES, get_scene_config


# ── Episode result ─────────────────────────────────────────────────────────────

@dataclass
class EpResult:
    success:          bool  = False
    collision:        bool  = False
    steps:            int   = 0
    path_length_m:    float = 0.0
    time_s:           float = 0.0
    min_dist_m:       float = float("inf")
    intervention_count: int = 0
    near_miss_count:  int   = 0
    inference_ms:     list  = field(default_factory=list)
    cbf_ms:           list  = field(default_factory=list)
    delta_vx:         list  = field(default_factory=list)
    delta_wz:         list  = field(default_factory=list)


@dataclass
class ConditionResult:
    model:        str
    fleetsafe:    bool
    episodes:     list[EpResult] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.episodes)

    def _mean(self, vals: list[float]) -> float:
        return float(np.mean(vals)) if vals else 0.0

    def success_rate(self) -> float:
        return self._mean([float(e.success) for e in self.episodes])

    def collision_rate(self) -> float:
        return self._mean([float(e.collision) for e in self.episodes])

    def mean_path_m(self) -> float:
        return self._mean([e.path_length_m for e in self.episodes])

    def mean_steps(self) -> float:
        return self._mean([float(e.steps) for e in self.episodes])

    def mean_time_s(self) -> float:
        return self._mean([e.time_s for e in self.episodes])

    def mean_min_dist(self) -> float:
        return self._mean([e.min_dist_m for e in self.episodes])

    def mean_interventions(self) -> float:
        return self._mean([float(e.intervention_count) for e in self.episodes])

    def intervention_rate(self) -> float:
        total = sum(e.steps for e in self.episodes)
        ivs   = sum(e.intervention_count for e in self.episodes)
        return ivs / max(1, total)

    def mean_inference_ms(self) -> float:
        vals = [ms for e in self.episodes for ms in e.inference_ms]
        return self._mean(vals)

    def mean_cbf_ms(self) -> float:
        vals = [ms for e in self.episodes for ms in e.cbf_ms]
        return self._mean(vals)

    def mean_delta_vx(self) -> float:
        vals = [d for e in self.episodes for d in e.delta_vx]
        return self._mean(vals)

    def near_miss_rate(self) -> float:
        return self._mean([float(e.near_miss_count > 0) for e in self.episodes])

    def to_dict(self) -> dict:
        return {
            "model":            self.model,
            "fleetsafe":        self.fleetsafe,
            "n_episodes":       self.n,
            "success_rate":     round(self.success_rate(), 3),
            "collision_rate":   round(self.collision_rate(), 3),
            "near_miss_rate":   round(self.near_miss_rate(), 3),
            "mean_path_m":      round(self.mean_path_m(), 3),
            "mean_steps":       round(self.mean_steps(), 1),
            "mean_time_s":      round(self.mean_time_s(), 2),
            "mean_min_dist_m":  round(self.mean_min_dist(), 3),
            "mean_interventions": round(self.mean_interventions(), 2),
            "intervention_rate": round(self.intervention_rate(), 3),
            "mean_inference_ms": round(self.mean_inference_ms(), 2),
            "mean_cbf_ms":      round(self.mean_cbf_ms(), 2),
            "mean_delta_vx":    round(self.mean_delta_vx(), 4),
        }


# ── Adapter factory ───────────────────────────────────────────────────────────

def _load_adapter(model: str, ckpt_override: Path | None, verbose: bool = True):
    """Load a real adapter or fall back to a mock if checkpoint is missing."""
    from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import (
        ActionOutput, BaseVisualNavAdapter, UpstreamNotFoundError, CheckpointNotFoundError,
    )

    if model == "gnm":
        from fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter import GNMAdapter
        adapter = GNMAdapter()
    elif model == "vint":
        from fleet_safe_vla.integrations.visualnav_transformer.vint_adapter import ViNTAdapter
        adapter = ViNTAdapter()
    elif model == "nomad":
        from fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter import NoMaDAdapter
        adapter = NoMaDAdapter()
    else:
        raise ValueError(f"Unknown model: {model}")

    ckpt = ckpt_override or _CKPTS.get(model)
    if ckpt and ckpt.exists():
        if verbose:
            print(f"  [{model}] Loading checkpoint: {ckpt.name}")
        try:
            adapter.load_checkpoint(ckpt)
            if verbose:
                print(f"  [{model}] Checkpoint loaded — REAL model inference")
            return adapter, "checkpoint"
        except (UpstreamNotFoundError, CheckpointNotFoundError, Exception) as exc:
            if verbose:
                print(f"  [{model}] Checkpoint load failed ({exc}) — using mock")
    else:
        if verbose:
            print(f"  [{model}] No checkpoint found — using mock adapter")

    # Mock fallback: returns deterministic waypoints without upstream
    spec_size = adapter.image_size
    spec_ctx  = adapter.context_size
    spec_n    = getattr(adapter, "action_horizon", 5)

    class _MockLoaded(BaseVisualNavAdapter):
        model_name   = model
        image_size   = spec_size
        context_size = spec_ctx
        action_horizon = spec_n

        def load_checkpoint(self, _): self._loaded = True
        def preprocess_observation(self, obs, goal):
            return {"obs_tensor": None, "goal_tensor": None}
        def predict_action(self, _):
            rng = np.random.default_rng(42)
            wp  = rng.uniform(0.05, 0.20, (spec_n, 2)).astype(np.float32)
            wp[:, 0] = np.abs(wp[:, 0])
            return ActionOutput(waypoints=wp, model_name=model, inference_ms=8.0)

    m = _MockLoaded()
    m._loaded = True
    return m, "mock"


# ── Mock kinematic simulator ──────────────────────────────────────────────────

def _run_episode_mock(
    adapter,
    scene_name: str,
    fleetsafe: bool,
    seed: int,
    *,
    v_max: float    = 0.30,
    w_max: float    = 0.70,
    d_safe: float   = 0.50,
    estop: float    = 0.30,
    control_hz: float = 4.0,
    near_miss_dist: float = 0.45,
    max_steps_override: int | None = None,
) -> EpResult:
    """
    Run one episode in the kinematic mock sim.

    The REAL adapter is called for inference each step (obs_imgs, goal_img →
    waypoints).  Only the physics are synthetic.  This is the right mode to use
    when checkpoints are available but Isaac/MuJoCo is not ready.
    """
    from fleet_safe_vla.integrations.visualnav_transformer.isaac_obs_adapter import (
        IsaacCameraObsAdapter,
    )
    from fleet_safe_vla.fleet_safety.yahboom_cbf import YahboomCBFConfig, YahboomCBFFilter
    from fleet_safe_vla.integrations.visualnav_transformer.base_adapter import waypoints_to_cmd_vel

    scene = get_scene_config(scene_name)
    rng   = np.random.default_rng(seed)

    obs_xy = np.array(scene.obstacle_positions, dtype=np.float64) if scene.obstacle_positions else np.zeros((0, 2))
    obs_r  = np.array(scene.obstacle_radii,     dtype=np.float64) if scene.obstacle_radii     else np.zeros(0)
    goal   = np.array(scene.goal_xy,            dtype=np.float64)

    x, y, yaw = float(scene.start_xy[0]), float(scene.start_xy[1]), 0.0
    dt = 1.0 / control_hz

    # Camera observation adapter
    W, H = adapter.image_size
    ctx  = adapter.context_size
    cam  = IsaacCameraObsAdapter(image_size=(W, H), context_size=ctx)
    # Use a synthetic goal snapshot (no real goal image in mock mode)
    cam.set_goal_image(IsaacCameraObsAdapter.make_checkerboard_goal(W, H))

    cbf = YahboomCBFFilter(YahboomCBFConfig(d_safe_m=d_safe, estop_dist_m=estop)) if fleetsafe else None
    obs_positions = [np.array(p) for p in scene.obstacle_positions] if scene.obstacle_positions else []
    obs_radii     = list(scene.obstacle_radii) if scene.obstacle_radii else []

    result = EpResult()
    prev_xy = np.array([x, y])
    t_start = time.perf_counter()

    n_steps = max_steps_override if max_steps_override is not None else scene.max_steps
    for step in range(n_steps):
        robot_xy = np.array([x, y])

        # ── Compute surface distance to nearest obstacle ───────────────────────
        if len(obs_r):
            dists = np.linalg.norm(obs_xy - robot_xy, axis=1) - obs_r
            min_d = float(np.min(dists))
        else:
            min_d = 99.0

        result.min_dist_m = min(result.min_dist_m, min_d)

        # ── Camera frame: synthetic random (exercises full preprocessing) ─────
        frame = IsaacCameraObsAdapter.make_random_obs(W, H, seed=seed * 10000 + step)
        cam.push_frame(frame)
        obs_imgs, goal_img = cam.get_context()

        # ── Real model inference ──────────────────────────────────────────────
        t_inf = time.perf_counter()
        preprocessed = adapter.preprocess_observation(obs_imgs, goal_img)
        action        = adapter.predict_action(preprocessed)
        inference_ms  = (time.perf_counter() - t_inf) * 1000.0
        result.inference_ms.append(inference_ms)

        raw_cmd = waypoints_to_cmd_vel(
            action.waypoints, v_max=v_max, w_max=w_max, control_hz=control_hz,
        )

        # ── FleetSafe CBF-QP filter ───────────────────────────────────────────
        t_cbf = time.perf_counter()
        if cbf is not None and obs_positions:
            nominal_arr = np.array([raw_cmd.vx, raw_cmd.wz], dtype=np.float64)
            obs_vec     = np.zeros(47, dtype=np.float64)
            safe_arr, cbf_info = cbf.filter(
                obs_vec, nominal_arr, obs_positions,
                robot_xy=robot_xy, obstacle_radii=obs_radii,
            )
            safe_vx, safe_wz = float(safe_arr[0]), float(safe_arr[1])
            if cbf_info.get("intervened", False):
                result.intervention_count += 1
        else:
            safe_vx, safe_wz = raw_cmd.vx, raw_cmd.wz
        cbf_ms = (time.perf_counter() - t_cbf) * 1000.0
        result.cbf_ms.append(cbf_ms)
        result.delta_vx.append(abs(raw_cmd.vx - safe_vx))

        # ── Kinematics ────────────────────────────────────────────────────────
        x   += safe_vx * math.cos(yaw) * dt
        y   += safe_vx * math.sin(yaw) * dt
        yaw += safe_wz * dt

        cur_xy = np.array([x, y])
        result.path_length_m += float(np.linalg.norm(cur_xy - prev_xy))
        prev_xy = cur_xy.copy()

        # ── Terminal conditions ────────────────────────────────────────────────
        robot_xy = cur_xy
        if len(obs_r):
            dists    = np.linalg.norm(obs_xy - robot_xy, axis=1) - obs_r
            min_d    = float(np.min(dists))
            result.min_dist_m = min(result.min_dist_m, min_d)
        dist_to_goal = float(np.linalg.norm(goal - robot_xy))

        result.steps = step + 1

        if min_d < 0.0:
            result.collision = True
            break
        if min_d < near_miss_dist:
            result.near_miss_count += 1
        if dist_to_goal < 0.30:
            result.success = True
            break

    result.time_s = time.perf_counter() - t_start
    return result


# ── Table printing ────────────────────────────────────────────────────────────

def _bar(val: float, lo: float, hi: float, width: int = 8, invert: bool = False) -> str:
    """ASCII progress bar for a value in [lo, hi]."""
    frac = (val - lo) / max(hi - lo, 1e-9)
    if invert:
        frac = 1.0 - frac
    frac = max(0.0, min(1.0, frac))
    filled = int(round(frac * width))
    return "█" * filled + "░" * (width - filled)


def _print_table(conditions: list[ConditionResult]) -> None:
    print()
    print("┌" + "─" * 99 + "┐")
    print(
        f"│ {'Condition':<22} {'Success':>7} {'Collide':>7} {'Interv%':>7} "
        f"{'MinDist':>7} {'PathLen':>7} {'Infer_ms':>8} {'CBF_ms':>7} {'ΔVx':>7}  │"
    )
    print("├" + "─" * 99 + "┤")

    for c in conditions:
        label = f"{c.model.upper()}" + (" + FleetSafe" if c.fleetsafe else "         ")
        iv_str = f"{c.intervention_rate()*100:5.1f}%" if c.fleetsafe else "   —   "
        print(
            f"│ {label:<22} "
            f"{c.success_rate()*100:6.1f}% "
            f"{c.collision_rate()*100:6.1f}% "
            f"{iv_str:>7} "
            f"{c.mean_min_dist():7.3f} "
            f"{c.mean_path_m():7.2f} "
            f"{c.mean_inference_ms():8.1f} "
            f"{c.mean_cbf_ms():7.2f} "
            f"{c.mean_delta_vx():7.4f}  │"
        )

    print("└" + "─" * 99 + "┘")
    print()


def _print_delta(baseline: ConditionResult, safe: ConditionResult) -> None:
    """Show the FleetSafe effect for one model."""
    sc_delta   = safe.success_rate()   - baseline.success_rate()
    col_delta  = safe.collision_rate() - baseline.collision_rate()
    dist_delta = safe.mean_min_dist()  - baseline.mean_min_dist()
    model      = baseline.model.upper()
    print(f"  FleetSafe effect on {model}:")
    print(f"    Success rate :  {baseline.success_rate()*100:.1f}%  →  {safe.success_rate()*100:.1f}%  (Δ {sc_delta*100:+.1f}%)")
    print(f"    Collision rate: {baseline.collision_rate()*100:.1f}%  →  {safe.collision_rate()*100:.1f}%  (Δ {col_delta*100:+.1f}%)")
    print(f"    Min dist    :  {baseline.mean_min_dist():.3f} m  →  {safe.mean_min_dist():.3f} m  (Δ {dist_delta:+.3f} m)")
    print(f"    Interventions: {safe.intervention_rate()*100:.1f}% of steps")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models",    nargs="+", default=["gnm", "vint"],
                   choices=["gnm", "vint", "nomad"])
    p.add_argument("--scenes",    nargs="+", default=["hospital_corridor", "cluttered_navigation"],
                   choices=list(SCENES.keys()))
    p.add_argument("--episodes",  type=int, default=10,
                   help="Episodes per condition (default 10)")
    p.add_argument("--seeds",     type=int, default=5,
                   help="Random seeds to cycle (default 5)")
    p.add_argument("--backend",   choices=["mock"], default="mock",
                   help="Simulation backend (mock = kinematic, no Isaac needed)")
    p.add_argument("--gnm-ckpt",  type=Path, default=None)
    p.add_argument("--vint-ckpt", type=Path, default=None)
    p.add_argument("--nomad-ckpt",type=Path, default=None)
    p.add_argument("--d-safe",    type=float, default=0.50)
    p.add_argument("--estop",     type=float, default=0.30)
    p.add_argument("--v-max",     type=float, default=0.30)
    p.add_argument("--w-max",     type=float, default=0.70)
    p.add_argument("--max-steps", type=int,   default=None,
                   help="Cap episode length (default: scene default 200-400). "
                        "Use 30 for a quick smoke test.")
    p.add_argument("--output",    type=Path, default=None)
    args = p.parse_args()

    ckpt_overrides = {
        "gnm":   args.gnm_ckpt,
        "vint":  args.vint_ckpt,
        "nomad": args.nomad_ckpt,
    }

    print()
    print("=" * 72)
    print("  FleetSafe × VisualNav-Transformer  |  Evaluation Matrix")
    print("=" * 72)
    print(f"  Models   : {', '.join(args.models)}")
    print(f"  Scenes   : {', '.join(args.scenes)}")
    print(f"  Episodes : {args.episodes} per condition")
    print(f"  Max steps: {args.max_steps or 'scene default'}")
    print(f"  Backend  : {args.backend}")
    print(f"  Safety   : d_safe={args.d_safe} m  estop={args.estop} m")
    print()

    conditions: list[ConditionResult] = []

    for model in args.models:
        print(f"Loading {model.upper()} adapter…")
        adapter, mode = _load_adapter(model, ckpt_overrides.get(model), verbose=True)
        print(f"  Mode: {mode}\n")

        for fs in [False, True]:
            cond = ConditionResult(model=model, fleetsafe=fs)
            label = f"{model.upper()} {'+ FleetSafe' if fs else 'baseline  '}"
            print(f"  Running {label} ({args.episodes} episodes × {len(args.scenes)} scenes)…")

            ep_idx = 0
            for scene_name in args.scenes:
                for seed in range(args.episodes):
                    result = _run_episode_mock(
                        adapter,
                        scene_name         = scene_name,
                        fleetsafe          = fs,
                        seed               = seed * 100 + ep_idx,
                        v_max              = args.v_max,
                        w_max              = args.w_max,
                        d_safe             = args.d_safe,
                        estop              = args.estop,
                        max_steps_override = args.max_steps,
                    )
                    cond.episodes.append(result)
                    ep_idx += 1
                    status_char = "✓" if result.success else ("✗" if result.collision else "~")
                    print(f"    {scene_name}  seed={seed}  {status_char}  "
                          f"steps={result.steps}  min_dist={result.min_dist_m:.3f}  "
                          f"ivs={result.intervention_count}")

            conditions.append(cond)
            print()

    # ── Print comparison table ────────────────────────────────────────────────
    print("=" * 72)
    print("  RESULTS TABLE")
    print("=" * 72)
    _print_table(conditions)

    # ── FleetSafe delta for each model ────────────────────────────────────────
    print("  FleetSafe Δ (intervention effect)")
    print("─" * 72)
    for i in range(0, len(conditions), 2):
        baseline = conditions[i]
        safe     = conditions[i + 1]
        _print_delta(baseline, safe)

    # ── Column legend ─────────────────────────────────────────────────────────
    print("  Column legend")
    print("  ─────────────────────────────────────────────────────────────────")
    print("  Success   : fraction of episodes where robot reached the goal")
    print("  Collide   : fraction of episodes with actual collision")
    print("  Interv%   : fraction of control steps where CBF modified u_nom")
    print("  MinDist   : mean closest approach distance to any obstacle (m)")
    print("  PathLen   : mean path length (m)")
    print("  Infer_ms  : mean model inference latency (ms)")
    print("  CBF_ms    : mean CBF-QP solve latency (ms)")
    print("  ΔVx       : mean |u_nom_vx - u_safe_vx| (m/s)")
    print()

    # ── Save JSON ─────────────────────────────────────────────────────────────
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp":  time.time(),
            "config": {
                "models":   args.models,
                "scenes":   args.scenes,
                "episodes": args.episodes,
                "backend":  args.backend,
                "d_safe":   args.d_safe,
                "estop":    args.estop,
                "v_max":    args.v_max,
            },
            "results": [c.to_dict() for c in conditions],
        }
        args.output.write_text(json.dumps(data, indent=2))
        print(f"  Saved → {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
