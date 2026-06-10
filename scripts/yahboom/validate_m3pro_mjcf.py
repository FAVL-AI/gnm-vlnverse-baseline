#!/usr/bin/env python3
"""
validate_m3pro_mjcf.py — M3Pro MJCF structural validator

Requires MuJoCo (available in the isaac conda env).
Run from the repo root:
    /home/favl/miniforge3/envs/isaac/bin/python scripts/yahboom/validate_m3pro_mjcf.py
    python scripts/yahboom/validate_m3pro_mjcf.py   # if mujoco is on PATH

Exit codes:
  0  all required checks pass
  1  one or more REQUIRED checks failed
  2  --strict: warnings promoted to failures

Usage:
    python scripts/yahboom/validate_m3pro_mjcf.py
    python scripts/yahboom/validate_m3pro_mjcf.py --mjcf path/to/custom.xml
    python scripts/yahboom/validate_m3pro_mjcf.py --strict
    python scripts/yahboom/validate_m3pro_mjcf.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT    = Path(__file__).resolve().parents[2]
DEFAULT_MJCF  = _REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/mjcf/yahboom_m3pro.xml"
CONTRACT_YAML = _REPO_ROOT / "fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml"

REQUIRED_JOINTS    = ("fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint")
REQUIRED_ACTUATORS = ("fl_drive",       "fr_drive",       "rl_drive",       "rr_drive")
REQUIRED_GEOMS     = ("fl_wheel_geom",  "fr_wheel_geom",  "rl_wheel_geom",  "rr_wheel_geom")

_TOL = 0.005   # 5 mm geometry tolerance


# ── Contract loader (stdlib) ──────────────────────────────────────────────────

def _load_contract(path: Path) -> dict:
    defaults = {"wheel_radius_m": 0.048, "wheelbase_m": 0.155, "track_width_m": 0.170}
    if not path.exists():
        return defaults
    text = path.read_text()
    for key in defaults:
        m = re.search(rf"^\s*{re.escape(key)}:\s*([\d.]+)", text, re.MULTILINE)
        if m:
            defaults[key] = float(m.group(1))
    return defaults


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class Check:
    name:    str
    passed:  bool
    warning: bool = False
    message: str  = ""

    def status_char(self) -> str:
        return "✓" if self.passed else ("!" if self.warning else "✗")

    def __str__(self) -> str:
        suffix = f"  ← {self.message}" if self.message else ""
        return f"  {self.status_char()}  {self.name}{suffix}"


# ── Validator ─────────────────────────────────────────────────────────────────

def validate(mjcf_path: Path, contract_path: Path = CONTRACT_YAML) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, ok: bool, *, warn: bool = False, msg: str = "") -> None:
        checks.append(Check(name=name, passed=ok, warning=warn, message=msg))

    # ── 1. File existence ─────────────────────────────────────────────────────
    if not mjcf_path.exists():
        add("MJCF file exists", False, msg=str(mjcf_path))
        return checks
    add("MJCF file exists", True, msg=mjcf_path.name)

    contract = _load_contract(contract_path)
    add("Contract YAML exists", contract_path.exists(),
        warn=not contract_path.exists(),
        msg="" if contract_path.exists() else "using defaults")

    # ── 2. MuJoCo import ─────────────────────────────────────────────────────
    try:
        import mujoco
        add("mujoco importable", True, msg=f"version {mujoco.__version__}")
    except ImportError as exc:
        add("mujoco importable", False,
            msg=f"{exc}  →  run with: /home/favl/miniforge3/envs/isaac/bin/python")
        return checks

    import numpy as np

    # ── 3. Model loads ────────────────────────────────────────────────────────
    try:
        m = mujoco.MjModel.from_xml_path(str(mjcf_path))
        add("MjModel.from_xml_path succeeds", True)
    except Exception as exc:
        add("MjModel.from_xml_path succeeds", False, msg=str(exc))
        return checks

    # ── 4. Required joints exist and are hinge ────────────────────────────────
    for jname in REQUIRED_JOINTS:
        jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, jname)
        ok = jid >= 0
        add(f"Joint '{jname}' exists", ok,
            msg="not found — obs_adapter uses this exact name" if not ok else "")
        if ok:
            jtype = m.jnt_type[jid]
            hinge_ok = (jtype == mujoco.mjtJoint.mjJNT_HINGE)
            add(f"Joint '{jname}' is hinge (continuous)", hinge_ok,
                msg=f"type={jtype}" if not hinge_ok else "")

    # ── 5. DoF counts ─────────────────────────────────────────────────────────
    # freejoint: nq=7 (pos×3 + quat×4), nv=6; 4 hinge wheels: nq=4, nv=4
    add(f"nq == 11 (7 freejoint + 4 wheels)", m.nq == 11, msg=f"nq={m.nq}")
    add(f"nv == 10 (6 freejoint + 4 wheels)", m.nv == 10, msg=f"nv={m.nv}")

    # ── 6. Actuators ──────────────────────────────────────────────────────────
    add("nu == 4 (one actuator per wheel)", m.nu == 4, msg=f"nu={m.nu}")
    for aname in REQUIRED_ACTUATORS:
        aid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, aname)
        ok = aid >= 0
        add(f"Actuator '{aname}' exists", ok, msg="not found" if not ok else "")

    # ── 7. Wheel geoms exist and radius matches contract ──────────────────────
    expected_r = contract["wheel_radius_m"]
    for gname in REQUIRED_GEOMS:
        gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, gname)
        ok = gid >= 0
        add(f"Geom '{gname}' exists", ok, msg="not found" if not ok else "")
        if ok:
            r = m.geom_size[gid, 0]
            rad_ok = abs(r - expected_r) <= _TOL
            delta_mm = abs(r - expected_r) * 1000
            add(f"  {gname} radius={r:.4f} m vs contract={expected_r:.4f} m",
                rad_ok,
                msg="" if rad_ok else f"Δ={delta_mm:.1f} mm — update MJCF or contract YAML")

    # ── 8. Wheel body positions match lx / ly ─────────────────────────────────
    lx = contract["wheelbase_m"]  / 2.0
    ly = contract["track_width_m"] / 2.0
    expected_bodies = {
        "fl_wheel": ( lx,  ly, 0.0),
        "fr_wheel": ( lx, -ly, 0.0),
        "rl_wheel": (-lx,  ly, 0.0),
        "rr_wheel": (-lx, -ly, 0.0),
    }
    for bname, (ex, ey, _ez) in expected_bodies.items():
        bid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, bname)
        if bid < 0:
            add(f"Body '{bname}' position", False, msg="body not found")
            continue
        bx, by, bz = m.body_pos[bid]
        ok = abs(bx - ex) <= _TOL and abs(by - ey) <= _TOL and abs(bz) <= _TOL
        add(
            f"Body '{bname}' pos ≈ ({ex:+.4f}, {ey:+.4f}, 0)",
            ok,
            msg="" if ok else
                f"got ({bx:+.4f}, {by:+.4f}, {bz:+.4f})  "
                f"Δx={abs(bx-ex)*1000:.1f}mm Δy={abs(by-ey)*1000:.1f}mm",
        )

    # ── 9. Body count ─────────────────────────────────────────────────────────
    # world(1) + base_link(1) + fl/fr/rl/rr(4) = 6
    add("nbody == 6 (world + base + 4 wheels)", m.nbody == 6, msg=f"nbody={m.nbody}")

    # ── 10. 100 steps without NaN — zero control ──────────────────────────────
    d = mujoco.MjData(m)
    try:
        for _ in range(100):
            mujoco.mj_step(m, d)
        nan_pos = bool(np.any(np.isnan(d.qpos)))
        nan_vel = bool(np.any(np.isnan(d.qvel)))
        add("No NaN in qpos after 100 steps (zero ctrl)", not nan_pos,
            msg="NaN detected — check inertials and friction" if nan_pos else "")
        add("No NaN in qvel after 100 steps (zero ctrl)", not nan_vel,
            msg="NaN detected" if nan_vel else "")
    except Exception as exc:
        add("100 steps completed (zero ctrl)", False, msg=str(exc))

    # ── 11. 100 steps without NaN — max velocity command ─────────────────────
    d2 = mujoco.MjData(m)
    d2.ctrl[:] = 20.0
    try:
        for _ in range(100):
            mujoco.mj_step(m, d2)
        nan_pos2 = bool(np.any(np.isnan(d2.qpos)))
        nan_vel2 = bool(np.any(np.isnan(d2.qvel)))
        add("No NaN in qpos after 100 steps (max ctrl=20 rad/s)", not nan_pos2,
            msg="NaN detected — reduce kv or timestep" if nan_pos2 else "")
        add("No NaN in qvel after 100 steps (max ctrl=20 rad/s)", not nan_vel2,
            msg="NaN detected" if nan_vel2 else "")
    except Exception as exc:
        add("100 steps (max ctrl)", False, msg=str(exc))

    return checks


# ── Reporting ─────────────────────────────────────────────────────────────────

def _report_human(mjcf_path: Path, checks: list[Check], strict: bool) -> int:
    n_fail = sum(1 for c in checks if not c.passed and not c.warning)
    n_warn = sum(1 for c in checks if not c.passed and c.warning)
    n_pass = sum(1 for c in checks if c.passed)

    print()
    print("═" * 62)
    print("  M3Pro MJCF Validator")
    print(f"  {mjcf_path}")
    print("═" * 62)
    for c in checks:
        print(c)
    print()
    print(f"  Passed: {n_pass}   Warnings: {n_warn}   Failed: {n_fail}")
    print()

    if n_fail == 0 and (n_warn == 0 or not strict):
        print("  ✓  MJCF VALID — MuJoCo smoke tests can proceed.")
        print("     Run: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \\")
        print("       /home/favl/miniforge3/envs/isaac/bin/python \\")
        print("       -m pytest tests/test_m3pro_mjcf.py -v --tb=short")
        if n_warn:
            print(f"     Note: {n_warn} warning(s) — not blocking smoke tests.")
    else:
        if n_fail:
            print(f"  ✗  BLOCKED — {n_fail} required check(s) failed.")
        if n_warn and strict:
            print(f"  !  BLOCKED (--strict) — {n_warn} warning(s).")
        print()
        print("  Fix the issues above, then re-run:")
        print("    python scripts/yahboom/validate_m3pro_mjcf.py")
    print()

    if n_fail:
        return 1
    return 2 if (n_warn and strict) else 0


def _report_json(mjcf_path: Path, checks: list[Check]) -> int:
    n_fail = sum(1 for c in checks if not c.passed and not c.warning)
    out = {
        "mjcf": str(mjcf_path),
        "mjcf_valid": n_fail == 0,
        "counts": {
            "passed":   sum(1 for c in checks if c.passed),
            "warnings": sum(1 for c in checks if not c.passed and c.warning),
            "failed":   n_fail,
        },
        "checks": [
            {"name": c.name, "passed": c.passed, "warning": c.warning, "message": c.message}
            for c in checks
        ],
    }
    print(json.dumps(out, indent=2))
    return 0 if n_fail == 0 else 1


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--mjcf",     type=Path, default=DEFAULT_MJCF)
    p.add_argument("--contract", type=Path, default=CONTRACT_YAML)
    p.add_argument("--strict",   action="store_true",
                   help="treat warnings as failures (exit code 2)")
    p.add_argument("--json",     action="store_true",
                   help="machine-readable JSON output")
    args = p.parse_args()

    checks = validate(args.mjcf, args.contract)

    if args.json:
        return _report_json(args.mjcf, checks)
    return _report_human(args.mjcf, checks, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
