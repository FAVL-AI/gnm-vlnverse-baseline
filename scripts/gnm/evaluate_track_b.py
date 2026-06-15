#!/usr/bin/env python3
"""Track B language-grounding offline evaluation.

Official evaluation script for Track B (language instruction → goal retrieval).
Computes Retrieval Euclidean Error (REE) and Retrieval Success Rate (RSR)
for oracle, last-frame, and optionally CLIP-based retrieval methods.

Metric definitions
------------------
REE = sqrt((retrieved_x - goal_x)^2 + (retrieved_y - goal_y)^2)  [metres]
RSR = n_success / n_episodes  where success := REE <= success_threshold_m

Evidence level
--------------
With synthetic (dry-run) data this script produces evidence_level:
    pipeline_diagnostic_only

This diagnostic validates metric and data-flow plumbing only.
It cannot distinguish retrieval methods because every synthetic trajectory
terminates exactly at its declared target.

Do NOT cite pipeline_diagnostic_only results as language-grounding evidence.

Usage
-----
    # Diagnostic run (oracle + last, no CLIP):
    python3 scripts/gnm/evaluate_track_b.py \\
        --dataset-root datasets/custom_vln_office \\
        --split train --stride 5 \\
        --methods oracle,last \\
        --output-dir results/track_b_language/custom_vln_office \\
        --overwrite

    # With CLIP (requires: pip install 'gnm-vlnverse[language]'):
    python3 scripts/gnm/evaluate_track_b.py \\
        --dataset-root datasets/custom_vln_office \\
        --split train --stride 5 \\
        --methods oracle,last,clip \\
        --output-dir results/track_b_language/custom_vln_office \\
        --overwrite

    # Dry run (evaluate but do not write files):
    python3 scripts/gnm/evaluate_track_b.py \\
        --dataset-root datasets/custom_vln_office \\
        --split train --dry-run
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

SUCCESS_THRESHOLD_M = 3.0

_LIMITATION_DIAGNOSTIC = (
    "This diagnostic validates metric and data-flow plumbing only. "
    "It cannot distinguish retrieval methods because every synthetic trajectory "
    "terminates exactly at its declared target."
)

_SEPARATION_STATEMENT = (
    "Current retrieval metrics evaluate language-to-image grounding only. "
    "They do not prove GNM navigation success. "
    "Oracle retrieval removes retrieval error but does not establish "
    "closed-loop navigation performance. "
    "Full language-conditioned navigation requires retrieval followed by actual "
    "GNM rollout and stopping criterion evaluation. "
    "Retrieval success and navigation success must not be combined into a single "
    "claim unless both stages are executed for the same episode."
)


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def _dep_version(mod: str) -> str:
    try:
        m = __import__(mod)
        return getattr(m, "__version__", "imported")
    except ImportError:
        return "UNAVAILABLE"


def _detect_rgb_frame_type(ep_dirs: list[Path]) -> str:
    """Classify RGB frames as synthetic-gradient or real by first-derivative std.

    Synthetic colour-gradient frames have low spatial variation between adjacent
    pixels (first-derivative std < 25).  Real camera frames have much higher
    local detail (first-derivative std >> 25 due to texture and edges).
    """
    if not ep_dirs:
        return "unknown"
    sample = ep_dirs[0] / "rgb" / "000000.jpg"
    if not sample.exists():
        return "unknown"
    try:
        import cv2
        import numpy as np
        img = cv2.imread(str(sample))
        if img is None:
            return "unknown"
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(float)
        dx_std = float(np.diff(gray, axis=1).std())
        return "synthetic_gradient_dry_run" if dx_std < 25.0 else "real_camera"
    except Exception:
        return "unknown"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _result_to_dict(r) -> dict:
    ree = r.retrieval_error_m
    return {
        "episode_id":        r.episode_id,
        "instruction":       r.instruction,
        "method":            r.method,
        "status":            r.status,
        "retrieved_idx":     r.retrieved_idx,
        "n_keyframes":       r.n_keyframes,
        "retrieved_pos":     list(r.retrieved_pos),
        "true_goal":         list(r.true_goal),
        "retrieval_error_m": ree if math.isfinite(ree) else None,
        "success":           r.success,
        "failure_reason":    r.failure_reason,
    }


def _summary_to_dict(s, *, stride: int, seed: int, threshold_m: float) -> dict:
    if s.status != "OK":
        return {
            "method":       s.method,
            "method_label": s.method_label,
            "status":       s.status,
            "reason":       s.reason,
        }
    errors = [
        r.retrieval_error_m for r in s.per_episode
        if math.isfinite(r.retrieval_error_m)
    ]
    arr = np.array(errors) if errors else np.array([])
    std_ddof1 = float(np.std(arr, ddof=1)) if arr.size > 1 else None

    return {
        "method":             s.method,
        "method_label":       s.method_label,
        "status":             s.status,
        "n_episodes":         s.n_episodes,
        "n_success":          s.n_success,
        "rsr":                s.rsr,
        "rsr_pct":            round(s.rsr * 100, 1),
        "mean_ree_m":         s.mean_ree_m,
        "median_ree_m":       s.median_ree_m,
        "std_ree_m_ddof0":    s.std_ree_m,
        "std_ree_m_ddof1":    std_ddof1,
        "min_ree_m":          s.min_ree_m,
        "max_ree_m":          s.max_ree_m,
        "threshold_m":        threshold_m,
        "stride":             stride,
        "seed":               seed,
        "ree_metric":         s.ree_metric,
        "ree_formula":        s.ree_formula,
        "rsr_formula":        s.rsr_formula,
        "per_episode_ree": {
            r.episode_id: r.retrieval_error_m
            for r in s.per_episode
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dataset-root", required=True,
                        help="Dataset root containing split directories (train/, val/)")
    parser.add_argument("--split", default="train",
                        help="Split to evaluate (default: train)")
    parser.add_argument("--stride", type=int, default=5,
                        help="Keyframe stride for topological map (default: 5)")
    parser.add_argument("--methods", default="oracle,last",
                        help="Comma-separated retrieval methods: oracle,last,clip (default: oracle,last)")
    parser.add_argument("--output-dir", default=None,
                        help="Directory for result artefacts (required unless --dry-run)")
    parser.add_argument("--device", default="cpu",
                        help="Device for CLIP inference: cpu or cuda (default: cpu)")
    parser.add_argument("--encoder-model", default="openai/clip-vit-base-patch16",
                        help="HuggingFace CLIP model identifier")
    parser.add_argument("--seed", type=int, default=0,
                        help="Random seed (reserved for future stochastic methods)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Evaluate but do not write output files")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing output files")
    args = parser.parse_args()

    methods      = [m.strip() for m in args.methods.split(",") if m.strip()]
    dataset_root = Path(args.dataset_root)

    if not args.dry_run and args.output_dir is None:
        parser.error("--output-dir is required unless --dry-run is set")

    out_dir = Path(args.output_dir) if args.output_dir else None

    if out_dir is not None and not args.dry_run:
        if out_dir.exists() and any(out_dir.iterdir()):
            if not args.overwrite:
                print(
                    f"ERROR: output directory already contains files: {out_dir}\n"
                    f"       Pass --overwrite to replace.",
                    file=sys.stderr,
                )
                sys.exit(1)
        out_dir.mkdir(parents=True, exist_ok=True)

    # Logging
    log_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if out_dir is not None and not args.dry_run:
        log_handlers.append(logging.FileHandler(out_dir / "evaluation.log"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=log_handlers,
        force=True,
    )
    log = logging.getLogger(__name__)

    log.info("Track B evaluation — %s split", args.split)
    log.info("Dataset root : %s", dataset_root)
    log.info("Methods      : %s", methods)
    log.info("Stride       : %d", args.stride)
    log.info("Threshold    : %.1f m", SUCCESS_THRESHOLD_M)
    if out_dir:
        log.info("Output dir   : %s  (dry_run=%s)", out_dir, args.dry_run)
    else:
        log.info("Output dir   : <none> (dry-run)")

    # Load episodes
    from gnm_vlnverse.vln.language_episode import load_dataset
    from gnm_vlnverse.evaluation.language_evaluator import (
        SUCCESS_THRESHOLD_M as _THRESH,
        compare_methods,
        evaluate,
    )

    try:
        episodes = load_dataset(dataset_root, split=args.split, stride=args.stride)
    except FileNotFoundError as exc:
        log.error(str(exc))
        sys.exit(1)

    log.info("Loaded %d episodes from %s/%s", len(episodes), dataset_root, args.split)

    split_dir  = dataset_root / args.split
    ep_dirs    = sorted(p for p in split_dir.iterdir() if (p / "traj_data.pkl").exists())
    rgb_type   = _detect_rgb_frame_type(ep_dirs)

    # Run evaluation
    summaries: dict = {}
    for method in methods:
        log.info("Running method=%r", method)
        summaries[method] = evaluate(
            episodes,
            method=method,
            success_threshold_m=_THRESH,
            clip_device=args.device,
            clip_model_name=args.encoder_model,
        )
        log.info(str(summaries[method]))

    # Print console summary
    print()
    print("Track B Evaluation Results")
    print("=" * 60)
    print(f"Evidence level : pipeline_diagnostic_only")
    print(f"Episodes       : {len(episodes)}")
    print(f"Threshold      : {_THRESH} m")
    print(f"RGB frames     : {rgb_type}")
    print()
    for method, s in summaries.items():
        print(f"  {s}")
    print()
    print(f"LIMITATION: {_LIMITATION_DIAGNOSTIC}")
    print()

    if args.dry_run:
        log.info("--dry-run: output files not written.")
        return

    # ── Build dependencies dict ───────────────────────────────────────────────

    deps = {
        "torch":        _dep_version("torch"),
        "numpy":        _dep_version("numpy"),
        "cv2":          _dep_version("cv2"),
        "pillow":       _dep_version("PIL"),
        "transformers": _dep_version("transformers"),
    }

    clip_available = deps["transformers"] != "UNAVAILABLE"
    timestamp      = datetime.now(timezone.utc).isoformat(timespec="seconds")
    commit         = _git_commit()

    limitations = [
        _LIMITATION_DIAGNOSTIC,
        "RGB frames are synthetic colour-gradient placeholders — not real camera images.",
        f"{len(episodes)} episodes is a local diagnostic run, not the full VLNVerse Track B benchmark.",
        "Instructions were authored for this dataset; independent benchmark annotation not established.",
        f"All episodes are from the {args.split} split and were used during development.",
        "Retrieval metrics evaluate language-to-image grounding only.",
        "Results do not prove GNM navigation success.",
        "Oracle retrieval removes retrieval error but does not establish closed-loop navigation performance.",
        "Full language-conditioned navigation requires retrieval followed by GNM rollout and stopping evaluation.",
    ]

    instruction_provenance = {
        ep.episode_id: {
            "instruction_source":           "project_authored_synthetic_dry_run",
            "rgb_frame_source":             rgb_type,
            "target_frame_source":          "trajectory_final_position",
            "target_defined_independently": True,
            "scene":                        ep.scene_id or "custom_vln_office",
            "split":                        args.split,
            "used_during_development":      True,
            "source_script":                "collect_custom_vln_office_data.py --dry-run",
            "isaac_assets_used":            False,
            "vlnverse_assets_used":         False,
        }
        for ep in episodes
    }

    # ── Write artefacts ───────────────────────────────────────────────────────

    episode_records = [
        _result_to_dict(r)
        for s in summaries.values()
        for r in s.per_episode
    ]
    _write_jsonl(out_dir / "episode_results.jsonl", episode_records)
    log.info("Written: episode_results.jsonl (%d records)", len(episode_records))

    aggregate = {
        "evidence_level":                "pipeline_diagnostic_only",
        "run_description":               "Track B language-grounding diagnostic evaluation",
        "run_timestamp":                 timestamp,
        "commit":                        commit,
        "dataset_root":                  str(dataset_root),
        "dataset":                       dataset_root.name,
        "dataset_split":                 args.split,
        "stride":                        args.stride,
        "threshold_m":                   _THRESH,
        "seed":                          args.seed,
        "n_episodes":                    len(episodes),
        "rgb_frame_type":                rgb_type,
        "instruction_type":              "project_authored_synthetic_dry_run",
        "vlnverse_benchmark":            False,
        "is_vlnverse_benchmark_track_b": False,
        "limitations":                   limitations,
        "navigation_separation_statement": _SEPARATION_STATEMENT,
        "dependencies":                  deps,
        "encoder_model":                 args.encoder_model,
        "methods": {
            m: _summary_to_dict(s, stride=args.stride, seed=args.seed, threshold_m=_THRESH)
            for m, s in summaries.items()
        },
    }
    (out_dir / "aggregate_metrics.json").write_text(json.dumps(aggregate, indent=2))
    log.info("Written: aggregate_metrics.json")

    manifest = {
        "run_description":     "Track B language-grounding diagnostic evaluation",
        "run_timestamp":       timestamp,
        "commit":              commit,
        "python_version":      sys.version,
        "dependencies":        deps,
        "clip_available":      clip_available,
        "evidence_level":      "pipeline_diagnostic_only",
        "dataset_root":        str(dataset_root),
        "split":               args.split,
        "n_episodes":          len(episodes),
        "stride":              args.stride,
        "threshold_m":         _THRESH,
        "methods":             methods,
        "seed":                args.seed,
        "device":              args.device,
        "encoder_model":       args.encoder_model,
        "output_dir":          str(out_dir),
        "output_files": [
            "episode_results.jsonl",
            "aggregate_metrics.json",
            "results_table.csv",
            "run_manifest.json",
            "evaluation.log",
        ],
        "instruction_provenance": instruction_provenance,
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("Written: run_manifest.json")

    csv_rows = []
    for s in summaries.values():
        if s.status != "OK":
            csv_rows.append({
                "method": s.method, "status": s.status,
                "n_episodes": s.n_episodes, "n_success": "",
                "rsr": "", "mean_ree_m": "", "median_ree_m": "",
                "std_ree_m_ddof0": "", "std_ree_m_ddof1": "",
                "min_ree_m": "", "max_ree_m": "",
            })
        else:
            errors = [r.retrieval_error_m for r in s.per_episode if math.isfinite(r.retrieval_error_m)]
            arr = np.array(errors) if errors else np.array([])
            std1 = float(np.std(arr, ddof=1)) if arr.size > 1 else None
            csv_rows.append({
                "method":          s.method,
                "status":          s.status,
                "n_episodes":      s.n_episodes,
                "n_success":       s.n_success,
                "rsr":             f"{s.rsr:.4f}",
                "mean_ree_m":      f"{s.mean_ree_m:.4f}" if s.mean_ree_m is not None else "",
                "median_ree_m":    f"{s.median_ree_m:.4f}" if s.median_ree_m is not None else "",
                "std_ree_m_ddof0": f"{s.std_ree_m:.4f}" if s.std_ree_m is not None else "",
                "std_ree_m_ddof1": f"{std1:.4f}" if std1 is not None else "",
                "min_ree_m":       f"{s.min_ree_m:.4f}" if s.min_ree_m is not None else "",
                "max_ree_m":       f"{s.max_ree_m:.4f}" if s.max_ree_m is not None else "",
            })

    if csv_rows:
        csv_path = out_dir / "results_table.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            w.writeheader()
            w.writerows(csv_rows)
        log.info("Written: results_table.csv")

    log.info("Evaluation complete.")


if __name__ == "__main__":
    main()
