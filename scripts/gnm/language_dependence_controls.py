#!/usr/bin/env python3
"""Language-dependence control evaluation for Track B subgoal retrieval.

Tests whether the clip_route method actually depends on instruction content,
or whether the route prior alone drives SR@3m to 1.000 regardless of language.

Control conditions
------------------
correct         : Original instruction for each episode.
shuffled        : Instructions randomly permuted across episodes (fixed seed).
empty           : Empty string passed as instruction.
constant        : Same fixed instruction for every episode.
random_text     : Random words of matched mean length.
route_only      : Semantic similarity fixed to 1.0; only route prior acts.
clip_only       : Pure CLIP, no route prior (beta=0).

If SR@3m is near 1.000 for shuffled/empty/constant/route_only, that is
evidence that the route prior alone drives performance and language
dependence is NOT demonstrated.

Additional metrics
------------------
- Correct vs shuffled delta (primary language-sensitivity test)
- Target-frame rank (rank of actual goal-region frame in score list)
- MRR (mean reciprocal rank of target frame)
- Recall@1, Recall@3, Recall@5 (within-3m-goal frames)
- Endpoint selection rate (fraction selecting the final frame)
- Final-frame agreement rate (fraction where selected == last frame)
- Route-only agreement rate (fraction where selected == route_only selected)
- Per-scene breakdown
- 95% confidence intervals on SR@3m

Usage
-----
    python3 scripts/gnm/language_dependence_controls.py
    python3 scripts/gnm/language_dependence_controls.py \\
        --split train --seed 42 --route-beta 1.0
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import pickle
import random as _random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
DEFAULT_SEED       = 42

CONSTANT_INSTRUCTION = (
    "Walk straight down the main corridor and stop at the end of the hallway."
)
RANDOM_TEXT_SEED = 12345
RANDOM_WORD_POOL = [
    "walk", "turn", "left", "right", "straight", "forward", "stop", "end",
    "room", "door", "wall", "table", "chair", "corridor", "hallway", "shelf",
    "window", "lamp", "sofa", "desk", "floor", "ceiling", "corner", "beside",
]


def _load_manifest(split: str) -> list[dict]:
    records = []
    for line in MANIFEST_PATH.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            if rec["split"] == split:
                records.append(rec)
    return records


def _load_episode(ep_dir: Path) -> tuple[np.ndarray, list[int]] | None:
    traj_file = ep_dir / "traj_data.pkl"
    if not traj_file.exists():
        return None
    try:
        data = pickle.loads(traj_file.read_bytes())
        pos  = np.asarray(data["position"])
        if pos.ndim != 2 or pos.shape[1] < 2:
            return None
        avail = sorted(int(f.stem) for f in ep_dir.glob("*.jpg"))
        return pos[:, :2], avail
    except Exception:
        return None


def _load_frames_pil(ep_dir: Path, indices: list[int]):
    import cv2
    from PIL import Image
    frames = []
    valid_idx = []
    for i in indices:
        p = ep_dir / f"{i}.jpg"
        if p.exists():
            img = cv2.imread(str(p))
            if img is not None:
                frames.append(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
                valid_idx.append(i)
    return frames, valid_idx


def _embed_images(frames, clip_model, clip_proc) -> np.ndarray:
    import torch, torch.nn.functional as F

    def _norm(t):
        if not isinstance(t, torch.Tensor):
            t = getattr(t, "image_embeds", None) or getattr(t, "pooler_output", t)
        return F.normalize(t.float(), dim=-1)

    all_emb = []
    for i in range(0, len(frames), 32):
        inp = clip_proc(images=frames[i:i+32], return_tensors="pt")
        with torch.no_grad():
            all_emb.append(_norm(clip_model.get_image_features(**inp)).cpu().numpy())
    return np.concatenate(all_emb, axis=0)


def _embed_text(text: str, clip_model, clip_proc) -> np.ndarray:
    import torch, torch.nn.functional as F

    def _norm(t):
        if not isinstance(t, torch.Tensor):
            t = getattr(t, "text_embeds", None) or getattr(t, "pooler_output", t)
        return F.normalize(t.float(), dim=-1)

    inp = clip_proc(text=[text or "."], return_tensors="pt", padding=True, truncation=True,
                    max_length=77)
    with torch.no_grad():
        return _norm(clip_model.get_text_features(**inp)).cpu().numpy()


def _route_weights(n: int, beta: float) -> np.ndarray:
    return np.array([1.0 + beta * k / max(n - 1, 1) for k in range(n)])


def _goal_region_mask(positions: np.ndarray, valid_idx: list[int],
                      goal_xy: np.ndarray, radius: float) -> np.ndarray:
    """Boolean mask over valid_idx: True if frame is within radius of goal."""
    pos_kf = positions[valid_idx]
    dists  = np.linalg.norm(pos_kf - goal_xy, axis=1)
    return dists <= radius


def _compute_metrics(
    sims: np.ndarray,
    route_w: np.ndarray,
    positions: np.ndarray,
    valid_idx: list[int],
    goal_xy: np.ndarray,
    last_frame: int,
) -> dict[str, Any]:
    """Compute all retrieval metrics for one episode given similarity scores."""
    n = len(valid_idx)
    route_scores = sims * route_w
    best_local   = int(np.argmax(route_scores))
    best_frame   = valid_idx[best_local]
    dist_m       = float(np.linalg.norm(positions[best_frame] - goal_xy))

    goal_mask = _goal_region_mask(positions, valid_idx, goal_xy, SUCCESS_RADIUS_M)
    goal_local_indices = [i for i, m in enumerate(goal_mask) if m]

    # Rank of best goal-region frame in score ranking (1-indexed; lower = better)
    sorted_idx = np.argsort(-route_scores)
    if goal_local_indices:
        best_goal_local_rank = min(
            int(np.where(sorted_idx == g)[0][0]) + 1
            for g in goal_local_indices
        )
    else:
        best_goal_local_rank = n + 1

    mrr    = 1.0 / best_goal_local_rank if goal_local_indices else 0.0
    r_at_1 = int(best_goal_local_rank <= 1)
    r_at_3 = int(best_goal_local_rank <= 3)
    r_at_5 = int(best_goal_local_rank <= 5)

    last_local  = valid_idx.index(last_frame) if last_frame in valid_idx else n - 1
    final_selected = int(best_local == last_local)

    return {
        "selected_frame":  best_frame,
        "dist_m":          round(dist_m, 3),
        "success":         dist_m <= SUCCESS_RADIUS_M,
        "target_rank":     best_goal_local_rank,
        "mrr":             round(mrr, 4),
        "recall_at_1":     r_at_1,
        "recall_at_3":     r_at_3,
        "recall_at_5":     r_at_5,
        "final_selected":  final_selected,
        "clip_sim_at_selected": round(float(sims[best_local]), 4),
    }


def _aggregate(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {}
    dists   = np.array([r["dist_m"] for r in records])
    success = np.array([r["success"] for r in records])
    sr      = float(success.mean())
    # Wilson 95% CI for SR
    z = 1.96
    se = z * math.sqrt(sr * (1 - sr) / n) if n > 0 else 0.0
    mrr_vals = [r["mrr"] for r in records]
    return {
        "n_episodes":       n,
        "sr_at_3m":         round(sr, 4),
        "sr_ci95_lo":       round(max(0, sr - se), 4),
        "sr_ci95_hi":       round(min(1, sr + se), 4),
        "mean_dist_m":      round(float(dists.mean()), 3),
        "median_dist_m":    round(float(np.median(dists)), 3),
        "mrr":              round(float(np.mean(mrr_vals)), 4),
        "recall_at_1":      round(float(np.mean([r["recall_at_1"] for r in records])), 4),
        "recall_at_3":      round(float(np.mean([r["recall_at_3"] for r in records])), 4),
        "recall_at_5":      round(float(np.mean([r["recall_at_5"] for r in records])), 4),
        "final_frame_rate": round(float(np.mean([r["final_selected"] for r in records])), 4),
        "mean_clip_sim":    round(float(np.mean([r["clip_sim_at_selected"] for r in records])), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--output-dir",
                        default="results/track_b_language/language_dependence_controls")
    parser.add_argument("--vlntube-root", default=str(FLEETSAFE_VLNTUBE))
    parser.add_argument("--split", default="train", choices=["train", "val"])
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--route-beta", type=float, default=DEFAULT_ROUTE_BETA)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--no-clip", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    vlntube = Path(args.vlntube_root)

    rng = _random.Random(args.seed)
    rng_text = _random.Random(RANDOM_TEXT_SEED)

    manifest = _load_manifest(args.split)
    logger.info(f"Loaded {len(manifest)} {args.split} episodes")

    # ── Load CLIP ─────────────────────────────────────────────────────────────
    clip_model = clip_proc = None
    if not args.no_clip:
        try:
            from transformers import CLIPModel, CLIPProcessor
            clip_proc  = CLIPProcessor.from_pretrained(CLIP_MODEL_ID)
            clip_model = CLIPModel.from_pretrained(CLIP_MODEL_ID)
            clip_model.eval()
            logger.info("CLIP loaded")
        except Exception as exc:
            logger.warning(f"CLIP unavailable: {exc}")

    # ── Build shuffled instruction mapping ────────────────────────────────────
    episode_ids = [r["episode_id"] for r in manifest]
    shuffled_ids = episode_ids[:]
    rng.shuffle(shuffled_ids)
    shuffle_map = {ep: sh for ep, sh in zip(episode_ids, shuffled_ids)}
    instr_by_id = {r["episode_id"]: r["instruction_text"] for r in manifest}

    # ── Mean word count for random text ──────────────────────────────────────
    mean_words = round(sum(len(r["instruction_text"].split()) for r in manifest) / len(manifest))

    def _random_instruction() -> str:
        words = [rng_text.choice(RANDOM_WORD_POOL) for _ in range(mean_words)]
        return " ".join(words)

    conditions = ["correct", "shuffled", "empty", "constant", "random_text",
                  "route_only", "clip_only"]
    all_records: dict[str, list[dict]] = {c: [] for c in conditions}
    per_ep_records: list[dict] = []

    for i, rec in enumerate(manifest):
        ep_id  = rec["episode_id"]
        ep_dir = vlntube / args.split / ep_id

        result = _load_episode(ep_dir)
        if result is None:
            logger.warning(f"Skip {ep_id}: no trajectory")
            continue
        positions, avail = result

        ep_info = json.loads((ep_dir / "episode_info.json").read_text())
        goal_xy = np.array(ep_info["goal_pos"][:2])
        last_frame = avail[-1]

        # Keyframe indices
        kf_idx = [avail[j] for j in range(0, len(avail), args.stride)]
        if kf_idx[-1] != last_frame:
            kf_idx.append(last_frame)

        # Load frames and embed once
        if clip_model is not None:
            frames_pil, valid_idx = _load_frames_pil(ep_dir, kf_idx)
            if not valid_idx:
                continue
            img_emb = _embed_images(frames_pil, clip_model, clip_proc)
        else:
            valid_idx = kf_idx
            img_emb   = None

        n_kf   = len(valid_idx)
        route_w = _route_weights(n_kf, args.route_beta)

        ep_row: dict[str, Any] = {
            "episode_id":  ep_id,
            "scene_id":    rec["scene_id"],
            "split":       args.split,
            "n_steps":     len(positions),
            "n_keyframes": n_kf,
        }

        for cond in conditions:
            if img_emb is None and cond not in ("route_only",):
                # No CLIP: only route_only can be computed
                if cond != "route_only":
                    continue

            if cond == "correct":
                instr = rec["instruction_text"]
            elif cond == "shuffled":
                instr = instr_by_id[shuffle_map[ep_id]]
            elif cond == "empty":
                instr = ""
            elif cond == "constant":
                instr = CONSTANT_INSTRUCTION
            elif cond == "random_text":
                instr = _random_instruction()
            elif cond == "route_only":
                instr = None   # will use uniform sims
            elif cond == "clip_only":
                instr = rec["instruction_text"]
            else:
                continue

            if cond == "route_only":
                sims = np.ones(n_kf)
            elif cond == "clip_only":
                if img_emb is None:
                    continue
                txt_emb = _embed_text(instr, clip_model, clip_proc)
                sims    = (img_emb @ txt_emb.T).squeeze()
                if sims.ndim == 0:
                    sims = np.array([float(sims)])
            else:
                if img_emb is None:
                    continue
                txt_emb = _embed_text(instr, clip_model, clip_proc)
                sims    = (img_emb @ txt_emb.T).squeeze()
                if sims.ndim == 0:
                    sims = np.array([float(sims)])

            rw = route_w if cond != "clip_only" else np.ones(n_kf)

            m = _compute_metrics(sims, rw, positions, valid_idx, goal_xy, last_frame)
            m["condition"] = cond
            all_records[cond].append(m)
            ep_row[cond] = {k: v for k, v in m.items() if k != "condition"}

        per_ep_records.append(ep_row)
        if (i + 1) % 50 == 0:
            logger.info(f"  {i+1}/{len(manifest)} episodes")

    # ── Aggregate ─────────────────────────────────────────────────────────────
    agg: dict[str, dict] = {}
    for cond in conditions:
        agg[cond] = _aggregate(all_records[cond])

    # Language-sensitivity metrics
    sr_correct   = agg.get("correct", {}).get("sr_at_3m", None)
    sr_shuffled  = agg.get("shuffled", {}).get("sr_at_3m", None)
    sr_empty     = agg.get("empty", {}).get("sr_at_3m", None)
    sr_constant  = agg.get("constant", {}).get("sr_at_3m", None)
    sr_route_only = agg.get("route_only", {}).get("sr_at_3m", None)

    if sr_correct is not None and sr_shuffled is not None:
        delta_shuffled = round(sr_correct - sr_shuffled, 4)
    else:
        delta_shuffled = None
    if sr_correct is not None and sr_constant is not None:
        delta_constant = round(sr_correct - sr_constant, 4)
    else:
        delta_constant = None

    lang_dep_concluded = None
    if (sr_shuffled is not None and sr_empty is not None and
            sr_constant is not None and sr_route_only is not None):
        controls_near_1 = all(
            s is not None and s >= 0.95
            for s in [sr_shuffled, sr_empty, sr_constant, sr_route_only]
        )
        lang_dep_concluded = (
            "LANGUAGE_DEPENDENCE_NOT_DEMONSTRATED" if controls_near_1
            else "LANGUAGE_DEPENDENCE_INDICATED"
        )

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    shuffle_save = {ep_id: shuffle_map[ep_id] for ep_id in episode_ids
                    if ep_id in shuffle_map}

    summary = {
        "audit_timestamp":    timestamp,
        "split":              args.split,
        "n_episodes":         len(per_ep_records),
        "clip_model":         CLIP_MODEL_ID if clip_model is not None else None,
        "stride":             args.stride,
        "route_beta":         args.route_beta,
        "seed":               args.seed,
        "success_radius_m":   SUCCESS_RADIUS_M,
        "conditions":         agg,
        "language_sensitivity": {
            "correct_vs_shuffled_delta": delta_shuffled,
            "correct_vs_constant_delta": delta_constant,
            "language_dependence_conclusion": lang_dep_concluded,
        },
        "shuffle_map_file":   "shuffle_map.json",
        "constant_instruction": CONSTANT_INSTRUCTION,
        "random_text_seed":   RANDOM_TEXT_SEED,
        "mean_words_in_random_text": mean_words,
    }

    # ── Write outputs ─────────────────────────────────────────────────────────
    with open(out_dir / "per_episode.jsonl", "w") as f:
        for row in per_ep_records:
            f.write(json.dumps(row) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "shuffle_map.json").write_text(json.dumps(shuffle_save, indent=2))

    # Per-scene breakdown
    scenes: dict[str, dict[str, list[float]]] = {}
    for row in per_ep_records:
        sc = row["scene_id"]
        if sc not in scenes:
            scenes[sc] = {c: [] for c in conditions}
        for c in conditions:
            if c in row and "success" in row[c]:
                scenes[sc][c].append(float(row[c]["success"]))
    scene_agg = {}
    for sc, cond_data in scenes.items():
        scene_agg[sc] = {}
        for c, vals in cond_data.items():
            if vals:
                scene_agg[sc][c] = {"sr_at_3m": round(sum(vals)/len(vals), 4),
                                     "n": len(vals)}
    (out_dir / "per_scene.json").write_text(json.dumps(scene_agg, indent=2))

    # Markdown report
    lines = [
        "# Language-Dependence Control Evaluation — Track B",
        "",
        f"**Date:** {timestamp[:10]}",
        f"**Split:** {args.split} ({len(per_ep_records)} episodes)",
        f"**CLIP model:** `{CLIP_MODEL_ID}`",
        f"**Route prior beta:** {args.route_beta}",
        "",
        "## Control conditions",
        "",
        "| Condition | Description |",
        "|-----------|-------------|",
        "| `correct` | Original instruction for each episode |",
        "| `shuffled` | Instructions permuted across episodes (seed {}) |".format(args.seed),
        "| `empty` | Empty string passed as instruction |",
        "| `constant` | Same fixed instruction for all episodes |",
        "| `random_text` | Random words, mean-length matched (seed {}) |".format(RANDOM_TEXT_SEED),
        "| `route_only` | Semantic similarity fixed to 1.0; only route prior |",
        "| `clip_only` | Pure CLIP, route prior disabled (beta=0) |",
        "",
        "## Results",
        "",
        "| Condition | SR@3m | 95% CI | Mean dist (m) | MRR | R@1 | R@3 | Final-frame rate |",
        "|-----------|-------|--------|---------------|-----|-----|-----|-----------------|",
    ]
    for cond in conditions:
        s = agg.get(cond, {})
        if not s:
            continue
        lines.append(
            f"| `{cond}` | {s['sr_at_3m']:.3f} | "
            f"[{s['sr_ci95_lo']:.3f}, {s['sr_ci95_hi']:.3f}] | "
            f"{s['mean_dist_m']:.2f} | "
            f"{s['mrr']:.3f} | "
            f"{s['recall_at_1']:.3f} | "
            f"{s['recall_at_3']:.3f} | "
            f"{s['final_frame_rate']:.3f} |"
        )

    lines += [
        "",
        "## Language sensitivity",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Correct vs shuffled delta (SR@3m) | {delta_shuffled} |",
        f"| Correct vs constant delta (SR@3m) | {delta_constant} |",
        f"| Language dependence conclusion | **{lang_dep_concluded}** |",
        "",
        "## Interpretation",
        "",
    ]

    if lang_dep_concluded == "LANGUAGE_DEPENDENCE_NOT_DEMONSTRATED":
        lines += [
            "> **LANGUAGE_DEPENDENCE_NOT_DEMONSTRATED**",
            ">",
            "> SR@3m remains near 1.000 under shuffled, empty, constant, and route-only",
            "> conditions.  The route prior alone (trajectory endpoint bias) is sufficient",
            "> to achieve SR@3m = 1.000 regardless of instruction content.  This result",
            "> should not be reported as language-grounding evidence.",
            ">",
            "> The dataset property that all trajectories end at goal_pos makes SR@3m",
            "> non-discriminative for language sensitivity.  A discriminative dataset",
            "> is needed before language grounding can be evaluated.",
        ]
    else:
        lines += [
            "> **LANGUAGE_DEPENDENCE_INDICATED**",
            ">",
            "> SR@3m differs between correct and control conditions, suggesting that",
            "> instruction content contributes to retrieval performance.",
        ]

    lines += [
        "",
        "## Per-scene results",
        "",
        "| Scene | correct SR@3m | shuffled SR@3m | route_only SR@3m | N |",
        "|-------|---------------|----------------|-----------------|---|",
    ]
    for sc, data in sorted(scene_agg.items()):
        c_sr = data.get("correct", {}).get("sr_at_3m", "—")
        s_sr = data.get("shuffled", {}).get("sr_at_3m", "—")
        r_sr = data.get("route_only", {}).get("sr_at_3m", "—")
        n_sc = data.get("correct", {}).get("n", "—")
        lines.append(f"| `{sc}` | {c_sr} | {s_sr} | {r_sr} | {n_sc} |")

    (out_dir / "report.md").write_text("\n".join(lines))

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\nLanguage-dependence controls: {len(per_ep_records)} episodes")
    print(f"\n{'Condition':<16} {'SR@3m':>7}  {'95% CI':>18}  {'MRR':>6}  {'FinalRate':>9}")
    print("-" * 65)
    for cond in conditions:
        s = agg.get(cond, {})
        if not s:
            continue
        ci = f"[{s['sr_ci95_lo']:.3f}, {s['sr_ci95_hi']:.3f}]"
        print(f"{cond:<16} {s['sr_at_3m']:>7.3f}  {ci:>18}  {s['mrr']:>6.3f}  {s['final_frame_rate']:>9.3f}")
    print(f"\nCorrect vs shuffled delta: {delta_shuffled}")
    print(f"Correct vs constant delta: {delta_constant}")
    print(f"Language dependence: {lang_dep_concluded}")
    print(f"\nOutput: {out_dir}")


if __name__ == "__main__":
    main()
