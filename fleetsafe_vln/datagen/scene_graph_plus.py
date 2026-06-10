"""Safety-aware scene graph — extends VLNTube scene graph with risk annotations.

Compatible with VLNTube scene_graph.json format. If VLNTube is installed
at third_party/VLNTube, uses its scene graph builder. Otherwise generates
a minimal graph from a task YAML.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SceneNode:
    node_id: str
    label: str
    position: List[float]          # [x, y, z]
    category: str = "region"       # region | object | waypoint | goal
    risk_level: str = "low"        # low | medium | high
    human_density: float = 0.0
    cbf_margin_m: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneGraphPlus:
    scene_id: str
    nodes: List[SceneNode] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    safety_zones: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: SceneNode) -> None:
        self.nodes.append(node)

    def add_edge(self, from_id: str, to_id: str, distance_m: float = 1.0,
                 risk_level: str = "low") -> None:
        self.edges.append({
            "from": from_id,
            "to": to_id,
            "distance_m": distance_m,
            "risk_level": risk_level,
        })

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": self.edges,
            "safety_zones": self.safety_zones,
            "metadata": self.metadata,
        }

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        print(f"[scene_graph_plus] Saved to {p}")


def build_from_task(task_id: str, scene: str) -> SceneGraphPlus:
    """Build a minimal scene graph from task metadata."""
    graph = SceneGraphPlus(scene_id=scene)
    graph.add_node(SceneNode(
        node_id="start",
        label="Start",
        position=[0.0, 0.0, 0.0],
        category="waypoint",
        risk_level="low",
    ))
    graph.add_node(SceneNode(
        node_id="goal",
        label="Goal",
        position=[5.0, 0.0, 0.0],
        category="goal",
        risk_level="low",
    ))
    graph.add_edge("start", "goal", distance_m=5.0, risk_level="low")
    return graph


def load_vlntube_graph(path: str | Path) -> Optional[SceneGraphPlus]:
    """Load a VLNTube scene graph JSON and convert to SceneGraphPlus format."""
    p = Path(path)
    if not p.exists():
        return None
    raw = json.loads(p.read_text(encoding="utf-8"))
    graph = SceneGraphPlus(scene_id=raw.get("scene_id", str(p.stem)))
    for node_data in raw.get("nodes", []):
        graph.add_node(SceneNode(
            node_id=str(node_data.get("id", "")),
            label=str(node_data.get("label", "")),
            position=list(node_data.get("position", [0.0, 0.0, 0.0])),
            category=str(node_data.get("category", "region")),
        ))
    for edge in raw.get("edges", []):
        graph.edges.append(edge)
    return graph
