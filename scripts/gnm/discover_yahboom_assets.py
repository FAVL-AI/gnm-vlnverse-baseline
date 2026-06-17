#!/usr/bin/env python3
"""Discover all Yahboom M3 Pro robot assets in the repository.

Searches for URDF, Xacro, mesh, USD, config, launch, and import-status files
related to the Yahboom ROSMASTER M3 Pro.

Writes:
    results/gnm_fleetsafe_v2_2/yahboom_asset_inventory.md
    results/gnm_fleetsafe_v2_2/yahboom_asset_inventory.json

Exits 0 always — does not require Isaac Sim or the physical robot.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "results" / "gnm_fleetsafe_v2_2"

SEARCH_PATTERNS = {
    "urdf": ["**/*.urdf"],
    "xacro": ["**/*.urdf.xacro", "**/*.xacro"],
    "mesh_stl": ["**/*.stl"],
    "mesh_dae": ["**/*.dae"],
    "mesh_obj": ["**/*.obj"],
    "usd": ["**/*.usd", "**/*.usda", "**/*.usdc"],
    "launch": ["**/*.launch.py", "**/*.launch.xml"],
    "config_yaml": ["**/*.yaml", "**/*.yml"],
    "import_status": ["**/isaac_import_status.json", "**/asset_report.json"],
}

YAHBOOM_KEYWORDS = {
    "yahboom", "m3pro", "m3_pro", "m3-pro", "rosmaster",
    "fleet_safe_yahboom", "yahboom_bringup",
}

SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", "node_modules",
    "third_party", "dist", "build", ".eggs",
}


def is_yahboom_related(path: Path) -> bool:
    path_lower = str(path).lower()
    return any(kw in path_lower for kw in YAHBOOM_KEYWORDS)


def discover() -> dict:
    found: dict[str, list[str]] = {key: [] for key in SEARCH_PATTERNS}

    def _walk(directory: Path):
        try:
            for entry in directory.iterdir():
                if entry.name in SKIP_DIRS:
                    continue
                if entry.is_dir():
                    _walk(entry)
                elif entry.is_file():
                    for category, patterns in SEARCH_PATTERNS.items():
                        for pat in patterns:
                            # Match by suffix / name pattern
                            suffix = pat.lstrip("*")
                            if entry.name.endswith(suffix) or entry.match(pat):
                                rel = str(entry.relative_to(ROOT))
                                if is_yahboom_related(entry):
                                    if rel not in found[category]:
                                        found[category].append(rel)
                                break
        except PermissionError:
            pass

    _walk(ROOT)

    for key in found:
        found[key].sort()

    return found


def summarise(found: dict) -> dict:
    return {
        "urdf_files": len(found["urdf"]),
        "xacro_files": len(found["xacro"]),
        "mesh_stl_files": len(found["mesh_stl"]),
        "mesh_dae_files": len(found["mesh_dae"]),
        "mesh_obj_files": len(found["mesh_obj"]),
        "usd_files": len(found["usd"]),
        "launch_files": len(found["launch"]),
        "config_yaml_files": len(found["config_yaml"]),
        "import_status_files": len(found["import_status"]),
        "has_urdf": len(found["urdf"]) > 0,
        "has_xacro": len(found["xacro"]) > 0,
        "has_mesh": any(
            len(found[k]) > 0
            for k in ("mesh_stl", "mesh_dae", "mesh_obj")
        ),
        "has_usd": len(found["usd"]) > 0,
    }


def write_json(found: dict, summary: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "robot": "Yahboom ROSMASTER M3 Pro",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(ROOT),
        "summary": summary,
        "files": found,
    }
    path = OUT_DIR / "yahboom_asset_inventory.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def write_markdown(found: dict, summary: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Yahboom M3 Pro Asset Inventory",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        "| Asset type | Count | Present? |",
        "|---|---:|---|",
        f"| URDF files | {summary['urdf_files']} | {'Yes' if summary['has_urdf'] else 'No — required'} |",
        f"| Xacro files | {summary['xacro_files']} | {'Yes' if summary['has_xacro'] else 'No'} |",
        f"| Mesh files (STL) | {summary['mesh_stl_files']} | {'Yes' if summary['mesh_stl_files'] else 'No — primitives only'} |",
        f"| Mesh files (DAE) | {summary['mesh_dae_files']} | {'Yes' if summary['mesh_dae_files'] else 'No'} |",
        f"| Mesh files (OBJ) | {summary['mesh_obj_files']} | {'Yes' if summary['mesh_obj_files'] else 'No'} |",
        f"| USD/USDA/USDC files | {summary['usd_files']} | {'Yes' if summary['has_usd'] else 'No — required for Isaac Sim'} |",
        f"| Launch files | {summary['launch_files']} | {'Yes' if summary['launch_files'] else 'No'} |",
        f"| Config YAML files | {summary['config_yaml_files']} | {'Yes' if summary['config_yaml_files'] else 'No'} |",
        f"| Import status files | {summary['import_status_files']} | {'Yes' if summary['import_status_files'] else 'No'} |",
        "",
    ]

    LABELS = {
        "urdf": "URDF files",
        "xacro": "Xacro files",
        "mesh_stl": "Mesh — STL",
        "mesh_dae": "Mesh — DAE",
        "mesh_obj": "Mesh — OBJ",
        "usd": "USD / USDA / USDC",
        "launch": "Launch files",
        "config_yaml": "Config YAML files",
        "import_status": "Import status JSON",
    }

    for key, label in LABELS.items():
        files = found[key]
        if not files:
            continue
        lines += [f"## {label}", ""]
        for f in files:
            lines.append(f"- `{f}`")
        lines.append("")

    lines += [
        "## Sim-to-Real Readiness",
        "",
        "| Requirement | Status |",
        "|---|---|",
        f"| URDF present | {'Ready' if summary['has_urdf'] else 'Missing — create from product spec'} |",
        f"| Xacro present | {'Ready' if summary['has_xacro'] else 'Optional — for Gazebo bringup'} |",
        f"| Mesh geometry | {'Present' if summary['has_mesh'] else 'Missing — primitive geometry only (sufficient for kinematics)'} |",
        f"| USD present | {'Present — verify it loads in Isaac Sim' if summary['has_usd'] else 'Not yet — run Isaac Sim URDF importer'} |",
        "| Five live topics verified | Pending — requires Isaac Sim session with Yahboom stage |",
        "| First rosbag episode | Pending — v2.3 |",
        "",
        "See `docs/YAHBOOM_URDF_TO_USD_IMPORT.md` for the URDF → USD import steps.",
        "See `docs/v2.2_yahboom_m3pro_sim_to_real_plan.md` for the full plan.",
    ]

    path = OUT_DIR / "yahboom_asset_inventory.md"
    path.write_text("\n".join(lines))
    return path


def main() -> int:
    print("=" * 60)
    print(" Yahboom M3 Pro Asset Discovery  [v2.2]")
    print("=" * 60)
    print(f"Repo root: {ROOT}")
    print()

    print("Searching for Yahboom-related assets...")
    found = discover()
    summary = summarise(found)

    print()
    print("Summary:")
    for key, count in {
        "URDF": summary["urdf_files"],
        "Xacro": summary["xacro_files"],
        "Mesh (STL/DAE/OBJ)": (
            summary["mesh_stl_files"]
            + summary["mesh_dae_files"]
            + summary["mesh_obj_files"]
        ),
        "USD/USDA/USDC": summary["usd_files"],
        "Launch": summary["launch_files"],
        "Config YAML": summary["config_yaml_files"],
        "Import status JSON": summary["import_status_files"],
    }.items():
        status = f"{count} found" if count else "none found"
        print(f"  {key:30s}: {status}")

    print()

    json_path = write_json(found, summary)
    md_path = write_markdown(found, summary)

    print(f"[OK] JSON inventory: {json_path.relative_to(ROOT)}")
    print(f"[OK] Markdown inventory: {md_path.relative_to(ROOT)}")
    print()

    if not summary["has_urdf"]:
        print("[WARN] No Yahboom URDF found — required for Isaac Sim import.")
    if not summary["has_usd"]:
        print("[WARN] No Yahboom USD found — run Isaac Sim URDF importer.")
    if not summary["has_mesh"]:
        print("[INFO] No mesh files found — primitive geometry only.")
        print("[INFO] Sufficient for kinematics; mesh needed only for visual fidelity.")

    print("[OK] Asset discovery complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
