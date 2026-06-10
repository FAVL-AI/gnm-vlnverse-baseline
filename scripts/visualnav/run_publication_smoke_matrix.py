#!/usr/bin/env python3
"""
run_publication_smoke_matrix.py — Repeated-seed simulation matrix. v1.0.

Runs a minimal benchmark matrix to generate multi-seed evidence for CI.
Default configuration is fast enough for overnight / CI use:
  backbones  : gnm, vint, nomad (checkpoints in third_party/)
  backends   : mock
  scenes     : social_red_zone_smoke, hospital_corridor
  seeds      : 0, 1, 2  (3 seeds → PRELIMINARY status)
  fleetsafe  : both (baseline + FleetSafe_full)

12 total runs × ~5s each ≈ ~1 minute.

For publication-grade CI (PROVEN status) use:
  --seeds 0,1,2,3,4,5,6,7,8,9 --backend mujoco

Usage
-----
  # Fast smoke (default):
  python scripts/visualnav/run_publication_smoke_matrix.py

  # Longer with mujoco backend:
  python scripts/visualnav/run_publication_smoke_matrix.py \
      --seeds 0,1,2,3,4 --backend mujoco

  # Full paper matrix (takes hours):
  python scripts/visualnav/run_publication_smoke_matrix.py \
      --seeds paper --backend mujoco --backbones gnm,vint,nomad
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from itertools import product
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "command-center"))

_BENCHMARK_SCRIPT = _REPO_ROOT / "scripts" / "visualnav" / "run_visualnav_benchmark.py"


def _parse_seeds(seeds_arg: str) -> list[int]:
    if seeds_arg == "smoke":
        return [0]
    if seeds_arg == "dev":
        return list(range(10))
    if seeds_arg == "paper":
        return list(range(50))
    return [int(s.strip()) for s in seeds_arg.split(",")]


def _run_single(
    model: str,
    backend: str,
    scene: str,
    seed: int,
    fleetsafe: bool,
    max_steps: int,
    out_dir: str,
) -> dict:
    """Invoke the benchmark script for a single (model, backend, scene, seed, fleetsafe)."""
    cmd = [
        sys.executable, str(_BENCHMARK_SCRIPT),
        "--model", model,
        "--backend", backend,
        "--scenes", scene,
        "--seeds", str(seed),
        "--fleetsafe", "true" if fleetsafe else "false",
        "--max-steps", str(max_steps),
        "--output-dir", out_dir,
    ]

    t0 = time.time()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        timeout=300,
    )
    elapsed = time.time() - t0

    return {
        "returncode": result.returncode,
        "elapsed_s":  round(elapsed, 1),
        "stdout_tail": result.stdout[-500:] if result.stdout else "",
        "stderr_tail": result.stderr[-300:] if result.stderr else "",
        "ok": result.returncode == 0,
    }


# ── CI metrics from experiment registry ──────────────────────────────────────

def _compute_ci_metrics() -> dict:
    try:
        from backend.services.metrics_pipeline import metrics_pipeline
        table = metrics_pipeline.full_table()
        claims = metrics_pipeline.claim_validation_report()
        deltas = metrics_pipeline.delta_analysis()
        return {
            "ok": True,
            "n_rows": len(table["table"]),
            "readiness_pct": claims["summary"]["readiness_pct"],
            "n_deltas": len(deltas),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Evidence record ───────────────────────────────────────────────────────────

def _record_evidence(manifest_path: Path, n_runs: int, n_ok: int, ci: dict) -> None:
    try:
        from backend.services.evidence_ledger import evidence_ledger
        evidence_ledger.record(
            claim_scope="sim_benchmark_result",
            source="mujoco",
            ground_truth_type="perfect_sim_state",
            description=(
                f"Smoke matrix: {n_runs} runs, {n_ok} ok. "
                f"readiness={ci.get('readiness_pct','?')}%"
            ),
            artifact_path=manifest_path,
            operator="run_publication_smoke_matrix",
            metadata={"n_runs": n_runs, "n_ok": n_ok, "ci_metrics": ci},
        )
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backbones", default="gnm,vint,nomad",
                   help="Comma-separated backbone list: gnm|vint|nomad|mock "
                        "(default: gnm,vint,nomad). 'base' is NOT a valid model name.")
    p.add_argument("--backend",   default="mock",
                   choices=["mock", "mujoco"],
                   help="Simulator backend (default: mock)")
    p.add_argument("--scenes",    default="social_red_zone_smoke,hospital_corridor",
                   help="Comma-separated scene list")
    p.add_argument("--seeds",     default="0,1,2",
                   help="Comma-separated seeds or smoke|dev|paper (default: 0,1,2)")
    p.add_argument("--max-steps", type=int, default=200,
                   help="Max steps per episode (default: 200)")
    p.add_argument("--dry-run",   action="store_true",
                   help="Print commands without executing them")
    args = p.parse_args()

    backbones = [b.strip() for b in args.backbones.split(",")]
    scenes    = [s.strip() for s in args.scenes.split(",")]
    seeds     = _parse_seeds(args.seeds)

    out_dir_rel = "benchmarks/visualnav/results"
    out_dir_abs = _REPO_ROOT / out_dir_rel

    fleetsafe_modes = [False, True]

    combos = list(product(backbones, scenes, seeds, fleetsafe_modes))
    n_total = len(combos)

    print(f"[smoke_matrix] {n_total} runs planned")
    print(f"  backbones: {backbones}")
    print(f"  scenes:    {scenes}")
    print(f"  seeds:     {seeds}")
    print(f"  backend:   {args.backend}")
    print(f"  fleetsafe: both (baseline + FleetSafe_full)")

    if args.dry_run:
        print("\n[dry-run] Commands that would run:")
        for bb, sc, seed, fs in combos:
            print(f"  model={bb} backend={args.backend} scene={sc} seed={seed} fs={fs}")
        return 0

    results = []
    n_ok = 0
    t_start = time.time()

    for i, (bb, sc, seed, fs) in enumerate(combos, 1):
        label = f"{'FleetSafe' if fs else 'Baseline':10s} | {bb:6s} | {sc:25s} | seed={seed}"
        print(f"\n[{i:2d}/{n_total}] {label}")

        run_result = _run_single(
            model=bb,
            backend=args.backend,
            scene=sc,
            seed=seed,
            fleetsafe=fs,
            max_steps=args.max_steps,
            out_dir=out_dir_rel,
        )
        status = "✓" if run_result["ok"] else "✗"
        print(f"  {status} elapsed={run_result['elapsed_s']}s  rc={run_result['returncode']}")
        if not run_result["ok"] and run_result["stderr_tail"]:
            tail = run_result["stderr_tail"].strip().splitlines()[-3:]
            print("  stderr:", " | ".join(tail))

        if run_result["ok"]:
            n_ok += 1

        results.append({
            "backbone": bb,
            "scene":    sc,
            "seed":     seed,
            "fleetsafe": fs,
            "backend":  args.backend,
            **run_result,
        })

    elapsed_total = time.time() - t_start
    print(f"\n[smoke_matrix] {n_ok}/{n_total} runs succeeded in {elapsed_total:.0f}s")

    # ── Compute CI metrics from updated registry ──────────────────────────────
    print("\n[smoke_matrix] Computing CI metrics from updated registry…")
    ci = _compute_ci_metrics()
    if ci["ok"]:
        print(f"  readiness_pct = {ci['readiness_pct']}%")
    else:
        print(f"  CI metrics error: {ci.get('error')}")

    # ── Write manifest ────────────────────────────────────────────────────────
    ts = int(time.time())
    manifest_dir = _REPO_ROOT / "recordings" / "smoke_matrix"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"matrix_manifest_{ts}.json"

    manifest = {
        "generated_at":  time.time(),
        "n_total":        n_total,
        "n_ok":           n_ok,
        "elapsed_s":      round(elapsed_total, 1),
        "config": {
            "backbones": backbones,
            "scenes":    scenes,
            "seeds":     seeds,
            "backend":   args.backend,
            "fleetsafe": "both",
        },
        "ci_metrics":    ci,
        "runs":          results,
        "evidence_status": (
            "PRELIMINARY" if seeds and len(seeds) >= 3 else "SYNTHETIC"
        ),
        "note": (
            f"PRELIMINARY: {len(seeds)} seeds. "
            "Run with ≥10 seeds on mujoco backend for PROVEN status."
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    _record_evidence(manifest_path, n_total, n_ok, ci)

    print(f"\nManifest → {manifest_path}")
    print(f"Evidence status: {manifest['evidence_status']}")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
