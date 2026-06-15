#!/usr/bin/env python3
"""Gate B: Audit authentic local language-grounding data for Track B.

Searches for VLNVerse, VLNTube, and Kujiale data roots and classifies
every source for language instructions, RGB images, trajectory poses,
goal annotations, and split files.

Source classifications
----------------------
benchmark_provided          Official VLNVerse / VLNTube benchmark data
upstream_repository_provided Data from the upstream VLNTube repository
project_authored            Created by this project (non-synthetic)
project_authored_synthetic  Created by this project as synthetic dry-run
templated                   Generated from templates (not hand-authored)
synthetic                   Machine-generated (Gemini, LLM, etc.)
unknown                     Cannot determine origin

Outputs
-------
results/track_b_language/data_audit/audit.json
results/track_b_language/data_audit/audit.md
results/track_b_language/data_audit/dataset_roots.jsonl
results/track_b_language/data_audit/instruction_sources.jsonl
results/track_b_language/data_audit/image_sources.jsonl
results/track_b_language/data_audit/trajectory_sources.jsonl
results/track_b_language/data_audit/missing_fields.jsonl

Usage
-----
    python3 scripts/gnm/audit_track_b_language_data.py
    python3 scripts/gnm/audit_track_b_language_data.py --output-dir results/track_b_language/data_audit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Known data roots to search
_CANDIDATE_ROOTS = [
    REPO / "datasets/vlnverse",
    REPO / "datasets/vlntube",
    REPO / "datasets/custom_vln_office",
    REPO / "external/VLNTube",
    Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark/datasets/vlntube"),
    Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark/datasets/vlnverse"),
    Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark/external/VLNTube"),
]


def _sha256_file(path: Path, max_bytes: int = 65536) -> str:
    """Hash first max_bytes of a file for content fingerprinting."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read(max_bytes))
        return h.hexdigest()[:16]
    except Exception:
        return "unavailable"


def _mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return "unknown"


def _classify_instruction_source(text: str | None, path: Path | None = None) -> str:
    """Classify instruction source from content and origin path."""
    if text is None:
        return "unknown"
    text_l = text.lower()
    if path is not None:
        path_s = str(path).lower()
        if "gemini" in path_s or "llm" in path_s or "generated" in path_s:
            return "synthetic"
        if "iamgoodnavigator" in path_s or "vlnverse" in path_s:
            if "imported" in path_s or "benchmark" in path_s:
                return "benchmark_provided"
        if "vlntube" in path_s and ("prebuilt" in path_s or "final_splits" in path_s):
            return "upstream_repository_provided"
    # Heuristic: benchmark instructions tend to have specific navigation verbs
    if any(kw in text_l for kw in ["walk forward", "turn left", "turn right", "proceed", "stop at"]):
        if len(text) > 80:
            return "benchmark_provided"
    return "unknown"


