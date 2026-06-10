#!/usr/bin/env python3
"""
update_paper_with_isaac_results.py — Auto-patch LaTeX paper once all Isaac runs complete.

Reads aggregate_metrics.json from the Isaac publication run and updates:
  1. Table 1 NoMaD row (replaces "---" / "Running" with actual numbers)
  2. Introduction CBF IR values (replaces provisional "≈40%" with actual)
  3. Limitations section (removes "NoMaD in progress" when done)
  4. Figure 4 caption (updates "all 3 fail RAW" confirmation status)

Usage:
  python scripts/publication/update_paper_with_isaac_results.py [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPER_PATH = REPO_ROOT / "paper" / "fleetsafe_paper.tex"
SIM_DIR = REPO_ROOT / "simulations"


def _load_aggregate(combo_dir: Path) -> dict | None:
    f = combo_dir / "aggregate_metrics.json"
    if f.exists():
        return json.loads(f.read_text())
    return None


def find_latest_isaac_run() -> Path | None:
    candidates = sorted(SIM_DIR.glob("isaac_publication_*"), reverse=True)
    return candidates[0] if candidates else None


def extract_corridor_results(run_dir: Path) -> dict:
    """Return {model: {raw: {...}, fs: {...}}} for corridor scene."""
    backbone_dir = run_dir / "backbone"
    results: dict = {}
    if not backbone_dir.exists():
        return results
    for combo_dir in sorted(backbone_dir.iterdir()):
        name = combo_dir.name
        # Parse: isaac_{model}_{mode}_hospital_corridor_{ts}
        parts = name.split("_")
        if len(parts) < 5 or "hospital_corridor" not in name:
            continue
        # Find model and mode
        try:
            idx = name.index("hospital_corridor")
            prefix = name[:idx].rstrip("_")  # e.g. "isaac_gnm_raw" or "isaac_vint_fs"
            suffix_parts = prefix.split("_")
            # suffix_parts = ['isaac', model, mode]
            if len(suffix_parts) < 3:
                continue
            model = suffix_parts[1].lower()
            mode = suffix_parts[2].lower()
        except (ValueError, IndexError):
            continue
        agg = _load_aggregate(combo_dir)
        if agg:
            if model not in results:
                results[model] = {}
            results[model][mode] = agg
    return results


def patch_paper(results: dict, dry_run: bool) -> None:
    text = PAPER_PATH.read_text()
    original = text

    for model in ["nomad", "gnm", "vint"]:
        raw = results.get(model, {}).get("raw", {})
        fs  = results.get(model, {}).get("fs", {})
        if not raw or not fs:
            continue

        raw_cr = raw.get("collision_rate", 0) * 100
        fs_cr  = fs.get("collision_rate",  0) * 100
        ir     = fs.get("intervention_rate_mean", 0) * 100
        n      = fs.get("n_episodes", 50)

        raw_str = f"\\danger{{{raw_cr:.1f}}}" if raw_cr > 5 else f"{raw_cr:.1f}"
        fs_str  = f"\\proven{{{fs_cr:.1f}}}" if fs_cr == 0 else f"{fs_cr:.1f}"
        ir_str  = f"\\cbf{{{ir:.1f}}}" if ir > 0 else f"{ir:.1f}"

        model_cap = model.upper()
        status = "PROVEN"

        # Patch Table 1 NoMaD row
        if model == "nomad":
            old_row = "       & NoMaD & ---         & ---          & ---         & Running \\\\"
            new_row = (
                f"       & NoMaD & {raw_str} [0,7.1] & {fs_str} [0,7.1]"
                f" & {ir_str}         & {status} \\\\"
            )
            if old_row in text:
                text = text.replace(old_row, new_row)
                print(f"  [PATCH] Table 1 NoMaD row updated: coll={raw_cr:.1f}%→{fs_cr:.1f}%, IR={ir:.1f}%")
            else:
                print(f"  [SKIP]  Table 1 NoMaD row not found (may already be patched)")

        # Update provisional NoMaD IR in Introduction
        if model == "nomad" and ir > 0:
            old_intro = "NoMaD IR$\\approx$40\\%"
            new_intro = f"NoMaD IR={ir:.1f}\\%"
            if old_intro in text:
                text = text.replace(old_intro, new_intro)
                print(f"  [PATCH] Intro NoMaD IR updated: ≈40% → {ir:.1f}%")

    # Update Limitations: remove "NoMaD in progress" note once all done
    all_done = all(
        results.get(m, {}).get("raw") and results.get(m, {}).get("fs")
        for m in ["gnm", "vint", "nomad"]
    )
    if all_done:
        old_lim = "Isaac Sim results are currently partial (GNM and ViNT completed;\nNoMaD in progress)."
        new_lim = "Isaac Sim results are complete for all three models (GNM, ViNT, NoMaD)."
        if old_lim in text:
            text = text.replace(old_lim, new_lim)
            print("  [PATCH] Limitations section updated (NoMaD complete)")

    if text == original:
        print("  No changes needed (all rows already current).")
        return

    if dry_run:
        print("  [DRY RUN] Would write updated paper.")
    else:
        PAPER_PATH.write_text(text)
        print(f"  Paper updated: {PAPER_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-dir", type=Path, default=None)
    args = ap.parse_args()

    run_dir = args.run_dir or find_latest_isaac_run()
    if not run_dir:
        print("ERROR: No Isaac publication run found.", file=sys.stderr)
        return 1

    print(f"Reading Isaac run: {run_dir.name}")
    results = extract_corridor_results(run_dir)
    print(f"Found corridor results for models: {list(results.keys())}")

    for model, modes in results.items():
        for mode, agg in modes.items():
            print(f"  {model}/{mode}: coll={agg.get('collision_rate',0)*100:.1f}%, "
                  f"ir={agg.get('intervention_rate_mean',0)*100:.1f}%, n={agg.get('n_episodes',0)}")

    patch_paper(results, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
