"""IAmGoodNavigator adapter — optional wrapper around third_party/IAmGoodNavigator.

Provides safe introspection and demo episode launching without modifying
IAmGoodNavigator's source code.  All functions degrade gracefully when the
third-party clone is absent.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_FLEETSAFE_ROOT = Path(__file__).resolve().parents[2]
_FLEETSAFE_ROOT = Path(os.environ.get("FLEETSAFE_ROOT", str(_DEFAULT_FLEETSAFE_ROOT)))

# Primary location: external/IAmGoodNavigator
# Legacy fallback:  third_party/IAmGoodNavigator
_IANG_EXTERNAL = _FLEETSAFE_ROOT / "external" / "IAmGoodNavigator"
_IANG_LEGACY   = _FLEETSAFE_ROOT / "third_party" / "IAmGoodNavigator"
_IANG_ROOT = _IANG_EXTERNAL if _IANG_EXTERNAL.exists() else _IANG_LEGACY

# Isaac Sim scene USDs expected by IAmGoodNavigator
_KNOWN_SCENES = [
    "hospital_corridor",
    "warehouse_aisle",
    "nurse_station",
    "blind_corner",
    "dynamic_human_crossing",
]


def is_available() -> bool:
    """Return True if IAmGoodNavigator clone exists with demo.py."""
    return _IANG_ROOT.exists() and (_IANG_ROOT / "demo.py").exists()


def setup_status() -> Dict[str, Any]:
    """Return a dict describing the current installation state."""
    root_exists = _IANG_ROOT.exists()
    download_script = _IANG_ROOT / "download.sh"
    scene_dirs = find_downloaded_scenes()
    return {
        "available": root_exists,
        "root": str(_IANG_ROOT),
        "download_script_present": download_script.exists() if root_exists else False,
        "downloaded_scenes": [str(p) for p in scene_dirs],
        "scene_count": len(scene_dirs),
        "ready_for_demo": root_exists and len(scene_dirs) > 0,
    }


def find_downloaded_scenes(search_root: Optional[str | Path] = None) -> List[Path]:
    """Return directories that contain downloaded Isaac Sim scene assets."""
    root = Path(search_root) if search_root else _IANG_ROOT
    if not root.exists():
        return []
    # IAmGoodNavigator stores scenes as subdirs with a scene.usd or similar
    candidates = []
    for name in _KNOWN_SCENES:
        d = root / "scenes" / name
        if d.is_dir():
            candidates.append(d)
    # Also search for any .usd under scenes/
    scenes_dir = root / "scenes"
    if scenes_dir.exists():
        for usd in scenes_dir.rglob("*.usd"):
            parent = usd.parent
            if parent not in candidates:
                candidates.append(parent)
    return sorted(set(candidates))


def list_demo_tasks() -> List[Dict[str, Any]]:
    """Return a list of demo task descriptors based on available scenes."""
    scenes = find_downloaded_scenes()
    tasks = []
    for scene_dir in scenes:
        name = scene_dir.name
        tasks.append({
            "task_id": f"iamgoodnavigator_{name}",
            "scene": name,
            "scene_dir": str(scene_dir),
            "type": "fine" if "corridor" in name or "aisle" in name else "coarse",
        })
    if not tasks:
        # Stub tasks even without downloaded assets
        for name in _KNOWN_SCENES:
            tasks.append({
                "task_id": f"iamgoodnavigator_{name}",
                "scene": name,
                "scene_dir": None,
                "type": "fine" if "corridor" in name or "aisle" in name else "coarse",
                "note": "Scene not downloaded — run scripts/setup_iamgoodnavigator.sh --download",
            })
    return tasks


def run_demo_episode(
    scene: str,
    log_dir: str | Path,
    mode: str = "fine",
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    """Launch IAmGoodNavigator demo episode for the given scene.

    Requires IAmGoodNavigator to be cloned and Isaac Sim to be running.
    Returns result metadata dict.
    """
    if not is_available():
        return {
            "success": False,
            "error": "IAmGoodNavigator not cloned. Run scripts/setup_iamgoodnavigator.sh",
        }

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    entry = _IANG_ROOT / "run_demo.py"
    if not entry.exists():
        entry = _IANG_ROOT / "demo.py"
    if not entry.exists():
        return {
            "success": False,
            "error": f"No demo entry point found in {_IANG_ROOT}",
        }

    cmd = [
        sys.executable, str(entry),
        "--task", mode,
        "--index", str(scene) if str(scene).isdigit() else "0",
        "--work_dir", str(log_dir),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=str(_IANG_ROOT),
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-1000:],
            "log_dir": str(log_dir),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Demo timed out after {timeout_s}s"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def list_imported_episodes(fleetsafe_root: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    """Return imported IAmGoodNavigator episodes from datasets/vlnverse/imported/."""
    root = Path(fleetsafe_root) if fleetsafe_root else _FLEETSAFE_ROOT
    imported_dir = root / "datasets" / "vlnverse" / "imported" / "iamgoodnavigator"
    if not imported_dir.exists():
        return []
    episodes = []
    for ep_dir in sorted(imported_dir.iterdir()):
        if not ep_dir.is_dir():
            continue
        meta_file = ep_dir / "episode_meta.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text())
                episodes.append(meta)
            except Exception:
                episodes.append({"name": ep_dir.name, "status": "parse_error"})
        else:
            episodes.append({"name": ep_dir.name, "status": "no_meta"})
    return episodes


def export_episode_metadata_to_fleetsafe(
    iang_log_dir: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    """Convert IAmGoodNavigator episode log to a FleetSafe episode_meta.json stub."""
    src = Path(iang_log_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    meta: Dict[str, Any] = {
        "source": "IAmGoodNavigator",
        "original_log_dir": str(src),
        "status": "stub",
    }

    # Try to read any existing JSON in the source dir
    for json_file in src.glob("*.json"):
        try:
            meta["original_data"] = json.loads(json_file.read_text())
            meta["status"] = "imported"
            break
        except Exception:
            pass

    dest = out / "episode_meta.json"
    dest.write_text(json.dumps(meta, indent=2))
    return {"written": str(dest), **meta}
