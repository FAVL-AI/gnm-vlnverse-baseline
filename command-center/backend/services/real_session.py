"""
Real-robot session recorder — v0.9.

Starts/stops a ros2 bag on the robot via SSH. Captures 14 topics covering
all evidence-worthy signals: RGB-D, odom, scan, commands, FleetSafe outputs.

On stop, writes a local session.json file and records a SHA256-verified entry
in the evidence ledger automatically. The bag stays on the robot at
~/recordings/<session_id>/; the metadata proof is stored locally.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .robot_ops import robot_ops, _audit
from .evidence_ledger import evidence_ledger, sha256_file
from ..config import settings

# 14-topic full evidence preset
TOPICS = [
    "/camera/color/image_raw",
    "/camera/depth/image_raw",
    "/camera/color/camera_info",
    "/odom_raw",
    "/scan0",
    "/battery",
    "/cmd_vel_raw",
    "/cmd_vel_safe",
    "/cmd_vel",
    "/fleetsafe/zone",
    "/fleetsafe/social_risk",
    "/fleetsafe/detections",
    "/fleetsafe/tracks",
    "/fleetsafe/latency",
]

RECORDINGS_DIR = settings.repo_root / "command-center" / "recordings"


def _write_session_meta(meta: dict) -> Path:
    """Write session metadata JSON locally and return its path."""
    session_dir = RECORDINGS_DIR / meta["session_id"]
    session_dir.mkdir(parents=True, exist_ok=True)
    path = session_dir / "session.json"
    path.write_text(json.dumps(meta, indent=2))
    return path


class RealSessionRecorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}

    async def start(self, robot_id: str) -> dict:
        session_id = f"real_{robot_id}_{int(time.time())}"
        bag_path = f"~/recordings/{session_id}"
        topics_str = " ".join(TOPICS)
        cmd = (
            f"mkdir -p ~/recordings && "
            f"nohup ros2 bag record -o {bag_path} {topics_str} "
            f"> /tmp/{session_id}.log 2>&1 & echo $!"
        )
        result = await robot_ops._run(
            f"ros_bag_start [{session_id}]", cmd, {"session_id": session_id},
        )
        meta: dict = {
            "session_id": session_id,
            "robot_id": robot_id,
            "bag_path": bag_path,
            "started_at": time.time(),
            "stopped_at": None,
            "duration_s": None,
            "topics": TOPICS,
            "n_topics": len(TOPICS),
            "evidence_id": None,
            "sha256": None,
            "ok": result["ok"],
        }
        with self._lock:
            self._sessions[session_id] = meta
        _audit("real_session_start", {"session_id": session_id, "n_topics": len(TOPICS)},
               "started", dry_run=robot_ops.dry_run)
        return meta

    async def stop(self, session_id: str) -> dict:
        with self._lock:
            meta = self._sessions.get(session_id)
        if not meta:
            return {"ok": False, "error": f"Unknown session: {session_id}"}

        cmd = f"pkill -SIGINT -f 'ros2 bag record.*{session_id}' || true"
        result = await robot_ops._run(
            f"ros_bag_stop [{session_id}]", cmd, {"session_id": session_id},
        )

        stopped_at = time.time()
        duration_s = stopped_at - meta["started_at"]

        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["stopped_at"] = stopped_at
                self._sessions[session_id]["duration_s"] = round(duration_s, 1)

        # Write local metadata proof and hash it
        updated_meta = {**meta, "stopped_at": stopped_at, "duration_s": round(duration_s, 1)}
        meta_path = _write_session_meta(updated_meta)
        sha = sha256_file(meta_path)

        # Auto-record evidence entry
        ledger_entry = evidence_ledger.record(
            claim_scope="real_robot_session",
            source="real_robot",
            ground_truth_type="sensor_derived",
            description=(
                f"ROS2 bag session {session_id}: "
                f"{len(TOPICS)} topics, {duration_s:.0f}s, "
                f"robot={meta['robot_id']}"
            ),
            artifact_path=meta_path,
            robot_id=meta["robot_id"],
            operator="operator",
            timestamp_start=meta["started_at"],
            timestamp_end=stopped_at,
            recording_rate_hz=None,
            metadata={
                "topics": TOPICS,
                "bag_path_on_robot": meta["bag_path"],
                "dry_run": robot_ops.dry_run,
                "n_topics": len(TOPICS),
            },
        )

        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["sha256"] = sha
                self._sessions[session_id]["evidence_id"] = ledger_entry["id"]

        _audit("real_session_stop",
               {"session_id": session_id, "duration_s": round(duration_s, 1)},
               "stopped", dry_run=robot_ops.dry_run)

        return {
            **updated_meta,
            "sha256": sha,
            "evidence_id": ledger_entry["id"],
            "stop_result": result["ok"],
        }

    def active_session_id(self) -> str | None:
        """Return the session_id of the first active (not stopped) session, or None."""
        with self._lock:
            for sid, meta in self._sessions.items():
                if meta.get("stopped_at") is None:
                    return sid
        return None

    def list_sessions(self) -> list[dict]:
        with self._lock:
            return list(self._sessions.values())

    def get_session(self, session_id: str) -> dict | None:
        with self._lock:
            return self._sessions.get(session_id)


real_session_recorder = RealSessionRecorder()
