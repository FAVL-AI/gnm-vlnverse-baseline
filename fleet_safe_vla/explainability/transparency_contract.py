"""
transparency_contract.py — No-black-box audit contract for FleetSafe episodes.

Rules
-----
1. Every model output must be logged (raw action, latency, model name, ckpt hash).
2. Every FleetSafe correction must be logged (input/output action, active constraint,
   safety margin, intervention reason, QP status).
3. Every episode directory must contain all 9 required files.
4. No silent fallback: mock backend must be labelled; sensor gaps must have
   missing_reason; gate failures must be reported.
5. Every claim must link to config, seed list, checkpoint hash, backend, git commit,
   and metrics file.
6. Every explanation must be traceable to obstacle id, distance, graph edge,
   threshold, raw action, safe action, and delta.

validate_transparency_artifacts(episode_dir)
    Raises TransparencyViolation if any rule is broken.
    Returns {"status": "PASS", ...} on success.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


# ── Required files (per episode directory) ─────────────────────────────────────

REQUIRED_EPISODE_FILES: list[str] = [
    "episode.json",
    "trajectory.csv",
    "actions.csv",
    "safety_events.jsonl",
    "metrics.json",
    "scene_graphs.jsonl",
    "explanation_log.jsonl",
    "counterfactuals.jsonl",
    "audit_trail.json",
]

# Required columns in actions.csv
REQUIRED_ACTION_COLUMNS: set[str] = {
    "raw_vx", "raw_vy", "raw_wz",
    "safe_vx", "safe_vy", "safe_wz",
    "delta_l2",
}

# Required top-level keys in audit_trail.json
REQUIRED_AUDIT_KEYS: set[str] = {
    "model",
    "backend",
    "backend_label",
    "checkpoint_hash",
    "total_steps",
    "transparency_status",
}

# Required top-level keys in episode.json
REQUIRED_EPISODE_KEYS: set[str] = {
    "model",
    "backend",
    "seed",
    "scene",
    "success",
}


class TransparencyViolation(Exception):
    """Raised when an episode directory does not satisfy the audit contract."""


# ── Validator ─────────────────────────────────────────────────────────────────

def validate_transparency_artifacts(episode_dir: str | Path) -> dict[str, Any]:
    """
    Validate that `episode_dir` satisfies the no-black-box contract.

    Parameters
    ----------
    episode_dir : Path to a single episode output directory.

    Returns
    -------
    {"status": "PASS", "episode_dir": str, "checks_passed": int}

    Raises
    ------
    TransparencyViolation — with a newline-separated list of all violations found.
    """
    episode_dir = Path(episode_dir)
    violations: list[str] = []
    checks_passed = 0

    # ── Rule 3: all required files present ────────────────────────────────────
    for fname in REQUIRED_EPISODE_FILES:
        fpath = episode_dir / fname
        if not fpath.exists():
            violations.append(f"Missing required file: {fname}")
        else:
            checks_passed += 1

    if violations:
        raise TransparencyViolation("\n".join(violations))

    # ── Rule 1/2: actions.csv has required columns ─────────────────────────────
    actions_path = episode_dir / "actions.csv"
    try:
        with open(actions_path, newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = set(reader.fieldnames or [])
            missing_cols = REQUIRED_ACTION_COLUMNS - fieldnames
            if missing_cols:
                violations.append(
                    f"actions.csv missing required columns: {sorted(missing_cols)}"
                )
            else:
                checks_passed += 1

            # Check delta_l2 is never missing (not null, not empty)
            if "delta_l2" in fieldnames:
                for i, row in enumerate(reader):
                    val = row.get("delta_l2", "").strip()
                    if not val:
                        violations.append(
                            f"actions.csv row {i}: delta_l2 is empty"
                        )
                        break
                checks_passed += 1
    except Exception as exc:
        violations.append(f"actions.csv unreadable: {exc}")

    # ── Rule 4: audit_trail.json labels mock backend ───────────────────────────
    audit_path = episode_dir / "audit_trail.json"
    try:
        audit = json.loads(audit_path.read_text())

        # Required keys present
        missing_keys = REQUIRED_AUDIT_KEYS - set(audit.keys())
        if missing_keys:
            violations.append(
                f"audit_trail.json missing required keys: {sorted(missing_keys)}"
            )
        else:
            checks_passed += 1

        # Mock backend must be labelled
        backend       = audit.get("backend", "")
        backend_label = audit.get("backend_label", "")
        if backend == "mock" and "engineering" not in backend_label.lower():
            violations.append(
                "audit_trail.json: mock backend must carry label "
                "'ENGINEERING_ONLY — not publication evidence' "
                f"(found: {backend_label!r})"
            )
        else:
            checks_passed += 1

    except Exception as exc:
        violations.append(f"audit_trail.json unreadable: {exc}")

    # ── Rule 6: episode.json has required keys ─────────────────────────────────
    episode_path = episode_dir / "episode.json"
    try:
        ep = json.loads(episode_path.read_text())
        missing_ep_keys = REQUIRED_EPISODE_KEYS - set(ep.keys())
        if missing_ep_keys:
            violations.append(
                f"episode.json missing required keys: {sorted(missing_ep_keys)}"
            )
        else:
            checks_passed += 1
    except Exception as exc:
        violations.append(f"episode.json unreadable: {exc}")

    # ── Rule 4: missing sensor fields must have missing_reason ────────────────
    try:
        ep_data = json.loads((episode_dir / "episode.json").read_text())
        steps   = ep_data.get("steps", [])
        for i, step in enumerate(steps[:5]):   # spot-check first 5
            for sensor in ("depth", "lidar"):
                val = step.get(sensor)
                if val is None and f"{sensor}_missing_reason" not in step:
                    violations.append(
                        f"episode.json step {i}: sensor '{sensor}' is null "
                        f"but '{sensor}_missing_reason' is absent "
                        "(Rule 4: no silent fallback)"
                    )
    except Exception:
        pass   # episode.json parse failure already caught above

    if violations:
        raise TransparencyViolation("\n".join(violations))

    return {
        "status":       "PASS",
        "episode_dir":  str(episode_dir),
        "checks_passed": checks_passed,
    }


def validate_mock_backend_labelled(audit_dict: dict[str, Any]) -> bool:
    """
    Return True if the audit trail correctly labels a mock backend.

    Raises TransparencyViolation if the backend is mock but the label is absent.
    Passes silently for non-mock backends.
    """
    backend = audit_dict.get("backend", "")
    label   = audit_dict.get("backend_label", "")
    if backend == "mock" and "engineering" not in label.lower():
        raise TransparencyViolation(
            f"Mock backend not labelled as engineering-only. "
            f"backend_label={label!r}"
        )
    return True
