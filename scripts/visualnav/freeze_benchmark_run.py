#!/usr/bin/env python3
"""
scripts/visualnav/freeze_benchmark_run.py

Validate and freeze a benchmark run artifact into benchmarks/frozen/v{version}/{run_id}/.

Usage:
    python scripts/visualnav/freeze_benchmark_run.py --run-dir <path> [--force]

The freeze process:
1. Validates the artifact via validate_benchmark_artifact.
2. Computes SHA256 hashes for all files.
3. Writes MANIFEST.json, SHA256SUMS, GIT_STATE.txt, ENVIRONMENT.txt.
4. Copies everything into benchmarks/frozen/v{version}/{run_id}/.
5. Refuses to overwrite an existing frozen run unless --force is passed.

Exit code 0 on success, 1 on failure.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.visualnav.validate_benchmark_artifact import (
    ArtifactViolation,
    _parse_metadata_yaml,
    validate_run_directory,
)
from fleet_safe_vla.benchmark_version import BENCHMARK_VERSION


# ── SHA256 helpers ─────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files(root: Path) -> list[Path]:
    """Return all regular files under root, sorted."""
    return sorted(p for p in root.rglob("*") if p.is_file())


# ── Git / environment helpers ──────────────────────────────────────────────────

def _run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
        return r.stdout.strip()
    except Exception as e:
        return f"(unavailable: {e})"


def git_state(repo_root: Path) -> str:
    log   = _run(["git", "log", "--oneline", "-5"], cwd=repo_root)
    status = _run(["git", "status"], cwd=repo_root)
    diff   = _run(["git", "diff", "--stat"], cwd=repo_root)
    return f"=== git log -5 ===\n{log}\n\n=== git status ===\n{status}\n\n=== git diff --stat ===\n{diff}\n"


def environment_snapshot() -> str:
    py_ver   = f"python {sys.version}"
    pip_list = _run([sys.executable, "-m", "pip", "list", "--format=columns"])
    platform = _run(["uname", "-a"])
    return f"=== python ===\n{py_ver}\n\n=== platform ===\n{platform}\n\n=== pip list ===\n{pip_list}\n"


# ── Freeze ─────────────────────────────────────────────────────────────────────

def freeze_run(run_dir: Path, frozen_base: Path, force: bool = False) -> Path:
    """
    Validate and freeze a benchmark run.

    Returns the path of the frozen artifact directory.
    """
    run_dir = run_dir.resolve()
    repo_root = Path(__file__).resolve().parents[2]

    # 1. Validate
    print(f"[freeze] Validating {run_dir} ...")
    try:
        val_result = validate_run_directory(run_dir)
    except ArtifactViolation as exc:
        print(f"[freeze] FAIL — artifact validation failed:\n{exc}", file=sys.stderr)
        sys.exit(1)
    print(f"[freeze] Validation PASS ({val_result['checks_passed']} checks)")

    # 2. Determine frozen path
    meta      = _parse_metadata_yaml(run_dir / "metadata.yaml")
    bv        = meta.get("benchmark_version", BENCHMARK_VERSION)
    run_id    = meta.get("run_id", run_dir.name)
    frozen_dir = frozen_base / f"v{bv}" / run_id

    if frozen_dir.exists():
        if force:
            print(f"[freeze] --force: overwriting existing frozen run at {frozen_dir}")
            shutil.rmtree(frozen_dir)
        else:
            print(
                f"[freeze] FAIL — frozen run already exists at {frozen_dir}\n"
                f"         Pass --force to overwrite.",
                file=sys.stderr,
            )
            sys.exit(1)

    frozen_dir.mkdir(parents=True, exist_ok=True)

    # 3. Copy all run files
    print(f"[freeze] Copying files to {frozen_dir} ...")
    shutil.copytree(str(run_dir), str(frozen_dir), dirs_exist_ok=True)

    # 4. Compute SHA256SUMS
    all_files = collect_files(frozen_dir)
    file_entries = []
    sha256_lines = []
    for fpath in all_files:
        digest = sha256_file(fpath)
        rel    = fpath.relative_to(frozen_dir)
        file_entries.append({
            "path":       str(rel),
            "sha256":     digest,
            "size_bytes": fpath.stat().st_size,
        })
        sha256_lines.append(f"{digest}  {rel}")

    # Write SHA256SUMS
    (frozen_dir / "SHA256SUMS").write_text("\n".join(sha256_lines) + "\n")
    print(f"[freeze] SHA256SUMS written ({len(sha256_lines)} files)")

    # 5. Write MANIFEST.json
    manifest = {
        "run_id":            run_id,
        "frozen_at":         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "benchmark_version": bv,
        "protocol_version":  meta.get("protocol_version", "unknown"),
        "backend":           meta.get("backend", "unknown"),
        "model":             meta.get("model", "unknown"),
        "git_commit":        meta.get("git_commit", "unknown"),
        "total_files":       len(file_entries),
        "files":             file_entries,
    }
    (frozen_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    print("[freeze] MANIFEST.json written")

    # 6. Write GIT_STATE.txt
    (frozen_dir / "GIT_STATE.txt").write_text(git_state(repo_root))
    print("[freeze] GIT_STATE.txt written")

    # 7. Write ENVIRONMENT.txt
    (frozen_dir / "ENVIRONMENT.txt").write_text(environment_snapshot())
    print("[freeze] ENVIRONMENT.txt written")

    print(f"\n[freeze] Frozen artifact → {frozen_dir}")
    return frozen_dir


# ── CLI ────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    import argparse
    repo_root   = Path(__file__).resolve().parents[2]
    frozen_base = repo_root / "benchmarks" / "frozen"

    parser = argparse.ArgumentParser(
        description="Validate and freeze a FleetSafe benchmark run artifact."
    )
    parser.add_argument(
        "--run-dir", required=True,
        help="Path to the benchmark run directory to freeze."
    )
    parser.add_argument(
        "--frozen-base", default=str(frozen_base),
        help=f"Root for frozen artifacts (default: {frozen_base})"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing frozen run if it exists."
    )
    args = parser.parse_args(argv)

    run_dir    = Path(args.run_dir)
    frozen_base_path = Path(args.frozen_base)

    if not run_dir.exists():
        print(f"ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        return 1

    frozen_dir = freeze_run(run_dir, frozen_base_path, force=args.force)
    print(f"\nFrozen artifact path: {frozen_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
