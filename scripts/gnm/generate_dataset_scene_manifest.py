#!/usr/bin/env python3
"""Generate dataset and scene manifest for the GNM-VLNVerse Track A study."""

from __future__ import annotations

import csv
import json
import pickle
import re
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "datasets" / "vlntube"
OUT_DIR = REPO_ROOT / "results" / "bo_reviewer_packet"

OUT_MD = OUT_DIR / "28_dataset_scene_manifest.md"
OUT_CSV = OUT_DIR / "28_dataset_scene_manifest.csv"
OUT_JSON = OUT_DIR / "28_dataset_scene_manifest.json"

SCENE_RE = re.compile(r"kujiale_[0-9]{4}")


UPSTREAM_SOURCES = [
    {
        "name": "VLNVerse data on Hugging Face",
        "url": "https://huggingface.co/datasets/Eyz/VLNVerse_data",
    },
    {
        "name": "VLNVerse paper",
        "url": "https://arxiv.org/abs/2512.19021",
    },
]


def scene_id_from_name(name: str) -> str:
    match = SCENE_RE.search(name)
    return match.group(0) if match else "unknown"


def safe_shape(value: Any) -> str:
    shape = getattr(value, "shape", None)
    if shape is not None:
        return "x".join(str(x) for x in shape)
    if isinstance(value, (list, tuple)):
        return f"len={len(value)}"
    if isinstance(value, dict):
        return f"keys={len(value)}"
    return type(value).__name__


def inspect_traj_pickle(path: Path) -> dict:
    try:
        with path.open("rb") as f:
            obj = pickle.load(f)
    except Exception as exc:
        return {
            "path": str(path.relative_to(REPO_ROOT)),
            "readable": False,
            "error": repr(exc),
            "keys": [],
            "shapes": {},
        }

    keys = []
    shapes = {}

    if isinstance(obj, dict):
        keys = sorted(str(k) for k in obj.keys())
        for key in keys:
            try:
                shapes[key] = safe_shape(obj[key])
            except Exception:
                shapes[key] = "unavailable"
    else:
        keys = [type(obj).__name__]
        shapes = {"object": safe_shape(obj)}

    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "readable": True,
        "error": "",
        "keys": keys,
        "shapes": shapes,
    }


def collect_split(split: str) -> dict:
    split_dir = DATA_ROOT / split
    traj_files = sorted(split_dir.glob("*/traj_data.pkl")) if split_dir.exists() else []
    traj_dirs = [p.parent for p in traj_files]

    scene_counts = Counter(scene_id_from_name(d.name) for d in traj_dirs)

    examples = []
    for traj_path in traj_files[:5]:
        examples.append(inspect_traj_pickle(traj_path))

    return {
        "split": split,
        "path": str(split_dir.relative_to(REPO_ROOT)) if split_dir.exists() else str(split_dir),
        "exists": split_dir.exists(),
        "trajectory_count": len(traj_files),
        "scene_counts": dict(sorted(scene_counts.items())),
        "example_trajectories": examples,
    }


def collect_envs() -> dict:
    env_dir = DATA_ROOT / "envs"
    env_items = []

    if env_dir.exists():
        for p in sorted(env_dir.iterdir()):
            if not p.exists() or p.name.startswith("."):
                continue

            scene_id = scene_id_from_name(p.name)
            if scene_id == "unknown":
                continue

            if p.is_dir():
                files = sorted(
                    x for x in p.rglob("*")
                    if x.is_file()
                    and not any(part.startswith(".") for part in x.relative_to(p).parts)
                )
                suffix_counts = Counter(x.suffix.lower() or "[no_suffix]" for x in files)
                env_items.append(
                    {
                        "scene_id": scene_id,
                        "name": p.name,
                        "path": str(p.relative_to(REPO_ROOT)),
                        "type": "directory",
                        "file_count": len(files),
                        "suffix_counts": dict(sorted(suffix_counts.items())),
                        "sample_files": [str(x.relative_to(REPO_ROOT)) for x in files[:10]],
                    }
                )
            elif p.is_file():
                env_items.append(
                    {
                        "scene_id": scene_id,
                        "name": p.name,
                        "path": str(p.relative_to(REPO_ROOT)),
                        "type": "file",
                        "file_count": 1,
                        "suffix_counts": {p.suffix.lower() or "[no_suffix]": 1},
                        "sample_files": [str(p.relative_to(REPO_ROOT))],
                    }
                )

    scene_ids = sorted({x["scene_id"] for x in env_items if x["scene_id"] != "unknown"})

    return {
        "path": str(env_dir.relative_to(REPO_ROOT)) if env_dir.exists() else str(env_dir),
        "exists": env_dir.exists(),
        "scene_ids": scene_ids,
        "scene_count": len(scene_ids),
        "items": env_items,
    }


def write_csv(train: dict, val: dict, envs: dict) -> None:
    scene_ids = sorted(
        set(train["scene_counts"])
        | set(val["scene_counts"])
        | set(envs["scene_ids"])
    )

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scene_id",
                "train_trajectories",
                "val_trajectories",
                "env_present",
            ],
        )
        writer.writeheader()

        for scene_id in scene_ids:
            writer.writerow(
                {
                    "scene_id": scene_id,
                    "train_trajectories": train["scene_counts"].get(scene_id, 0),
                    "val_trajectories": val["scene_counts"].get(scene_id, 0),
                    "env_present": scene_id in envs["scene_ids"],
                }
            )


