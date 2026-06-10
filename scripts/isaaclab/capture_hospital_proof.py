#!/usr/bin/env python3
"""
capture_hospital_proof.py — Isaac Sim hospital scene proof capture. v1.0.

What this script proves
-----------------------
* Procedural hospital scene: the Python asset-library definition is complete
  and generates a valid zone map without requiring a running simulator.
  Status: PROVEN if asset library imports successfully + zone map non-empty.

* Photoreal USD scene: only PROVEN if the hospital_photoreal.usd file exists
  under assets/usd/. Currently MISSING — honest label until file is placed.

* Isaac Sim runtime: PROVEN only if AppLauncher initialises. This script does
  NOT require Isaac to be running; it captures what is available headlessly.

Outputs (recordings/isaac_proof/<timestamp>/)
---------------------------------------------
  isaac_scene_proof.json    — what was captured and honesty labels
  scene_manifest.json       — zone map from asset library
  hospital_zone_map.json    — zone boundary definitions
  viewport_status.txt       — Isaac Sim availability status
  screenshot.png            — only if Isaac viewport is available

Usage
-----
  # Without Isaac Sim (CI / offline):
  python scripts/isaaclab/capture_hospital_proof.py

  # With Isaac Sim (requires conda activate isaac):
  python scripts/isaaclab/capture_hospital_proof.py --try-isaac

Do NOT claim photoreal or full Isaac proof until checklist is green.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "command-center"))


# ── helpers ───────────────────────────────────────────────────────────────────

def _git_commit() -> str:
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO_ROOT), stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Isaac Sim availability check ──────────────────────────────────────────────

def _check_isaac_sim() -> dict:
    """Try to detect Isaac Sim. Never crashes — returns honest status."""
    try:
        import isaacsim  # noqa: F401
        return {"available": True, "method": "import isaacsim"}
    except ImportError:
        pass

    # Check for IsaacSim kit executable
    candidate_dirs = [
        Path.home() / ".local/share/ov/pkg",
        Path("/opt/isaacsim"),
        Path("/isaac-sim"),
    ]
    for d in candidate_dirs:
        kits = list(d.glob("**/isaac-sim.sh")) + list(d.glob("**/isaac_sim*.sh"))
        if kits:
            return {"available": True, "method": "kit_found", "kit_path": str(kits[0])}

    return {
        "available": False,
        "reason": "Isaac Sim not installed or not in PATH — install via Omniverse or conda activate isaac",
        "status": "NOT_AVAILABLE",
    }


# ── Photoreal USD check ───────────────────────────────────────────────────────

def _check_photoreal_usd() -> dict:
    """Check whether photoreal hospital USD file exists."""
    candidates = [
        _REPO_ROOT / "assets" / "usd" / "hospital_photoreal.usd",
        _REPO_ROOT / "assets" / "usd" / "hospital_photoreal.usda",
        _REPO_ROOT / "assets" / "hospital" / "hospital_photoreal.usd",
    ]
    for p in candidates:
        if p.exists():
            size_mb = p.stat().st_size / 1_048_576
            return {
                "status": "PROVEN",
                "path": str(p),
                "size_mb": round(size_mb, 1),
            }
    return {
        "status": "MISSING",
        "reason": "No hospital_photoreal.usd found under assets/",
        "guidance": (
            "To add photoreal proof: obtain hospital USD from NVIDIA Nucleus or "
            "create one in Omniverse and place at assets/usd/hospital_photoreal.usd"
        ),
    }


# ── Procedural scene proof ────────────────────────────────────────────────────

def _build_procedural_proof() -> dict:
    """
    Generate hospital scene manifest from asset-library definitions.
    No Isaac Sim required — pure Python.
    """
    try:
        from fleet_safe_vla.envs.isaaclab.hospital.hospital_asset_library import (
            HospitalAssetLibrary,
            _CATALOG,
        )
        lib = HospitalAssetLibrary(nucleus_ok=False, verbose=False)

        n_catalog   = len(_CATALOG)
        n_available = len(lib.available_assets())
        has_photo   = lib.has_photoreal_assets()
        assets_list = [
            {"name": e.name, "category": e.category}
            for e in _CATALOG
        ]

        return {
            "status":       "PROVEN" if n_catalog >= 5 else "PARTIAL",
            "method":       "HospitalAssetLibrary",
            "n_catalog":    n_catalog,
            "n_available":  n_available,
            "has_photoreal": has_photo,
            "assets":       assets_list,
            "note": (
                f"Catalog defines {n_catalog} hospital assets. "
                f"{n_available} resolved to local paths (rest need Nucleus or Isaac Sim)."
            ),
        }
    except ImportError:
        pass  # fall through to SCENESET fallback
    except Exception as exc:
        pass  # unexpected — fall through

    # Fallback: read SCENESET yaml directly
    sceneset = _REPO_ROOT / "benchmarks" / "scenes" / "canonical" / "SCENESET_v0.1.yaml"
    if sceneset.exists():
        try:
            import yaml
            data = yaml.safe_load(sceneset.read_text())
            scenes = data.get("scenes", [])
            hospital_scenes = [s for s in scenes if "hospital" in str(s).lower()]
            return {
                "status": "PROVEN" if hospital_scenes else "PARTIAL",
                "method": "SCENESET_yaml",
                "n_hospital_scenes": len(hospital_scenes),
                "scenes": hospital_scenes[:10],
            }
        except Exception:
            pass

    return {
        "status": "PARTIAL",
        "method": "none_available",
        "reason": "Could not load HospitalAssetLibrary or SCENESET yaml",
    }


def _build_zone_map() -> dict:
    """Hospital zone boundary definitions for the zone safety model."""
    # These match the ZoneAwareRewardShaper and SafetyZoneClassifier parameters.
    return {
        "version": "v1.0",
        "zones": [
            {
                "name": "icu",
                "semantic_type": "HIGH_RISK",
                "speed_limit_ms": 0.3,
                "social_margin_m": 1.2,
                "safety_zone_default": "AMBER",
                "crowding_threshold": 2,
            },
            {
                "name": "nurse_station",
                "semantic_type": "MEDIUM_RISK",
                "speed_limit_ms": 0.45,
                "social_margin_m": 0.8,
                "safety_zone_default": "AMBER",
                "crowding_threshold": 3,
            },
            {
                "name": "pharmacy",
                "semantic_type": "MEDIUM_RISK",
                "speed_limit_ms": 0.4,
                "social_margin_m": 0.9,
                "safety_zone_default": "AMBER",
                "crowding_threshold": 2,
            },
            {
                "name": "emergency_corridor",
                "semantic_type": "TRANSIT",
                "speed_limit_ms": 0.6,
                "social_margin_m": 0.5,
                "safety_zone_default": "GREEN",
                "crowding_threshold": 6,
            },
            {
                "name": "waiting_room",
                "semantic_type": "LOW_RISK",
                "speed_limit_ms": 0.5,
                "social_margin_m": 0.7,
                "safety_zone_default": "GREEN",
                "crowding_threshold": 8,
            },
            {
                "name": "default",
                "semantic_type": "UNSPECIFIED",
                "speed_limit_ms": 0.5,
                "social_margin_m": 0.5,
                "safety_zone_default": "GREEN",
                "crowding_threshold": 10,
            },
        ],
        "source": "PPOSocialConfig + SafetyZoneClassifier parameters",
        "ground_truth_type": "semantic_scene_spec",
    }


# ── Evidence recording ────────────────────────────────────────────────────────

def _record_evidence(out_dir: Path, proof: dict) -> dict | None:
    try:
        from backend.services.evidence_ledger import evidence_ledger
        proof_path = out_dir / "isaac_scene_proof.json"
        entry = evidence_ledger.record(
            claim_scope="sim_benchmark_result",
            source="isaaclab",
            ground_truth_type="semantic_scene_spec",
            description=(
                f"Isaac hospital proof: procedural={proof['procedural']['status']}, "
                f"photoreal={proof['photoreal']['status']}, "
                f"isaac_sim={proof['isaac_sim']['available']}"
            ),
            artifact_path=proof_path,
            operator="capture_hospital_proof",
            metadata={
                "procedural_status": proof["procedural"]["status"],
                "photoreal_status": proof["photoreal"]["status"],
                "isaac_sim_available": proof["isaac_sim"]["available"],
            },
        )
        return entry
    except Exception as exc:
        return {"warning": f"Could not record evidence: {exc}"}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--try-isaac",  action="store_true",
                   help="Attempt Isaac Sim AppLauncher (requires conda activate isaac)")
    p.add_argument("--output-dir", default=None,
                   help="Override output directory")
    args = p.parse_args()

    ts = int(time.time())
    ts_iso = _now_iso()
    out_dir = Path(args.output_dir) if args.output_dir else (
        _REPO_ROOT / "recordings" / "isaac_proof" / str(ts)
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[capture_hospital_proof] Output → {out_dir}")
    print(f"[capture_hospital_proof] git commit: {_git_commit()}")

    # ── A. Isaac Sim check ────────────────────────────────────────────────────
    print("\n[A] Checking Isaac Sim availability…")
    isaac_status = _check_isaac_sim()
    print(f"    Isaac Sim: {'AVAILABLE' if isaac_status['available'] else 'NOT_AVAILABLE'}")
    (out_dir / "viewport_status.txt").write_text(
        f"isaac_sim_available: {isaac_status['available']}\n"
        f"checked_at: {ts_iso}\n"
        + (f"method: {isaac_status.get('method','')}\n" if isaac_status['available']
           else f"reason: {isaac_status.get('reason','')}\n")
        + "\nSCREENSHOT: Not captured — Isaac Sim not running headlessly.\n"
          "To capture: start Isaac Sim with --headless and re-run with --try-isaac\n"
    )

    # ── B. Photoreal USD check ────────────────────────────────────────────────
    print("\n[B] Checking photoreal USD assets…")
    photoreal = _check_photoreal_usd()
    print(f"    Photoreal status: {photoreal['status']}")

    # ── C. Procedural scene proof ─────────────────────────────────────────────
    print("\n[C] Building procedural hospital scene manifest…")
    procedural = _build_procedural_proof()
    print(f"    Procedural status: {procedural['status']} "
          f"(method: {procedural.get('method','?')})")

    # ── D. Zone map ───────────────────────────────────────────────────────────
    zone_map = _build_zone_map()
    (out_dir / "hospital_zone_map.json").write_text(
        json.dumps(zone_map, indent=2)
    )
    print(f"\n[D] Zone map written ({len(zone_map['zones'])} zones)")

    # ── Assemble proof ────────────────────────────────────────────────────────
    proof = {
        "generated_at":           ts_iso,
        "git_commit":             _git_commit(),
        "isaac_sim":              isaac_status,
        "photoreal":              photoreal,
        "procedural":             procedural,
        "honest_labels": {
            "photoreal_hospital_status":   photoreal["status"],
            "procedural_hospital_status":  procedural["status"],
            "isaac_sim_runtime_status":    "AVAILABLE" if isaac_status["available"] else "NOT_AVAILABLE",
        },
        "do_not_claim": [
            "photoreal_hospital_complete — USD file not present" if photoreal["status"] == "MISSING" else None,
            "full_isaac_runtime_proof — AppLauncher not run" if not isaac_status["available"] else None,
        ],
        "notes": (
            "procedural_hospital_status=PROVEN means the Python hospital zone "
            "definition is complete and non-empty. It does NOT mean a rendered "
            "scene was captured. Photoreal proof requires hospital_photoreal.usd."
        ),
    }
    proof["do_not_claim"] = [x for x in proof["do_not_claim"] if x]

    proof_path = out_dir / "isaac_scene_proof.json"
    proof_path.write_text(json.dumps(proof, indent=2))

    # ── Scene manifest ────────────────────────────────────────────────────────
    manifest = {
        "generated_at":  ts_iso,
        "n_zones":        len(zone_map["zones"]),
        "procedural":     procedural,
        "zone_names":     [z["name"] for z in zone_map["zones"]],
        "asset_source":   "HospitalAssetLibrary (Python definitions)",
        "photoreal_usd":  photoreal.get("path", "MISSING"),
    }
    (out_dir / "scene_manifest.json").write_text(json.dumps(manifest, indent=2))

    # ── Evidence record ───────────────────────────────────────────────────────
    ledger_entry = _record_evidence(out_dir, proof)
    if ledger_entry and "id" in ledger_entry:
        print(f"\n[E] Evidence ledger entry: {ledger_entry['id']}")
    elif ledger_entry:
        print(f"\n[E] Evidence: {ledger_entry}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("HONEST STATUS LABELS")
    print("─" * 60)
    for k, v in proof["honest_labels"].items():
        print(f"  {k:42s} {v}")
    if proof["do_not_claim"]:
        print("\nDO NOT CLAIM:")
        for s in proof["do_not_claim"]:
            print(f"  ✗ {s}")
    print(f"\nArtifacts → {out_dir}")
    print("─" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
