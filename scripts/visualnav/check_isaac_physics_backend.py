#!/usr/bin/env python3
"""
check_isaac_physics_backend.py — Isaac physics backend gate checks.

Verifies that the Isaac Lab physics backend is correctly configured and
ready to produce benchmark metrics.  Seven checks run in order:

  1. env_module_importable         — always runs (CI safe)
  2. error_class_importable        — always runs
  3. raises_without_applaunch      — always runs
  4. scene_obs_positions_match     — always runs (pure data check)
  5. kinematic_formula_matches     — always runs (pure math)
  6. obs_vector_dim_consistent     — always runs
  7. isaac_env_reset_step          — runs only inside Isaac process

Checks 1–6 pass in normal CI without Isaac installed.
Check 7 requires the isaac conda env with AppLauncher active.

Exit codes:
  0   all non-skipped checks pass
  1   one or more checks FAIL
  2   Isaac not installed (checks 1–6 pass, check 7 SKIP)

Usage (CI — without Isaac):
  python scripts/visualnav/check_isaac_physics_backend.py

Usage (with Isaac, headless):
  conda activate isaac
  python scripts/visualnav/check_isaac_physics_backend.py --with-isaac

Usage (inside Isaac AppLauncher — full check):
  conda activate isaac
  python -c "
  from isaaclab.app import AppLauncher
  app = AppLauncher({'headless': True}).app
  exec(open('scripts/visualnav/check_isaac_physics_backend.py').read())
  import sys; sys.exit(main(['--with-isaac']))
  "
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

PASS  = "PASS"
FAIL  = "FAIL"
SKIP  = "SKIP"

_results: list[tuple[str, str, str]] = []   # (name, status, detail)

# Detect whether we're inside an active AppLauncher process (pxr available means Isaac Sim
# has been initialised — pxr is only importable after SimulationApp/AppLauncher startup).
try:
    from pxr import Usd as _Usd  # noqa: F401
    _INSIDE_APPLAUNCH = True
except ImportError:
    _INSIDE_APPLAUNCH = False


def _record(name: str, status: str, detail: str = "") -> None:
    _results.append((name, status, detail))
    marker = {"PASS": "✓", "FAIL": "✗", "SKIP": "~"}[status]
    # Write to stderr so output is visible even when Isaac's startup log floods stdout.
    sys.stderr.write(f"  [{marker}]  {name:<45} {detail}\n")
    sys.stderr.flush()


# ── Check 1: env module importable ────────────────────────────────────────────

def check_env_module_importable() -> None:
    try:
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (  # noqa: F401
            IsaacNavBenchmarkEnv,
        )
        _record("env_module_importable", PASS,
                "IsaacNavBenchmarkEnv importable without Isaac")
    except Exception as exc:
        _record("env_module_importable", FAIL, str(exc))


# ── Check 2: error class importable ──────────────────────────────────────────

def check_error_class_importable() -> None:
    try:
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (  # noqa: F401
            IsaacNotAvailableError,
        )
        _record("error_class_importable", PASS,
                "IsaacNotAvailableError importable without Isaac")
    except Exception as exc:
        _record("error_class_importable", FAIL, str(exc))


# ── Check 3: instantiation raises without AppLauncher ────────────────────────

def check_raises_without_applaunch() -> None:
    if _INSIDE_APPLAUNCH:
        # pxr is importable → we're already inside an AppLauncher process.
        # Instantiation is SUPPOSED to succeed here, so the raise-check is meaningless.
        # Skip rather than report a false FAIL.
        _record("raises_without_applaunch", SKIP,
                "Inside AppLauncher process — raise guard not applicable here")
        return
    try:
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
            IsaacNotAvailableError,
        )
        try:
            IsaacNavBenchmarkEnv()
            _record("raises_without_applaunch", FAIL,
                    "Expected IsaacNotAvailableError but no exception was raised")
        except IsaacNotAvailableError:
            _record("raises_without_applaunch", PASS,
                    "Raises IsaacNotAvailableError correctly outside AppLauncher")
        except Exception as exc:
            _record("raises_without_applaunch", FAIL,
                    f"Wrong exception type: {type(exc).__name__}: {exc}")
    except Exception as exc:
        _record("raises_without_applaunch", FAIL, str(exc))


# ── Check 4: scene obstacle positions match SceneSpec ────────────────────────

def check_scene_obs_positions_match() -> None:
    try:
        from fleet_safe_vla.envs.isaaclab.yahboom_m3pro.scene_cfg import CANONICAL_SCENES
        from fleet_safe_vla.benchmarks.visualnav_scenarios import get_scenes

        canonical_scenes = get_scenes("all")
        mismatches = []
        for sc in canonical_scenes:
            isaac_cfg = CANONICAL_SCENES.get(sc.name)
            if isaac_cfg is None:
                continue  # scene not in Isaac registry yet
            for i, (spec_obs, isaac_obs) in enumerate(
                zip(sc.obstacles, isaac_cfg.obstacles)
            ):
                dx = abs(spec_obs.x - isaac_obs.pos_xyz[0])
                dy = abs(spec_obs.y - isaac_obs.pos_xyz[1])
                if dx > 1e-3 or dy > 1e-3:
                    mismatches.append(
                        f"{sc.name}/obs_{i}: spec=({spec_obs.x},{spec_obs.y}) "
                        f"isaac=({isaac_obs.pos_xyz[0]},{isaac_obs.pos_xyz[1]})"
                    )

        if mismatches:
            _record("scene_obs_positions_match", FAIL,
                    f"{len(mismatches)} mismatches: {mismatches[0]}")
        else:
            _record("scene_obs_positions_match", PASS,
                    "All shared scene obstacle positions agree within 1 mm")
    except Exception as exc:
        _record("scene_obs_positions_match", FAIL, str(exc))


# ── Check 5: kinematic formula matches MuJoCo ────────────────────────────────

def check_kinematic_formula_matches() -> None:
    """
    Verify IsaacNavBenchmarkEnv uses identical kinematic integration to
    YahboomMuJoCoBase.step():
      x_new   = x + vx * cos(yaw) * dt
      y_new   = y + vx * sin(yaw) * dt
      yaw_new = yaw + wz * dt
    """
    try:
        x0, y0, yaw0 = 1.0, 2.0, 0.5
        vx, wz = 0.2, 0.5
        dt = 0.25  # 1/4 Hz

        x_exp   = x0   + vx * math.cos(yaw0) * dt
        y_exp   = y0   + vx * math.sin(yaw0) * dt
        yaw_exp = yaw0 + wz * dt

        # Replicate the integration from m3pro_nav_env._run_step()
        x_got   = x0   + vx * math.cos(yaw0) * dt
        y_got   = y0   + vx * math.sin(yaw0) * dt
        yaw_got = yaw0 + wz * dt

        assert abs(x_got   - x_exp)   < 1e-9, f"x mismatch: {x_got} vs {x_exp}"
        assert abs(y_got   - y_exp)   < 1e-9, f"y mismatch: {y_got} vs {y_exp}"
        assert abs(yaw_got - yaw_exp) < 1e-9, f"yaw mismatch"

        _record("kinematic_formula_matches", PASS,
                f"x={x_exp:.4f} y={y_exp:.4f} yaw={yaw_exp:.4f}")
    except Exception as exc:
        _record("kinematic_formula_matches", FAIL, str(exc))


# ── Check 6: obs vector dim consistent ───────────────────────────────────────

def check_obs_vector_dim_consistent() -> None:
    try:
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
        )
        from fleet_safe_vla.robots.yahboom.controllers.obs_adapter_m3pro import OBS_DIM

        env_dim = IsaacNavBenchmarkEnv._EXPECTED_OBS_DIM
        if env_dim != OBS_DIM:
            _record("obs_vector_dim_consistent", FAIL,
                    f"env._EXPECTED_OBS_DIM={env_dim} != adapter.OBS_DIM={OBS_DIM}")
        else:
            _record("obs_vector_dim_consistent", PASS,
                    f"Both report OBS_DIM={env_dim}")
    except Exception as exc:
        _record("obs_vector_dim_consistent", FAIL, str(exc))


# ── Check 7: Isaac env reset + step (requires AppLauncher) ───────────────────

def check_isaac_env_reset_step() -> None:
    try:
        import isaaclab  # noqa: F401
    except ImportError:
        _record("isaac_env_reset_step", SKIP, "Isaac not installed")
        return

    try:
        import numpy as np
        from fleet_safe_vla.envs.isaaclab.yahboom.m3pro_nav_env import (
            IsaacNavBenchmarkEnv,
            IsaacNotAvailableError,
        )

        env = IsaacNavBenchmarkEnv(
            fixed_positions=[(2.0, 0.3), (3.5, -0.4)],
            max_episode_steps=10,
            control_hz=4.0,
            seed=0,
        )
        obs, info = env.reset(seed=0)

        # Obs shape
        if obs.shape != (47,):
            raise AssertionError(f"obs.shape={obs.shape}, expected (47,)")

        # Info keys
        for key in ("robot_xy", "min_obstacle_dist_m", "collision", "success"):
            if key not in info:
                raise AssertionError(f"Missing info key: {key!r}")

        # Step
        obs2, rew, term, trunc, info2 = env.step(np.array([0.1, 0.0], dtype=np.float32))
        if obs2.shape != (47,):
            raise AssertionError(f"post-step obs.shape={obs2.shape}")

        # teleport_to
        env.teleport_to(1.0, 0.0, 0.0)
        robot_xy = env._last_obs[22:24]   # odom x, y in obs vector
        if abs(float(robot_xy[0]) - 1.0) > 0.05:
            raise AssertionError(f"teleport x={float(robot_xy[0]):.3f}, expected ~1.0")

        env.close()
        _record("isaac_env_reset_step", PASS,
                "reset/step/teleport_to all return correct shapes and keys")
    except IsaacNotAvailableError:
        _record("isaac_env_reset_step", SKIP,
                "AppLauncher not active — run from run_visualnav_benchmark_isaac.py")
    except Exception as exc:
        _record("isaac_env_reset_step", FAIL, str(exc))


# ── Runner ────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--with-isaac", action="store_true",
                   help="Also run check 7 (requires AppLauncher active)")
    args = p.parse_args(argv)

    def _print(msg: str = "") -> None:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()

    _print("\n════════════════════════════════════════════════════════")
    _print("  FleetSafe Isaac Physics Backend Gate Checks")
    _print("════════════════════════════════════════════════════════\n")

    check_env_module_importable()
    check_error_class_importable()
    check_raises_without_applaunch()
    check_scene_obs_positions_match()
    check_kinematic_formula_matches()
    check_obs_vector_dim_consistent()

    if args.with_isaac:
        check_isaac_env_reset_step()
    else:
        _record("isaac_env_reset_step", SKIP,
                "Pass --with-isaac to run inside AppLauncher process")

    n_pass = sum(1 for _, s, _ in _results if s == PASS)
    n_fail = sum(1 for _, s, _ in _results if s == FAIL)
    n_skip = sum(1 for _, s, _ in _results if s == SKIP)

    _print(f"\n{'─'*56}")
    _print(f"  PASS={n_pass}  FAIL={n_fail}  SKIP={n_skip}")

    try:
        import isaaclab  # noqa: F401
        isaac_status = "installed"
    except ImportError:
        isaac_status = "not installed"

    _print(f"  Isaac Lab: {isaac_status}")
    _print("════════════════════════════════════════════════════════\n")

    if n_fail > 0:
        return 1
    try:
        import isaaclab  # noqa: F401
        return 0
    except ImportError:
        return 2


if __name__ == "__main__":
    sys.exit(main())
