"""scripts/gnm/h8_episode_validator.py

H8-S1 — FAIL-CLOSED EPISODE-MANIFEST VALIDATION, GOAL REGISTRY, DUPLICATE SCREENING AND
METRIC READINESS.

Implements the controls specified in H8_HOSPITAL_DATASET_PROTOCOL_V2.md against the
`h8-episode-manifest/2.0.0` schema. Every rejection carries a deterministic reason code from
`h8_s1_reason_codes`.

The 2026-07-22 forensic audit found the historical corpus unusable for four reasons this module is
built to refuse: a shared placeholder goal (93/154 episodes), a declared start pose disagreeing with
the observed one (118/140), a `gnm_closed_loop` label on episodes driven by a scripted waypoint
follower (92), and acquisition below the canonical resolution (157/157). Each has a rejection path
here, and each rejection path has a test.

Validation is not trust: a conforming manifest is still unsigned, unattested and capture-ineligible.
That boundary belongs to the H8 G2 envelope work and is not touched here.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from h8_s1_reason_codes import (
    H8_ACQUISITION_ENCODING_MISMATCH,
    H8_ACQUISITION_RESOLUTION_MALFORMED,
    H8_ACQUISITION_RESOLUTION_MISMATCH,
    H8_ACQUISITION_RESOLUTION_MISSING,
    H8_CAMERA_IDENTITY_MISSING,
    H8_CAMERA_MOUNT_UNSUPPORTED,
    H8_CAPTURE_AUTHORISATION_MISSING,
    H8_CONTACT_TELEMETRY_UNAVAILABLE,
    H8_CONTROLLER_CHECKPOINT_MISSING,
    H8_CONTROLLER_MODE_MISSING,
    H8_CONTROLLER_MODE_UNKNOWN,
    H8_CONTROLLER_POLICY_MISMATCH,
    H8_GOAL_AMBIGUOUS,
    H8_GOAL_CAMERA_MISMATCH,
    H8_GOAL_HASH_MISMATCH,
    H8_GOAL_HASH_MISSING,
    H8_GOAL_ID_MISSING,
    H8_GOAL_ID_PLACEHOLDER,
    H8_GOAL_IMAGE_CROSS_SPLIT_REUSE,
    H8_GOAL_MAP_MISMATCH,
    H8_GOAL_NOT_FOUND,
    H8_GOAL_POSE_MISMATCH,
    H8_GOAL_RESOLUTION_MISMATCH,
    H8_GOAL_SCENE_MISMATCH,
    H8_GOAL_SPLIT_MISMATCH,
    H8_MANIFEST_SCHEMA_INVALID,
    H8_MANIFEST_VERSION_UNSUPPORTED,
    H8_MAP_VERSION_MISSING,
    H8_NAVMESH_VERSION_MISSING,
    H8_RETRY_NOT_INDEPENDENT,
    H8_ROUTE_SPLIT_DUPLICATE,
    H8_SCENE_DIGEST_MISSING,
    H8_SCENE_IDENTITY_FAILED,
    H8_SPLIT_UNKNOWN,
    H8_START_POSE_DECLARED_MISSING,
    H8_START_POSE_FRAME_MISMATCH,
    H8_START_POSE_OBSERVED_MISSING,
    H8_START_POSE_TOLERANCE_EXCEEDED,
    H8_SUCCESS_CRITERION_NOT_PREREGISTERED,
    H8_SUCCESS_RADIUS_MISMATCH,
    H8_SUCCESS_RADIUS_MISSING,
)

MANIFEST_VERSION = "h8-episode-manifest/2.0.0"
PROTOCOL_VERSION = "h8-hospital-dataset-protocol/2.0.0"

#: Forbidden placeholder goal. Present in 93/154 historical episodes, incl. all 33 gate-verified.
PLACEHOLDER_GOAL_IDS = frozenset({"h2_weave_J"})

CANONICAL_RESOLUTION = [1280, 720]
CANONICAL_ENCODING = "rgb8"
CANONICAL_CAMERA_RAISE_M = 0.12
CANONICAL_SUCCESS_RADIUS_M = 0.5

START_POSE_TOLERANCE_M = 0.05
START_POSE_TOLERANCE_RAD = 0.0873  # ~5 degrees

CONTROLLER_MODES = (
    "scripted_waypoint_follower",
    "gnm_shadow",
    "gnm_closed_loop",
    "manual_control",
    "replay_only",
)
#: Only this mode may assert a learned policy was actuating.
POLICY_IN_LOOP_MODES = frozenset({"gnm_closed_loop"})

SPLITS = ("train", "val", "test")

# --------------------------------------------------------------------------------------------
# Metric readiness
# --------------------------------------------------------------------------------------------

COMPUTABLE_VALID = "COMPUTABLE_VALID"
COMPUTABLE_DIAGNOSTIC_ONLY = "COMPUTABLE_DIAGNOSTIC_ONLY"
PARTIAL = "PARTIAL"
NOT_COMPUTED_MISSING_GOAL = "NOT_COMPUTED_MISSING_GOAL"
NOT_COMPUTED_MISSING_SUCCESS_RADIUS = "NOT_COMPUTED_MISSING_SUCCESS_RADIUS"
NOT_COMPUTED_MISSING_REFERENCE_PATH = "NOT_COMPUTED_MISSING_REFERENCE_PATH"
NOT_COMPUTED_MISSING_NAVMESH = "NOT_COMPUTED_MISSING_NAVMESH"
NOT_COMPUTED_MISSING_CONTACTS = "NOT_COMPUTED_MISSING_CONTACTS"
NOT_COMPUTED_MISSING_STOP_EVENT = "NOT_COMPUTED_MISSING_STOP_EVENT"
NOT_COMPUTED_MISSING_LATENCY_TIMESTAMPS = "NOT_COMPUTED_MISSING_LATENCY_TIMESTAMPS"
NOT_COMPUTED_ALIGNMENT_FAILED = "NOT_COMPUTED_ALIGNMENT_FAILED"
NOT_COMPUTED_UNTRUSTED_METADATA = "NOT_COMPUTED_UNTRUSTED_METADATA"

METRICS = (
    "SR_0.50", "OSR_0.50", "SR_OSR_GAP_0.50", "NE", "TL", "SPL", "nDTW", "SDTW", "CLS",
    "collision_count", "collision_rate", "completion_time", "stop_timing_error",
    "overshoot_distance", "pose_aligned_success", "inference_latency", "command_latency",
    "provenance_completeness",
)
PATH_METRICS = frozenset({"SPL", "nDTW", "SDTW", "CLS"})


@dataclass
class ValidationResult:
    """Outcome of validating one episode manifest."""

    episode_id: str | None = None
    ok: bool = False
    reason_codes: list[str] = field(default_factory=list)
    detail: list[dict[str, Any]] = field(default_factory=list)

    def fail(self, code: str, **info: Any) -> "ValidationResult":
        self.reason_codes.append(code)
        self.detail.append({"code": code, **info})
        self.ok = False
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "ok": self.ok,
            "reason_codes": list(self.reason_codes),
            "detail": list(self.detail),
        }


# --------------------------------------------------------------------------------------------
# Goal registry
# --------------------------------------------------------------------------------------------


class GoalRegistry:
    """The locked goal bank.

    A route episode that cannot resolve its ``goal_id`` to exactly one locked record fails before
    any frame or trajectory is processed. This is the control that makes goal substitution
    structurally impossible rather than merely discouraged.
    """

    REQUIRED_FIELDS = (
        "goal_id", "scene_id", "scene_usd_sha256", "map_version", "split", "goal_pose",
        "camera_prim", "camera_frame_id", "camera_resolution", "camera_encoding",
        "goal_image_path", "goal_image_sha256", "goal_capture_timestamp",
        "capture_authorisation_id",
    )

    def __init__(self, records: Sequence[dict[str, Any]]):
        self.records = list(records)
        self._by_id: dict[str, list[dict[str, Any]]] = {}
        for rec in self.records:
            self._by_id.setdefault(rec.get("goal_id"), []).append(rec)

    @classmethod
    def from_file(cls, path: str | Path) -> "GoalRegistry":
        data = json.loads(Path(path).read_text())
        return cls(data["goals"] if isinstance(data, dict) else data)

    def structural_errors(self) -> list[dict[str, Any]]:
        """Registry-level problems that make the whole bank unusable."""
        errs: list[dict[str, Any]] = []
        for rec in self.records:
            missing = [f for f in self.REQUIRED_FIELDS if rec.get(f) in (None, "")]
            if missing:
                errs.append({"code": H8_GOAL_HASH_MISSING if "goal_image_sha256" in missing
                             else H8_MANIFEST_SCHEMA_INVALID,
                             "goal_id": rec.get("goal_id"), "missing": missing})
            if rec.get("goal_id") in PLACEHOLDER_GOAL_IDS:
                errs.append({"code": H8_GOAL_ID_PLACEHOLDER, "goal_id": rec.get("goal_id")})
        for gid, recs in self._by_id.items():
            if len(recs) > 1:
                errs.append({"code": H8_GOAL_AMBIGUOUS, "goal_id": gid, "count": len(recs)})
        # A goal image reused across splits defeats held-out evaluation.
        by_hash: dict[str, set[str]] = {}
        for rec in self.records:
            h = rec.get("goal_image_sha256")
            if h:
                by_hash.setdefault(h, set()).add(rec.get("split"))
        for h, splits in by_hash.items():
            if len(splits) > 1:
                errs.append({"code": H8_GOAL_IMAGE_CROSS_SPLIT_REUSE,
                             "goal_image_sha256": h, "splits": sorted(splits)})
        return errs

    def resolve(self, manifest: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Resolve a manifest's goal against the bank. Returns (record | None, errors)."""
        goal = manifest.get("goal") or {}
        gid = goal.get("goal_id")
        errs: list[dict[str, Any]] = []
        if not gid:
            return None, [{"code": H8_GOAL_ID_MISSING}]
        if gid in PLACEHOLDER_GOAL_IDS:
            return None, [{"code": H8_GOAL_ID_PLACEHOLDER, "goal_id": gid}]
        recs = self._by_id.get(gid, [])
        if not recs:
            return None, [{"code": H8_GOAL_NOT_FOUND, "goal_id": gid}]
        if len(recs) > 1:
            return None, [{"code": H8_GOAL_AMBIGUOUS, "goal_id": gid, "count": len(recs)}]
        rec = recs[0]

        if not goal.get("goal_image_sha256"):
            errs.append({"code": H8_GOAL_HASH_MISSING, "goal_id": gid})
        elif goal["goal_image_sha256"] != rec.get("goal_image_sha256"):
            errs.append({"code": H8_GOAL_HASH_MISMATCH, "goal_id": gid,
                         "manifest": goal["goal_image_sha256"], "registry": rec.get("goal_image_sha256")})

        scene = (manifest.get("scene") or {}).get("scene_usd_sha256")
        if scene and rec.get("scene_usd_sha256") and scene != rec["scene_usd_sha256"]:
            errs.append({"code": H8_GOAL_SCENE_MISMATCH, "goal_id": gid})
        mv = (manifest.get("map") or {}).get("map_version")
        if mv and rec.get("map_version") and mv != rec["map_version"]:
            errs.append({"code": H8_GOAL_MAP_MISMATCH, "goal_id": gid,
                         "manifest": mv, "registry": rec["map_version"]})
        if manifest.get("split") and rec.get("split") and manifest["split"] != rec["split"]:
            errs.append({"code": H8_GOAL_SPLIT_MISMATCH, "goal_id": gid,
                         "manifest": manifest["split"], "registry": rec["split"]})

        gp, rp = goal.get("goal_pose") or {}, rec.get("goal_pose") or {}
        if gp and rp:
            d = math.hypot(gp.get("x", 0.0) - rp.get("x", 0.0), gp.get("y", 0.0) - rp.get("y", 0.0))
            if d > 1e-6:
                errs.append({"code": H8_GOAL_POSE_MISMATCH, "goal_id": gid, "distance_m": round(d, 9)})

        cam = manifest.get("camera") or {}
        if cam.get("camera_prim") and rec.get("camera_prim") and \
                cam["camera_prim"] != rec["camera_prim"]:
            errs.append({"code": H8_GOAL_CAMERA_MISMATCH, "goal_id": gid})
        if rec.get("camera_resolution") and list(rec["camera_resolution"]) != CANONICAL_RESOLUTION:
            errs.append({"code": H8_GOAL_RESOLUTION_MISMATCH, "goal_id": gid,
                         "registry_resolution": rec["camera_resolution"]})
        return rec, errs