def _audit_custom_vln_office(root: Path) -> dict:
    """Audit the custom_vln_office synthetic diagnostic dataset."""
    result = {
        "dataset_id":          "custom_vln_office",
        "dataset_root":        str(root),
        "dataset_type":        "synthetic_dry_run",
        "source_classification": "project_authored_synthetic",
        "evidence":            "provenance.json per episode + dataset_provenance.json",
        "splits_available":    [],
        "episode_count":       0,
        "instruction_count":   0,
        "image_count":         0,
        "trajectory_count":    0,
        "has_goal_pos":        False,
        "has_language_instructions": False,
        "has_real_images":     False,
        "has_independent_targets": False,
        "missing_fields":      [],
        "episodes":            [],
        "dataset_provenance":  None,
    }

    if not root.is_dir():
        result["missing_fields"].append("dataset_root")
        return result

    ds_prov_path = root / "dataset_provenance.json"
    if ds_prov_path.exists():
        result["dataset_provenance"] = json.loads(ds_prov_path.read_text())

    for split in ("train", "val", "test"):
        split_dir = root / split
        if not split_dir.is_dir():
            continue
        result["splits_available"].append(split)
        for ep_dir in sorted(split_dir.iterdir()):
            pkl = ep_dir / "traj_data.pkl"
            if not pkl.exists():
                continue
            data = pickle.loads(pkl.read_bytes())
            instr = data.get("instruction", "")
            images = list((ep_dir / "rgb").glob("*.jpg")) if (ep_dir / "rgb").is_dir() else []
            goal = data.get("goal_pos")
            result["episode_count"] += 1
            result["instruction_count"] += 1 if instr else 0
            result["image_count"] += len(images)
            result["trajectory_count"] += 1
            result["has_goal_pos"] = result["has_goal_pos"] or (goal is not None)
            result["has_language_instructions"] = result["has_language_instructions"] or bool(instr)
            result["episodes"].append({
                "episode_id":     data.get("episode_id", ep_dir.name),
                "split":          split,
                "instruction":    instr,
                "n_images":       len(images),
                "has_goal_pos":   goal is not None,
                "instruction_source": "project_authored_synthetic_dry_run",
                "image_source":   "synthetic_gradient_dry_run",
            })

    result["has_independent_targets"] = False  # goal == last trajectory position
    result["missing_fields"] = (
        ["independent_target_annotation"] +
        (["language_instructions"] if not result["has_language_instructions"] else []) +
        (["real_images"] if not result["has_real_images"] else [])
    )
    return result


def _audit_vlntube_real(root: Path, label: str = "vlntube_fleetsafe") -> dict:
    """Audit the VLNTube real-image trajectory dataset (FleetSafe copy)."""
    result = {
        "dataset_id":            label,
        "dataset_root":          str(root),
        "dataset_type":          "real_kujiale_trajectories",
        "source_classification": "upstream_repository_provided",
        "evidence":              "traj_data.pkl with position/yaw; JPG images; episode_info.json with goal_pos",
        "splits_available":      [],
        "episode_count":         0,
        "instruction_count":     0,
        "image_count":           0,
        "trajectory_count":      0,
        "has_goal_pos":          False,
        "has_language_instructions": False,
        "has_real_images":       False,
        "has_independent_targets": False,
        "missing_fields":        [],
        "scenes":                set(),
        "episodes":              [],
    }

    if not root.is_dir():
        result["missing_fields"].append("dataset_root")
        result["scenes"] = []
        return result

    for split in ("train", "val", "test"):
        split_dir = root / split
        if not split_dir.is_dir():
            continue
        result["splits_available"].append(split)
        for ep_dir in sorted(split_dir.iterdir()):
            pkl = ep_dir / "traj_data.pkl"
            if not pkl.exists():
                continue
            data = pickle.loads(pkl.read_bytes())
            images = list(ep_dir.glob("*.jpg"))
            ep_info_path = ep_dir / "episode_info.json"
            ep_info = json.loads(ep_info_path.read_text()) if ep_info_path.exists() else {}
            goal = ep_info.get("goal_pos")
            scan = ep_info.get("scan", ep_dir.name.rsplit("_", 2)[0] if "_" in ep_dir.name else "unknown")
            result["scenes"].add(scan)
            result["episode_count"] += 1
            result["image_count"] += len(images)
            result["trajectory_count"] += 1
            result["has_goal_pos"] = result["has_goal_pos"] or (goal is not None)
            result["has_real_images"] = result["has_real_images"] or len(images) > 0
            result["has_independent_targets"] = result["has_goal_pos"]
            result["episodes"].append({
                "episode_id":          ep_dir.name,
                "split":               split,
                "scan":                scan,
                "n_images":            len(images),
                "has_goal_pos":        goal is not None,
                "has_instruction":     False,
                "instruction_source":  "unknown",
                "image_source":        "real_camera",
            })

    result["scenes"] = sorted(result["scenes"])
    result["missing_fields"] = (
        ["language_instructions"] +
        ([] if result["has_goal_pos"] else ["goal_pos"]) +
        ([] if result["has_real_images"] else ["real_images"])
    )
    return result


