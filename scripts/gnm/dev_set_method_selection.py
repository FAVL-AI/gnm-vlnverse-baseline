#!/usr/bin/env python3
"""Development-set method selection for Track B subgoal retrieval.

Evaluates 7 subgoal-selection methods on the 238 train episodes from the
frozen generated-language manifest.  The 15 val episodes are NOT touched.

Methods
-------
random          : Uniformly random frame.
first           : Frame 0.
final           : Last frame (frame N-1).
oracle          : Frame with minimum Euclidean distance to goal_pos (upper bound).
clip            : CLIP cosine similarity, argmax.
clip_route      : CLIP score * linear route prior (later frames upweighted).
clip_route_rej  : clip_route, with rejection fallback to final when max score < threshold.

Metric
------
SR@3m  : fraction of episodes where selected frame is within 3 m of goal_pos.
mean_dist_m    : mean Euclidean distance of selected frame to goal_pos (m).
median_dist_m  : median Euclidean distance.

Output
------
results/track_b_language/dev_set_method_selection/
    per_episode.jsonl   — per-episode selected indices and distances for each method
    summary.json        — aggregate SR@3m and dist stats per method
    report.md           — human-readable comparison table

Usage
-----
    python3 scripts/gnm/dev_set_method_selection.py
    python3 scripts/gnm/dev_set_method_selection.py --stride 5 --route-beta 1.0
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import random as _random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

logger = logging.getLogger(__name__)

FLEETSAFE_VLNTUBE = Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark/datasets/vlntube")
MANIFEST_PATH     = REPO / "data/track_b_annotations/generated_language_manifest.jsonl"
SUCCESS_RADIUS_M  = 3.0
CLIP_MODEL_ID     = "openai/clip-vit-base-patch16"
DEFAULT_STRIDE    = 5
DEFAULT_ROUTE_BETA = 1.0
DEFAULT_REJECTION_THRESHOLD = 0.20


def _load_manifest(split: str = "train") -> list[dict]:
    records = []
    for line in MANIFEST_PATH.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            if rec["split"] == split:
                records.append(rec)
    return records


def _load_episode(ep_dir: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Return (positions_xy (N,2), frame_indices present as sorted list)."""
    traj_file = ep_dir / "traj_data.pkl"
    if not traj_file.exists():
        return None
    try:
        data = pickle.loads(traj_file.read_bytes())
        pos  = np.asarray(data["position"])
        if pos.ndim != 2 or pos.shape[1] < 2:
            return None
        return pos[:, :2], pos
    except Exception:
        return None


def _available_jpg_indices(ep_dir: Path) -> list[int]:
    indices = []
    for f in ep_dir.glob("*.jpg"):
        try:
            indices.append(int(f.stem))
        except ValueError:
            pass
    return sorted(indices)


def _load_frames(ep_dir: Path, indices: list[int]) -> list[np.ndarray]:
    """Load RGB frames for specified indices (returns list of H×W×3 uint8 arrays)."""
    import cv2
    frames = []
    for i in indices:
        p = ep_dir / f"{i}.jpg"
        if p.exists():
            img = cv2.imread(str(p))
            if img is not None:
                frames.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            else:
                frames.append(None)
        else:
            frames.append(None)
    return frames


def _to_tensor(output, import_torch):
    """Extract float tensor from CLIPModel feature output (handles transformers 4.x and 5.x)."""
    import torch
    import torch.nn.functional as F
    if isinstance(output, torch.Tensor):
        t = output
    elif hasattr(output, "image_embeds"):
        t = output.image_embeds
    elif hasattr(output, "text_embeds"):
        t = output.text_embeds
    elif hasattr(output, "pooler_output"):
        t = output.pooler_output
    else:
        raise TypeError(f"Cannot extract tensor from {type(output)}")
    return F.normalize(t.float(), dim=-1)


def _clip_embed_frames(frames: list[np.ndarray], clip_model, clip_proc) -> np.ndarray:
    import torch
    from PIL import Image

    valid = [f for f in frames if f is not None]
    if not valid:
        return np.zeros((0, 512))

    all_embeds = []
    batch_size = 32
    for i in range(0, len(valid), batch_size):
        batch = valid[i : i + batch_size]
        pil   = [Image.fromarray(f) for f in batch]
        inp   = clip_proc(images=pil, return_tensors="pt")
        with torch.no_grad():
            feats = _to_tensor(clip_model.get_image_features(**inp), torch)
        all_embeds.append(feats.cpu().numpy())
    return np.concatenate(all_embeds, axis=0)