def format_scene_table(train: dict, val: dict, envs: dict) -> list[str]:
    scene_ids = sorted(
        set(train["scene_counts"])
        | set(val["scene_counts"])
        | set(envs["scene_ids"])
    )

    lines = [
        "| Scene ID | Train trajectories | Validation trajectories | Env asset present |",
        "|---|---:|---:|---:|",
    ]

    for scene_id in scene_ids:
        lines.append(
            f"| {scene_id} | "
            f"{train['scene_counts'].get(scene_id, 0)} | "
            f"{val['scene_counts'].get(scene_id, 0)} | "
            f"{'yes' if scene_id in envs['scene_ids'] else 'no'} |"
        )

    return lines


def format_example_block(split: dict) -> list[str]:
    lines = []
    for example in split["example_trajectories"]:
        lines.append(f"### {example['path']}")
        lines.append("")
        lines.append(f"- Readable: {example['readable']}")
        if example["error"]:
            lines.append(f"- Error: `{example['error']}`")
        lines.append("- Keys/shapes:")
        for key in example["keys"]:
            lines.append(f"  - `{key}`: `{example['shapes'].get(key, '')}`")
        lines.append("")
    return lines


def write_markdown(train: dict, val: dict, envs: dict) -> None:
    md = [
        "# Dataset and Scene Manifest — GNM-VLNVerse Track A",
        "",
        "This document records the local dataset and scene evidence used by the GNM-VLNVerse Track A study.",
        "",
        "The purpose is to answer supervisor/reviewer questions about which trajectories, scenes, labels, and local files are used.",
        "",
        "## Upstream sources",
        "",
    ]

    for item in UPSTREAM_SOURCES:
        md.append(f"- {item['name']}: {item['url']}")

    md.extend(
        [
            "",
            "## Local dataset roots",
            "",
            f"- Train root: `{train['path']}`",
            f"- Validation root: `{val['path']}`",
            f"- Environment root: `{envs['path']}`",
            "",
            "## Local split summary",
            "",
            f"- Train trajectory files: {train['trajectory_count']}",
            f"- Validation trajectory files: {val['trajectory_count']}",
            f"- Local environment scenes detected: {envs['scene_count']}",
            "",
            "## Scene-level manifest",
            "",
        ]
    )

    md.extend(format_scene_table(train, val, envs))

    md.extend(
        [
            "",
            "## Environment asset inventory",
            "",
            "| Scene ID | Local path | Type | File count | Suffix counts |",
            "|---|---|---|---:|---|",
        ]
    )

    for item in envs["items"]:
        suffix_counts = ", ".join(f"{k}: {v}" for k, v in item["suffix_counts"].items())
        md.append(
            f"| {item['scene_id']} | `{item['path']}` | {item['type']} | "
            f"{item['file_count']} | {suffix_counts} |"
        )

    md.extend(
        [
            "",
            "## Example train trajectory structures",
            "",
        ]
    )
    md.extend(format_example_block(train))

    md.extend(
        [
            "## Example validation trajectory structures",
            "",
        ]
    )
    md.extend(format_example_block(val))

    md.extend(
        [
            "## Shareable evidence commands",
            "",
            "The following commands can be used to show the dataset layout without exposing the full image/asset contents:",
            "",
            "```bash",
            "find datasets/vlntube -maxdepth 3 -type f | head -80",
            "find datasets/vlntube/train -maxdepth 2 -type f | head -40",
            "find datasets/vlntube/val -maxdepth 2 -type f | head -40",
            "find datasets/vlntube/envs -maxdepth 3 -type f | head -80",
            "```",
            "",
            "The stable Isaac live trajectory demo can be run with:",
            "",
            "```bash",
            "conda activate isaac",
            "python scripts/gnm/isaac_live_trajectory_demo.py",
            "```",
            "",
            "## Interpretation",
            "",
            "This manifest confirms the concrete local files used for training, validation, scene lookup, and live Isaac trajectory replay.",
            "",
            "The source-code release packages the scripts and evidence summaries. Full image trajectories and scene assets should be shared separately if a supervisor requests the dataset payload itself, because those assets may be large.",
            "",
        ]
    )

    OUT_MD.write_text("\n".join(md))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    train = collect_split("train")
    val = collect_split("val")
    envs = collect_envs()

    data = {
        "data_root": str(DATA_ROOT.relative_to(REPO_ROOT)),
        "upstream_sources": UPSTREAM_SOURCES,
        "train": train,
        "val": val,
        "envs": envs,
    }

    OUT_JSON.write_text(json.dumps(data, indent=2))
    write_csv(train, val, envs)
    write_markdown(train, val, envs)

    print(f"[OK] wrote {OUT_MD}")
    print(f"[OK] wrote {OUT_CSV}")
    print(f"[OK] wrote {OUT_JSON}")
    print(f"[SUMMARY] train={train['trajectory_count']} val={val['trajectory_count']} env_scenes={envs['scene_count']}")


if __name__ == "__main__":
    main()