# --------------------------------------------------------------------------------------------
# Manifest validation
# --------------------------------------------------------------------------------------------


def _pose_missing(p: Any) -> bool:
    return not isinstance(p, dict) or any(k not in p for k in ("x", "y", "yaw_rad"))


def validate_manifest(
    manifest: dict[str, Any],
    *,
    registry: GoalRegistry | None = None,
    require_navmesh: bool = False,
) -> ValidationResult:
    """Validate one episode manifest fail-closed. Collects every applicable reason code."""
    res = ValidationResult(episode_id=manifest.get("episode_id"))
    res.ok = True

    if manifest.get("manifest_version") != MANIFEST_VERSION:
        res.fail(H8_MANIFEST_VERSION_UNSUPPORTED, found=manifest.get("manifest_version"),
                 expected=MANIFEST_VERSION)
    if not manifest.get("episode_id"):
        res.fail(H8_MANIFEST_SCHEMA_INVALID, field="episode_id")
    if not manifest.get("capture_authorisation_id"):
        res.fail(H8_CAPTURE_AUTHORISATION_MISSING)

    # --- scene -------------------------------------------------------------------------------
    scene = manifest.get("scene") or {}
    if not scene.get("scene_usd_sha256"):
        res.fail(H8_SCENE_DIGEST_MISSING)
    if scene.get("scene_identity_pass") is not True:
        res.fail(H8_SCENE_IDENTITY_FAILED, scene_identity_pass=scene.get("scene_identity_pass"))

    # --- map / navmesh ------------------------------------------------------------------------
    mp = manifest.get("map") or {}
    if not mp.get("map_version"):
        res.fail(H8_MAP_VERSION_MISSING)
    if require_navmesh and not mp.get("navmesh_version"):
        res.fail(H8_NAVMESH_VERSION_MISSING)

    # --- split --------------------------------------------------------------------------------
    if manifest.get("split") not in SPLITS:
        res.fail(H8_SPLIT_UNKNOWN, split=manifest.get("split"))

    # --- goal ---------------------------------------------------------------------------------
    goal = manifest.get("goal") or {}
    gid = goal.get("goal_id")
    if not gid:
        res.fail(H8_GOAL_ID_MISSING)
    elif gid in PLACEHOLDER_GOAL_IDS:
        res.fail(H8_GOAL_ID_PLACEHOLDER, goal_id=gid)
    if gid and not goal.get("goal_image_sha256"):
        res.fail(H8_GOAL_HASH_MISSING, goal_id=gid)
    if registry is not None and gid and gid not in PLACEHOLDER_GOAL_IDS:
        _, errs = registry.resolve(manifest)
        for e in errs:
            res.fail(e.pop("code"), **e)

    # --- success criterion --------------------------------------------------------------------
    sc = manifest.get("success_criterion") or {}
    if sc.get("success_radius_m") is None:
        res.fail(H8_SUCCESS_RADIUS_MISSING)
    elif abs(float(sc["success_radius_m"]) - CANONICAL_SUCCESS_RADIUS_M) > 1e-9:
        res.fail(H8_SUCCESS_RADIUS_MISMATCH, found=sc["success_radius_m"],
                 expected=CANONICAL_SUCCESS_RADIUS_M)
    if sc.get("preregistered") is not True or not sc.get("approved_by"):
        res.fail(H8_SUCCESS_CRITERION_NOT_PREREGISTERED,
                 preregistered=sc.get("preregistered"), approved_by=sc.get("approved_by"))

    # --- camera -------------------------------------------------------------------------------
    cam = manifest.get("camera") or {}
    if not cam.get("camera_prim") or not cam.get("camera_frame_id"):
        res.fail(H8_CAMERA_IDENTITY_MISSING)
    if "camera_resolution" not in cam:
        res.fail(H8_ACQUISITION_RESOLUTION_MISSING)
    else:
        r = cam["camera_resolution"]
        if not (isinstance(r, (list, tuple)) and len(r) == 2
                and all(isinstance(v, int) and not isinstance(v, bool) for v in r)):
            res.fail(H8_ACQUISITION_RESOLUTION_MALFORMED, found=r)
        elif list(r) != CANONICAL_RESOLUTION:
            res.fail(H8_ACQUISITION_RESOLUTION_MISMATCH, found=list(r),
                     expected=CANONICAL_RESOLUTION)
    if cam.get("camera_encoding") != CANONICAL_ENCODING:
        res.fail(H8_ACQUISITION_ENCODING_MISMATCH, found=cam.get("camera_encoding"),
                 expected=CANONICAL_ENCODING)
    raise_m = cam.get("camera_mount_raise_m")
    if raise_m is None or abs(float(raise_m) - CANONICAL_CAMERA_RAISE_M) > 1e-9:
        res.fail(H8_CAMERA_MOUNT_UNSUPPORTED, found=raise_m, expected=CANONICAL_CAMERA_RAISE_M)

    # --- controller ---------------------------------------------------------------------------
    ctl = manifest.get("controller") or {}
    mode = ctl.get("controller_mode")
    if mode is None:
        res.fail(H8_CONTROLLER_MODE_MISSING)
    elif mode not in CONTROLLER_MODES:
        res.fail(H8_CONTROLLER_MODE_UNKNOWN, found=mode, allowed=list(CONTROLLER_MODES))
    else:
        pil = ctl.get("policy_in_loop")
        if mode in POLICY_IN_LOOP_MODES:
            if pil is not True:
                res.fail(H8_CONTROLLER_POLICY_MISMATCH, controller_mode=mode, policy_in_loop=pil)
            if not ctl.get("policy_checkpoint_sha256"):
                res.fail(H8_CONTROLLER_CHECKPOINT_MISSING, controller_mode=mode)
        elif pil is True:
            res.fail(H8_CONTROLLER_POLICY_MISMATCH, controller_mode=mode, policy_in_loop=pil)

    # --- start pose ---------------------------------------------------------------------------
    declared, observed = manifest.get("start_pose_declared"), manifest.get("start_pose_observed")
    if _pose_missing(declared):
        res.fail(H8_START_POSE_DECLARED_MISSING)
    if _pose_missing(observed):
        res.fail(H8_START_POSE_OBSERVED_MISSING)
    if not _pose_missing(declared) and not _pose_missing(observed):
        if declared.get("frame") and observed.get("frame") and \
                declared["frame"] != observed["frame"]:
            res.fail(H8_START_POSE_FRAME_MISMATCH, declared=declared.get("frame"),
                     observed=observed.get("frame"))
        dp = math.hypot(declared["x"] - observed["x"], declared["y"] - observed["y"])
        dyaw = abs(_wrap(declared["yaw_rad"] - observed["yaw_rad"]))
        if dp > START_POSE_TOLERANCE_M or dyaw > START_POSE_TOLERANCE_RAD:
            res.fail(H8_START_POSE_TOLERANCE_EXCEEDED, position_m=round(dp, 6),
                     yaw_rad=round(dyaw, 6), tolerance_position_m=START_POSE_TOLERANCE_M,
                     tolerance_yaw_rad=START_POSE_TOLERANCE_RAD)

    # --- contact telemetry --------------------------------------------------------------------
    ct = manifest.get("contact_telemetry") or {}
    if ct.get("contact_telemetry_available") is not True:
        res.fail(H8_CONTACT_TELEMETRY_UNAVAILABLE,
                 available=ct.get("contact_telemetry_available"))

    res.ok = not res.reason_codes
    return res