def _audit_vlntube_prebuilt(root: Path) -> dict:
    """Audit the VLNTube prebuilt trajectory data with benchmark instructions."""
    result = {
        "dataset_id":            "vlntube_prebuilt",
        "dataset_root":          str(root),
        "dataset_type":          "vlntube_benchmark_trajectories",
        "source_classification": "upstream_repository_provided",
        "evidence":              "episodes.jsonl with instruction_text; rgb.npy image arrays",
        "splits_available":      [],
        "episode_count":         0,
        "instruction_count":     0,
        "image_count":           0,
        "trajectory_count":      0,
        "has_goal_pos":          False,
        "has_language_instructions": False,
        "has_real_images":       False,
        "has_independent_targets": False,
        "missing_fields":        [],
        "scenes":                set(),
        "episodes":              [],
    }

    traj_dir = root / "prebuilt_data" / "traj_data" / "vlnverse"
    if not traj_dir.is_dir():
        result["missing_fields"].append("prebuilt_data/traj_data/vlnverse")
        result["scenes"] = []
        return result

    for scene_dir in sorted(traj_dir.iterdir()):
        if not scene_dir.is_dir():
            continue
        result["scenes"].add(scene_dir.name)
        for ep_dir in sorted(scene_dir.iterdir()):
            if not ep_dir.is_dir():
                continue
            episodes_file = ep_dir / "meta" / "episodes.jsonl"
            rgb_file = ep_dir / "videos" / "chunk-000" / "observation.images.rgb" / "rgb.npy"
            if not episodes_file.exists():
                continue
            result["splits_available"] = ["prebuilt"]
            for line in episodes_file.read_text().splitlines():
                if not line.strip():
                    continue
                ep = json.loads(line)
                instr = ep.get("instruction_text", "")
                result["episode_count"] += 1
                result["instruction_count"] += 1 if instr else 0
                result["has_language_instructions"] = result["has_language_instructions"] or bool(instr)
                has_img = rgb_file.exists()
                result["has_real_images"] = result["has_real_images"] or has_img
                result["episodes"].append({
                    "episode_id":         ep.get("episode_id"),
                    "scan":               scene_dir.name,
                    "instruction":        instr[:120] + "..." if len(instr) > 120 else instr,
                    "has_rgb":            has_img,
                    "instruction_source": _classify_instruction_source(instr, episodes_file),
                    "image_source":       "real_camera" if has_img else "unknown",
                    "finish_status":      ep.get("finish_status"),
                })

    result["scenes"] = sorted(result["scenes"])
    result["has_independent_targets"] = False  # no goal_pos in prebuilt meta
    result["missing_fields"] = (
        ([] if result["has_language_instructions"] else ["language_instructions"]) +
        ([] if result["has_real_images"] else ["rgb_images"]) +
        ["goal_pos", "independent_target_annotation"]
    )
    return result


def _audit_vlnverse_imported(root: Path) -> dict:
    """Audit VLNVerse imported episode metadata (IAmGoodNavigator results)."""
    result = {
        "dataset_id":            "vlnverse_imported",
        "dataset_root":          str(root),
        "dataset_type":          "vlnverse_navigator_runs",
        "source_classification": "benchmark_provided",
        "evidence":              "imported/iamgoodnavigator/*/episode_meta.json",
        "episode_count":         0,
        "instruction_count":     0,
        "image_count":           0,
        "trajectory_count":      0,
        "has_goal_pos":          False,
        "has_language_instructions": False,
        "has_real_images":       False,
        "has_independent_targets": False,
        "missing_fields":        [],
        "episodes":              [],
    }

    imported_dir = root / "imported" / "iamgoodnavigator"
    if not imported_dir.is_dir():
        result["missing_fields"].append("imported/iamgoodnavigator")
        return result

    for run_dir in sorted(imported_dir.iterdir()):
        meta_file = run_dir / "episode_meta.json"
        if not meta_file.exists():
            continue
        meta = json.loads(meta_file.read_text())
        instr = meta.get("instruction", "")
        images = meta.get("file_counts", {}).get("images", 0)
        trajs  = meta.get("file_counts", {}).get("trajectories", 0)
        result["episode_count"] += 1
        result["instruction_count"] += 1 if instr else 0
        result["image_count"] += images
        result["trajectory_count"] += trajs
        result["has_language_instructions"] = result["has_language_instructions"] or bool(instr)
        result["has_real_images"] = result["has_real_images"] or images > 0
        result["episodes"].append({
            "episode_id":         meta.get("scan_id", run_dir.name),
            "instruction":        instr[:120] + "..." if len(instr) > 120 else instr,
            "instruction_source": _classify_instruction_source(instr, meta_file),
            "image_source":       "real_camera" if images > 0 else "unknown",
            "n_images":           images,
            "n_trajectories":     trajs,
            "finish_status":      meta.get("status"),
        })

    result["missing_fields"] = (
        ([] if result["has_language_instructions"] else ["language_instructions"]) +
        ([] if result["has_real_images"] else ["rgb_images"]) +
        ["independent_target_annotation"]
    )
    return result


