#!/usr/bin/env python3
"""
Yahboom dynamic realism validation script.

Compares commanded velocity, wheel angular velocity, body velocity,
slip ratio, and yaw drift across physics parameter sweeps.

Usage
-----
    # Single straight-line episode with default params
    python scripts/yahboom/validate_motion.py

    # Run all sweeps
    python scripts/yahboom/validate_motion.py --sweeps all

    # Specific sweep
    python scripts/yahboom/validate_motion.py --sweeps friction kp

    # Custom friction, more episodes
    python scripts/yahboom/validate_motion.py --friction 0.8 --n_episodes 5

    # Skip plots (CI mode)
    python scripts/yahboom/validate_motion.py --no_plots
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

# ── Repo root on path ────────────────────────────────────────────────────────── #
REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fleet_safe_vla.envs.mujoco.yahboom.physics_env import YahboomPhysicsEnv
from fleet_safe_vla.validation.motion_validator import MotionValidator
from fleet_safe_vla.validation.domain_sweep import (
    FrictionSweep,
    ActuatorGainSweep,
    MassSweep,
)


def _header(title: str) -> None:
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


def run_baseline(args, out_dir: Path) -> None:
    """Single-episode characterisation at nominal params."""
    _header("Baseline: Nominal Physics Parameters")

    env = YahboomPhysicsEnv(
        friction=args.friction,
        robot_mass=args.robot_mass,
        pid_kp=args.pid_kp,
        pid_ki=args.pid_ki,
    )
    validator = MotionValidator(env)

    # Straight line
    print(f"  straight-line vx={args.vx:.2f} m/s  duration={args.duration:.1f}s")
    records_sl = validator.run_straight_line(vx=args.vx, duration_s=args.duration, seed=42)
    m_sl = validator.compute_metrics(records_sl)

    # Turn in place
    print(f"  turn-in-place wz=1.0 rad/s  duration=2.0s")
    records_tp = validator.run_turn_in_place(wz=1.0, duration_s=2.0, seed=42)
    m_tp = validator.compute_metrics(records_tp)

    # Velocity ramp
    print(f"  velocity ramp 0→{args.vx:.2f} m/s  duration={args.duration:.1f}s")
    records_ramp = validator.run_velocity_ramp(vx_max=args.vx, duration_s=args.duration, seed=42)
    m_ramp = validator.compute_metrics(records_ramp)

    env.close()

    print()
    print(f"  {'Metric':<28} {'Straight':>10} {'Turn':>10} {'Ramp':>10}")
    print(f"  {'-'*58}")
    for metric in ["vx_rmse", "vx_ss_error", "mean_slip", "max_slip",
                   "yaw_drift_rad_per_m", "time_to_90pct_s", "stable"]:
        vs = getattr(m_sl, metric)
        vt = getattr(m_tp, metric)
        vr = getattr(m_ramp, metric)
        vs_s = f"{vs:.4f}" if isinstance(vs, float) and np.isfinite(vs) else str(vs)
        vt_s = f"{vt:.4f}" if isinstance(vt, float) and np.isfinite(vt) else str(vt)
        vr_s = f"{vr:.4f}" if isinstance(vr, float) and np.isfinite(vr) else str(vr)
        print(f"  {metric:<28} {vs_s:>10} {vt_s:>10} {vr_s:>10}")

    if not args.no_plots:
        validator.plot_velocity_tracking(records_sl,
            out_dir / "baseline_velocity_tracking.png", title="Baseline: Velocity Tracking")
        validator.plot_slip_ratio(records_sl,
            out_dir / "baseline_slip_ratio.png", title="Baseline: Slip Ratio")
        validator.plot_yaw_drift(records_sl,
            out_dir / "baseline_yaw_drift.png", title="Baseline: Yaw Drift")
        print(f"\n  Plots → {out_dir}/baseline_*.png")

    validator.export_csv(records_sl, out_dir / "baseline_straight_line.csv")
    validator.export_csv(records_tp, out_dir / "baseline_turn.csv")
    validator.export_csv(records_ramp, out_dir / "baseline_ramp.csv")
    print(f"  CSV  → {out_dir}/baseline_*.csv")


def run_sweep(name: str, sweep, out_dir: Path, args) -> None:
    _header(f"Sweep: {name}")
    t0 = time.monotonic()
    rows = sweep.run(verbose=True)
    elapsed = time.monotonic() - t0
    print(f"\n  Completed in {elapsed:.1f}s")

    csv_path = out_dir / f"sweep_{name}.csv"
    MotionValidator.export_metrics_csv(rows, csv_path)
    print(f"  CSV → {csv_path}")

    if not args.no_plots:
        png_path = out_dir / f"sweep_{name}.png"
        MotionValidator.plot_sweep_summary(
            rows,
            param_key="param_value",
            metrics=["vx_rmse", "mean_slip", "time_to_90pct_s"],
            path=png_path,
            title=f"{name} sweep",
        )
        print(f"  Plot → {png_path}")


def main() -> None:
    p = argparse.ArgumentParser(description="Yahboom physics validation")
    p.add_argument("--sweeps", nargs="*", default=[],
                   choices=["all", "friction", "kp", "mass"],
                   help="Which parameter sweeps to run (default: none, baseline only)")
    p.add_argument("--n_episodes", type=int, default=3,
                   help="Episodes per sweep point")
    p.add_argument("--vx", type=float, default=0.3,
                   help="Commanded forward speed for tests (m/s)")
    p.add_argument("--duration", type=float, default=3.0,
                   help="Episode duration (s)")
    p.add_argument("--friction", type=float, default=0.8)
    p.add_argument("--robot_mass", type=float, default=2.1)
    p.add_argument("--pid_kp", type=float, default=0.10)
    p.add_argument("--pid_ki", type=float, default=0.50)
    p.add_argument("--out_dir", type=str, default="logs/yahboom/validation")
    p.add_argument("--no_plots", action="store_true",
                   help="Skip matplotlib output (CI mode)")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_baseline(args, out_dir)

    sweeps_to_run = set(args.sweeps)
    if "all" in sweeps_to_run:
        sweeps_to_run = {"friction", "kp", "mass"}

    kw = dict(n_episodes=args.n_episodes, vx_cmd=args.vx, duration_s=args.duration)

    if "friction" in sweeps_to_run:
        run_sweep("friction", FrictionSweep(**kw), out_dir, args)

    if "kp" in sweeps_to_run:
        run_sweep("actuator_kp", ActuatorGainSweep(**kw), out_dir, args)

    if "mass" in sweeps_to_run:
        run_sweep("mass", MassSweep(**kw), out_dir, args)

    print(f"\n[validate_motion] All outputs in {out_dir}/")


if __name__ == "__main__":
    main()