def _wrap(a: float) -> float:
    """Wrap an angle to (-pi, pi]."""
    return math.atan2(math.sin(a), math.cos(a))


# --------------------------------------------------------------------------------------------
# Duplicate / retry screening
# --------------------------------------------------------------------------------------------


def episode_identity_digest(manifest: dict[str, Any]) -> str:
    """Content digest over the fields that make an episode a distinct *sample*.

    Deliberately excludes episode_id and timestamps: two captures that differ only in when they ran
    are re-runs, not independent samples.
    """
    goal = manifest.get("goal") or {}
    payload = {
        "route_instance_id": (manifest.get("route") or {}).get("route_instance_id"),
        "goal_id": goal.get("goal_id"),
        "goal_image_sha256": goal.get("goal_image_sha256"),
        "start_pose_observed": manifest.get("start_pose_observed"),
        "goal_pose": goal.get("goal_pose"),
        "controller_mode": (manifest.get("controller") or {}).get("controller_mode"),
        "trajectory_digest": (manifest.get("counters") or {}).get("trajectory_digest"),
        "image_sequence_digest": (manifest.get("counters") or {}).get("image_sequence_digest"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def screen_duplicates(manifests: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Classify re-runs and cross-split route reuse.

    A retry is NOT an independent sample. The audit found `h8mx_val_val_A` and
    `h8mx_val_val_A_retry` identical to four decimal places on both path length and terminal goal
    distance; counting them separately would inflate any N.
    """
    ms = list(manifests)
    by_digest: dict[str, list[str]] = {}
    by_route: dict[str, set[str]] = {}
    for m in ms:
        eid = m.get("episode_id")
        by_digest.setdefault(episode_identity_digest(m), []).append(eid)
        rid = (m.get("route") or {}).get("route_instance_id")
        if rid:
            by_route.setdefault(rid, set()).add(m.get("split"))

    reruns = {d: ids for d, ids in by_digest.items() if len(ids) > 1}
    split_dupes = {r: sorted(s) for r, s in by_route.items() if len(s) > 1}
    findings: list[dict[str, Any]] = []
    for d, ids in sorted(reruns.items()):
        findings.append({"code": H8_RETRY_NOT_INDEPENDENT, "identity_digest": d,
                         "episode_ids": sorted(ids),
                         "note": "identical content digest - re-runs of one instance, not "
                                 "independent samples"})
    for r, splits in sorted(split_dupes.items()):
        findings.append({"code": H8_ROUTE_SPLIT_DUPLICATE, "route_instance_id": r,
                         "splits": splits,
                         "note": "one route instance appears in more than one split"})
    return {
        "n_manifests": len(ms),
        "n_distinct_instances": len(by_digest),
        "n_rerun_groups": len(reruns),
        "findings": findings,
        "ok": not findings,
    }


# --------------------------------------------------------------------------------------------
# Metric readiness
# --------------------------------------------------------------------------------------------


def metric_readiness(
    manifest: dict[str, Any],
    *,
    alignment_ok: bool = True,
    manifest_valid: bool = True,
) -> dict[str, str]:
    """Per-metric readiness state. Never returns a numeric zero in place of missing evidence."""
    goal = manifest.get("goal") or {}
    sc = manifest.get("success_criterion") or {}
    ref = manifest.get("reference_path") or {}
    mp = manifest.get("map") or {}
    stop = manifest.get("stop_event") or {}
    ct = manifest.get("contact_telemetry") or {}

    has_goal = bool(goal.get("goal_id")) and goal.get("goal_id") not in PLACEHOLDER_GOAL_IDS
    has_tau = sc.get("success_radius_m") is not None
    has_navmesh = bool(mp.get("navmesh_version"))
    has_ref = ref.get("source") not in (None, "UNAVAILABLE") and bool(ref.get("nodes"))
    has_stop = "stop_emitted" in stop
    has_contacts = ct.get("contact_telemetry_available") is True
    has_latency = bool((manifest.get("counters") or {}).get("inference_latency_samples"))

    out: dict[str, str] = {}
    for m in METRICS:
        if not manifest_valid:
            out[m] = NOT_COMPUTED_UNTRUSTED_METADATA
            continue
        if not alignment_ok:
            out[m] = NOT_COMPUTED_ALIGNMENT_FAILED
            continue
        if m == "TL":
            out[m] = COMPUTABLE_VALID
        elif m == "provenance_completeness":
            out[m] = COMPUTABLE_VALID
        elif m == "completion_time":
            out[m] = COMPUTABLE_DIAGNOSTIC_ONLY
        elif m in ("collision_count", "collision_rate"):
            out[m] = COMPUTABLE_VALID if has_contacts else NOT_COMPUTED_MISSING_CONTACTS
        elif m in ("inference_latency", "command_latency"):
            out[m] = COMPUTABLE_DIAGNOSTIC_ONLY if has_latency \
                else NOT_COMPUTED_MISSING_LATENCY_TIMESTAMPS
        elif m in PATH_METRICS:
            if not has_navmesh:
                out[m] = NOT_COMPUTED_MISSING_NAVMESH
            elif not has_ref:
                out[m] = NOT_COMPUTED_MISSING_REFERENCE_PATH
            elif m in ("SPL", "SDTW") and not (has_goal and has_tau):
                out[m] = NOT_COMPUTED_MISSING_GOAL if not has_goal \
                    else NOT_COMPUTED_MISSING_SUCCESS_RADIUS
            else:
                out[m] = COMPUTABLE_VALID
        elif m == "NE":
            out[m] = COMPUTABLE_VALID if has_goal else NOT_COMPUTED_MISSING_GOAL
        elif m in ("stop_timing_error", "overshoot_distance"):
            if not has_goal:
                out[m] = NOT_COMPUTED_MISSING_GOAL
            elif not has_tau:
                out[m] = NOT_COMPUTED_MISSING_SUCCESS_RADIUS
            elif not has_stop:
                out[m] = NOT_COMPUTED_MISSING_STOP_EVENT
            else:
                out[m] = COMPUTABLE_VALID
        else:  # SR / OSR / gap / pose-aligned success
            if not has_goal:
                out[m] = NOT_COMPUTED_MISSING_GOAL
            elif not has_tau:
                out[m] = NOT_COMPUTED_MISSING_SUCCESS_RADIUS
            elif m != "OSR_0.50" and not has_stop:
                out[m] = NOT_COMPUTED_MISSING_STOP_EVENT
            else:
                out[m] = COMPUTABLE_VALID
    return out
