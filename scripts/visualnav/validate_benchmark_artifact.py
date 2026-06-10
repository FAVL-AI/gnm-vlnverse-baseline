#!/usr/bin/env python3
"""
scripts/visualnav/validate_benchmark_artifact.py

Validate a generated benchmark result directory against the governance contract.

Usage:
    python scripts/visualnav/validate_benchmark_artifact.py <run_dir>

Returns exit code 0 on PASS, 1 on FAIL.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# Injected via sys.path if run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── Required artifact structure ────────────────────────────────────────────────

REQUIRED_RUN_FILES = [
    "metadata.yaml",
    "aggregate_metrics.json",
    "aggregate_metrics.csv",
    "aggregate_by_scene.json",
]

REQUIRED_EPISODE_FILES = [
    "episode.json",
    "trajectory.csv",
    "actions.csv",
    "safety_events.jsonl",
    "metrics.json",
    "intervention_evidence.jsonl",
]

REQUIRED_METADATA_KEYS = {
    "run_id", "model", "backend",
    "benchmark_version", "protocol_version",
    "sceneset_version", "metricset_version",
    "git_commit",
}

REQUIRED_AGGREGATE_KEYS = {
    "run_id", "model", "backend",
    "benchmark_version", "protocol_version",
    "git_commit",
}


class ArtifactViolation(Exception):
    """Raised when a benchmark artifact fails governance checks."""


def _parse_metadata_yaml(path: Path) -> dict:
    """Parse the simple key: value metadata.yaml (no PyYAML required)."""
    result: dict = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def validate_run_directory(run_dir: Path) -> dict:
    """
    Validate a benchmark run directory.

    Parameters
    ----------
    run_dir : Path
        Root of a single benchmark run (contains metadata.yaml, episodes/, etc.)

    Returns
    -------
    dict with {"status": "PASS", "checks_passed": N, "run_dir": str}

    Raises
    ------
    ArtifactViolation if any check fails.
    """
    violations: list[str] = []
    checks_passed = 0

    run_dir = Path(run_dir)

    # ── Run-level files ────────────────────────────────────────────────────────
    for fname in REQUIRED_RUN_FILES:
        p = run_dir / fname
        if not p.exists():
            violations.append(f"Missing required run file: {fname}")
        else:
            checks_passed += 1

    if violations:
        raise ArtifactViolation("\n".join(violations))

    # ── metadata.yaml content ─────────────────────────────────────────────────
    meta = _parse_metadata_yaml(run_dir / "metadata.yaml")
    missing_meta_keys = REQUIRED_METADATA_KEYS - set(meta.keys())
    if missing_meta_keys:
        violations.append(
            f"metadata.yaml missing required keys: {sorted(missing_meta_keys)}"
        )
    else:
        checks_passed += 1

    # ── Backend labelling ──────────────────────────────────────────────────────
    backend = meta.get("backend", "")
    if backend == "mock":
        claim_scope = meta.get("claim_scope", "")
        if "engineering_only" not in claim_scope.lower():
            violations.append(
                "Mock backend run: metadata.yaml claim_scope must contain "
                "'engineering_only'. "
                f"Found: {claim_scope!r}"
            )
        else:
            checks_passed += 1

        # Ensure no publication claim allowed for mock
        if "publication" in claim_scope.lower() and "not_publication" not in claim_scope.lower():
            violations.append(
                "Mock backend run must not set claim_scope to allow publication."
            )
    else:
        checks_passed += 1

    # ── aggregate_metrics.json content ────────────────────────────────────────
    try:
        agg = json.loads((run_dir / "aggregate_metrics.json").read_text())
        missing_agg = REQUIRED_AGGREGATE_KEYS - set(agg.keys())
        if missing_agg:
            violations.append(
                f"aggregate_metrics.json missing keys: {sorted(missing_agg)}"
            )
        else:
            checks_passed += 1
    except (json.JSONDecodeError, OSError) as e:
        violations.append(f"aggregate_metrics.json unreadable: {e}")

    # ── Episodes ──────────────────────────────────────────────────────────────
    ep_root = run_dir / "episodes"
    if not ep_root.exists():
        violations.append("Missing episodes/ directory")
    else:
        checks_passed += 1
        ep_dirs = sorted(ep_root.iterdir()) if ep_root.exists() else []
        for ep_dir in ep_dirs:
            if not ep_dir.is_dir():
                continue
            ep_violations = _validate_episode_directory(ep_dir, backend)
            violations.extend(ep_violations)
            if not ep_violations:
                checks_passed += 1

    if violations:
        raise ArtifactViolation("\n".join(violations))

    return {
        "status": "PASS",
        "checks_passed": checks_passed,
        "run_dir": str(run_dir),
        "backend": backend,
        "episodes_validated": len([d for d in (run_dir / "episodes").iterdir() if d.is_dir()])
        if (run_dir / "episodes").exists() else 0,
    }


def _validate_episode_directory(ep_dir: Path, backend: str) -> list[str]:
    """Return list of violation strings for one episode directory."""
    violations: list[str] = []

    for fname in REQUIRED_EPISODE_FILES:
        if not (ep_dir / fname).exists():
            violations.append(f"{ep_dir.name}: missing {fname}")

    # Check actions.csv has required columns
    actions_csv = ep_dir / "actions.csv"
    if actions_csv.exists():
        try:
            with actions_csv.open() as f:
                reader = csv.DictReader(f)
                cols = set(reader.fieldnames or [])
            required_cols = {"raw_vx", "raw_vy", "raw_wz", "safe_vx", "safe_vy", "safe_wz", "delta_l2"}
            missing_cols = required_cols - cols
            if missing_cols:
                violations.append(
                    f"{ep_dir.name}/actions.csv missing columns: {sorted(missing_cols)}"
                )
        except OSError as e:
            violations.append(f"{ep_dir.name}/actions.csv unreadable: {e}")

    # Check episode.json has required keys
    ep_json = ep_dir / "episode.json"
    if ep_json.exists():
        try:
            ep = json.loads(ep_json.read_text())
            required_ep_keys = {"model", "backend", "seed", "scene", "success"}
            missing_ep_keys = required_ep_keys - set(ep.keys())
            if missing_ep_keys:
                violations.append(
                    f"{ep_dir.name}/episode.json missing keys: {sorted(missing_ep_keys)}"
                )
            # Mock backend: check no publication claim
            if backend == "mock":
                claim_scope = ep.get("claim_scope", "")
                if claim_scope and "engineering_only" not in claim_scope.lower():
                    violations.append(
                        f"{ep_dir.name}/episode.json: mock backend claim_scope must "
                        f"contain 'engineering_only'. Found: {claim_scope!r}"
                    )
        except (json.JSONDecodeError, OSError) as e:
            violations.append(f"{ep_dir.name}/episode.json unreadable: {e}")

    # intervention_evidence.jsonl: if intervention_count > 0, evidence events must be present
    ev_path = ep_dir / "intervention_evidence.jsonl"
    metrics_path = ep_dir / "metrics.json"
    if ev_path.exists() and metrics_path.exists():
        try:
            metrics_data = json.loads(metrics_path.read_text())
            intervention_count = int(metrics_data.get("intervention_count", 0))
            ev_lines = [
                ln for ln in ev_path.read_text().splitlines()
                if ln.strip()
            ]
            ev_intervention_count = sum(
                1 for ln in ev_lines
                if json.loads(ln).get("intervention_applied", False)
            )
            if intervention_count > 0 and ev_intervention_count == 0:
                violations.append(
                    f"{ep_dir.name}: intervention_count={intervention_count} but "
                    f"intervention_evidence.jsonl contains 0 intervention events"
                )
        except (json.JSONDecodeError, OSError, ValueError) as e:
            violations.append(
                f"{ep_dir.name}: could not validate intervention_evidence.jsonl: {e}"
            )

    return violations


# ── CLI ────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Validate a FleetSafe benchmark run artifact."
    )
    parser.add_argument("run_dir", help="Path to the benchmark run directory.")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        print(f"ERROR: run_dir does not exist: {run_dir}", file=sys.stderr)
        return 1

    try:
        result = validate_run_directory(run_dir)
        print(f"PASS  checks={result['checks_passed']}  "
              f"episodes={result['episodes_validated']}  "
              f"backend={result['backend']}")
        return 0
    except ArtifactViolation as exc:
        print(f"FAIL\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
