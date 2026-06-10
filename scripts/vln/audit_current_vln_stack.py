"""audit_current_vln_stack.py — Report what VLN capabilities are available.

Inspects model adapters, robot topics, bag directories, safety tools, and
ROS2 environment without requiring a live robot or GPU.

Usage:
    python3 scripts/vln/audit_current_vln_stack.py
    make vln-audit
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

RESULTS_DIR = REPO_ROOT / "results" / "vln"


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------

def _check_import(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except ImportError:
        return False


def _check_file(path: str | Path) -> bool:
    return Path(REPO_ROOT / path).exists()


def _check_dir(path: str | Path) -> tuple[bool, int]:
    p = REPO_ROOT / path
    if not p.exists():
        return False, 0
    files = list(p.rglob("*"))
    return True, len(files)


def _check_ros2() -> dict:
    ros_ok = bool(os.environ.get("AMENT_PREFIX_PATH", ""))
    domain = os.environ.get("ROS_DOMAIN_ID", "not set")
    return {"ros2_sourced": ros_ok, "domain_id": domain}


def _check_bags() -> dict:
    bag_dir = REPO_ROOT / "data" / "real_robot_bags"
    if not bag_dir.exists():
        return {"count": 0, "latest": None}
    bags = sorted(bag_dir.glob("m3pro_full_motion_*"))
    return {
        "count": len(bags),
        "latest": str(bags[-1]) if bags else None,
    }


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def run_audit() -> dict:
    report = {
        "timestamp": int(time.time()),
        "repo_root": str(REPO_ROOT),
    }

    # Model adapters
    adapters = {}
    for name, module in [
        ("gnm",   "fleet_safe_vla.integrations.visualnav_transformer.gnm_adapter"),
        ("vint",  "fleet_safe_vla.integrations.visualnav_transformer.vint_adapter"),
        ("nomad", "fleet_safe_vla.integrations.visualnav_transformer.nomad_adapter"),
    ]:
        adapters[name] = _check_import(module)
    report["model_adapters"] = adapters

    # VLN package
    vln_modules = {}
    for mod in [
        "fleet_safe_vla.vln.instruction_schema",
        "fleet_safe_vla.vln.grounding",
        "fleet_safe_vla.vln.backbone_router",
        "fleet_safe_vla.vln.vln_trace_logger",
        "fleet_safe_vla.vln.instruction_intake",
    ]:
        vln_modules[mod.split(".")[-1]] = _check_import(mod)
    report["vln_package"] = vln_modules

    # Safety tools
    safety_tools = {
        "certificate_module": _check_import("fleet_safe_vla.safety.certificate"),
        "certificate_logger": _check_import("fleet_safe_vla.safety.certificate_logger"),
        "cbf_filter":         _check_import("fleet_safe_vla.fleet_safety.yahboom_cbf"),
        "verify_script":      _check_file("scripts/evaluation/verify_cbf_certificates.py"),
        "certify_bag_script": _check_file("scripts/evaluation/certify_rosbag_run.py"),
    }
    report["safety_tools"] = safety_tools

    # Config files
    configs = {
        "fleetsafe_real_robot.env": _check_file("config/fleetsafe_real_robot.env"),
        "fleetsafe_vln.env":        _check_file("config/fleetsafe_vln.env"),
    }
    report["config_files"] = configs

    # Scripts
    scripts = {
        "check_robot_topics":      _check_file("scripts/live/check_robot_topics.sh"),
        "record_bag":              _check_file("scripts/live/record_real_robot_bag.sh"),
        "send_vln_instruction":    _check_file("scripts/live/send_vln_text_instruction.sh"),
        "start_vln_stack":         _check_file("scripts/live/start_vln_stack.sh"),
        "check_voice_module":      _check_file("scripts/robot/check_voice_module.sh"),
        "start_voice_listener":    _check_file("scripts/robot/start_voice_listener.sh"),
        "vln_instruction_demo":    _check_file("scripts/vln/run_vln_instruction_demo.py"),
    }
    report["scripts"] = scripts

    # Data
    bag_info, hdf5_ok = _check_bags(), _check_dir("data/hdf5_test")
    converters_ok = _check_dir("scripts/visualnav")
    report["data"] = {
        "real_robot_bags": bag_info,
        "hdf5_dir_exists": hdf5_ok[0],
        "visualnav_converters": converters_ok[0],
        "topomap_dir_exists": _check_dir("topomaps")[0],
    }

    # LaunchPad
    launchpad = {
        "launchpad_sh":  _check_file("scripts/demo/launchpad.sh"),
        "makefile":      _check_file("Makefile"),
        "dashboard_backend": _check_file("command-center/backend/main.py"),
        "dashboard_frontend": _check_file("command-center/frontend/src/app/dashboard/page.tsx"),
    }
    report["launchpad"] = launchpad

    # ROS2 environment
    report["ros2_env"] = _check_ros2()

    # Convert checkpoints
    ckpt_dir = REPO_ROOT / "third_party" / "visualnav-transformer" / "model_weights"
    ckpts = {}
    for model in ["gnm", "vint", "nomad"]:
        model_dir = ckpt_dir / model
        ckpts[model] = model_dir.exists() and any(model_dir.iterdir()) if model_dir.exists() else False
    report["model_checkpoints"] = ckpts

    return report


def _print_report(r: dict) -> None:
    def ok(v): return "✅" if v else "❌"

    print("╔══════════════════════════════════════════════════════════╗")
    print("║        FleetSafe-VLN Stack Audit                        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"  Repo: {r['repo_root']}")
    print()

    print("  Model Adapters:")
    for k, v in r["model_adapters"].items():
        print(f"    {ok(v)} {k}")

    print("  Model Checkpoints:")
    for k, v in r["model_checkpoints"].items():
        print(f"    {ok(v)} {k}")

    print("  VLN Package:")
    for k, v in r["vln_package"].items():
        print(f"    {ok(v)} {k}")

    print("  Safety Tools:")
    for k, v in r["safety_tools"].items():
        print(f"    {ok(v)} {k}")

    print("  Config Files:")
    for k, v in r["config_files"].items():
        print(f"    {ok(v)} {k}")

    print("  Scripts:")
    for k, v in r["scripts"].items():
        print(f"    {ok(v)} {k}")

    print("  Data:")
    bags = r["data"]["real_robot_bags"]
    print(f"    {'✅' if bags['count'] > 0 else '❌'} real_robot_bags ({bags['count']} found)")
    for k, v in r["data"].items():
        if k == "real_robot_bags":
            continue
        print(f"    {ok(v)} {k}")

    print("  ROS2 Environment:")
    ros = r["ros2_env"]
    print(f"    {ok(ros['ros2_sourced'])} sourced | domain_id={ros['domain_id']}")

    print()
    # Summary
    all_vals = (
        list(r["model_adapters"].values()) +
        list(r["vln_package"].values()) +
        list(r["safety_tools"].values()) +
        list(r["config_files"].values())
    )
    n_ok = sum(1 for v in all_vals if v)
    n_total = len(all_vals)
    pct = 100 * n_ok // n_total
    print(f"  Stack readiness: {n_ok}/{n_total} ({pct}%)")
    print()


def main() -> None:
    report = run_audit()
    _print_report(report)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = RESULTS_DIR / "current_stack_audit.json"
    md_path   = RESULTS_DIR / "current_stack_audit.md"

    with json_path.open("w") as fh:
        json.dump(report, fh, indent=2)

    # Markdown version
    lines = ["# FleetSafe-VLN Stack Audit\n", f"Timestamp: {report['timestamp']}\n\n"]
    for section, items in report.items():
        if section in ("timestamp", "repo_root"):
            continue
        lines.append(f"## {section}\n\n")
        if isinstance(items, dict):
            for k, v in items.items():
                lines.append(f"- `{k}`: {'✅' if v else '❌'}\n")
        lines.append("\n")

    with md_path.open("w") as fh:
        fh.writelines(lines)

    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
