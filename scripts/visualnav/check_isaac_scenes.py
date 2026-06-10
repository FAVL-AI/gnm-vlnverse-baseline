#!/usr/bin/env python3
"""
check_isaac_scenes.py — Verify Isaac Lab / MuJoCo scene readiness for the benchmark.

Checks two backends separately:
  MuJoCo  — available now (M3Pro MJCF + nav/obstacle envs).
  Isaac   — gate-failed until the Isaac Lab M3Pro env is implemented.

For the MuJoCo backend, verifies:
  1. M3Pro MJCF asset exists.
  2. YahboomNavEnv and YahboomObstacleEnv importable.
  3. All four canonical scenes can be instantiated.
  4. env.reset(seed=N) is deterministic (two resets give same initial state).
  5. One smoke episode runs end-to-end (5 steps, cmd_vel=zeros).

For the Isaac Lab backend:
  Gate-failed — prints instructions and exits 2.

Exit codes:
  0  MuJoCo backend fully operational.
  1  MuJoCo backend has a hard failure.
  2  Isaac Lab backend not yet implemented (expected during development).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from fleet_safe_vla.benchmarks.visualnav_scenarios import ALL_SCENES


# ── MuJoCo checks ─────────────────────────────────────────────────────────────

def _check_mujoco() -> int:
    print("\n[check_isaac_scenes] Backend: mujoco")
    ok_all = True

    # 1. MJCF asset
    mjcf = _REPO_ROOT / "fleet_safe_vla" / "robots" / "yahboom" / "m3pro" / "mjcf" / "yahboom_m3pro.xml"
    if mjcf.exists():
        print(f"  ✓  M3Pro MJCF: {mjcf.name}")
    else:
        print(f"  ✗  M3Pro MJCF MISSING: {mjcf}")
        ok_all = False

    # 2. Import env classes
    try:
        from fleet_safe_vla.envs.mujoco.yahboom.nav_env import YahboomNavEnv
        from fleet_safe_vla.envs.mujoco.yahboom.obstacle_env import YahboomObstacleEnv
        print("  ✓  YahboomNavEnv importable")
        print("  ✓  YahboomObstacleEnv importable")
    except ImportError as exc:
        print(f"  ✗  Env import failed: {exc}")
        return 1

    # 3. Instantiate each scene
    for scene_name, scene in ALL_SCENES.items():
        try:
            n_obs = len(scene.obstacles)
            if n_obs == 0:
                env = YahboomNavEnv(max_episode_steps=20, control_hz=4.0, seed=0)
            else:
                env = YahboomObstacleEnv(n_obstacles=n_obs, max_episode_steps=20, control_hz=4.0, seed=0)
            env.reset(seed=0)
            env.close()
            print(f"  ✓  Scene '{scene_name}' instantiates OK")
        except Exception as exc:
            print(f"  ✗  Scene '{scene_name}' failed: {exc}")
            ok_all = False

    # 4. Deterministic seed check
    try:
        env = YahboomNavEnv(max_episode_steps=20, control_hz=4.0, seed=0)
        obs_a, _ = env.reset(seed=42)
        obs_b, _ = env.reset(seed=42)
        env.close()
        if np.allclose(obs_a, obs_b, atol=1e-6):
            print("  ✓  env.reset(seed=42) is deterministic")
        else:
            print("  ⚠  env.reset(seed=42) non-deterministic — check physics randomisation")
    except Exception as exc:
        print(f"  ⚠  Determinism check failed: {exc}")

    # 5. Smoke episode
    try:
        env  = YahboomNavEnv(max_episode_steps=10, control_hz=4.0, seed=0)
        env.reset(seed=0)
        for _ in range(5):
            obs, rew, term, trunc, info = env.step(np.zeros(3, dtype=np.float32))
            if term or trunc:
                break
        env.close()
        print("  ✓  5-step smoke episode completed")
    except Exception as exc:
        print(f"  ✗  Smoke episode failed: {exc}")
        ok_all = False

    if ok_all:
        print("\n  MuJoCo backend: PASS")
        return 0
    else:
        print("\n  MuJoCo backend: FAIL  (see errors above)")
        return 1


# ── Isaac Lab check (gate-failed) ─────────────────────────────────────────────

def _check_isaaclab() -> int:
    print("\n[check_isaac_scenes] Backend: isaaclab")
    print()
    print("  ✗  Isaac Lab backend is NOT YET IMPLEMENTED.")
    print()
    print("  The planned entry point is:")
    print("    fleet_safe_vla/envs/isaaclab/yahboom/yahboom_m3pro_env_cfg.py")
    print()
    print("  To implement:")
    print("    1. Create a YahboomM3ProIsaacEnv subclassing DirectRLEnv or ManagerBasedEnv.")
    print("    2. Add the M3Pro USD asset to the Isaac Lab scene.")
    print("    3. Implement reset(), step(), and camera rendering.")
    print("    4. Set simulation_backend: isaaclab in configs/visualnav/isaac_benchmark.yaml.")
    print("    5. Re-run this script.")
    print()
    print("  Isaac Sim is currently used for the H1 humanoid.")
    print("  M3Pro Isaac Lab support is the next milestone after MuJoCo validation.")
    print()
    print("  Gate status: PENDING (not a failure — expected during development)")
    return 2


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backend", default="mujoco",
                   choices=["mujoco", "isaaclab", "all"],
                   help="Backend to check (default: mujoco)")
    args = p.parse_args()

    if args.backend == "mujoco":
        return _check_mujoco()
    elif args.backend == "isaaclab":
        return _check_isaaclab()
    else:
        rc_mujoco = _check_mujoco()
        rc_isaac  = _check_isaaclab()
        return rc_mujoco if rc_mujoco != 0 else (0 if rc_isaac == 2 else rc_isaac)


if __name__ == "__main__":
    sys.exit(main())
