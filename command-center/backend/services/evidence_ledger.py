"""
Append-only evidence ledger.

Every simulation run, robot session, training artefact, video, and dashboard
action is recorded with a SHA256 hash, git commit, host, operator, and a
claim_scope that precisely states what the entry proves.

The ledger file is never modified — only new lines are appended.
Past entries are immutable evidence.

Claim scopes (what an entry proves):
  sim_benchmark_result   — aggregate metrics from a simulation run
  sim_episode_trajectory — per-episode trajectory + events
  real_robot_session     — ROS2 bag recorded on real robot
  real_robot_motion_proof— verified cmd_vel_raw → cmd_vel path validated
  dashboard_audit        — timestamped operator action
  training_checkpoint    — saved ML model weights
  training_run           — full training run (curves + config)
  video_evidence         — RGB video of robot or sim
  ros2_verification      — ros2 node/topic graph snapshot
  manual_annotation      — human-labeled ground truth

Ground truth types (what truth underlies the data):
  perfect_sim_state   — sim state is exact ground truth
  semantic_scene_spec — procedurally designed semantic scene
  sensor_derived      — derived from robot sensors, not verified vs ground truth
  human_labeled       — manually annotated by a human
  none                — no ground truth; inference-only
"""
from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Literal

from ..config import settings

LEDGER_PATH = settings.repo_root / "command-center" / "recordings" / "evidence_ledger.jsonl"

ClaimScope = Literal[
    "sim_benchmark_result", "sim_episode_trajectory",
    "real_robot_session", "real_robot_motion_proof",
    "dashboard_audit", "training_checkpoint", "training_run",
    "video_evidence", "ros2_verification", "manual_annotation",
]

GroundTruthType = Literal[
    "perfect_sim_state", "semantic_scene_spec",
    "sensor_derived", "human_labeled", "none",
]

Source = Literal[
    "mujoco", "isaaclab", "real_robot", "dashboard", "wandb", "huggingface",
]

_lock = threading.Lock()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(settings.repo_root), stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def sha256_file(path: Path) -> str | None:
    """SHA256 of a local file. Returns None if file doesn't exist."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (FileNotFoundError, PermissionError):
        return None


def sha256_string(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class EvidenceLedger:
    def __init__(self) -> None:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        claim_scope: ClaimScope,
        source: Source,
        ground_truth_type: GroundTruthType,
        *,
        description: str,
        artifact_path: Path | str | None = None,
        robot_id: str | None = None,
        operator: str = "system",
        recording_rate_hz: float | None = None,
        fps: float | None = None,
        timestamp_start: float | None = None,
        timestamp_end: float | None = None,
        metadata: dict | None = None,
    ) -> dict:
        sha = None
        path_str = None
        size_bytes = None

        if artifact_path is not None:
            p = Path(artifact_path)
            path_str = str(p)
            sha = sha256_file(p)
            try:
                size_bytes = p.stat().st_size
            except Exception:
                pass

        entry = {
            "id": sha256_string(f"{time.time()}{claim_scope}{path_str}")[:16],
            "timestamp": time.time(),
            "claim_scope": claim_scope,
            "source": source,
            "ground_truth_type": ground_truth_type,
            "description": description,
            "artifact_path": path_str,
            "sha256": sha,
            "size_bytes": size_bytes,
            "robot_id": robot_id,
            "operator": operator,
            "git_commit": _git_commit(),
            "host": socket.gethostname(),
            "recording_rate_hz": recording_rate_hz,
            "fps": fps,
            "timestamp_start": timestamp_start,
            "timestamp_end": timestamp_end,
            "metadata": metadata or {},
        }
        with _lock:
            with LEDGER_PATH.open("a") as f:
                f.write(json.dumps(entry) + "\n")
        return entry

    def query(
        self,
        source: str | None = None,
        claim_scope: str | None = None,
        n: int = 500,
    ) -> list[dict]:
        if not LEDGER_PATH.exists():
            return []
        entries: list[dict] = []
        with _lock:
            lines = LEDGER_PATH.read_text().splitlines()
        for line in lines:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if source and e.get("source") != source:
                continue
            if claim_scope and e.get("claim_scope") != claim_scope:
                continue
            entries.append(e)
        return entries[-n:]

    def get_stats(self) -> dict:
        entries = self.query()
        by_scope: dict[str, int] = {}
        by_source: dict[str, int] = {}
        hashed = 0
        for e in entries:
            by_scope[e.get("claim_scope", "?")] = by_scope.get(e.get("claim_scope", "?"), 0) + 1
            by_source[e.get("source", "?")] = by_source.get(e.get("source", "?"), 0) + 1
            if e.get("sha256"):
                hashed += 1
        return {
            "total": len(entries),
            "hashed": hashed,
            "by_scope": by_scope,
            "by_source": by_source,
        }


evidence_ledger = EvidenceLedger()
