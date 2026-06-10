#!/usr/bin/env python3
"""
setup_gnm_indoor_datasets.py
============================
Download and catalogue public GNM training datasets that are relevant to
indoor / hospital-corridor navigation for the FleetSafe-VisualNav-Benchmark.

Background
----------
GNM (General Navigation Model) was trained on a mixture of outdoor and indoor
datasets.  For fine-tuning on hospital/clinic corridor navigation the most
relevant public datasets are:

  GoStanford2  — Stanford University indoor office/corridor footage collected
                 with a mobile robot.  This is the closest match to hospital
                 hallways in the GNM training corpus.  Part of the
                 drive-any-robot (DARo) data release.

  SCAND        — UT Austin Social-Comfort-Aware Navigation Dataset.  Contains
                 both indoor and outdoor sequences (indoor component is mainly
                 office/lab corridors).  Publicly available; some sequences are
                 directly GNM-compatible.

  TartanDrive  — Primarily outdoor (off-road), included for completeness but
                 low relevance for hospital navigation.

  RECON        — Outdoor exploration, not relevant for indoor fine-tuning.

Usage
-----
  # Download everything (will prompt for manual steps where required)
  python scripts/data/setup_gnm_indoor_datasets.py

  # Single dataset
  python scripts/data/setup_gnm_indoor_datasets.py --dataset gostanford2
  python scripts/data/setup_gnm_indoor_datasets.py --dataset scand

  # Custom output directory
  python scripts/data/setup_gnm_indoor_datasets.py --data-dir /mnt/ssd/gnm_data

The script creates:
  <data_dir>/
    dataset_registry.json          — machine-readable catalogue of datasets
    README.md                      — human-readable notes
    gostanford2/                   — GoStanford2 data (if downloaded)
    scand/                         — SCAND data (if downloaded)
    yahboom_hospital/              — placeholder for real-robot recordings
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path


# ── Dataset registry ──────────────────────────────────────────────────────────

DATASET_REGISTRY: dict[str, dict] = {
    "gostanford2": {
        "name": "GoStanford2",
        "description": (
            "Stanford University indoor office and corridor navigation dataset. "
            "Collected with a ground robot traversing hallways and open spaces "
            "inside the Gates Computer Science Building.  The closest match in "
            "the GNM training corpus to hospital corridor navigation."
        ),
        "relevance_for_hospital": "HIGH",
        "environment": "indoor",
        "scenes": ["corridors", "offices", "open_areas", "doorways"],
        "gnm_format_compatible": True,
        "format_notes": (
            "Folders named traj_NNNN/ each containing numbered JPG images "
            "(0.jpg, 1.jpg, …) and traj_data.pkl with keys 'position' "
            "(shape [T,2]) and 'yaw' (shape [T])."
        ),
        "approximate_trajectories": 3000,
        "approximate_size_gb": 8.5,
        "access": "request",
        "access_notes": (
            "GoStanford2 is distributed as part of the drive-any-robot (DARo) "
            "dataset release.  Access is via the project page: "
            "https://sites.google.com/view/drive-any-robot\n"
            "Direct download link is provided after accepting the data-use "
            "agreement on the project page or the associated HuggingFace repo:\n"
            "  https://huggingface.co/datasets/robodhruv/drive-any-robot\n"
            "Once downloaded, extract to <data_dir>/gostanford2/ so that "
            "traj_data.pkl files live at "
            "<data_dir>/gostanford2/<split>/<traj_id>/traj_data.pkl"
        ),
        "citation": (
            "Shah, D., Osinski, B., Ichter, B., & Levine, S. (2023). "
            "GNM: A General Navigation Model to Drive Any Robot. "
            "ICRA 2023. https://arxiv.org/abs/2210.03370"
        ),
        "huggingface_url": "https://huggingface.co/datasets/robodhruv/drive-any-robot",
        "project_url": "https://sites.google.com/view/drive-any-robot",
    },
    "scand": {
        "name": "SCAND (Social Comfort-Aware Navigation Dataset)",
        "description": (
            "UT Austin dataset of human-accompanying navigation in both indoor "
            "(office/lab corridors) and outdoor (sidewalks, plazas) environments. "
            "Contains ROS bag recordings plus processed image+odometry data. "
            "The indoor splits are relevant for hospital hallway navigation."
        ),
        "relevance_for_hospital": "MEDIUM",
        "environment": "indoor_and_outdoor",
        "scenes": ["indoor_corridors", "sidewalks", "plazas", "crossings"],
        "gnm_format_compatible": "partial",
        "format_notes": (
            "Distributed as ROS1 bags and processed HDF5/pickle files. "
            "The processed format includes image sequences and odometry. "
            "Use gnm_dataset_converter.py to convert to GNM traj format."
        ),
        "approximate_trajectories": 138,
        "approximate_size_gb": 25.0,
        "access": "public",
        "access_notes": (
            "SCAND is freely downloadable from the UT Austin project page:\n"
            "  https://cs.utexas.edu/~xiao/SCAND/SCAND.html\n"
            "Download the 'processed data' archive for GNM-compatible sequences."
        ),
        "download_url_page": "https://cs.utexas.edu/~xiao/SCAND/SCAND.html",
        "citation": (
            "Karnan, H., Nair, A., Xiao, X., Warnell, G., Pirk, S., Toshev, A., "
            "Hart, J., Biswas, J., & Stone, P. (2022). SCAND: A Large-Scale Dataset "
            "of Human-Driven Robot Navigation. RA-L 2022. "
            "https://arxiv.org/abs/2203.13924"
        ),
        "project_url": "https://cs.utexas.edu/~xiao/SCAND/SCAND.html",
    },
    "tartandrive": {
        "name": "TartanDrive",
        "description": (
            "Carnegie Mellon University off-road terrain dataset. "
            "Collected with an ATV in outdoor rough terrain. "
            "Low relevance for indoor hospital navigation but included for "
            "reference as it is part of the GNM training mixture."
        ),
        "relevance_for_hospital": "LOW",
        "environment": "outdoor_offroad",
        "gnm_format_compatible": True,
        "access": "public",
        "download_url_page": "https://github.com/castacks/tartan_drive",
        "citation": (
            "Triest, S., Wang, G., Sivaprakasam, M., et al. (2022). "
            "TartanDrive: A Large-Scale Dataset for Learning Off-Road Dynamics Models. "
            "ICRA 2022."
        ),
    },
    "recon": {
        "name": "RECON",
        "description": (
            "Exploration dataset collected at outdoor locations (trails, parks). "
            "Not relevant for hospital/corridor navigation."
        ),
        "relevance_for_hospital": "NONE",
        "environment": "outdoor_exploration",
        "gnm_format_compatible": True,
        "access": "restricted",
        "access_notes": "Contact the GNM authors for access.",
        "project_url": "https://sites.google.com/view/drive-any-robot",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess, printing the command first."""
    print(f"  $ {' '.join(cmd)}")
    kwargs: dict = {"check": check}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)