def _clip_embed_text(text: str, clip_model, clip_proc) -> np.ndarray:
    import torch
    inp = clip_proc(text=[text or "."], return_tensors="pt", padding=True,
                    truncation=True, max_length=77)
    with torch.no_grad():
        feat = _to_tensor(clip_model.get_text_features(**inp), torch)
    return feat.cpu().numpy()   # (1, D)


def _dist_to_goal(positions: np.ndarray, frame_idx: int, goal_xy: np.ndarray) -> float:
    if frame_idx >= len(positions):
        frame_idx = len(positions) - 1
    return float(np.linalg.norm(positions[frame_idx] - goal_xy))


def run_methods(
    ep_dir: Path,
    positions: np.ndarray,
    goal_xy: np.ndarray,
    instruction: str,
    stride: int,
    route_beta: float,
    rejection_threshold: float,
    clip_model,
    clip_proc,
    rng: _random.Random,
) -> dict[str, dict]:
    """Return per-method results for one episode."""
    n_total    = len(positions)
    all_idx    = list(range(n_total))
    # Only use frame indices that have corresponding jpg files
    available  = _available_jpg_indices(ep_dir)
    if not available:
        return {}

    last_avail = available[-1]
    first_avail = available[0]

    def _nearest_available(i: int) -> int:
        return min(available, key=lambda x: abs(x - i))

    results: dict[str, dict] = {}

    # ── 1. random ────────────────────────────────────────────────────────────
    rand_idx = rng.choice(available)
    results["random"] = {
        "selected_frame": rand_idx,
        "dist_m": _dist_to_goal(positions, rand_idx, goal_xy),
    }

    # ── 2. first ─────────────────────────────────────────────────────────────
    results["first"] = {
        "selected_frame": first_avail,
        "dist_m": _dist_to_goal(positions, first_avail, goal_xy),
    }

    # ── 3. final ─────────────────────────────────────────────────────────────
    results["final"] = {
        "selected_frame": last_avail,
        "dist_m": _dist_to_goal(positions, last_avail, goal_xy),
    }

    # ── 4. oracle ─────────────────────────────────────────────────────────────
    dists = np.linalg.norm(positions[available] - goal_xy, axis=1)
    oracle_idx = available[int(np.argmin(dists))]
    results["oracle"] = {
        "selected_frame": oracle_idx,
        "dist_m": float(np.min(dists)),
    }

    # ── CLIP methods ─────────────────────────────────────────────────────────
    if clip_model is not None:
        # Stride-sampled keyframe indices from available frames
        kf_indices = [available[i] for i in range(0, len(available), stride)]
        if not kf_indices or kf_indices[-1] != last_avail:
            kf_indices.append(last_avail)   # always include last

        kf_frames  = _load_frames(ep_dir, kf_indices)
        kf_valid   = [(i, f) for i, f in zip(kf_indices, kf_frames) if f is not None]
        if not kf_valid:
            for m in ("clip", "clip_route", "clip_route_rej"):
                results[m] = {"selected_frame": last_avail,
                               "dist_m": _dist_to_goal(positions, last_avail, goal_xy),
                               "note": "no_valid_frames"}
        else:
            kf_valid_idx, kf_valid_frames = zip(*kf_valid)
            kf_valid_idx   = list(kf_valid_idx)
            kf_valid_frames = list(kf_valid_frames)

            img_embeds = _clip_embed_frames(kf_valid_frames, clip_model, clip_proc)
            text_embed = _clip_embed_text(instruction, clip_model, clip_proc)
            sims = (img_embeds @ text_embed.T).squeeze()  # (K,)
            if sims.ndim == 0:
                sims = np.array([float(sims)])

            N = len(kf_valid_idx)

            # 5. clip: argmax similarity
            best_clip_local = int(np.argmax(sims))
            best_clip_frame = kf_valid_idx[best_clip_local]
            results["clip"] = {
                "selected_frame": best_clip_frame,
                "dist_m": _dist_to_goal(positions, best_clip_frame, goal_xy),
                "clip_sim": float(sims[best_clip_local]),
            }

            # 6. clip_route: sim * (1 + beta * rank/N)
            route_weights = np.array([1.0 + route_beta * k / max(N - 1, 1) for k in range(N)])
            route_scores  = sims * route_weights
            best_cr_local = int(np.argmax(route_scores))
            best_cr_frame = kf_valid_idx[best_cr_local]
            results["clip_route"] = {
                "selected_frame": best_cr_frame,
                "dist_m": _dist_to_goal(positions, best_cr_frame, goal_xy),
                "clip_sim": float(sims[best_cr_local]),
                "route_score": float(route_scores[best_cr_local]),
            }

            # 7. clip_route_rej: fall back to final when max route_score < threshold
            if float(np.max(route_scores)) < rejection_threshold:
                results["clip_route_rej"] = {
                    "selected_frame": last_avail,
                    "dist_m": _dist_to_goal(positions, last_avail, goal_xy),
                    "fallback": "rejection",
                    "route_score": float(np.max(route_scores)),
                }
            else:
                results["clip_route_rej"] = {
                    "selected_frame": best_cr_frame,
                    "dist_m": _dist_to_goal(positions, best_cr_frame, goal_xy),
                    "clip_sim": float(sims[best_cr_local]),
                    "route_score": float(route_scores[best_cr_local]),
                    "fallback": "none",
                }

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--output-dir", default="results/track_b_language/dev_set_method_selection")
    parser.add_argument("--vlntube-root", default=str(FLEETSAFE_VLNTUBE))
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE,
                        help="Keyframe stride for CLIP methods (default: 5)")
    parser.add_argument("--route-beta", type=float, default=DEFAULT_ROUTE_BETA,
                        help="Route prior weight (default: 1.0)")
    parser.add_argument("--rejection-threshold", type=float, default=DEFAULT_REJECTION_THRESHOLD,
                        help="Minimum route score for rejection fallback (default: 0.20)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-clip", action="store_true", help="Skip CLIP methods")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    vlntube = Path(args.vlntube_root)

    rng = _random.Random(args.seed)

    # Load CLIP
    clip_model = clip_proc = None
    if not args.no_clip:
        try:
            from transformers import CLIPModel, CLIPProcessor
            logger.info(f"Loading CLIP: {CLIP_MODEL_ID}")
            clip_proc  = CLIPProcessor.from_pretrained(CLIP_MODEL_ID)
            clip_model = CLIPModel.from_pretrained(CLIP_MODEL_ID)
            clip_model.eval()
            logger.info("CLIP loaded")
        except Exception as exc:
            logger.warning(f"CLIP unavailable: {exc}")

    manifest = _load_manifest("train")
    logger.info(f"Train episodes: {len(manifest)}")

    method_names = ["random", "first", "final", "oracle"]
    if clip_model is not None:
        method_names += ["clip", "clip_route", "clip_route_rej"]

    all_records = []
    method_dists: dict[str, list[float]] = {m: [] for m in method_names}

    for i, rec in enumerate(manifest):
        ep_id   = rec["episode_id"]
        split   = rec["split"]
        ep_dir  = vlntube / split / ep_id

        if not ep_dir.is_dir():
            logger.warning(f"Episode dir not found: {ep_dir}")
            continue

        result = _load_episode(ep_dir)
        if result is None:
            logger.warning(f"Could not load trajectory: {ep_id}")
            continue
        positions, _ = result

        goal_pos = rec.get("goal_pos")
        if goal_pos is None:
            # Fall back to episode_info.json
            ep_info_file = ep_dir / "episode_info.json"
            if ep_info_file.exists():
                ep_info  = json.loads(ep_info_file.read_text())
                goal_pos = ep_info.get("goal_pos")
        if goal_pos is None:
            logger.warning(f"No goal_pos for {ep_id}")
            continue

        goal_xy = np.array(goal_pos[:2])

        method_results = run_methods(
            ep_dir=ep_dir,
            positions=positions,
            goal_xy=goal_xy,
            instruction=rec["instruction_text"],
            stride=args.stride,
            route_beta=args.route_beta,
            rejection_threshold=args.rejection_threshold,
            clip_model=clip_model,
            clip_proc=clip_proc,
            rng=rng,
        )

        row = {
            "episode_id": ep_id,
            "scene_id":   rec["scene_id"],
            "n_steps":    len(positions),
        }
        for m in method_names:
            if m in method_results:
                r = method_results[m]
                row[f"{m}_frame"]  = r["selected_frame"]
                row[f"{m}_dist_m"] = round(r["dist_m"], 3)
                row[f"{m}_success"] = r["dist_m"] <= SUCCESS_RADIUS_M
                method_dists[m].append(r["dist_m"])
        all_records.append(row)

        if (i + 1) % 50 == 0:
            logger.info(f"  {i+1}/{len(manifest)} episodes done")

    # Aggregate
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary: dict[str, dict] = {}
    for m in method_names:
        dists = np.array(method_dists[m])
        n = len(dists)
        if n == 0:
            summary[m] = {}
            continue
        n_success = int((dists <= SUCCESS_RADIUS_M).sum())
        summary[m] = {
            "n_episodes":    n,
            "sr_at_3m":      round(n_success / n, 4),
            "n_success":     n_success,
            "mean_dist_m":   round(float(dists.mean()), 3),
            "median_dist_m": round(float(np.median(dists)), 3),
            "p25_dist_m":    round(float(np.percentile(dists, 25)), 3),
            "p75_dist_m":    round(float(np.percentile(dists, 75)), 3),
        }

    summary_out = {
        "audit_timestamp":      timestamp,
        "split":                "train",
        "n_episodes":           len(all_records),
        "success_radius_m":     SUCCESS_RADIUS_M,
        "clip_model":           CLIP_MODEL_ID if clip_model is not None else None,
        "stride":               args.stride,
        "route_beta":           args.route_beta,
        "rejection_threshold":  args.rejection_threshold,
        "seed":                 args.seed,
        "methods":              summary,
    }

    # Write outputs
    with open(out_dir / "per_episode.jsonl", "w") as f:
        for row in all_records:
            f.write(json.dumps(row) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary_out, indent=2))

    # Markdown report
    lines = [
        "# Dev-Set Method Selection — Track B Subgoal Retrieval",
        "",
        f"**Date:** {timestamp[:10]}",
        f"**Split:** train ({len(all_records)} episodes)",
        f"**Success radius:** {SUCCESS_RADIUS_M} m",
        "",
        "## Configuration",
        "",
        f"| Parameter | Value |",
        f"|-----------|-------|",
        f"| CLIP model | `{CLIP_MODEL_ID}` |" if clip_model else "| CLIP | not used |",
        f"| Keyframe stride | {args.stride} |",
        f"| Route prior beta | {args.route_beta} |",
        f"| Rejection threshold | {args.rejection_threshold} |",
        f"| Random seed | {args.seed} |",
        "",
        "## Results",
        "",
        "| Method | SR@3m | Mean dist (m) | Median dist (m) |",
        "|--------|-------|---------------|-----------------|",
    ]
    for m in method_names:
        s = summary.get(m, {})
        if s:
            lines.append(
                f"| `{m}` | {s['sr_at_3m']:.3f} | {s['mean_dist_m']:.2f} | {s['median_dist_m']:.2f} |"
            )
    lines += [
        "",
        "## Notes",
        "",
        "- `oracle` is an upper bound: it selects the frame closest to goal_pos.",
        "  It requires privileged information (goal_pos) not available at inference time.",
        "- `clip_route_rej` falls back to `final` frame when the maximum route-weighted",
        f"  CLIP score is below the rejection threshold ({args.rejection_threshold}).",
        "- Evaluation uses the **train split only** (238 episodes). The 15 val episodes",
        "  are reserved for final held-out evaluation.",
        "- SR@3m = fraction of episodes where the selected frame position is within",
        f"  {SUCCESS_RADIUS_M} m of goal_pos.",
    ]
    (out_dir / "report.md").write_text("\n".join(lines))

    print(f"\nDev-set method selection complete: {len(all_records)} episodes")
    print(f"\n{'Method':<20} {'SR@3m':>7}  {'Mean dist':>10}  {'Median dist':>11}")
    print("-" * 55)
    for m in method_names:
        s = summary.get(m, {})
        if s:
            print(f"{m:<20} {s['sr_at_3m']:>7.3f}  {s['mean_dist_m']:>10.2f}  {s['median_dist_m']:>11.2f}")
    print(f"\nOutput: {out_dir}")


if __name__ == "__main__":
    main()
