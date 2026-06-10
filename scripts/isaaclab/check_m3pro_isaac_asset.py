#!/usr/bin/env python3
"""
scripts/isaaclab/check_m3pro_isaac_asset.py

Yahboom M3Pro asset gate checker.

Validates the M3Pro URDF, checks for required joint and sensor frames,
and optionally runs a 100-step ground contact test in Isaac Sim.

Exit codes:
  0 = all checks pass (or all non-Isaac checks pass with --no-isaac)
  1 = one or more checks failed
  2 = Isaac Sim unavailable (expected in CI without GPU/license)

Usage:
  python scripts/isaaclab/check_m3pro_isaac_asset.py          (full check)
  python scripts/isaaclab/check_m3pro_isaac_asset.py --no-isaac  (URDF checks only)
  python scripts/isaaclab/check_m3pro_isaac_asset.py --verbose
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── Check results ─────────────────────────────────────────────────────────────

PASS  = "PASS"
FAIL  = "FAIL"
WARN  = "WARN"
SKIP  = "SKIP"


class CheckResult:
    def __init__(self, name: str, status: str, detail: str = "") -> None:
        self.name   = name
        self.status = status
        self.detail = detail

    def __str__(self) -> str:
        icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "SKIP": "○"}[self.status]
        line = f"  [{icon}] {self.status:<4}  {self.name}"
        if self.detail:
            line += f"\n            {self.detail}"
        return line


# ── URDF checks (no Isaac required) ──────────────────────────────────────────

def check_urdf_exists(urdf_path: Path) -> CheckResult:
    if urdf_path.exists():
        return CheckResult("URDF file exists", PASS, str(urdf_path.relative_to(REPO_ROOT)))
    return CheckResult(
        "URDF file exists", FAIL,
        f"Missing: {urdf_path}\n"
        "  Run: python scripts/yahboom/validate_m3pro_assets.py"
    )


def check_urdf_parseable(urdf_path: Path) -> CheckResult:
    if not urdf_path.exists():
        return CheckResult("URDF parseable", SKIP, "URDF missing — skipped")
    try:
        import xml.etree.ElementTree as ET
        ET.parse(urdf_path)
        return CheckResult("URDF parseable (valid XML)", PASS)
    except Exception as e:
        return CheckResult("URDF parseable", FAIL, str(e))


def check_wheel_joints(urdf_path: Path) -> CheckResult:
    required = {"fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint"}
    if not urdf_path.exists():
        return CheckResult("4 wheel joints present", SKIP, "URDF missing — skipped")
    try:
        text = urdf_path.read_text()
        found = {j for j in required if f'name="{j}"' in text}
        missing = required - found
        if not missing:
            return CheckResult("4 wheel joints present", PASS, f"Found: {sorted(found)}")
        return CheckResult(
            "4 wheel joints present", FAIL,
            f"Missing joints: {sorted(missing)}\n"
            "  Joint names must not be renamed — obs_adapter and env_cfg depend on them."
        )
    except Exception as e:
        return CheckResult("4 wheel joints present", FAIL, str(e))


def check_camera_frame(urdf_path: Path) -> CheckResult:
    if not urdf_path.exists():
        return CheckResult("camera_link frame exists", SKIP, "URDF missing — skipped")
    text = urdf_path.read_text()
    if 'name="camera_link"' in text or 'name="camera_optical_link"' in text:
        return CheckResult("camera_link frame exists", PASS)
    return CheckResult(
        "camera_link frame exists", FAIL,
        "No camera_link or camera_optical_link found in URDF.\n"
        "  Add a camera_link fixed joint for visual navigation observation pipeline."
    )


def check_lidar_frame(urdf_path: Path) -> CheckResult:
    if not urdf_path.exists():
        return CheckResult("lidar_link frame exists", SKIP, "URDF missing — skipped")
    text = urdf_path.read_text()
    if 'name="lidar_link"' in text:
        return CheckResult("lidar_link frame exists", PASS)
    return CheckResult(
        "lidar_link frame exists", WARN,
        "No lidar_link found. LiDAR sensor disabled — add when sensor is available."
    )


def check_collision_geoms(urdf_path: Path) -> CheckResult:
    if not urdf_path.exists():
        return CheckResult("collision geometries present", SKIP, "URDF missing — skipped")
    text = urdf_path.read_text()
    n_collision = text.count("<collision>")
    if n_collision >= 5:  # base_link + 4 wheels minimum
        return CheckResult(
            "collision geometries present", PASS,
            f"Found {n_collision} <collision> blocks (≥5 required)"
        )
    return CheckResult(
        "collision geometries present", FAIL,
        f"Found only {n_collision} <collision> blocks — expected ≥5 (base + 4 wheels)."
    )


def check_usd_cache(usd_dir: Path) -> CheckResult:
    candidates = list(usd_dir.rglob("*.usd")) if usd_dir.exists() else []
    if candidates:
        rel = candidates[0].relative_to(REPO_ROOT)
        return CheckResult("USD cache present", PASS, f"Found: {rel}")
    return CheckResult(
        "USD cache present", WARN,
        f"USD not yet generated under: {usd_dir.relative_to(REPO_ROOT)}\n"
        "  Will be auto-generated on first Isaac Sim run via UrdfConverter.\n"
        "  Run: ./scripts/isaaclab/view_m3pro.sh"
    )


def check_inertials_measured(urdf_path: Path) -> CheckResult:
    if not urdf_path.exists():
        return CheckResult("inertials physically measured", SKIP, "URDF missing — skipped")
    text = urdf_path.read_text()
    # Structural URDF contains this warning comment
    if "PLACEHOLDER" in text or "product-spec" in text or "approximat" in text:
        return CheckResult(
            "inertials physically measured", WARN,
            "Inertial values are box/cylinder approximations from product spec.\n"
            "  Replace with physically measured values before Stage 1 RL training.\n"
            "  Expected ~30% velocity tracking error until corrected.\n"
            "  See: fleet_safe_vla/robots/yahboom/m3pro/ASSET_IMPORT_PLAN.md"
        )
    return CheckResult("inertials physically measured", PASS)


# ── Isaac Sim checks (require GPU + Isaac Sim license) ────────────────────────

def check_isaac_available() -> CheckResult:
    try:
        import isaaclab  # noqa: F401
        return CheckResult("Isaac Lab importable", PASS)
    except ImportError:
        return CheckResult(
            "Isaac Lab importable", SKIP,
            "isaaclab not found — run 'conda activate isaac' for full checks.\n"
            "  CI runs without Isaac are expected and valid."
        )


def run_isaac_ground_contact_test(urdf_path: Path, usd_dir: Path) -> CheckResult:
    """
    Spawn M3Pro in Isaac Sim headless, run 100 steps, check for NaNs and
    ground contact. Must be called AFTER AppLauncher.
    """
    try:
        import torch
        import numpy as np
        from isaaclab.app import AppLauncher
        import isaaclab.sim as sim_utils
        from isaaclab.assets import Articulation
        from isaaclab.sim import SimulationContext

        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import (
            build_m3pro_articulation_cfg,
        )

        class _Args:
            headless = True
            device   = "cpu"

        launcher = AppLauncher(_Args())
        app      = launcher.app

        sim_cfg = sim_utils.SimulationCfg(dt=0.01, device="cpu")
        sim     = SimulationContext(sim_cfg)

        gnd = sim_utils.GroundPlaneCfg()
        gnd.func("/World/Ground", gnd)

        robot = Articulation(cfg=build_m3pro_articulation_cfg())
        sim.reset()

        nan_steps  = 0
        min_z      = float("inf")
        sim_dt     = sim.get_physics_dt()

        for _ in range(100):
            robot.write_data_to_sim()
            sim.step()
            robot.update(sim_dt)

            pos = robot.data.root_pos_w[0]
            vel = robot.data.root_lin_vel_w[0]

            if torch.isnan(pos).any() or torch.isnan(vel).any():
                nan_steps += 1

            z = float(pos[2])
            if z < min_z:
                min_z = z

        app.close()

        if nan_steps > 0:
            return CheckResult(
                "Isaac 100-step ground contact", FAIL,
                f"NaN detected in {nan_steps}/100 steps — physics instability."
            )
        if min_z < -0.02:
            return CheckResult(
                "Isaac 100-step ground contact", FAIL,
                f"Robot fell through ground: min_z={min_z:.4f} m"
            )
        if min_z > 0.20:
            return CheckResult(
                "Isaac 100-step ground contact", WARN,
                f"Robot appears to be floating: min_z={min_z:.4f} m "
                "(expected ~0.048 m = wheel_radius)"
            )
        return CheckResult(
            "Isaac 100-step ground contact", PASS,
            f"100 steps clean, no NaNs, min_z={min_z:.4f} m"
        )

    except ImportError as e:
        return CheckResult(
            "Isaac 100-step ground contact", SKIP,
            f"Isaac unavailable: {e}"
        )
    except Exception as e:
        return CheckResult(
            "Isaac 100-step ground contact", FAIL,
            f"Unexpected error during Isaac test: {e}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Yahboom M3Pro Isaac Sim asset gate checker."
    )
    parser.add_argument(
        "--no-isaac", action="store_true",
        help="Skip Isaac Sim checks (URDF checks only — safe for CI without GPU)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show all check details including PASS"
    )
    args = parser.parse_args(argv)

    from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.asset_cfg import (
        M3PRO_URDF, M3PRO_USD_DIR,
    )
    from fleet_safe_vla.benchmark_version import GIT_COMMIT

    print()
    print("═══════════════════════════════════════════════════════════════════")
    print("  Yahboom M3Pro — Isaac Sim Asset Gate Checker")
    print("═══════════════════════════════════════════════════════════════════")
    print(f"  URDF    : {M3PRO_URDF.relative_to(REPO_ROOT)}")
    print(f"  USD dir : {M3PRO_USD_DIR.relative_to(REPO_ROOT)}")
    print(f"  Commit  : {GIT_COMMIT}")
    print("═══════════════════════════════════════════════════════════════════")
    print()

    results: list[CheckResult] = [
        check_urdf_exists(M3PRO_URDF),
        check_urdf_parseable(M3PRO_URDF),
        check_wheel_joints(M3PRO_URDF),
        check_camera_frame(M3PRO_URDF),
        check_lidar_frame(M3PRO_URDF),
        check_collision_geoms(M3PRO_URDF),
        check_usd_cache(M3PRO_USD_DIR),
        check_inertials_measured(M3PRO_URDF),
        check_isaac_available(),
    ]

    if not args.no_isaac:
        # Only run Isaac test if module is available (it launches headless Isaac Sim)
        try:
            import isaaclab  # noqa: F401
            results.append(run_isaac_ground_contact_test(M3PRO_URDF, M3PRO_USD_DIR))
        except ImportError:
            results.append(CheckResult(
                "Isaac 100-step ground contact", SKIP,
                "Isaac unavailable — skipped (expected in CI)"
            ))

    # ── Print results ─────────────────────────────────────────────────────────
    n_pass = sum(1 for r in results if r.status == PASS)
    n_fail = sum(1 for r in results if r.status == FAIL)
    n_warn = sum(1 for r in results if r.status == WARN)
    n_skip = sum(1 for r in results if r.status == SKIP)

    for r in results:
        if args.verbose or r.status != PASS:
            print(r)
    if not args.verbose:
        print(f"\n  ({n_pass} PASS hidden — use --verbose to show all)")

    print()
    print("═══════════════════════════════════════════════════════════════════")
    print(f"  Result: {n_pass} PASS  {n_fail} FAIL  {n_warn} WARN  {n_skip} SKIP")
    if n_fail == 0 and n_warn == 0:
        print("  STATUS: ALL CHECKS PASSED")
    elif n_fail == 0:
        print("  STATUS: PASS WITH WARNINGS — review WARN items before RL training")
    else:
        print("  STATUS: FAIL — resolve FAIL items before launching Isaac Sim")
    print("═══════════════════════════════════════════════════════════════════")
    print()

    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
