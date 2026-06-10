"""Central configuration — all path resolution lives here."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    repo_root: Path = Path(__file__).resolve().parents[2]
    results_dir: Path | None = None
    scripts_dir: Path | None = None
    host: str = "0.0.0.0"
    port: int = 8000
    robot_ssh: str = "jetson@100.91.232.55"
    robot_dry_run: bool = True
    # SSH password fallback — used only when key auth is unavailable.
    # Set via FLEETSAFE_ROBOT_PASSWORD env var. Never logged or audited.
    robot_password: str = ""
    yolo_model_path: str = "~/models/yolov8n.pt"
    yolo_node_package: str = "fleetsafe_perception"

    model_config = {"env_prefix": "FLEETSAFE_"}

    @property
    def _results_dir(self) -> Path:
        return self.results_dir or (self.repo_root / "benchmarks" / "visualnav" / "results")

    @property
    def _scripts_dir(self) -> Path:
        return self.scripts_dir or (self.repo_root / "scripts")


settings = Settings()


# ── Script allowlist ───────────────────────────────────────────────────────────
# Only these scripts may be launched via the API.
ALLOWED_SCRIPTS: dict[str, dict] = {
    "smoke": {
        "label": "Smoke test (mock, 1 seed)",
        "path": "scripts/visualnav/run_e2e_smoke.sh",
        "args": [],
        "preset": "smoke",
        "backend": "mock",
        "description": "Quick sanity check — 1 seed, straight_corridor, mock backend",
        "estimated_s": 30,
    },
    "dev_mujoco": {
        "label": "Dev run (MuJoCo, 10 seeds)",
        "path": "scripts/visualnav/run_publishable_matrix.sh",
        "args": ["--backend", "mujoco", "--seeds", "dev"],
        "preset": "dev",
        "backend": "mujoco",
        "description": "10 seeds × all scenes × all models, MuJoCo backend",
        "estimated_s": 600,
    },
    "baseline_isaac": {
        "label": "Baseline matrix (Isaac Sim)",
        "path": "scripts/visualnav/run_baseline_isaac.sh",
        "args": [],
        "preset": "paper",
        "backend": "isaaclab",
        "description": "Full Isaac Sim baseline benchmark run",
        "estimated_s": 3600,
    },
    "fleetsafe_isaac": {
        "label": "FleetSafe matrix (Isaac Sim)",
        "path": "scripts/visualnav/run_fleetsafe_isaac.sh",
        "args": [],
        "preset": "paper",
        "backend": "isaaclab",
        "description": "Full Isaac Sim FleetSafe benchmark run",
        "estimated_s": 3600,
    },
    "matrix": {
        "label": "Full paper matrix",
        "path": "scripts/visualnav/run_matrix.sh",
        "args": [],
        "preset": "paper",
        "backend": "mujoco",
        "description": "50 seeds × 14 scenes × 6 conditions — publication grade",
        "estimated_s": 7200,
    },
    "perception_node_mock": {
        "label": "Perception node (mock)",
        "path": "scripts/ros2/fleetsafe_perception_node.py",
        "args": ["--perception", "mock", "--monitor-only"],
        "preset": "real_robot",
        "backend": "real",
        "description": "Live perception node — monitor-only, mock detections",
        "estimated_s": None,
    },
}
