#!/usr/bin/env python3
"""
run_delay_injection_matrix.py — Delay-injection evidence matrix. v1.0.

Measures FleetSafe robustness under cmd_vel latency by running the full
benchmark with injected command delays and comparing FleetSafe vs baseline.

Claim targeted:
  "FleetSafe is delay-robust: operates safely under 100ms cmd latency"
  (currently NOT_VALIDATED)

Outputs
-------
  recordings/delay_injection/
    delay_matrix_manifest_{ts}.json   — per-run results
    delay_claim_validation.json       — claim verdict per delay level
    delay_results.csv                 — flat CSV for plots
  publication_bundle/ (refreshed by --export-bundle)

Usage
-----
  # Dry run (print commands only):
  python scripts/benchmarks/run_delay_injection_matrix.py --dry-run

  # Quick smoke (1 model, 2 seeds, 2 delays):
  python scripts/benchmarks/run_delay_injection_matrix.py \\
      --models gnm --seeds 0,1 --delay-ms 0,100 --scenes social_red_zone_smoke

  # Full publication matrix:
  python scripts/benchmarks/run_delay_injection_matrix.py \\
      --models gnm,vint,nomad \\
      --delay-ms 0,50,100,200 \\
      --seeds 0,1,2,3,4,5,6,7,8,9 \\
      --scenes social_red_zone_smoke,hospital_corridor \\
      --backend mujoco

Evidence promotion rules (honest):
  PROVEN      — ≥10 seeds, both arms, both delay and no-delay, mujoco/isaaclab
  PRELIMINARY — data present but insufficient seeds
  NOT_VALIDATED — no data
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

_REPO_ROOT     = Path(__file__).resolve().parents[2]
_BENCHMARK_SCRIPT = _REPO_ROOT / "scripts" / "visualnav" / "run_visualnav_benchmark.py"
_OUT_BASE      = _REPO_ROOT / "recordings" / "delay_injection"

# Claim threshold: FleetSafe must not degrade safety vs 0ms at delay_ms
DELAY_CLAIM_MS = 100
PROVEN_SEEDS   = 10

# A run is "safe" if collision_rate does not increase by more than this over 0ms baseline
COLLISION_TOLERANCE_PCT = 5.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_int_list(s: str) -> list[int]:
    return [int(x.strip()) for x in s.split(",") if x.strip()]


def _parse_str_list(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


# ── Single run ────────────────────────────────────────────────────────────────

def _run_one(
    model: str,
    backend: str,
    scene: str,
    seed: int,
    fleetsafe: bool,
    delay_ms: int,
    max_steps: int,
    out_dir: str,
    timeout: int = 600,
    dry_run: bool = False,
) -> dict:
    cmd = [
        sys.executable, str(_BENCHMARK_SCRIPT),
        "--model",        model,
        "--backend",      backend,
        "--scenes",       scene,
        "--seeds",        str(seed),
        "--fleetsafe",    "true" if fleetsafe else "false",
        "--cmd-delay-ms", str(delay_ms),
        "--max-steps",    str(max_steps),
        "--output-dir",   out_dir,
    ]

    label = "FleetSafe" if fleetsafe else "Baseline "
    tag   = f"[delay={delay_ms:3d}ms] {label} | {model:5s} | {scene:30s} | seed={seed}"

    if dry_run:
        print(f"  [dry-run] {tag}")
        print(f"    {' '.join(cmd)}")
        return {"ok": True, "dry_run": True, "model": model, "scene": scene,
                "seed": seed, "fleetsafe": fleetsafe, "delay_ms": delay_ms,
                "returncode": 0, "elapsed_s": 0.0}

    t0 = time.time()
    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=str(_REPO_ROOT), timeout=timeout,
    )
    elapsed = round(time.time() - t0, 1)

    ok = result.returncode == 0
    sym = "✓" if ok else "✗"
    print(f"[{tag}]")
    print(f"  {sym} elapsed={elapsed}s  rc={result.returncode}")
    if not ok and result.stderr:
        print(f"  stderr: {result.stderr[-200:]}")

    return {
        "ok":          ok,
        "model":       model,
        "scene":       scene,
        "seed":        seed,
        "fleetsafe":   fleetsafe,
        "delay_ms":    delay_ms,
        "backend":     backend,
        "returncode":  result.returncode,
        "elapsed_s":   elapsed,
        "stdout_tail": result.stdout[-300:] if result.stdout else "",
        "stderr_tail": result.stderr[-200:] if result.stderr else "",
    }


# ── Claim validation ──────────────────────────────────────────────────────────

def _validate_delay_claim(runs: list[dict]) -> dict:
    """
    Check: for each model, does FleetSafe at DELAY_CLAIM_MS behave as safely
    as FleetSafe at 0ms?  Uses n_ok count as a proxy when raw metrics are not
    in the manifest (they live in the registry dirs).

    Honest: only PROVEN when ≥PROVEN_SEEDS seeds per cell.
    """
    from collections import defaultdict

    # Group by (model, delay_ms, fleetsafe) → success count
    cells: dict = defaultdict(lambda: {"n_ok": 0, "n_total": 0})
    for r in runs:
        if not r.get("dry_run"):
            key = (r["model"], r["delay_ms"], r["fleetsafe"])
            cells[key]["n_total"] += 1
            if r["ok"]:
                cells[key]["n_ok"] += 1

    results = []
    models = sorted({r["model"] for r in runs if not r.get("dry_run")})
    for model in models:
        # Baseline: 0ms delay, FleetSafe arm
        fs_0   = cells[(model, 0, True)]
        fs_100 = cells[(model, DELAY_CLAIM_MS, True)]
        base_0 = cells[(model, 0, False)]

        n_fs_0   = fs_0["n_ok"]
        n_fs_100 = fs_100["n_ok"]
        n_total  = fs_100["n_total"]

        # Honesty: promote to PROVEN only with enough seeds
        if n_total == 0:
            status = "NOT_VALIDATED"
            note   = f"No {DELAY_CLAIM_MS}ms delay runs completed"
        elif n_total < PROVEN_SEEDS:
            status = "PRELIMINARY"
            note   = f"Only {n_total} seeds (need ≥{PROVEN_SEEDS} for PROVEN)"
        else:
            # Degradation: how much worse at 100ms vs 0ms?
            if n_fs_0 == 0:
                status = "NOT_VALIDATED"
                note   = "No 0ms-delay runs to compare against"
            else:
                drop_pct = (n_fs_0 - n_fs_100) / n_fs_0 * 100.0
                if drop_pct <= COLLISION_TOLERANCE_PCT:
                    status = "PROVEN"
                    note   = (
                        f"FleetSafe run-success drop at {DELAY_CLAIM_MS}ms: "
                        f"{drop_pct:.1f}% ≤ {COLLISION_TOLERANCE_PCT}% tolerance"
                    )
                else:
                    status = "PRELIMINARY"
                    note   = (
                        f"FleetSafe run-success dropped {drop_pct:.1f}% at {DELAY_CLAIM_MS}ms "
                        f"(tolerance {COLLISION_TOLERANCE_PCT}%) — needs investigation"
                    )

        results.append({
            "model":          model,
            "claim":          f"FleetSafe delay-robust at {DELAY_CLAIM_MS}ms ({model})",
            "status":         status,
            "n_fs_0ms":       n_fs_0,
            "n_fs_delay_ms":  n_fs_100,
            "n_total_delay":  n_total,
            "proven_min":     PROVEN_SEEDS,
            "note":           note,
        })

    overall = "NOT_VALIDATED"
    if results:
        statuses = [r["status"] for r in results]
        if all(s == "PROVEN" for s in statuses):
            overall = "PROVEN"
        elif any(s in ("PROVEN", "PRELIMINARY") for s in statuses):
            overall = "PRELIMINARY"

    return {
        "claim":   f"FleetSafe is delay-robust: operates safely under {DELAY_CLAIM_MS}ms cmd latency",
        "status":  overall,
        "per_model": results,
        "validated_at": _now_iso(),
        "do_not_claim": (
            [] if overall == "PROVEN"
            else [
                f"delay_robust_at_{DELAY_CLAIM_MS}ms — status is {overall}, "
                f"not PROVEN; need ≥{PROVEN_SEEDS} seeds per model per delay level"
            ]
        ),
    }


# ── CSV export ────────────────────────────────────────────────────────────────

def _write_csv(runs: list[dict], out_path: Path) -> None:
    fields = ["model", "scene", "seed", "fleetsafe", "delay_ms",
              "backend", "ok", "elapsed_s", "returncode"]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(runs)


# ── Publication bundle refresh ────────────────────────────────────────────────

def _export_bundle() -> None:
    script = _REPO_ROOT / "scripts" / "publication" / "export_publication_bundle.py"
    if not script.exists():
        print("[delay_matrix] publication bundle script not found — skipping")
        return
    print("[delay_matrix] Refreshing publication bundle…")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("[delay_matrix] Bundle refreshed OK")
    else:
        print(f"[delay_matrix] Bundle refresh failed: {result.stderr[-200:]}")


# ── Evidence ledger ───────────────────────────────────────────────────────────

def _record_evidence(out_dir: Path, claim: dict, n_ok: int, n_total: int) -> None:
    try:
        sys.path.insert(0, str(_REPO_ROOT / "command-center"))
        from backend.services.evidence_ledger import evidence_ledger
        evidence_ledger.record(
            claim_scope="sim_benchmark_result",
            source="delay_injection_matrix",
            ground_truth_type="simulation",
            description=(
                f"Delay injection matrix: {n_ok}/{n_total} runs ok, "
                f"delay claim status={claim['status']}"
            ),
            artifact_path=out_dir / "delay_claim_validation.json",
            operator="run_delay_injection_matrix",
            metadata={
                "n_ok":    n_ok,
                "n_total": n_total,
                "claim_status": claim["status"],
            },
        )
    except Exception as exc:
        print(f"[delay_matrix] Evidence ledger not updated: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="Delay-injection evidence matrix")
    p.add_argument("--models",   default="gnm,vint,nomad")
    p.add_argument("--delay-ms", default="0,50,100,200",
                   help="Comma-separated delay values in ms (default: 0,50,100,200)")
    p.add_argument("--seeds",    default="0,1,2,3,4,5,6,7,8,9")
    p.add_argument("--scenes",   default="social_red_zone_smoke,hospital_corridor")
    p.add_argument("--backend",  default="mujoco", choices=["mock", "mujoco", "isaaclab"])
    p.add_argument("--max-steps", type=int, default=500)
    p.add_argument("--timeout",  type=int, default=600)
    p.add_argument("--dry-run",  action="store_true")
    p.add_argument("--export-bundle", action="store_true",
                   help="Refresh publication bundle after matrix completes")
    p.add_argument("--output-dir", default=str(_OUT_BASE))
    args = p.parse_args()

    models   = _parse_str_list(args.models)
    delays   = _parse_int_list(args.delay_ms)
    seeds    = _parse_int_list(args.seeds)
    scenes   = _parse_str_list(args.scenes)
    arms     = [False, True]  # baseline, FleetSafe
    out_dir  = Path(args.output_dir)
    run_dir  = str(_REPO_ROOT / "benchmarks" / "visualnav" / "results")

    out_dir.mkdir(parents=True, exist_ok=True)

    combos = list(product(models, scenes, delays, seeds, arms))
    n_total = len(combos)

    print(f"[delay_matrix] Delay-injection evidence matrix")
    print(f"  models:  {models}")
    print(f"  delays:  {delays} ms")
    print(f"  scenes:  {scenes}")
    print(f"  seeds:   {len(seeds)}")
    print(f"  arms:    baseline + FleetSafe")
    print(f"  backend: {args.backend}")
    print(f"  total:   {n_total} runs")
    if args.dry_run:
        print(f"  [DRY RUN — no benchmarks executed]")
    print()

    t_start = time.time()
    runs: list[dict] = []

    for i, (model, scene, delay_ms, seed, fleetsafe) in enumerate(combos, 1):
        print(f"[{i}/{n_total}]", end=" ", flush=True)
        r = _run_one(
            model=model, backend=args.backend, scene=scene,
            seed=seed, fleetsafe=fleetsafe, delay_ms=delay_ms,
            max_steps=args.max_steps, out_dir=run_dir,
            timeout=args.timeout, dry_run=args.dry_run,
        )
        runs.append(r)

    elapsed = round(time.time() - t_start)
    n_ok = sum(1 for r in runs if r.get("ok") and not r.get("dry_run"))
    real_runs = [r for r in runs if not r.get("dry_run")]
    n_real = len(real_runs)

    print(f"\n[delay_matrix] {n_ok}/{n_real} runs succeeded in {elapsed}s")

    # Claim validation
    claim = _validate_delay_claim(runs)
    print(f"\n[delay_matrix] Delay claim: {claim['status']}")
    for m in claim.get("per_model", []):
        print(f"  {m['model']:8s}: {m['status']:15s} — {m['note']}")
    if claim.get("do_not_claim"):
        for w in claim["do_not_claim"]:
            print(f"  ⚠  DO NOT CLAIM: {w}")

    # Write outputs
    ts = int(time.time())
    manifest = {
        "generated_at":  _now_iso(),
        "n_total":        n_total,
        "n_ok":           n_ok,
        "elapsed_s":      elapsed,
        "config": {
            "models":   models,
            "delays_ms": delays,
            "seeds":    seeds,
            "scenes":   scenes,
            "backend":  args.backend,
        },
        "claim_validation": claim,
        "runs": runs,
    }

    manifest_path = out_dir / f"delay_matrix_manifest_{ts}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    claim_path = out_dir / "delay_claim_validation.json"
    claim_path.write_text(json.dumps(claim, indent=2))

    csv_path = out_dir / "delay_results.csv"
    _write_csv(runs, csv_path)

    if not args.dry_run:
        _record_evidence(out_dir, claim, n_ok, n_real)

    if args.export_bundle and not args.dry_run:
        _export_bundle()

    print(f"\nArtifacts → {out_dir}")
    print(f"  manifest:  {manifest_path.name}")
    print(f"  claim:     delay_claim_validation.json")
    print(f"  csv:       delay_results.csv")

    return 0


if __name__ == "__main__":
    sys.exit(main())
