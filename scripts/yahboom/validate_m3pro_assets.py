#!/usr/bin/env python3
"""
validate_m3pro_assets.py — M3Pro URDF structural validator

Checks that the M3Pro URDF exists and has the correct structure for
Stage 0 training gate validation.  No simulation engine required.
Runs in under 1 second on any Python 3.8+ installation.

Exit codes:
  0  all required checks pass
  1  one or more REQUIRED checks failed
  2  only warnings (no required failures), with --strict flag

Usage:
    python scripts/yahboom/validate_m3pro_assets.py
    python scripts/yahboom/validate_m3pro_assets.py --urdf path/to/custom.urdf
    python scripts/yahboom/validate_m3pro_assets.py --strict
    python scripts/yahboom/validate_m3pro_assets.py --json   # machine-readable
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────

_REPO_ROOT    = Path(__file__).resolve().parents[2]
DEFAULT_URDF  = _REPO_ROOT / "fleet_safe_vla/robots/yahboom/m3pro/urdf/yahboom_m3pro.urdf"
CONTRACT_YAML = _REPO_ROOT / "fleet_safe_vla/robots/yahboom/config/robot_contract_m3pro.yaml"

# ── Contract defaults (if YAML is absent or unparseable) ─────────────────────

_CONTRACT_DEFAULTS = {
    "wheel_radius_m": 0.048,
    "wheelbase_m":    0.155,
    "track_width_m":  0.170,
}

# Joint names are fixed by contract — do not change
REQUIRED_JOINTS = ("fl_wheel_joint", "fr_wheel_joint", "rl_wheel_joint", "rr_wheel_joint")
REQUIRED_LINKS  = ("base_link",)
SENSOR_LINKS    = ("lidar_link", "camera_link")

# Geometry tolerance: 5 mm
_TOL = 0.005


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class Check:
    name:    str
    passed:  bool
    warning: bool  = False  # True = informational; does not count as failure
    message: str   = ""

    def status_char(self) -> str:
        if self.passed:
            return "✓"
        return "!" if self.warning else "✗"

    def __str__(self) -> str:
        suffix = f"  ← {self.message}" if self.message else ""
        return f"  {self.status_char()}  {self.name}{suffix}"


# ── YAML loader (stdlib only) ─────────────────────────────────────────────────

def _load_contract(path: Path) -> dict:
    vals = dict(_CONTRACT_DEFAULTS)
    if not path.exists():
        return vals
    text = path.read_text()
    for key in vals:
        m = re.search(rf"^\s*{re.escape(key)}:\s*([\d.]+)", text, re.MULTILINE)
        if m:
            vals[key] = float(m.group(1))
    return vals


# ── XML helpers ───────────────────────────────────────────────────────────────

def _xyz(s: str) -> tuple[float, float, float]:
    parts = s.strip().split()
    if len(parts) < 3:
        raise ValueError(f"expected 3 floats, got {s!r}")
    return float(parts[0]), float(parts[1]), float(parts[2])


def _approx(a: float, b: float, tol: float = _TOL) -> bool:
    return abs(a - b) <= tol


# ── Main validator ────────────────────────────────────────────────────────────

def validate(urdf_path: Path, contract_path: Path = CONTRACT_YAML) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, ok: bool, *, warn: bool = False, msg: str = "") -> None:
        checks.append(Check(name=name, passed=ok, warning=warn, message=msg))

    # ── 1. File existence ─────────────────────────────────────────────────────
    if not urdf_path.exists():
        add("URDF file exists", False,
            msg=f"not found: {urdf_path}")
        add("Contract YAML exists", contract_path.exists(),
            msg="" if contract_path.exists() else str(contract_path))
        return checks  # nothing more to check

    add("URDF file exists", True, msg=urdf_path.name)

    contract = _load_contract(contract_path)
    add("Contract YAML exists", contract_path.exists(),
        warn=not contract_path.exists(),
        msg="" if contract_path.exists() else f"using defaults: {_CONTRACT_DEFAULTS}")

    # ── 2. XML parse ─────────────────────────────────────────────────────────
    try:
        root = ET.parse(urdf_path).getroot()
    except ET.ParseError as e:
        add("URDF is valid XML", False, msg=str(e))
        return checks
    add("URDF is valid XML", True)

    # ── 3. Robot root element ─────────────────────────────────────────────────
    is_robot = root.tag == "robot"
    add("Root element is <robot>",
        is_robot,
        msg=f"name={root.get('name', '?')}" if is_robot else f"got <{root.tag}>")

    # Build lookup dicts
    links  = {el.get("name"): el for el in root.findall("link")}
    joints = {el.get("name"): el for el in root.findall("joint")}

    # ── 4. Required links ─────────────────────────────────────────────────────
    for lname in REQUIRED_LINKS:
        ok = lname in links
        add(f"Link '{lname}' exists", ok,
            msg="" if ok else "required for all simulations")

    # ── 5. Sensor links (warning only — needed later stages) ──────────────────
    for lname in SENSOR_LINKS:
        ok = lname in links
        add(f"Link '{lname}' exists", ok, warn=not ok,
            msg="" if ok else "needed for Stage 3 (lidar) / camera obs")

    # ── 6. Required wheel joints exist ────────────────────────────────────────
    for jname in REQUIRED_JOINTS:
        ok = jname in joints
        add(f"Joint '{jname}' exists", ok,
            msg="" if ok else "obs_adapter and env_cfg use this exact name")

    # ── 7. Wheel joints are type=continuous ───────────────────────────────────
    for jname in REQUIRED_JOINTS:
        if jname not in joints:
            continue
        jtype = joints[jname].get("type", "")
        ok = jtype == "continuous"
        add(f"Joint '{jname}' type=continuous", ok,
            msg=f"got type={jtype!r}" if not ok else "")

    # ── 8. Wheel geometry radius matches contract ─────────────────────────────
    expected_r = contract["wheel_radius_m"]
    for jname in REQUIRED_JOINTS:
        if jname not in joints:
            continue
        child_el = joints[jname].find("child")
        if child_el is None:
            continue
        clink_name = child_el.get("link", "")
        if clink_name not in links:
            continue
        for cyl in links[clink_name].iter("cylinder"):
            r_str = cyl.get("radius", "")
            try:
                r = float(r_str)
                ok = _approx(r, expected_r)
                add(
                    f"Wheel radius in {clink_name} ({jname})", ok,
                    msg=f"{r:.4f} m (contract={expected_r:.4f} m)"
                        + ("" if ok else f"  delta={abs(r-expected_r)*1000:.1f} mm"),
                )
            except (ValueError, TypeError):
                add(f"Wheel radius in {clink_name} ({jname})", False,
                    msg=f"could not parse radius={r_str!r}")
            break  # only first cylinder per wheel link

    # ── 9. Wheel joint positions match contract lx / ly ───────────────────────
    lx = contract["wheelbase_m"]  / 2.0
    ly = contract["track_width_m"] / 2.0
    expected_pos = {
        "fl_wheel_joint": ( lx,  ly, 0.0),
        "fr_wheel_joint": ( lx, -ly, 0.0),
        "rl_wheel_joint": (-lx,  ly, 0.0),
        "rr_wheel_joint": (-lx, -ly, 0.0),
    }
    for jname, (ex, ey, ez) in expected_pos.items():
        if jname not in joints:
            continue
        origin = joints[jname].find("origin")
        if origin is None:
            add(f"Joint '{jname}' position ≈ ({ex:+.4f}, {ey:+.4f}, 0)", False,
                msg="no <origin> element")
            continue
        try:
            x, y, z = _xyz(origin.get("xyz", "0 0 0"))
            ok = _approx(x, ex) and _approx(y, ey) and _approx(z, ez)
            add(
                f"Joint '{jname}' position ≈ ({ex:+.4f}, {ey:+.4f}, 0)", ok,
                msg="" if ok else
                    f"got ({x:+.4f}, {y:+.4f}, {z:+.4f})  "
                    f"Δx={abs(x-ex)*1000:.1f}mm Δy={abs(y-ey)*1000:.1f}mm",
            )
        except Exception as exc:
            add(f"Joint '{jname}' position", False, msg=str(exc))

    # ── 10. Wheel joint spin axis ≈ (0, 1, 0) in base frame ─────────────────
    #  Accepts two equivalent conventions:
    #    A: axis=(0,1,0)  with joint origin rpy=(0,0,0)   [M3Pro URDF convention]
    #    B: axis=(0,0,1)  with joint origin rpy=(±π/2,0,0) [X3 URDF convention]
    HALF_PI = math.pi / 2.0
    for jname in REQUIRED_JOINTS:
        if jname not in joints:
            continue
        axis_el = joints[jname].find("axis")
        if axis_el is None:
            add(f"Joint '{jname}' spin axis ≈ Y", False, warn=True,
                msg="no <axis> element; default is (1,0,0)")
            continue
        try:
            ax, ay, az = _xyz(axis_el.get("xyz", "1 0 0"))
            origin = joints[jname].find("origin")
            rpy_str = origin.get("rpy", "0 0 0") if origin is not None else "0 0 0"
            rx, ry, rz = _xyz(rpy_str)

            # Convention A: axis directly along Y
            conv_a = _approx(ax, 0.0, 0.01) and _approx(ay, 1.0, 0.01) and _approx(az, 0.0, 0.01)
            # Convention B: axis=(0,0,1) with RPY≈(±π/2, 0, 0) → Y in parent
            conv_b = (
                _approx(ax, 0.0, 0.01) and _approx(ay, 0.0, 0.01) and _approx(az, 1.0, 0.01)
                and _approx(abs(rx), HALF_PI, 0.01)
            )
            ok = conv_a or conv_b
            conv_label = "(convention A)" if conv_a else "(convention B)" if conv_b else ""
            add(f"Joint '{jname}' spin axis ≈ Y {conv_label}", ok, warn=not ok,
                msg="" if ok else
                    f"axis=({ax:.2f},{ay:.2f},{az:.2f}) rpy=({rx:.3f},{ry:.3f},{rz:.3f})")
        except Exception as exc:
            add(f"Joint '{jname}' spin axis", False, warn=True, msg=str(exc))

    # ── 11. Physical links have <inertial> (Isaac Sim requirement) ───────────
    # Virtual frame links (no visual/collision geometry) do NOT need inertials.
    # Examples: base_footprint, camera_optical_link, imu_virtual_link.
    physical_links_missing = [
        n for n, el in links.items()
        if el.find("inertial") is None
        and (el.find("visual") is not None or el.find("collision") is not None)
    ]
    virtual_links_missing = [
        n for n, el in links.items()
        if el.find("inertial") is None
        and el.find("visual") is None
        and el.find("collision") is None
    ]
    if physical_links_missing:
        for lname in physical_links_missing:
            add(f"Link '{lname}' has <inertial>", False,
                msg="Isaac Sim rejects physical links without inertials")
    else:
        add("All physical links have <inertial>", True)
    if virtual_links_missing:
        # Informational only — virtual frame links are fine without inertials
        add(
            f"Virtual frame links without <inertial>: {', '.join(virtual_links_missing)}",
            True, warn=False,
            msg="OK — virtual frames do not need inertials",
        )

    # ── 12. Wheel joints have <dynamics> (optional, improves sim stability) ───
    for jname in REQUIRED_JOINTS:
        if jname not in joints:
            continue
        has_dyn = joints[jname].find("dynamics") is not None
        add(f"Joint '{jname}' has <dynamics>", has_dyn, warn=not has_dyn,
            msg="" if has_dyn else "optional; add damping/friction for stable sim")

    return checks


# ── Reporting ─────────────────────────────────────────────────────────────────

def _print_report(urdf_path: Path, checks: list[Check], strict: bool = False) -> int:
    n_fail = sum(1 for c in checks if not c.passed and not c.warning)
    n_warn = sum(1 for c in checks if not c.passed and c.warning)
    n_pass = sum(1 for c in checks if c.passed)

    print()
    print("═" * 60)
    print("  M3Pro URDF Validator")
    print(f"  {urdf_path}")
    print("═" * 60)
    for c in checks:
        print(c)
    print()
    print(f"  Passed: {n_pass}   Warnings: {n_warn}   Failed: {n_fail}")
    print()

    if n_fail == 0 and (n_warn == 0 or not strict):
        print("  ✓  STAGE 0 READY — URDF structure is valid.")
        print("     Next: ./scripts/isaaclab/train_yahboom.sh --stage 0")
        if n_warn:
            print(f"     Note: {n_warn} warning(s) above (not blocking Stage 0).")
            print("     Fix warnings before Stage 1 training for best results.")
    else:
        if n_fail:
            print(f"  ✗  BLOCKED — {n_fail} required check(s) failed.")
        if n_warn and strict:
            print(f"  !  BLOCKED (--strict) — {n_warn} warning(s) treated as failures.")
        print()
        print("  Fix the issues above, then re-run:")
        print("    python scripts/yahboom/validate_m3pro_assets.py")

    print()

    if n_fail:
        return 1
    if n_warn and strict:
        return 2
    return 0


def _print_json(urdf_path: Path, checks: list[Check]) -> int:
    n_fail = sum(1 for c in checks if not c.passed and not c.warning)
    output = {
        "urdf": str(urdf_path),
        "stage0_ready": n_fail == 0,
        "counts": {
            "passed":   sum(1 for c in checks if c.passed),
            "warnings": sum(1 for c in checks if not c.passed and c.warning),
            "failed":   n_fail,
        },
        "checks": [
            {
                "name":    c.name,
                "passed":  c.passed,
                "warning": c.warning,
                "message": c.message,
            }
            for c in checks
        ],
    }
    print(json.dumps(output, indent=2))
    return 0 if n_fail == 0 else 1


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--urdf", type=Path, default=DEFAULT_URDF,
        help=f"path to URDF (default: {DEFAULT_URDF})",
    )
    parser.add_argument(
        "--contract", type=Path, default=CONTRACT_YAML,
        help=f"path to robot_contract YAML (default: {CONTRACT_YAML})",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="exit with code 2 if any warnings are present",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="print machine-readable JSON instead of human-readable table",
    )
    args = parser.parse_args()

    checks = validate(args.urdf, args.contract)

    if args.json:
        return _print_json(args.urdf, checks)
    return _print_report(args.urdf, checks, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
