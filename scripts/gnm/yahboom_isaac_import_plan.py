#!/usr/bin/env python3
"""Inspect existing Yahboom M3 Pro assets and produce an ordered Isaac Sim import plan.

Reads:
    assets/robots/yahboom_m3_pro/  — URDF, USD, import status
    docs/YAHBOOM_URDF_TO_USD_IMPORT.md
    assets/robots/yahboom_m3_pro/asset_report.json
    assets/robots/yahboom_m3_pro/isaac_import_status.json

Writes:
    results/gnm_fleetsafe_v2_3/yahboom_isaac_import_plan.md
    results/gnm_fleetsafe_v2_3/yahboom_isaac_import_plan.json

Exits 0 always — does not require Isaac Sim or the physical robot.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "results" / "gnm_fleetsafe_v2_3"

CANONICAL_URDF = ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro.urdf"
CANONICAL_USD = ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro.usd"
REFERENCE_USDA = ROOT / "assets" / "robots" / "yahboom_m3_pro" / "yahboom_m3pro_reference.usda"
IMPORT_STATUS = ROOT / "assets" / "robots" / "yahboom_m3_pro" / "isaac_import_status.json"
ASSET_REPORT = ROOT / "assets" / "robots" / "yahboom_m3_pro" / "asset_report.json"
IMPORT_DOC = ROOT / "docs" / "YAHBOOM_URDF_TO_USD_IMPORT.md"
XACRO = (
    ROOT
    / "ros2_ws"
    / "src"
    / "fleet_safe_description"
    / "urdf"
    / "yahboom_m3pro.urdf.xacro"
)

IMPORT_STEPS = [
    {
        "step": 1,
        "title": "Launch Isaac Sim",
        "command": "~/.local/share/ov/pkg/isaac-sim-*/isaac-sim.sh",
        "notes": (
            "Use the full GUI launcher, not headless mode, for the URDF importer."
        ),
        "gate": "Isaac Sim opens and shows an empty stage.",
        "blocking": True,
    },
    {
        "step": 2,
        "title": "Enable URDF Importer extension",
        "command": "Window → Extensions → search 'URDF' → enable",
        "notes": (
            "Look for 'Isaac URDF Importer' (omni.isaac.urdf) or "
            "'Asset Importer URDF' (isaacsim.asset.importer.urdf). "
            "Either works — enable the one that appears in your Isaac Sim version."
        ),
        "gate": "Extension shows as enabled (green toggle).",
        "blocking": True,
    },
    {
        "step": 3,
        "title": "Import the Yahboom URDF",
        "command": "File → Import → URDF → select assets/robots/yahboom_m3_pro/yahboom_m3pro.urdf",
        "notes": (
            "Import settings: Merge fixed joints OFF, Fix base OFF, "
            "Import inertia tensors ON. "
            "Do NOT use TurtleBot, JetBot, Carter, or any other robot. "
            "Only the Yahboom M3 Pro URDF is accepted."
        ),
        "gate": (
            "Robot appears in the stage. Four wheel joints are visible: "
            "fl_wheel_joint, fr_wheel_joint, rl_wheel_joint, rr_wheel_joint."
        ),
        "blocking": True,
    },
    {
        "step": 4,
        "title": "Save robot stage as USD",
        "command": (
            "File → Save As → "
            "assets/robots/yahboom_m3_pro/yahboom_m3pro.usd"
        ),
        "notes": (
            "Save as .usd (binary). The reference stage (.usda) already exists "
            "as a text backup. "
            "Update assets/robots/yahboom_m3_pro/isaac_import_status.json "
            "after saving."
        ),
        "gate": "USD file exists at the expected path.",
        "blocking": True,
    },
    {
        "step": 5,
        "title": "Enable ROS 2 Bridge extension",
        "command": "Window → Extensions → search 'ROS2 Bridge' → enable",
        "notes": (
            "The bridge starts automatically when enabled. "
            "Set ROS_DOMAIN_ID=0 in the terminal before launching Isaac Sim "
            "to match the default ROS 2 domain."
        ),
        "gate": "ROS 2 Bridge extension shows as enabled.",
        "blocking": True,
    },
    {
        "step": 6,
        "title": "Add OmniGraph camera publisher",
        "command": "Window → Visual Scripting → Action Graph → add ROS2PublishImage node",
        "notes": (
            "Connect the camera sensor prim output to the publisher. "
            "Set topic_name = /camera/image_raw. "
            "This is the canonical GNM camera topic."
        ),
        "gate": "Node appears in graph. Topic name field shows /camera/image_raw.",
        "blocking": True,
    },
    {
        "step": 7,
        "title": "Add OmniGraph odometry publisher",
        "command": "Add ROS2PublishOdometry node → connect to drive articulation",
        "notes": (
            "Connect to the robot's differential drive or mecanum drive "
            "articulation. Set topic_name = /odom."
        ),
        "gate": "Node appears. Topic = /odom.",
        "blocking": True,
    },
    {
        "step": 8,
        "title": "Add OmniGraph TF publisher",
        "command": "Add ROS2PublishTransformTree node → connect to robot prim",
        "notes": (
            "Publishes the full robot TF tree including base_link, "
            "camera_link, and lidar_link frames."
        ),
        "gate": "Node appears. TF tree includes base_link.",
        "blocking": True,
    },
    {
        "step": 9,
        "title": "Add OmniGraph lidar scan publisher",
        "command": "Add ROS2PublishLaserScan node → connect to lidar prim",
        "notes": (
            "Connect to the lidar sensor prim. Set topic_name = /scan. "
            "Set frame_id = lidar_link."
        ),
        "gate": "Node appears. Topic = /scan.",
        "blocking": True,
    },
    {
        "step": 10,
        "title": "Add OmniGraph cmd_vel subscriber",
        "command": "Add ROS2SubscribeTwist node → connect to wheel joint controllers",
        "notes": (
            "Subscribe on /cmd_vel. Connect the twist output to the four "
            "wheel velocity controllers using mecanum inverse kinematics "
            "(fl, fr, rl, rr). "
            "Set topic_name = /cmd_vel."
        ),
        "gate": "Node appears. Topic = /cmd_vel.",
        "blocking": True,
    },
    {
        "step": 11,
        "title": "Press Play and verify topics",
        "command": "Press Play in Isaac Sim toolbar, then in a separate terminal:\n  python3 scripts/gnm/verify_yahboom_live_topics.py --strict",
        "notes": (
            "All five canonical topics must pass. "
            "If any topic is missing, stop and fix the OmniGraph before continuing."
        ),
        "gate": "verify_yahboom_live_topics.py --strict exits 0.",
        "blocking": True,
    },
]


def read_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def assess_assets() -> dict:
    import_status = read_json_safe(IMPORT_STATUS)
    asset_report = read_json_safe(ASSET_REPORT)

    return {
        "canonical_urdf": {
            "path": str(CANONICAL_URDF.relative_to(ROOT)),
            "exists": CANONICAL_URDF.exists(),
        },
        "canonical_usd": {
            "path": str(CANONICAL_USD.relative_to(ROOT)),
            "exists": CANONICAL_USD.exists(),
        },
        "reference_usda": {
            "path": str(REFERENCE_USDA.relative_to(ROOT)),
            "exists": REFERENCE_USDA.exists(),
        },
        "xacro": {
            "path": str(XACRO.relative_to(ROOT)),
            "exists": XACRO.exists(),
        },
        "import_status": import_status,
        "asset_report_summary": {
            "urdf_count": asset_report.get("assets", {}).get("urdf_count", 0),
            "xacro_count": asset_report.get("assets", {}).get("xacro_count", 0),
            "has_urdf": asset_report.get("has_urdf", False),
        },
        "import_doc_exists": IMPORT_DOC.exists(),
    }


def first_blocking_step(assets: dict) -> int:
    if not assets["canonical_urdf"]["exists"]:
        return 0
    if not assets["canonical_usd"]["exists"]:
        return 4
    return 5


def write_json(assets: dict, first_step: int) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "robot": "Yahboom ROSMASTER M3 Pro",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assets": assets,
        "first_blocking_step": first_step,
        "import_steps": IMPORT_STEPS,
    }
    path = OUT_DIR / "yahboom_isaac_import_plan.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def write_markdown(assets: dict, first_step: int) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Yahboom M3 Pro — Isaac Sim Import Plan",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Asset Status",
        "",
        "| Asset | Path | Present? |",
        "|---|---|---|",
        f"| Canonical URDF | `{assets['canonical_urdf']['path']}` | "
        f"{'Yes' if assets['canonical_urdf']['exists'] else 'No — required'} |",
        f"| Canonical USD | `{assets['canonical_usd']['path']}` | "
        f"{'Yes' if assets['canonical_usd']['exists'] else 'No — generate via importer'} |",
        f"| Reference USDA | `{assets['reference_usda']['path']}` | "
        f"{'Yes' if assets['reference_usda']['exists'] else 'No'} |",
        f"| Xacro | `{assets['xacro']['path']}` | "
        f"{'Yes' if assets['xacro']['exists'] else 'No'} |",
        f"| Import reference doc | `docs/YAHBOOM_URDF_TO_USD_IMPORT.md` | "
        f"{'Yes' if assets['import_doc_exists'] else 'No'} |",
        "",
        f"**First blocking step: Step {first_step}**",
        "",
        "## Ordered Import Steps",
        "",
    ]

    for step in IMPORT_STEPS:
        num = step["step"]
        marker = " ← start here" if num == first_step else ""
        lines += [
            f"### Step {num} — {step['title']}{marker}",
            "",
            f"**Command/Action:** `{step['command']}`",
            "",
            f"**Notes:** {step['notes']}",
            "",
            f"**Gate:** {step['gate']}",
            "",
        ]

    lines += [
        "## After All Steps Complete",
        "",
        "Run strict topic verification from a terminal (Isaac Sim must be playing):",
        "",
        "```bash",
        "python3 scripts/gnm/verify_yahboom_live_topics.py --strict",
        "```",
        "",
        "All five topics must pass before recording any rosbag2 episode.",
        "",
        "See `docs/v2.3_yahboom_isaac_import_topic_verification.md` for full context.",
    ]

    path = OUT_DIR / "yahboom_isaac_import_plan.md"
    path.write_text("\n".join(lines))
    return path


def main() -> int:
    print("=" * 60)
    print(" Yahboom M3 Pro Isaac Import Plan  [v2.3]")
    print("=" * 60)
    print(f"Repo root: {ROOT}")
    print()

    assets = assess_assets()
    first_step = first_blocking_step(assets)

    print("Asset inventory:")
    for key, info in assets.items():
        if not isinstance(info, dict) or "exists" not in info:
            continue
        status = "present" if info["exists"] else "MISSING"
        print(f"  {info['path']:<60s}: {status}")

    print()

    if assets["canonical_urdf"]["exists"]:
        print("[OK] Canonical URDF present — Step 1–3 can proceed.")
    else:
        print("[WARN] Canonical URDF missing — Isaac Sim import cannot begin.")

    if assets["canonical_usd"]["exists"]:
        print("[OK] Canonical USD present — skip to Step 5 (ROS 2 bridge setup).")
    else:
        print("[INFO] Canonical USD not yet generated.")
        print("[INFO] Steps 1–4 must complete before ROS 2 bridge setup.")

    print()
    print(f"First blocking step: Step {first_step}")
    print()

    json_path = write_json(assets, first_step)
    md_path = write_markdown(assets, first_step)

    print(f"[OK] JSON plan: {json_path.relative_to(ROOT)}")
    print(f"[OK] Markdown plan: {md_path.relative_to(ROOT)}")
    print()
    print("[OK] Import plan complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
