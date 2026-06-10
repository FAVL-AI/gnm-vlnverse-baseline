"""
verify_proven_gate.py — Standalone PROVEN gate verifier for publication runs.

Usage:
  python scripts/publication/verify_proven_gate.py
  python scripts/publication/verify_proven_gate.py --backend mujoco
  python scripts/publication/verify_proven_gate.py --backend isaaclab --verbose

Exits 0 if all checked backends are PROVEN, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "command-center"))

from backend.services.publication_run_scanner import (
    scan_publication_runs,
    latest_run_by_backend,
    cross_backend_comparison,
)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m~\033[0m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _check_backend(backend: str, verbose: bool) -> bool:
    run = latest_run_by_backend(backend)
    label = "MuJoCo" if backend == "mujoco" else "Isaac Sim"
    print(f"\n{BOLD}[{label} — {backend}]{RESET}")

    if not run:
        print(f"  {FAIL} No run found for backend '{backend}'")
        return False

    print(f"  Run ID:   {run['run_id']}")
    print(f"  Seeds:    {run['n_seeds']}")
    print(f"  Models:   {run['models']}")
    print(f"  Combos:   {run['n_results']}/{run['expected_combos']} ({run['progress_pct']:.1f}%)")
    print(f"  Complete: {run['complete']}")

    gates_passed = True
    detail = run.get("proven_detail", {})

    # Gate 1: Seeds
    ok = run["n_seeds"] >= 50
    gates_passed &= ok
    print(f"  {PASS if ok else FAIL} Gate 1 — Seeds ≥50: {run['n_seeds']}")

    # Gate 2: All models (check both summary and disk backbone dirs)
    EXPECTED = {"gnm", "vint", "nomad"}
    summary_models = {m.lower() for m in run["models"]}
    # Also check backbone dirs directly
    from pathlib import Path as _Path
    sims_dir = repo_root / "simulations"
    run_backbone = sims_dir / run["run_id"] / "backbone"
    disk_models: set[str] = set()
    if run_backbone.exists():
        import re as _re
        for sub in run_backbone.iterdir():
            if sub.is_dir():
                parts = sub.name.split("_")
                if parts and parts[0] == "isaac" and len(parts) > 1:
                    disk_models.add(parts[1])
                elif len(parts) >= 2:
                    disk_models.add(parts[0])
    have = summary_models | disk_models
    ok = EXPECTED.issubset(summary_models)  # Gate passes on summary (final written state)
    gates_passed &= ok
    disk_info = f" [disk: {sorted(disk_models)}]" if disk_models != summary_models else ""
    print(f"  {PASS if ok else FAIL} Gate 2 — All models in summary: {sorted(summary_models)}{disk_info}"
          + (f" — missing from summary: {EXPECTED - summary_models}" if not ok else ""))

    # Gate 3: Complete
    ok = run["complete"]
    gates_passed &= ok
    print(f"  {PASS if ok else WARN} Gate 3 — Complete: {run['n_results']}/{run['expected_combos']}")

    # Gate 4: Safety monotonicity (FS coll <= RAW coll everywhere)
    backbone_results = run.get("backbone_results", [])
    violations = []
    for fs_r in backbone_results:
        if not fs_r.get("fleetsafe", False):
            continue
        model = fs_r.get("model", "")
        scene = fs_r.get("scene", "")
        raw_r = next(
            (r for r in backbone_results
             if not r.get("fleetsafe", False)
             and r.get("model", "") == model
             and r.get("scene", "") == scene),
            None,
        )
        if raw_r is None:
            continue
        fs_coll  = fs_r.get("collision_rate", 0)
        raw_coll = raw_r.get("collision_rate", 0)
        if fs_coll > raw_coll + 0.01:
            violations.append(f"{model}/{scene}: FS={fs_coll:.2f} > RAW={raw_coll:.2f}")
    ok = len(violations) == 0
    gates_passed &= ok
    if ok:
        print(f"  {PASS} Gate 4 — Safety monotonicity (FS ≤ RAW)")
    else:
        print(f"  {FAIL} Gate 4 — Safety monotonicity VIOLATED: {violations}")

    # Gate 5: CBF active (IR > 0 in at least one combo)
    any_ir = any(r.get("intervention_rate_mean", 0) > 0
                 for r in backbone_results if r.get("fleetsafe", False))
    ok = any_ir
    gates_passed &= ok
    print(f"  {PASS if ok else FAIL} Gate 5 — CBF active (IR > 0): {any_ir}")

    # Gate 6: Collision reduction (wherever RAW > 5%, FS ≤ 5%)
    reduction_fails = []
    for fs_r in backbone_results:
        if not fs_r.get("fleetsafe", False):
            continue
        model = fs_r.get("model", "")
        scene = fs_r.get("scene", "")
        raw_r = next(
            (r for r in backbone_results
             if not r.get("fleetsafe", False)
             and r.get("model", "") == model
             and r.get("scene", "") == scene),
            None,
        )
        if raw_r is None:
            continue
        raw_coll = raw_r.get("collision_rate", 0)
        fs_coll  = fs_r.get("collision_rate", 0)
        if raw_coll > 0.05 and fs_coll > 0.05:
            reduction_fails.append(
                f"{model}/{scene}: RAW={raw_coll:.2f} but FS={fs_coll:.2f}"
            )
    ok = len(reduction_fails) == 0
    gates_passed &= ok
    if ok:
        print(f"  {PASS} Gate 6 — Collision reduction (FS ≤ 5% where RAW > 5%)")
    else:
        print(f"  {FAIL} Gate 6 — Collision reduction FAILED: {reduction_fails}")

    if verbose:
        print(f"\n  Backbone results ({len(backbone_results)} total):")
        for r in sorted(backbone_results, key=lambda r: (r.get("model",""), r.get("scene",""), r.get("fleetsafe", False))):
            mode = "FS " if r.get("fleetsafe", False) else "RAW"
            coll = r.get("collision_rate", 0)
            ir   = r.get("intervention_rate_mean", 0)
            n    = r.get("n_episodes", 0)
            scene = r.get("scene", r.get("scene_name", "?"))[:20]
            model = r.get("model", "?")
            dist  = r.get("min_obstacle_distance_m_mean")
            dist_s = f" min_dist={dist:.3f}m" if dist is not None else ""
            print(f"    {model:8} {scene:25} {mode} coll={coll*100:5.1f}% IR={ir*100:5.1f}% n={n}{dist_s}")

    overall = PASS if gates_passed else FAIL
    print(f"\n  {overall} {BOLD}PROVEN: {gates_passed}{RESET}")
    return gates_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify FleetSafe PROVEN gate")
    parser.add_argument("--backend", choices=["mujoco", "isaaclab", "both"], default="both")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    backends = (
        ["mujoco", "isaaclab"] if args.backend == "both"
        else [args.backend]
    )

    print(f"{BOLD}FleetSafe PROVEN Gate Verifier{RESET}")
    print("=" * 50)

    results = {}
    for backend in backends:
        results[backend] = _check_backend(backend, args.verbose)

    print(f"\n{'=' * 50}")
    all_pass = all(results.values())
    for backend, ok in results.items():
        sym = PASS if ok else FAIL
        print(f"  {sym} {backend}: {'PROVEN' if ok else 'NOT PROVEN'}")

    if all_pass:
        print(f"\n{PASS} {BOLD}All backends PROVEN — ready for publication!{RESET}")
        print("  Next: python scripts/paper/generate_figures.py --out figures/ --png command-center/frontend/public/figures/")
        print("  Then: python scripts/publication/export_publication_bundle.py")
    else:
        print(f"\n{FAIL} {BOLD}Not all backends proven — check failures above{RESET}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