def _gate_b_decision(audits: dict) -> tuple[str, str]:
    """Determine Gate B readiness decision.

    All three conditions must be present in the SAME dataset/episode set:
      1. Real camera images
      2. Authentic language instructions
      3. Independently established targets (goal_pos or target frame from benchmark)
    Returns (decision_code, rationale).
    """
    total_real_images  = sum(a.get("image_count", 0) for a in audits.values()
                             if a.get("has_real_images", False))
    total_authentic    = sum(a.get("instruction_count", 0) for a in audits.values()
                             if a.get("has_language_instructions", False)
                             and a.get("source_classification") not in (
                                 "project_authored_synthetic", "unknown"
                             ))

    # READY_FOR_BENCHMARK requires all three in the SAME dataset
    fully_ready = [
        name for name, a in audits.items()
        if a.get("has_real_images", False)
        and a.get("has_language_instructions", False)
        and a.get("has_independent_targets", False)
        and a.get("episode_count", 0) > 0
        and a.get("instruction_count", 0) > 0
        and a.get("image_count", 0) > 0
    ]

    if fully_ready:
        n_ep = sum(audits[n]["episode_count"] for n in fully_ready)
        return (
            "READY_FOR_BENCHMARK_LANGUAGE_EVALUATION",
            (
                f"Datasets {fully_ready} have real images, authentic instructions, "
                f"and independently established targets for {n_ep} episodes."
            ),
        )

    if total_real_images == 0:
        return (
            "BLOCKED_MISSING_REAL_IMAGE_OR_POSE_DATA",
            "No real camera images found in any audited data root.",
        )

    # Real images exist but instruction+image+target not colocated in any single dataset
    real_with_goals = [name for name, a in audits.items()
                       if a.get("has_real_images", False)
                       and a.get("has_independent_targets", False)]
    datasets_with_instructions = [name for name, a in audits.items()
                                   if a.get("has_language_instructions", False)]
    return (
        "READY_FOR_PROJECT_AUTHORED_ANNOTATION",
        (
            f"Real images present: {total_real_images} images. "
            f"Datasets with real images + goal_pos: {real_with_goals}. "
            f"Datasets with authentic instructions: {datasets_with_instructions} "
            f"({total_authentic} instructions). "
            "Instructions and real images are NOT colocated within any single episode set. "
            "Action required: pair vlntube_fleetsafe episodes (real images + goal_pos) "
            "with language instructions via data/track_b_annotations/ before CLIP evaluation."
        ),
    )


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", default="results/track_b_language/data_audit",
                        help="Output directory for audit artefacts")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    print("Track B Language Data Audit")
    print("=" * 60)

    # ── Run all audits ────────────────────────────────────────────────────────
    audits: dict[str, dict] = {}

    audits["custom_vln_office"] = _audit_custom_vln_office(
        REPO / "datasets/custom_vln_office"
    )
    audits["vlntube_fleetsafe"] = _audit_vlntube_real(
        Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark/datasets/vlntube")
    )
    audits["vlntube_prebuilt"] = _audit_vlntube_prebuilt(
        Path("/home/favl/robotics/FleetSafe-VisualNav-Benchmark/datasets/vlntube")
    )
    audits["vlnverse_imported"] = _audit_vlnverse_imported(
        REPO / "datasets/vlnverse"
    )

    for name, audit in audits.items():
        print(f"\n  {name}")
        print(f"    root          : {audit['dataset_root']}")
        print(f"    type          : {audit['dataset_type']}")
        print(f"    classification: {audit['source_classification']}")
        print(f"    episodes      : {audit['episode_count']}")
        print(f"    instructions  : {audit['instruction_count']}")
        print(f"    images        : {audit['image_count']}")
        print(f"    has_real_imgs : {audit['has_real_images']}")
        print(f"    has_instruct  : {audit['has_language_instructions']}")
        print(f"    indep_targets : {audit['has_independent_targets']}")
        if audit.get('missing_fields'):
            print(f"    missing       : {', '.join(audit['missing_fields'])}")

    decision_code, decision_rationale = _gate_b_decision(audits)

    print()
    print(f"\nGate B Decision: {decision_code}")
    print(f"  {decision_rationale}")

    # ── Build output records ──────────────────────────────────────────────────

    dataset_roots = []
    instruction_sources = []
    image_sources = []
    trajectory_sources = []
    missing_fields_records = []

    for name, audit in audits.items():
        dataset_roots.append({
            "dataset_id":            name,
            "absolute_path":         audit["dataset_root"],
            "source_classification": audit["source_classification"],
            "episode_count":         audit["episode_count"],
            "instruction_count":     audit["instruction_count"],
            "image_count":           audit["image_count"],
            "trajectory_count":      audit["trajectory_count"],
            "has_real_images":       audit["has_real_images"],
            "has_language_instructions": audit["has_language_instructions"],
            "has_independent_targets": audit["has_independent_targets"],
            "splits_available":      audit.get("splits_available", []),
        })
        for ep in audit.get("episodes", [])[:50]:  # cap per-episode records
            instruction_sources.append({
                "dataset_id":         name,
                "episode_id":         ep.get("episode_id"),
                "instruction_source": ep.get("instruction_source", "unknown"),
                "has_instruction":    bool(ep.get("instruction") or ep.get("has_instruction")),
            })
            image_sources.append({
                "dataset_id":   name,
                "episode_id":   ep.get("episode_id"),
                "image_source": ep.get("image_source", "unknown"),
                "n_images":     ep.get("n_images", ep.get("has_rgb", False)),
            })
            trajectory_sources.append({
                "dataset_id":    name,
                "episode_id":    ep.get("episode_id"),
                "has_positions": True,
                "has_goal_pos":  ep.get("has_goal_pos", False),
            })
        for field in audit.get("missing_fields", []):
            missing_fields_records.append({
                "dataset_id": name,
                "field":      field,
            })

    # aggregate audit JSON
    aggregate = {
        "audit_timestamp":   timestamp,
        "audited_roots":     len(audits),
        "gate_b_decision":   decision_code,
        "gate_b_rationale":  decision_rationale,
        "datasets":          {
            name: {
                k: v for k, v in audit.items()
                if k != "episodes"  # keep top-level only
            }
            for name, audit in audits.items()
        },
        "totals": {
            "total_episodes":     sum(a["episode_count"] for a in audits.values()),
            "total_instructions": sum(a["instruction_count"] for a in audits.values()),
            "total_images":       sum(a["image_count"] for a in audits.values()),
            "authentic_instructions": sum(
                a["instruction_count"] for a in audits.values()
                if a.get("source_classification") not in (
                    "project_authored_synthetic", "unknown"
                )
            ),
            "real_image_count":   sum(
                a["image_count"] for a in audits.values()
                if a.get("has_real_images", False)
            ),
            "anchored_episodes":  sum(
                a["episode_count"] for a in audits.values()
                if a.get("has_independent_targets", False)
            ),
        },
    }

    (out_dir / "audit.json").write_text(json.dumps(aggregate, indent=2))
    _write_jsonl(out_dir / "dataset_roots.jsonl", dataset_roots)
    _write_jsonl(out_dir / "instruction_sources.jsonl", instruction_sources)
    _write_jsonl(out_dir / "image_sources.jsonl", image_sources)
    _write_jsonl(out_dir / "trajectory_sources.jsonl", trajectory_sources)
    _write_jsonl(out_dir / "missing_fields.jsonl", missing_fields_records)

    # Markdown report
    md_lines = [
        "# Track B Language Data Audit",
        "",
        f"**Date:** {timestamp[:10]}  ",
        f"**Audited data roots:** {len(audits)}",
        "",
        f"## Gate B Decision: `{decision_code}`",
        "",
        f"> {decision_rationale}",
        "",
        "## Dataset Summary",
        "",
        "| Dataset | Type | Source | Episodes | Instructions | Images | Real Images | Indep. Targets |",
        "|---------|------|--------|----------|--------------|--------|-------------|----------------|",
    ]
    for name, a in audits.items():
        md_lines.append(
            f"| {name} | {a['dataset_type']} | {a['source_classification']} "
            f"| {a['episode_count']} | {a['instruction_count']} | {a['image_count']} "
            f"| {'✓' if a['has_real_images'] else '✗'} "
            f"| {'✓' if a['has_independent_targets'] else '✗'} |"
        )

    md_lines += [
        "",
        "## Totals",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total episodes | {aggregate['totals']['total_episodes']} |",
        f"| Total instructions | {aggregate['totals']['total_instructions']} |",
        f"| Authentic instructions (non-synthetic) | {aggregate['totals']['authentic_instructions']} |",
        f"| Total images | {aggregate['totals']['total_images']} |",
        f"| Real camera images | {aggregate['totals']['real_image_count']} |",
        f"| Independently anchored episodes | {aggregate['totals']['anchored_episodes']} |",
        "",
        "## Missing Fields Per Dataset",
        "",
    ]
    for name, a in audits.items():
        if a.get("missing_fields"):
            md_lines.append(f"**{name}:** {', '.join(a['missing_fields'])}")
    md_lines += [
        "",
        "## Classification Guide",
        "",
        "| Code | Meaning |",
        "|------|---------|",
        "| `benchmark_provided` | Official VLNVerse or VLNTube benchmark data |",
        "| `upstream_repository_provided` | From the VLNTube repository |",
        "| `project_authored_synthetic` | Created by this project (synthetic, dry-run) |",
        "| `project_authored` | Created by this project (non-synthetic) |",
        "| `synthetic` | Machine-generated instructions (LLM/Gemini) |",
        "| `unknown` | Origin cannot be determined |",
        "",
        "## Next Steps",
        "",
        f"**Decision: {decision_code}**",
        "",
    ]
    if decision_code == "READY_FOR_PROJECT_AUTHORED_ANNOTATION":
        md_lines += [
            "Real camera images and pose data are available. To proceed:",
            "",
            "1. Create `data/track_b_annotations/schema.json`",
            "2. For each VLNTube episode, freeze a target frame index independently of model retrieval",
            "3. Write `train.jsonl` and `validation.jsonl` with episode_id, instruction, target_frame_idx",
            "4. Hash and freeze annotation manifest before evaluation",
            "5. Only then run CLIP retrieval against these targets",
        ]
    elif decision_code == "BLOCKED_MISSING_REAL_IMAGE_OR_POSE_DATA":
        md_lines += [
            "Real image data is missing. Obtain:",
            "- VLNTube rendered images (requires Isaac Sim)",
            "- Or a pre-rendered VLNTube image dataset",
        ]

    (out_dir / "audit.md").write_text("\n".join(md_lines))

    print(f"\nAudit artefacts written to: {out_dir}")
    for f in sorted(out_dir.iterdir()):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
