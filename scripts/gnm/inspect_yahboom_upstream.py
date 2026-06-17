#!/usr/bin/env python3
"""Inspect the cloned Yahboom ROSMASTER M3 Pro upstream repository.

Searches external/yahboom/ROSMASTER-M3PRO for:
  - URDF and Xacro robot description files
  - ROS 2 launch files
  - Camera topic references
  - LiDAR / laser scan references
  - Odometry references
  - TF frame references
  - cmd_vel / Twist references
  - Mecanum wheel references
  - ROS 2 and Humble references

Writes:
  results/yahboom_upstream/yahboom_upstream_inventory.json
  results/yahboom_upstream/yahboom_upstream_inventory.md

If the upstream repo is not cloned, exits 0 with clone instructions.

Usage:
    python3 scripts/gnm/inspect_yahboom_upstream.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
UPSTREAM_DIR = ROOT / "external" / "yahboom" / "ROSMASTER-M3PRO"
OUT_DIR = ROOT / "results" / "yahboom_upstream"

UPSTREAM_URL = "https://github.com/YahboomTechnology/ROSMASTER-M3PRO"

SEARCH_PATTERNS = {
    "urdf_files": {"glob": "**/*.urdf", "type": "file"},
    "xacro_files": {"glob": "**/*.xacro", "type": "file"},
    "launch_files_py": {"glob": "**/*.launch.py", "type": "file"},
    "launch_files_xml": {"glob": "**/*.launch", "type": "file"},
    "package_xml": {"glob": "**/package.xml", "type": "file"},
}

TEXT_SEARCHES = [
    ("camera_image_raw",       "/camera/image_raw"),
    ("camera_color_image_raw", "/camera/color/image_raw"),
    ("odom_topic",             "/odom"),
    ("scan_topic",             "/scan"),
    ("cmd_vel_topic",          "cmd_vel"),
    ("mecanum",                "mecanum"),
    ("ros2_humble",            "humble"),
    ("ros2_keyword",           "ROS 2"),
    ("tf_keyword",             "tf2"),
    ("twist_type",             "geometry_msgs"),
    ("slam",                   "slam"),
    ("openclaw",               "openclaw"),
]


def find_files(base: Path) -> dict:
    results = {}
    for key, spec in SEARCH_PATTERNS.items():
        found = sorted(str(p.relative_to(base)) for p in base.glob(spec["glob"]))
        results[key] = found
    return results


def text_search(base: Path, keyword: str) -> list[str]:
    matches = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".py", ".sh", ".xml", ".yaml", ".yml", ".launch",
                          ".urdf", ".xacro", ".txt", ".md", ".rst", ""}:
            continue
        try:
            text = path.read_text(errors="ignore")
            if keyword in text:
                matches.append(str(path.relative_to(base)))
        except (PermissionError, OSError):
            pass
    return sorted(matches)[:20]


def main() -> int:
    print("=" * 60)
    print(" Yahboom ROSMASTER M3 Pro Upstream Inspector  [v2.4]")
    print("=" * 60)
    print()

    if not UPSTREAM_DIR.exists():
        print(f"[INFO] Upstream repo not found at: {UPSTREAM_DIR}")
        print()
        print("[INFO] To clone the upstream repo, run:")
        print(f"  bash scripts/setup/clone_yahboom_rosmaster_m3pro.sh")
        print()
        print("[INFO] Then re-run this inspector:")
        print("  python3 scripts/gnm/inspect_yahboom_upstream.py")
        print()
        print("[INFO] Upstream URL:")
        print(f"  {UPSTREAM_URL}")
        print()

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "upstream_url": UPSTREAM_URL,
            "upstream_dir": str(UPSTREAM_DIR),
            "status": "not_cloned",
            "clone_command": "bash scripts/setup/clone_yahboom_rosmaster_m3pro.sh",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        json_path = OUT_DIR / "yahboom_upstream_inventory.json"
        json_path.write_text(json.dumps(payload, indent=2))
        print(f"[OK] Status written to: {json_path.relative_to(ROOT)}")
        print("[OK] Exiting 0 (upstream not cloned — expected before setup).")
        return 0

    print(f"Upstream dir : {UPSTREAM_DIR}")
    print(f"Repo root    : {ROOT}")
    print()

    file_results = find_files(UPSTREAM_DIR)

    print("File discovery:")
    for key, files in file_results.items():
        label = key.replace("_", " ")
        print(f"  {label:<30s}: {len(files)} found")
        for f in files[:5]:
            print(f"      {f}")
        if len(files) > 5:
            print(f"      ... and {len(files) - 5} more")
    print()

    print("Text search results (up to 20 files each):")
    text_results = {}
    for key, keyword in TEXT_SEARCHES:
        files = text_search(UPSTREAM_DIR, keyword)
        text_results[key] = {"keyword": keyword, "files": files, "count": len(files)}
        found_str = f"{len(files)} file(s)" if files else "not found"
        print(f"  {key:<30s}: {found_str}")
    print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "upstream_url": UPSTREAM_URL,
        "upstream_dir": str(UPSTREAM_DIR),
        "status": "cloned",
        "inspected_at": datetime.now(timezone.utc).isoformat(),
        "file_counts": {k: len(v) for k, v in file_results.items()},
        "files": file_results,
        "text_searches": text_results,
    }

    json_path = OUT_DIR / "yahboom_upstream_inventory.json"
    json_path.write_text(json.dumps(payload, indent=2))

    lines = [
        "# Yahboom Upstream Inventory",
        "",
        f"Upstream: {UPSTREAM_URL}",
        f"Inspected: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Files Found",
        "",
        "| Type | Count |",
        "|---|---|",
    ]
    for key, files in file_results.items():
        lines.append(f"| {key.replace('_', ' ')} | {len(files)} |")
    lines += [
        "",
        "## Text Search Summary",
        "",
        "| Keyword | Files containing it |",
        "|---|---|",
    ]
    for key, res in text_results.items():
        lines.append(f"| `{res['keyword']}` | {res['count']} |")

    lines += [
        "",
        "## Topic Mapping Reference",
        "",
        "See `docs/yahboom_to_fleetsafe_topic_mapping.md` for the complete remap table.",
        "",
        "## Integration Reference",
        "",
        "See `docs/yahboom_upstream_integration.md` for architecture and claim boundary.",
    ]

    md_path = OUT_DIR / "yahboom_upstream_inventory.md"
    md_path.write_text("\n".join(lines))

    print(f"[OK] JSON inventory: {json_path.relative_to(ROOT)}")
    print(f"[OK] Markdown inventory: {md_path.relative_to(ROOT)}")
    print()
    print("[OK] Inspection complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