def _which(binary: str) -> str | None:
    """Return the path of a binary, or None if not found."""
    return shutil.which(binary)


def _download(url: str, dest: Path, *, tool: str | None = None) -> bool:
    """
    Download *url* to *dest* using wget or curl (whichever is available).
    Returns True on success, False on failure.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    if tool is None:
        tool = "wget" if _which("wget") else ("curl" if _which("curl") else None)

    if tool is None:
        print("  [ERROR] Neither wget nor curl found.  Install one and retry.")
        return False

    if tool == "wget":
        result = _run(["wget", "-q", "--show-progress", "-O", str(dest), url], check=False)
    else:
        result = _run(["curl", "-L", "--progress-bar", "-o", str(dest), url], check=False)

    if result.returncode != 0:
        print(f"  [WARN] Download failed (exit {result.returncode}): {url}")
        if dest.exists() and dest.stat().st_size == 0:
            dest.unlink()
        return False
    return True


def _print_manual_instructions(key: str, info: dict, data_dir: Path) -> None:
    """Print clear manual download instructions for datasets that require it."""
    print()
    print(f"  {'='*60}")
    print(f"  MANUAL DOWNLOAD REQUIRED: {info['name']}")
    print(f"  {'='*60}")
    notes = info.get("access_notes", "See project page for instructions.")
    for line in textwrap.wrap(notes, width=72):
        print(f"  {line}")
    print()
    print(f"  Target directory: {data_dir / key}/")
    print(f"  Expected layout after extraction:")
    if key == "gostanford2":
        print(f"    {data_dir / key}/train/traj_0000/0.jpg")
        print(f"    {data_dir / key}/train/traj_0000/traj_data.pkl")
        print(f"    {data_dir / key}/test/traj_0001/0.jpg")
        print(f"    ...")
    print()


def _validate_gnm_traj(traj_dir: Path) -> dict:
    """
    Check that *traj_dir* looks like a valid GNM trajectory folder.

    Returns a dict with keys:
      ok (bool), n_images (int), has_pkl (bool), errors (list[str])
    """
    errors: list[str] = []
    has_pkl = (traj_dir / "traj_data.pkl").exists()
    if not has_pkl:
        errors.append("Missing traj_data.pkl")

    images = sorted(traj_dir.glob("*.jpg")) + sorted(traj_dir.glob("*.png"))
    n_images = len(images)
    if n_images == 0:
        errors.append("No JPG/PNG images found")

    pkl_ok = False
    if has_pkl:
        try:
            import pickle
            data = pickle.loads((traj_dir / "traj_data.pkl").read_bytes())
            if "position" not in data:
                errors.append("traj_data.pkl missing 'position' key")
            if "yaw" not in data:
                errors.append("traj_data.pkl missing 'yaw' key")
            pkl_ok = True
        except Exception as exc:
            errors.append(f"traj_data.pkl unreadable: {exc}")

    return {
        "ok": len(errors) == 0,
        "n_images": n_images,
        "has_pkl": has_pkl,
        "pkl_readable": pkl_ok,
        "errors": errors,
    }


# ── Dataset-specific handlers ─────────────────────────────────────────────────

def setup_gostanford2(data_dir: Path) -> dict:
    """
    Attempt to set up GoStanford2.

    Direct automated download is not possible without accepting the data-use
    agreement.  This function:
      1. Creates the target directory.
      2. Prints clear instructions.
      3. Returns status dict.
    """
    key = "gostanford2"
    info = DATASET_REGISTRY[key]
    target = data_dir / key
    target.mkdir(parents=True, exist_ok=True)

    print()
    print(f"[{key}] Setting up {info['name']} ...")
    print(f"  Relevance for hospital navigation: {info['relevance_for_hospital']}")
    print()

    # Check if data is already present
    existing_trajs = list(target.rglob("traj_data.pkl"))
    if existing_trajs:
        print(f"  Found {len(existing_trajs)} existing trajectory folder(s) in {target}")
        results = [_validate_gnm_traj(p.parent) for p in existing_trajs[:5]]
        n_ok = sum(1 for r in results if r["ok"])
        print(f"  Spot-check (first 5): {n_ok}/{len(results)} pass GNM format validation")
        return {
            "dataset": key,
            "status": "present",
            "n_trajectories": len(existing_trajs),
            "spot_check_pass": n_ok,
        }

    # Data not present — print manual instructions
    _print_manual_instructions(key, info, data_dir)

    # Write a placeholder README inside the target dir
    readme = target / "DOWNLOAD_INSTRUCTIONS.md"
    readme.write_text(textwrap.dedent(f"""\
        # GoStanford2 — Download Instructions

        GoStanford2 is part of the drive-any-robot (DARo) dataset release.

        ## Step 1 — Accept the data-use agreement
        Visit: {info['project_url']}
        or:    {info['huggingface_url']}

        ## Step 2 — Download
        After accepting, you will receive a download link or can clone from HuggingFace:

            # Option A — HuggingFace (requires git-lfs)
            git lfs install
            git clone https://huggingface.co/datasets/robodhruv/drive-any-robot

            # Option B — direct tar.gz link (provided after accepting agreement)
            wget <link-from-project-page> -O gostanford2.tar.gz
            tar -xzf gostanford2.tar.gz -C {target}/

        ## Step 3 — Expected layout
            {target}/train/traj_0000/0.jpg
            {target}/train/traj_0000/traj_data.pkl
            {target}/test/traj_0001/0.jpg
            ...

        ## Step 4 — Validate
            python scripts/data/setup_gnm_indoor_datasets.py --dataset gostanford2

        ## Citation
        {info['citation']}
    """))
    print(f"  Wrote instructions to: {readme}")

    return {
        "dataset": key,
        "status": "instructions_written",
        "target_dir": str(target),
        "action_required": "manual_download",
        "url": info["huggingface_url"],
    }


def setup_scand(data_dir: Path) -> dict:
    """
    Set up the SCAND dataset.

    SCAND is publicly available.  This function attempts to download the
    processed data index from the UT Austin project page and prints instructions
    for the large archive files (which must be downloaded manually due to size).
    """
    key = "scand"
    info = DATASET_REGISTRY[key]
    target = data_dir / key
    target.mkdir(parents=True, exist_ok=True)

    print()
    print(f"[{key}] Setting up {info['name']} ...")
    print(f"  Relevance for hospital navigation: {info['relevance_for_hospital']}")
    print()

    # Check if data is already present
    existing_bags = list(target.rglob("*.db3")) + list(target.rglob("*.bag"))
    existing_pkls = list(target.rglob("traj_data.pkl"))

    if existing_bags or existing_pkls:
        print(f"  Found {len(existing_bags)} bag file(s) and "
              f"{len(existing_pkls)} processed trajectory folder(s)")
        return {
            "dataset": key,
            "status": "present",
            "n_bags": len(existing_bags),
            "n_trajectories": len(existing_pkls),
        }

    # SCAND is public but large — print instructions and offer a metadata fetch
    print("  SCAND is publicly available but must be downloaded manually due to size.")
    print()
    print("  Download page:")
    print(f"    {info['project_url']}")
    print()
    print("  Recommended: download the 'Processed Data' archive which contains")
    print("  image sequences + odometry in a format closer to GNM's.")
    print()
    print("  After download, extract to:")
    print(f"    {target}/")
    print()
    print("  Then convert to GNM format with:")
    print(f"    python scripts/data/gnm_dataset_converter.py ros2-bag-to-gnm \\")
    print(f"        --bag {target}/<sequence>.db3 \\")
    print(f"        --output {data_dir}/scand_gnm/")
    print()

    # Write instructions file
    readme = target / "DOWNLOAD_INSTRUCTIONS.md"
    readme.write_text(textwrap.dedent(f"""\
        # SCAND — Download Instructions

        SCAND (Social Comfort-Aware Navigation Dataset) is freely available
        from UT Austin.

        ## Download
        Project page: {info['project_url']}

        Download the **Processed Data** archive (recommended) or the raw ROS bags.

        ## Extract
            tar -xzf SCAND_processed.tar.gz -C {target}/

        ## Convert to GNM format (for fine-tuning)
            python scripts/data/gnm_dataset_converter.py ros2-bag-to-gnm \\
                --bag {target}/<sequence>.db3 \\
                --output {data_dir}/scand_gnm/ \\
                --camera-topic /usb_cam/image_raw \\
                --odom-topic /odom

        ## Indoor vs Outdoor
        SCAND contains both indoor (office corridors) and outdoor sequences.
        Filter by sequence name prefix — indoor sequences are labelled in the
        dataset's metadata CSV on the project page.

        ## Citation
        {info['citation']}
    """))
    print(f"  Wrote instructions to: {readme}")

    return {
        "dataset": key,
        "status": "instructions_written",
        "target_dir": str(target),
        "action_required": "manual_download",
        "url": info["project_url"],
    }


def setup_yahboom_placeholder(data_dir: Path) -> dict:
    """Create placeholder directory for real Yahboom M3Pro hospital recordings."""
    key = "yahboom_hospital"
    target = data_dir / key
    target.mkdir(parents=True, exist_ok=True)

    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(textwrap.dedent("""\
            # Yahboom M3Pro Hospital Recordings

            This directory holds GNM-format trajectories recorded with the
            Yahboom M3Pro robot (Jetson Orin NX) in a real hospital environment.

            ## Recording
            Use the ROS2 recording pipeline on the robot:

                ros2 bag record /usb_cam/image_raw /odom -o <session_name>

            ## Converting to GNM format
                python scripts/data/gnm_dataset_converter.py ros2-bag-to-gnm \\
                    --bag <session_name>/<session_name>.db3 \\
                    --output data/gnm_datasets/yahboom_hospital/ \\
                    --camera-topic /usb_cam/image_raw \\
                    --odom-topic /odom

            ## Expected layout after conversion
                yahboom_hospital/
                    traj_0000/
                        0.jpg
                        1.jpg
                        ...
                        traj_data.pkl
                    traj_0001/
                        ...

            ## Robot specs (Yahboom M3Pro / Jetson Orin NX)
            - Wheel radius : 0.048 m
            - Half wheelbase (lx) : 0.0775 m
            - Half track width (ly) : 0.0850 m
            - Drive type : mecanum
        """))
        print(f"  Created placeholder: {target}/")

    return {
        "dataset": key,
        "status": "placeholder",
        "target_dir": str(target),
    }


# ── Validation ────────────────────────────────────────────────────────────────

def validate_dataset(data_dir: Path, key: str) -> dict:
    """
    Validate that a downloaded dataset matches the expected GNM format.

    Returns a summary dict with per-trajectory validation results.
    """
    target = data_dir / key
    if not target.exists():
        return {"dataset": key, "ok": False, "error": "Directory not found"}

    traj_dirs = sorted([p.parent for p in target.rglob("traj_data.pkl")])
    if not traj_dirs:
        return {
            "dataset": key,
            "ok": False,
            "error": "No traj_data.pkl files found — data may not be downloaded yet",
        }

    print(f"\n  Validating {len(traj_dirs)} trajectories in {target} ...")

    results: list[dict] = []
    for traj_dir in traj_dirs:
        r = _validate_gnm_traj(traj_dir)
        r["traj"] = traj_dir.name
        results.append(r)

    n_ok = sum(1 for r in results if r["ok"])
    n_total = len(results)
    failed = [r for r in results if not r["ok"]]

    print(f"  Pass: {n_ok}/{n_total}")
    if failed:
        print(f"  Failed trajectories ({len(failed)}):")
        for r in failed[:10]:
            print(f"    {r['traj']}: {', '.join(r['errors'])}")

    return {
        "dataset": key,
        "ok": n_ok == n_total,
        "n_trajectories": n_total,
        "n_pass": n_ok,
        "n_fail": n_total - n_ok,
        "failed_sample": [r["traj"] for r in failed[:5]],
    }


# ── Registry file ─────────────────────────────────────────────────────────────

def write_registry(data_dir: Path, statuses: list[dict]) -> Path:
    """Write dataset_registry.json summarising what is available."""
    registry = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "datasets": {},
    }

    # Merge static metadata with download status
    for status in statuses:
        key = status.get("dataset", "unknown")
        static = DATASET_REGISTRY.get(key, {})
        registry["datasets"][key] = {**static, "download_status": status}

    out = data_dir / "dataset_registry.json"
    out.write_text(json.dumps(registry, indent=2))
    print(f"\n  Registry written: {out}")
    return out


def write_readme(data_dir: Path) -> None:
    """Write a human-readable README.md into data_dir."""
    rows = []
    for key, info in DATASET_REGISTRY.items():
        rows.append(
            f"| {info['name']} | {info['relevance_for_hospital']} "
            f"| {info['environment']} | {info['access']} |"
        )

    content = textwrap.dedent(f"""\
        # GNM Indoor Datasets — FleetSafe-VisualNav-Benchmark

        This directory contains (or placeholders for) GNM-compatible training
        datasets relevant to indoor / hospital-corridor navigation.

        ## Dataset Summary

        | Dataset | Hospital Relevance | Environment | Access |
        |---------|-------------------|-------------|--------|
        {chr(10).join(rows)}

        ## Directory Layout

            gnm_datasets/
                gostanford2/          ← GoStanford2 (indoor corridors — BEST MATCH)
                scand/                ← SCAND (indoor+outdoor corridors)
                yahboom_hospital/     ← Real Yahboom M3Pro hospital recordings
                dataset_registry.json ← Machine-readable catalogue
                README.md             ← This file

        ## GNM Trajectory Format

        Each trajectory is a folder with:
            traj_NNNN/
                0.jpg               ← first frame
                1.jpg
                ...
                traj_data.pkl       ← {{"position": np.array([[x,y],...], shape [T,2]),
                                        "yaw": np.array([...], shape [T])}}

        ## Usage with Fine-Tuning

            # Validate all datasets
            python scripts/data/setup_gnm_indoor_datasets.py

            # Convert FleetSafe episodes → GNM format for fine-tuning
            python scripts/data/gnm_dataset_converter.py fleetsafe-to-gnm \\
                --input data/training_episodes/gnm/hospital_corridor \\
                --output data/gnm_datasets/fleetsafe_converted/

            # Launch GNM fine-tuning (requires visualnav-transformer)
            cd third_party/visualnav-transformer/train
            python train.py \\
                --config ../config/gnm/gnm.yaml \\
                --data-dir ../../../data/gnm_datasets/ \\
                --pretrained gnm.pth

        ## Why GoStanford2 for Hospitals?

        Hospital corridors share key visual features with office corridors:
        - Long straight hallways with uniform lighting
        - Doorways at regular intervals
        - Hard floors with low visual texture
        - Dynamic obstacles (people, carts) at low density

        GoStanford2 was collected in the Gates CS Building at Stanford University,
        which has very similar visual statistics to a modern hospital wing.

        ## References

        - GNM paper: https://arxiv.org/abs/2210.03370
        - drive-any-robot: https://sites.google.com/view/drive-any-robot
        - SCAND: https://cs.utexas.edu/~xiao/SCAND/SCAND.html
    """)
    out = data_dir / "README.md"
    out.write_text(content)
    print(f"  README written: {out}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dataset",
        choices=["gostanford2", "scand", "all"],
        default="all",
        help="Which dataset to set up (default: all)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "gnm_datasets",
        help="Root directory for GNM datasets (default: data/gnm_datasets/)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip downloads; only validate what is already present",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 64)
    print("  FleetSafe GNM Indoor Dataset Setup")
    print("=" * 64)
    print(f"  Data directory : {data_dir}")
    print(f"  Mode           : {'validate' if args.validate_only else 'setup'}")
    print(f"  Dataset        : {args.dataset}")
    print()

    statuses: list[dict] = []

    if args.validate_only:
        keys = (
            ["gostanford2", "scand"]
            if args.dataset == "all"
            else [args.dataset]
        )
        for key in keys:
            result = validate_dataset(data_dir, key)
            statuses.append(result)
            status_str = "OK" if result.get("ok") else "INCOMPLETE"
            print(f"  [{key}] {status_str}")
    else:
        if args.dataset in ("gostanford2", "all"):
            s = setup_gostanford2(data_dir)
            statuses.append(s)

        if args.dataset in ("scand", "all"):
            s = setup_scand(data_dir)
            statuses.append(s)

        if args.dataset == "all":
            s = setup_yahboom_placeholder(data_dir)
            statuses.append(s)

        # Validate whatever is present
        print()
        print("  Validating present data ...")
        for status in statuses:
            key = status.get("dataset", "")
            if status.get("status") == "present":
                validation = validate_dataset(data_dir, key)
                status["validation"] = validation

    write_registry(data_dir, statuses)
    write_readme(data_dir)

    print()
    print("  Summary")
    print("  " + "-" * 50)
    for s in statuses:
        key = s.get("dataset", "?")
        st = s.get("status", s.get("ok", "?"))
        if st is True:
            st = "valid"
        elif st is False:
            st = "INVALID"
        print(f"  {key:<25} {st}")

    print()
    print("  Next steps:")
    print("    1. Follow DOWNLOAD_INSTRUCTIONS.md in each dataset subfolder")
    print("    2. Re-run this script to validate after downloading")
    print("    3. Use gnm_dataset_converter.py to convert/combine datasets")
    print("    4. Fine-tune GNM with hospital-specific data")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
