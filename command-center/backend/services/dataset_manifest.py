"""
Dataset manifest builder.

Scans the repo for every category of evidence and produces an honest
dataset_manifest.json. Items that don't exist are flagged with
missing_warning — never silently omitted.

Categories and their ground_truth_type:
  synthetic_sim    → perfect_sim_state  (MuJoCo/IsaacLab state is exact GT)
  semantic_sim     → semantic_scene_spec (procedural hospital scenes)
  photoreal_sim    → semantic_scene_spec (Isaac photoreal assets)
  real_robot       → sensor_derived      (sensors, not verified vs GT)
  training_logs    → none               (artefacts of learning, not GT)
  model_outputs    → none               (inference-only)
  dashboard_audit  → none               (operator actions)
  video_evidence   → sensor_derived     (camera frames)
  manual_labels    → human_labeled      (only if manually annotated)
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from ..config import settings

MANIFEST_PATH = settings.repo_root / "command-center" / "recordings" / "dataset_manifest.json"
RESULTS_DIR   = settings.repo_root / "benchmarks" / "visualnav" / "results"
RECORDINGS_DIR = settings.repo_root / "command-center" / "recordings"

# Known recording rates (Hz) from hardware profiling
KNOWN_RATES: dict[str, float] = {
    "/scan0":                    7.0,
    "/odom_raw":                11.0,
    "/odom":                    11.0,
    "/camera/color/image_raw":  30.0,
    "/camera/depth/image_raw":  10.0,
    "/imu/data_raw":            "unstable",   # type: ignore[assignment]
    "/cmd_vel_raw":             "on_demand",  # type: ignore[assignment]
    "/cmd_vel_safe":            "on_demand",
    "/cmd_vel":                 "on_demand",
    "/battery_state":            1.0,
}


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(settings.repo_root), stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _count_runs(backend_filter: str | None = None, model_filter: str | None = None) -> list[dict]:
    if not RESULTS_DIR.exists():
        return []
    items = []
    for d in sorted(RESULTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        m = d / "aggregate_metrics.json"
        if not m.exists():
            continue
        try:
            data = json.loads(m.read_text())
        except Exception:
            continue
        if backend_filter and data.get("backend") != backend_filter:
            continue
        if model_filter and data.get("model") != model_filter:
            continue
        items.append({
            "run_id": d.name,
            "backend": data.get("backend"),
            "model": data.get("model"),
            "fleetsafe": data.get("fleetsafe"),
            "n_episodes": data.get("n_episodes"),
            "success_rate": data.get("success_rate"),
        })
    return items


def _real_robot_sessions() -> list[dict]:
    sessions = []
    if not RECORDINGS_DIR.exists():
        return sessions
    for d in RECORDINGS_DIR.iterdir():
        if d.is_dir() and (d / "session.json").exists():
            try:
                meta = json.loads((d / "session.json").read_text())
                sessions.append(meta)
            except Exception:
                pass
    # Also include bags
    for bag in RECORDINGS_DIR.glob("real_*"):
        if bag.is_dir() and not (bag / "session.json").exists():
            sessions.append({"session_id": bag.name, "type": "ros2_bag"})
    return sessions


def _video_evidence() -> list[dict]:
    videos = []
    for ext in ("*.mp4", "*.avi", "*.mkv"):
        for v in RECORDINGS_DIR.glob(ext):
            videos.append({"path": str(v), "size_bytes": v.stat().st_size})
    # GIFs in repo root count as video evidence
    for gif in settings.repo_root.glob("*.gif"):
        videos.append({"path": str(gif), "type": "gif_replay"})
    return videos


def _training_artifacts() -> list[dict]:
    items = []
    for pattern in ("**/*.pt", "**/*.ckpt", "**/*.pkl", "**/ppo*.log", "**/wandb/"):
        for p in settings.repo_root.glob(pattern):
            items.append({"path": str(p)})
    return items


def build_manifest() -> dict:
    mujoco_runs   = _count_runs(backend_filter="mujoco")
    mock_runs     = _count_runs(backend_filter="mock")
    isaac_runs    = _count_runs(backend_filter="isaaclab")
    real_sessions = _real_robot_sessions()
    videos        = _video_evidence()
    training      = _training_artifacts()

    manifest = {
        "generated_at": time.time(),
        "git_commit": _git_commit(),
        "host": __import__("socket").gethostname(),
        "known_recording_rates_hz": KNOWN_RATES,
        "categories": {

            "synthetic_sim": {
                "ground_truth_type": "perfect_sim_state",
                "description": "MuJoCo + mock-backend simulation runs with exact sim-state GT",
                "present": len(mujoco_runs) + len(mock_runs) > 0,
                "count": len(mujoco_runs) + len(mock_runs),
                "missing_warning": None if (mujoco_runs or mock_runs) else
                    "No MuJoCo/mock benchmark runs found in results/",
                "items": mujoco_runs + mock_runs,
            },

            "semantic_sim": {
                "ground_truth_type": "semantic_scene_spec",
                "description": "Procedural hospital scenes — roles/zones from scene spec",
                "present": len(isaac_runs) > 0,
                "count": len(isaac_runs),
                "missing_warning": None if isaac_runs else
                    "No IsaacLab runs found in results/",
                "items": isaac_runs,
            },

            "photoreal_sim": {
                "ground_truth_type": "semantic_scene_spec",
                "description": "IsaacLab photoreal hospital asset renders",
                "present": False,
                "count": 0,
                "missing_warning":
                    "Photoreal Isaac hospital assets not yet captured — "
                    "requires Isaac scene loaded and viewport screenshot pipeline",
                "items": [],
            },

            "real_robot": {
                "ground_truth_type": "sensor_derived",
                "description": "Yahboom M3Pro sessions: ROS2 bags, cmd_vel paths, odom",
                "present": len(real_sessions) > 0,
                "count": len(real_sessions),
                "missing_warning": None if real_sessions else
                    "No real robot ROS2 bag sessions recorded yet — "
                    "run /dashboard/robot-control → Session Start to capture",
                "items": real_sessions,
            },

            "training_logs": {
                "ground_truth_type": "none",
                "description": "PPO / RL training checkpoints and reward curves",
                "present": len(training) > 0,
                "count": len(training),
                "missing_warning": None if training else
                    "No PPO training checkpoints found — PPO adapter exists but "
                    "full training run not yet completed",
                "items": training,
            },

            "model_outputs": {
                "ground_truth_type": "none",
                "description": "Inference artifacts: detections, trajectories, risk scores",
                "present": len(mujoco_runs) + len(isaac_runs) > 0,
                "count": len(mujoco_runs) + len(isaac_runs),
                "missing_warning": None,
                "items": [],
            },

            "dashboard_audit": {
                "ground_truth_type": "none",
                "description": "Command Center operator audit log",
                "present": (RECORDINGS_DIR / "audit.jsonl").exists(),
                "count": _audit_count(),
                "missing_warning": None if (RECORDINGS_DIR / "audit.jsonl").exists() else
                    "No audit log yet — start Command Center",
                "items": [],
            },

            "video_evidence": {
                "ground_truth_type": "sensor_derived",
                "description": "RGB video recordings and GIF replays",
                "present": len(videos) > 0,
                "count": len(videos),
                "missing_warning": None if videos else
                    "No video recordings — MP4 sessions not yet captured",
                "items": videos,
            },

            "manual_labels": {
                "ground_truth_type": "human_labeled",
                "description": "Human-verified ground truth for real-world semantic roles",
                "present": False,
                "count": 0,
                "missing_warning":
                    "No manually labeled real-world data — human annotation not yet collected. "
                    "Sim semantic roles are spec-derived, not human-verified for real scenes.",
                "items": [],
            },
        },
    }

    # Summary stats
    total = sum(c["count"] for c in manifest["categories"].values())
    missing = [k for k, v in manifest["categories"].items() if not v["present"]]
    manifest["summary"] = {
        "total_items": total,
        "categories_present": sum(1 for v in manifest["categories"].values() if v["present"]),
        "categories_missing": missing,
        "defensibility_score": f"{sum(1 for v in manifest['categories'].values() if v['present'])}/{len(manifest['categories'])}",
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    return manifest


def _audit_count() -> int:
    p = RECORDINGS_DIR / "audit.jsonl"
    if not p.exists():
        return 0
    return sum(1 for _ in p.open())


def load_manifest() -> dict | None:
    if not MANIFEST_PATH.exists():
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except Exception:
        return None
