"""ReplayExporter — package episode artifacts for dashboard replay."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class ReplayExporter:
    """Build a dashboard_replay.json from episode artifacts."""

    @staticmethod
    def from_log_dir(log_dir: str | Path) -> Dict[str, Any]:
        d = Path(log_dir)
        replay: Dict[str, Any] = {}

        config_path = d / "run_config.json"
        if config_path.exists():
            replay.update(json.loads(config_path.read_text(encoding="utf-8")))

        metrics_path = d / "metrics.json"
        if metrics_path.exists():
            replay["summary"] = json.loads(metrics_path.read_text(encoding="utf-8"))

        traj_path = d / "trajectory.csv"
        if traj_path.exists():
            import csv
            with traj_path.open(encoding="utf-8") as f:
                replay["trajectory"] = list(csv.DictReader(f))

        cert_path = d / "safety_certificates.jsonl"
        if cert_path.exists():
            certs = []
            for line in cert_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        certs.append(json.loads(line))
                    except Exception:
                        pass
            replay["certificates"] = certs

        return replay

    @staticmethod
    def save(replay: Dict[str, Any], path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(replay, indent=2), encoding="utf-8")
        print(f"[replay_export] Saved {p}")
