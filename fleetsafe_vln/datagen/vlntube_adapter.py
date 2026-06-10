"""VLNTube adapter — optional wrapper around third_party/VLNTube.

Does NOT modify VLNTube code. Treats it as a black-box sub-pipeline for:
  - scene graph extraction (vistube)
  - RGB/depth path rendering
  - instruction generation (instube)
  - datatube-format export

All calls fail gracefully if VLNTube is not present.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# fleetsafe_vln/datagen/ → fleetsafe_vln/ → repo_root/
# parents[0] = datagen/, parents[1] = fleetsafe_vln/, parents[2] = repo_root/
_DEFAULT_FLEETSAFE_ROOT = Path(__file__).resolve().parents[2]
_FLEETSAFE_ROOT = Path(os.environ.get("FLEETSAFE_ROOT", str(_DEFAULT_FLEETSAFE_ROOT)))
_VLNTUBE_ROOT = _FLEETSAFE_ROOT / "third_party" / "VLNTube"


def is_available() -> bool:
    """Return True if the VLNTube third-party clone exists and looks valid."""
    return _VLNTUBE_ROOT.exists() and (
        (_VLNTUBE_ROOT / "README.md").exists()
        or (_VLNTUBE_ROOT / ".git").exists()
    )


def inspect_modules() -> Dict[str, bool]:
    """Return which VLNTube sub-modules are present on disk."""
    modules = {
        "vistube/scene_graph.py": False,
        "vistube/render.py": False,
        "instube/generate.py": False,
        "datatube/export.py": False,
    }
    if not is_available():
        return modules
    for key in modules:
        modules[key] = (_VLNTUBE_ROOT / key).exists()
    return modules


def find_usd_scenes(search_root: Optional[str | Path] = None) -> List[Path]:
    """Return all .usd / .usda files under search_root (default: third_party/VLNTube)."""
    root = Path(search_root) if search_root else _VLNTUBE_ROOT
    if not root.exists():
        return []
    return sorted(root.rglob("*.usd")) + sorted(root.rglob("*.usda"))


def find_scene_graph_files(search_root: Optional[str | Path] = None) -> List[Path]:
    """Return all scene graph JSON files under search_root."""
    root = Path(search_root) if search_root else _VLNTUBE_ROOT
    if not root.exists():
        return []
    return sorted(root.rglob("scene_graph*.json"))


def find_prebuilt_data(search_root: Optional[str | Path] = None) -> List[Path]:
    """Return pre-rendered episode directories (contain rgb/ subdirs)."""
    root = Path(search_root) if search_root else _VLNTUBE_ROOT
    if not root.exists():
        return []
    return [p.parent for p in root.rglob("rgb") if p.is_dir()]


def generate_fleetsafe_scene_index(
    search_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Build a FleetSafe-compatible index of all scenes found in VLNTube."""
    usd = find_usd_scenes(search_root)
    graphs = find_scene_graph_files(search_root)
    data_dirs = find_prebuilt_data(search_root)
    return {
        "source": "VLNTube",
        "vlntube_root": str(_VLNTUBE_ROOT),
        "available": is_available(),
        "usd_scenes": [str(p) for p in usd],
        "scene_graphs": [str(p) for p in graphs],
        "prebuilt_episode_dirs": [str(p) for p in data_dirs],
        "module_status": inspect_modules(),
    }


def export_vlntube_to_fleetsafe_stub(
    scene_usd_path: str,
    output_dir: str | Path,
) -> Dict[str, Any]:
    """Write a minimal FleetSafe episode stub from a VLNTube scene path.

    Returns a dict describing what was written. Does not require VLNTube
    Python modules — only scene file presence is needed.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stub = {
        "source": "VLNTube",
        "scene_usd": str(scene_usd_path),
        "status": "stub",
        "note": "Full episode data requires running VLNTube pipeline.",
    }
    import json
    stub_path = out / "episode_stub.json"
    stub_path.write_text(json.dumps(stub, indent=2))
    return {"written": str(stub_path), **stub}


def _load_module(relative_path: str) -> Any:
    full = _VLNTUBE_ROOT / relative_path
    if not full.exists():
        raise ImportError(f"VLNTube module not found: {full}")
    spec = importlib.util.spec_from_file_location(full.stem, str(full))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load VLNTube module: {full}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VLNTubeAdapter:
    """Thin wrapper providing safe access to VLNTube pipeline stages."""

    def __init__(self):
        if not is_available():
            raise ImportError(
                f"VLNTube not found at {_VLNTUBE_ROOT}. "
                "Clone it: git clone https://github.com/william13077/VLNTube third_party/VLNTube"
            )

    def build_scene_graph(self, scene_usd_path: str) -> Dict[str, Any]:
        mod = _load_module("vistube/scene_graph.py")
        return mod.build_graph(scene_usd_path)

    def render_trajectory(
        self,
        scene_usd_path: str,
        waypoints: List[Dict[str, float]],
        output_dir: str,
    ) -> List[str]:
        mod = _load_module("vistube/render.py")
        return mod.render(
            scene=scene_usd_path,
            waypoints=waypoints,
            output_dir=output_dir,
        )

    def generate_instructions(
        self,
        scene_graph: Dict[str, Any],
        goal_label: str,
        n: int = 5,
    ) -> List[str]:
        mod = _load_module("instube/generate.py")
        return mod.generate_instructions(
            scene_graph=scene_graph,
            goal=goal_label,
            n=n,
        )

    def export_datatube(self, episodes: List[Dict[str, Any]], output_path: str) -> str:
        mod = _load_module("datatube/export.py")
        return mod.export(episodes=episodes, output_path=output_path)
