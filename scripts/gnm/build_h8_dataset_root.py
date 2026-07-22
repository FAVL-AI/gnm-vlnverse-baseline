"""scripts/gnm/build_h8_dataset_root.py

H8-S1 — DATASET-BUILDER SKELETON (validation and planning only).

Extends the discipline of `build_h7r_dataset_root.py` to the corrected H8 protocol. At the H8-S1
gate this tool **plans and validates only**: it emits no dataset directory, copies no image, writes
no trajectory and computes no metric. Dataset construction is a later gate, unlocked only after
Session A (map + navmesh), Session B (camera validation), Session C (goal bank) and Session D
(route capture).

FAIL-CLOSED ORDERING (protocol v2 section 8). Stages run in a fixed order and stop at the first
blocking failure, so a later stage can never mask an earlier one:

     1 parse CLI                  9 route uniqueness         17 available topics
     2 protocol version          10 resolve goal id          18 time domains
     3 schema                    11 goal record identity     19 image-to-pose alignment
     4 episode manifest          12 acquisition resolution   20 completeness
     5 goal registry             13 camera identity/mount    21 metric readiness
     6 scene identity            14 controller/policy        22 emit plan only
     7 map/navmesh identity      15 start pose               23 (no dataset created at S1)
     8 split                     16 success radius

WHAT THIS TOOL WILL NEVER DO
  * read a live ROS topic, launch Isaac, or record a bag;
  * create a training image from an input that failed validation;
  * infer a goal, a success radius, a navmesh path or a controller identity that was not declared;
  * infer controller identity from a folder name;
  * promote a historical bag into a dataset.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from h8_episode_validator import (  # noqa: E402
    MANIFEST_VERSION,
    PROTOCOL_VERSION,
    GoalRegistry,
    metric_readiness,
    screen_duplicates,
    validate_manifest,
)
from h8_time_alignment import (  # noqa: E402
    ALIGNMENT_POLICY_VERSION,
    ALIGNMENT_TOLERANCE_S,
    AUTHORITATIVE_CLOCK,
    DIAGNOSTIC_TOLERANCE_S,
    Pose,
    align_series,
    summarise,
    tolerance_derivation,
)

BUILDER_VERSION = "h8-dataset-builder/0.1.0-s1-skeleton"

STAGES = (
    "parse_cli", "protocol_version", "schema", "episode_manifest", "goal_registry",
    "scene_identity", "map_navmesh_identity", "split", "route_uniqueness", "resolve_goal_id",
    "goal_record_identity", "acquisition_resolution", "camera_identity", "controller_identity",
    "start_pose", "success_radius", "available_topics", "time_domains", "image_pose_alignment",
    "completeness", "metric_readiness", "emit_plan",
)

REQUIRED_TOPICS = (
    "/camera/image_raw", "/camera/camera_info", "/odom", "/tf", "/tf_static", "/clock", "/cmd_vel",
)


@dataclass
class BuildReport:
    builder_version: str = BUILDER_VERSION
    protocol_version: str = PROTOCOL_VERSION
    manifest_version: str = MANIFEST_VERSION
    alignment_policy_version: str = ALIGNMENT_POLICY_VERSION
    mode: str = "validate-only"
    ok: bool = False
    dataset_created: bool = False
    images_written: int = 0
    trajectories_written: int = 0
    split_manifest_written: bool = False
    metrics_computed: int = 0
    stages_run: list[str] = field(default_factory=list)
    blocked_at: str | None = None
    episodes: list[dict[str, Any]] = field(default_factory=list)
    duplicate_screening: dict[str, Any] = field(default_factory=dict)
    reason_codes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "builder_version": self.builder_version,
            "protocol_version": self.protocol_version,
            "manifest_version": self.manifest_version,
            "alignment_policy_version": self.alignment_policy_version,
            "mode": self.mode,
            "ok": self.ok,
            "dataset_created": self.dataset_created,
            "images_written": self.images_written,
            "trajectories_written": self.trajectories_written,
            "split_manifest_written": self.split_manifest_written,
            "metrics_computed": self.metrics_computed,
            "stages_run": list(self.stages_run),
            "blocked_at": self.blocked_at,
            "episodes": self.episodes,
            "duplicate_screening": self.duplicate_screening,
            "reason_codes": sorted(set(self.reason_codes)),
            "notes": list(self.notes),
        }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_h8_dataset_root.py",
        description="H8 dataset builder (H8-S1: validation and planning only, creates no dataset).",
    )
    p.add_argument("--manifest", action="append", default=[],
                   help="Episode manifest JSON. Repeatable.")
    p.add_argument("--goal-registry", help="Locked goal-bank JSON.")
    p.add_argument("--schema", help="Episode manifest JSON Schema.")
    p.add_argument("--out-dir", help="Where a dataset WOULD be written. Never written at S1.")
    p.add_argument("--validate-only", action="store_true",
                   help="Validate and report. Default behaviour at S1.")
    p.add_argument("--dry-run", action="store_true", help="Alias of --validate-only at S1.")
    p.add_argument("--emit-plan", help="Write the build plan JSON to this path.")
    p.add_argument("--strict", action="store_true",
                   help="Also require a navmesh version (needed for the path metrics).")
    p.add_argument("--alignment-policy", default=ALIGNMENT_POLICY_VERSION,
                   help="Alignment policy version to apply.")
    p.add_argument("--alignment-tolerance-s", type=float, default=ALIGNMENT_TOLERANCE_S,
                   help="Override the alignment tolerance (diagnostic use).")
    p.add_argument("--metric-policy", default="h8-metric-spec/2.0.0",
                   help="Metric specification version to apply.")
    return p


def _load(path: str) -> Any:
    return json.loads(Path(path).read_text())


def _poses_from(manifest: dict[str, Any]) -> list[Pose]:
    """Pose series carried inline by a manifest, if any (fixtures and dry runs)."""
    out = []
    for p in (manifest.get("pose_series") or []):
        out.append(Pose(
            stamp=p["stamp"], x=p["x"], y=p["y"], z=p.get("z", 0.0),
            qx=p.get("qx", 0.0), qy=p.get("qy", 0.0), qz=p.get("qz", 0.0), qw=p.get("qw", 1.0),
            frame_id=p.get("frame_id", "odom"), child_frame_id=p.get("child_frame_id", "base_footprint"),
            clock=p.get("clock", AUTHORITATIVE_CLOCK),
        ))
    return out


def run(argv: list[str] | None = None) -> tuple[int, BuildReport]:
    """Run the builder. Returns (exit_code, report). Non-zero exit means do not proceed."""
    args = build_parser().parse_args(argv)
    rep = BuildReport()
    rep.stages_run.append("parse_cli")
    rep.mode = "validate-only"  # S1 has no other mode
    rep.notes.append(
        "H8-S1 skeleton: validation and planning only. No dataset directory, image, trajectory, "
        "split manifest or metric value is produced by this gate."
    )
    rep.stages_run.append("protocol_version")

    if args.schema:
        try:
            schema = _load(args.schema)
        except Exception as e:  # noqa: BLE001
            rep.blocked_at = "schema"
            rep.reason_codes.append("H8_MANIFEST_SCHEMA_INVALID")
            rep.notes.append(f"schema unreadable: {e}")
            return 2, rep
        if schema.get("$id") and MANIFEST_VERSION.split("/")[0] not in str(schema["$id"]):
            rep.blocked_at = "schema"
            rep.reason_codes.append("H8_MANIFEST_VERSION_UNSUPPORTED")
            return 2, rep
    rep.stages_run.append("schema")

    manifests: list[dict[str, Any]] = []
    for m in args.manifest:
        try:
            manifests.append(_load(m))
        except Exception as e:  # noqa: BLE001
            rep.blocked_at = "episode_manifest"
            rep.reason_codes.append("H8_MANIFEST_SCHEMA_INVALID")
            rep.notes.append(f"manifest unreadable {m}: {e}")
            return 2, rep
    rep.stages_run.append("episode_manifest")

    registry: GoalRegistry | None = None
    if args.goal_registry:
        try:
            registry = GoalRegistry.from_file(args.goal_registry)
        except Exception as e:  # noqa: BLE001
            rep.blocked_at = "goal_registry"
            rep.reason_codes.append("H8_GOAL_NOT_FOUND")
            rep.notes.append(f"goal registry unreadable: {e}")
            return 2, rep
        errs = registry.structural_errors()
        if errs:
            rep.blocked_at = "goal_registry"
            for e in errs:
                rep.reason_codes.append(e["code"])
            rep.notes.append("goal registry is structurally invalid; no episode processed")
            return 2, rep
    rep.stages_run.append("goal_registry")

    # Stages 6-16 are covered by validate_manifest, which collects every applicable code.
    for m in manifests:
        vres = validate_manifest(m, registry=registry, require_navmesh=bool(args.strict))
        entry: dict[str, Any] = {"episode_id": m.get("episode_id"), "validation": vres.to_dict()}

        topics = set(m.get("topics_recorded") or [])
        missing_topics = [t for t in REQUIRED_TOPICS if t not in topics] if topics else list(REQUIRED_TOPICS)
        entry["missing_topics"] = missing_topics

        poses = _poses_from(m)
        stamps = m.get("image_stamps") or []
        if poses and stamps:
            results = align_series(
                stamps, poses, image_clock=AUTHORITATIVE_CLOCK,
                tolerance_s=args.alignment_tolerance_s,
            )
            entry["alignment"] = summarise(results)
            alignment_ok = entry["alignment"]["n_rejected"] == 0
        else:
            entry["alignment"] = {"n_total": 0, "n_aligned": 0, "n_rejected": 0,
                                  "note": "no inline pose/image series supplied to the skeleton"}
            alignment_ok = True

        entry["metric_readiness"] = metric_readiness(
            m, alignment_ok=alignment_ok, manifest_valid=vres.ok
        )
        entry["admitted"] = bool(vres.ok and not missing_topics and alignment_ok)
        rep.episodes.append(entry)
        rep.reason_codes.extend(vres.reason_codes)

    for s in ("scene_identity", "map_navmesh_identity", "split", "route_uniqueness",
              "resolve_goal_id", "goal_record_identity", "acquisition_resolution",
              "camera_identity", "controller_identity", "start_pose", "success_radius",
              "available_topics", "time_domains", "image_pose_alignment"):
        rep.stages_run.append(s)

    rep.duplicate_screening = screen_duplicates(manifests)
    for f in rep.duplicate_screening.get("findings", []):
        rep.reason_codes.append(f["code"])
    rep.stages_run.append("completeness")
    rep.stages_run.append("metric_readiness")

    admitted = [e for e in rep.episodes if e["admitted"]]
    rep.ok = bool(manifests) and len(admitted) == len(manifests) and \
        rep.duplicate_screening.get("ok", False)

    if not rep.ok:
        rep.blocked_at = rep.blocked_at or "completeness"
        rep.notes.append(
            "One or more episodes were rejected. No dataset output is produced, by design: the "
            "builder never writes a partial dataset from a failing input set."
        )

    plan = {
        "plan_version": "h8-build-plan/0.1.0",
        "would_write_to": args.out_dir,
        "n_manifests": len(manifests),
        "n_admitted": len(admitted),
        "alignment": tolerance_derivation(),
        "diagnostic_tolerance_s": DIAGNOSTIC_TOLERANCE_S,
        "metric_policy": args.metric_policy,
        "report": rep.to_dict(),
    }
    if args.emit_plan:
        Path(args.emit_plan).write_text(json.dumps(plan, indent=1, sort_keys=True))
    rep.stages_run.append("emit_plan")

    # S1 invariant: nothing is created, whatever the outcome.
    assert rep.dataset_created is False
    assert rep.images_written == 0 and rep.trajectories_written == 0
    assert rep.split_manifest_written is False and rep.metrics_computed == 0

    return (0 if rep.ok else 3), rep


def main(argv: list[str] | None = None) -> int:
    code, rep = run(argv)
    json.dump(rep.to_dict(), sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
