"""scripts/gnm/h8_evidence_schema.py

H8 Render-Valid / Drive-Valid EVIDENCE SCHEMA + pure conformance validator (DESIGN GATE).

This module defines a versioned, fail-closed evidence *contract* and a side-effect-free conformance
validator for it. It answers, for one planned H8 hospital capture instance:

    "Do we possess current, authentic, correctly bound and independently verifiable evidence that the
     scene renders correctly and that the intended robot route is drive-valid?"

SCOPE / BOUNDARY (schema-design gate only):
  * NO Isaac Sim, NO ROS 2, NO camera, NO robot command, NO policy/model inference.
  * NO dataset directory, NO RGB image, NO trajectory, NO rosbag, NO capture backend, NO real
    evidence provider. This module imports NONE of those.
  * It validates the STRUCTURE, IDENTITY BINDING, FRESHNESS, REVOCATION, INTEGRITY and PAIRING of
    synthetic evidence envelopes. A schema-valid synthetic fixture is NOT runtime (Level-3) evidence
    and MUST NOT be promoted to one.

Determinism: time checks take an INJECTED `review_time` (RFC 3339 UTC). Digests are SHA-256 over a
canonical JSON serialisation (sorted keys, tight separators, UTF-8). No wall-clock, no randomness.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone

# ── versions ──────────────────────────────────────────────────────────────────────
SCHEMA_ID = "h8-evidence-envelope"
SCHEMA_VERSION = "h8-evidence/1.0.0"
SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})
VALIDATOR_VERSION = "h8-evidence-validator/1.0.0"
CANONICALIZATION = "h8-canonical-json/1.0"
DIGEST_ALGORITHM = "sha256"

# CL_BOUND_XY watchdog value — MIRRORED read-only from the reviewed drive-validation harness (6.0 m).
# This module never modifies it; the schema binds evidence to exactly this value.
CL_BOUND_XY = 6.0

EVIDENCE_TYPES = frozenset({"render_valid", "drive_valid"})
STATUS_VALUES = frozenset({"valid", "invalid", "indeterminate", "revoked"})
SPLIT_VALUES = frozenset({"train", "val", "test"})

# A synthetic-test-fixture producer sentinel. In production mode an envelope produced by a fixture is
# rejected (threat: accidental acceptance of test fixtures in production).
FIXTURE_PRODUCER = "synthetic-test-fixture"

# ── stable reason-code taxonomy (§20) ─────────────────────────────────────────────
EVIDENCE_MISSING = "EVIDENCE_MISSING"
SCHEMA_VERSION_UNSUPPORTED = "SCHEMA_VERSION_UNSUPPORTED"
SCHEMA_MALFORMED = "SCHEMA_MALFORMED"
EVIDENCE_TYPE_INVALID = "EVIDENCE_TYPE_INVALID"
STATUS_NOT_VALID = "STATUS_NOT_VALID"
EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
EVIDENCE_NOT_YET_VALID = "EVIDENCE_NOT_YET_VALID"
EVIDENCE_REVOKED = "EVIDENCE_REVOKED"
INSTANCE_MISMATCH = "INSTANCE_MISMATCH"
SCENE_MISMATCH = "SCENE_MISMATCH"
ROUTE_MISMATCH = "ROUTE_MISMATCH"
CONFIG_MISMATCH = "CONFIG_MISMATCH"
FRAME_MISMATCH = "FRAME_MISMATCH"
BOUND_MISMATCH = "BOUND_MISMATCH"
DIGEST_MISMATCH = "DIGEST_MISMATCH"
SIGNATURE_UNVERIFIED = "SIGNATURE_UNVERIFIED"
VALIDITY_WINDOW_MISMATCH = "VALIDITY_WINDOW_MISMATCH"
DUPLICATE_EVIDENCE_ID = "DUPLICATE_EVIDENCE_ID"
FIXTURE_IN_PRODUCTION = "FIXTURE_IN_PRODUCTION"
PAIR_INCOMPLETE = "PAIR_INCOMPLETE"
PAIR_BINDING_MISMATCH = "PAIR_BINDING_MISMATCH"
PAIR_WINDOW_DISJOINT = "PAIR_WINDOW_DISJOINT"
ACCEPTED = "ACCEPTED"

REASON_CODES = frozenset({
    EVIDENCE_MISSING, SCHEMA_VERSION_UNSUPPORTED, SCHEMA_MALFORMED, EVIDENCE_TYPE_INVALID,
    STATUS_NOT_VALID, EVIDENCE_EXPIRED, EVIDENCE_NOT_YET_VALID, EVIDENCE_REVOKED, INSTANCE_MISMATCH,
    SCENE_MISMATCH, ROUTE_MISMATCH, CONFIG_MISMATCH, FRAME_MISMATCH, BOUND_MISMATCH, DIGEST_MISMATCH,
    SIGNATURE_UNVERIFIED, VALIDITY_WINDOW_MISMATCH, DUPLICATE_EVIDENCE_ID, FIXTURE_IN_PRODUCTION,
    PAIR_INCOMPLETE, PAIR_BINDING_MISMATCH, PAIR_WINDOW_DISJOINT, ACCEPTED,
})

_EVIDENCE_ID_RE = re.compile(r"^h8ev-[a-z]+-[a-z0-9]{2,}-[0-9]{4,}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# top-level envelope keys (§5) — strict: unknown top-level keys are rejected.
_ENVELOPE_KEYS = frozenset({
    "schema_version", "evidence_id", "evidence_type", "status", "subject", "context", "producer",
    "observation_time", "issue_time", "validity_window", "integrity", "provenance", "revocation",
    "payload",
})

# subject identity-binding fields (§6). Fields required for BOTH evidence types.
_SUBJECT_COMMON = (
    "dataset_plan_id", "instance_id", "split", "scene_id", "scene_digest", "route_id",
    "route_plan_digest", "config_digest", "cl_bound_xy", "coordinate_frame",
)
# identity fields compared against an `expected` binding, mapped to their mismatch reason codes.
_BINDING_REASON = {
    "instance_id": INSTANCE_MISMATCH,
    "scene_id": SCENE_MISMATCH,
    "scene_digest": SCENE_MISMATCH,
    "route_id": ROUTE_MISMATCH,
    "route_plan_digest": ROUTE_MISMATCH,
    "config_digest": CONFIG_MISMATCH,
    "coordinate_frame": FRAME_MISMATCH,
    "dataset_plan_id": INSTANCE_MISMATCH,
    "split": INSTANCE_MISMATCH,
}

_RENDER_PAYLOAD_FIELDS = (
    "scene_loaded", "camera_present", "camera_transform_matches", "resolution", "encoding",
    "frame_nonempty", "frame_not_constant", "required_geometry_visible", "no_invalid_render_condition",
    "validation_method", "thresholds", "diagnostic_ref",
)
_DRIVE_PAYLOAD_FIELDS = (
    "start_bound_to_instance", "goal_bound_to_instance", "within_spatial_bounds", "collision_feasible",
    "min_clearance_m", "clearance_threshold_m", "avoids_prohibited_geometry", "route_length_m",
    "waypoint_count", "coordinate_frame", "validation_method", "planner_version", "sim_context",
    "degraded", "diagnostic_ref",
)


# ── canonicalisation + digests (§12, §15) ─────────────────────────────────────────
def canonical_bytes(obj) -> bytes:
    """Deterministic canonical JSON serialisation: sorted keys, tight separators, UTF-8, no NaN."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def content_digest(obj) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(obj)).hexdigest()


def _digest_view(envelope: dict) -> dict:
    """Envelope copy with self-referential integrity fields blanked, for the content digest."""
    e = copy.deepcopy(envelope)
    ig = e.get("integrity")
    if isinstance(ig, dict):
        # blank every derived/self-referential integrity field so the content digest depends only on
        # the semantic content (and is stable between sealing and validation).
        ig["subject_digest"] = ""
        ig["payload_digest"] = ""
        ig["content_digest"] = ""
        ig["signature"] = None
        ig["verification_status"] = ""
    return e


def compute_digests(envelope: dict) -> dict:
    """The three canonical digests the schema binds (§12): subject, payload, whole-content."""
    return {
        "subject_digest": content_digest(envelope.get("subject", {})),
        "payload_digest": content_digest(envelope.get("payload", {})),
        "content_digest": content_digest(_digest_view(envelope)),
    }


# ── time helpers (§10) ────────────────────────────────────────────────────────────
def _parse_ts(value):
    """Parse an RFC 3339 / ISO-8601 timestamp into a timezone-AWARE UTC datetime.
    Raises ValueError on a non-string, an unparseable value, or a naive (tz-less) timestamp."""
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    s = value.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)  # raises ValueError if malformed
    if dt.tzinfo is None:
        raise ValueError("timestamp missing timezone (naive timestamps are rejected)")
    return dt.astimezone(timezone.utc)


# ── structured result (§19) ───────────────────────────────────────────────────────
def _result(accepted, code, explanation, env=None, failed_field=None, expected=None, observed=None):
    subj = (env or {}).get("subject", {}) if isinstance(env, dict) else {}
    return {
        "accepted": bool(accepted),
        "reason_code": code,
        "explanation": explanation,
        "evidence_id": (env or {}).get("evidence_id") if isinstance(env, dict) else None,
        "instance_id": subj.get("instance_id") if isinstance(subj, dict) else None,
        "evidence_type": (env or {}).get("evidence_type") if isinstance(env, dict) else None,
        "failed_field": failed_field,
        "expected": expected,
        "observed": observed,
        "schema_version": (env or {}).get("schema_version") if isinstance(env, dict) else None,
        "validator_version": VALIDATOR_VERSION,
    }


def _ok(env):
    return _result(True, ACCEPTED, "evidence envelope satisfies the H8 conformance contract", env)


# ── the conformance validator (§18) ───────────────────────────────────────────────
def validate_envelope(envelope, *, review_time, expected=None, seen_ids=None,
                      require_signature=False, production_mode=False) -> dict:
    """Pure, side-effect-free conformance check for ONE evidence envelope. Returns a structured result
    (§19). Fails closed: any structural, identity, freshness, revocation or integrity defect → accepted
    False with a stable reason code. `review_time` (RFC 3339) is INJECTED — no wall-clock is read.
    `expected` is the caller's required identity binding; `seen_ids` detects duplicate evidence ids."""
    # 0. presence
    if envelope is None:
        return _result(False, EVIDENCE_MISSING, "no evidence supplied", None, "envelope")
    if not isinstance(envelope, dict):
        return _result(False, SCHEMA_MALFORMED, "envelope is not an object", None, "envelope",
                       "object", type(envelope).__name__)

    # 1. schema version (with downgrade / unsupported protection)
    sv = envelope.get("schema_version")
    if sv not in SUPPORTED_SCHEMA_VERSIONS:
        return _result(False, SCHEMA_VERSION_UNSUPPORTED, f"unsupported schema_version {sv!r}",
                       envelope, "schema_version", sorted(SUPPORTED_SCHEMA_VERSIONS), sv)

    # 2. structural: strict top-level key set + required nested objects
    keys = set(envelope.keys())
    unknown = keys - _ENVELOPE_KEYS
    if unknown:
        return _result(False, SCHEMA_MALFORMED, f"unknown top-level field(s): {sorted(unknown)}",
                       envelope, sorted(unknown)[0], "no unknown fields", sorted(unknown))
    missing = _ENVELOPE_KEYS - keys
    if missing:
        return _result(False, SCHEMA_MALFORMED, f"missing top-level field(s): {sorted(missing)}",
                       envelope, sorted(missing)[0], "present", "absent")
    for sect in ("subject", "context", "producer", "validity_window", "integrity", "provenance",
                 "revocation", "payload"):
        if not isinstance(envelope.get(sect), dict):
            return _result(False, SCHEMA_MALFORMED, f"section {sect!r} must be an object", envelope,
                           sect, "object", type(envelope.get(sect)).__name__)

    ev_id = envelope.get("evidence_id")
    if not isinstance(ev_id, str) or not _EVIDENCE_ID_RE.match(ev_id):
        return _result(False, SCHEMA_MALFORMED, "evidence_id malformed", envelope, "evidence_id",
                       _EVIDENCE_ID_RE.pattern, ev_id)

    et = envelope.get("evidence_type")
    if et not in EVIDENCE_TYPES:
        return _result(False, EVIDENCE_TYPE_INVALID, f"evidence_type {et!r} not permitted", envelope,
                       "evidence_type", sorted(EVIDENCE_TYPES), et)

    # 3. duplicate evidence id (replay / duplicate-id threat)
    if seen_ids is not None and ev_id in seen_ids:
        return _result(False, DUPLICATE_EVIDENCE_ID, f"evidence_id {ev_id!r} already seen", envelope,
                       "evidence_id", "unique", "duplicate")

    # 4. fixture-in-production guard
    prod = envelope.get("producer", {})
    if production_mode and prod.get("component") == FIXTURE_PRODUCER:
        return _result(False, FIXTURE_IN_PRODUCTION, "synthetic test fixture rejected in production",
                       envelope, "producer.component", "real producer", FIXTURE_PRODUCER)

    # 5. status + revocation (both must clear before any acceptance)
    rev = envelope.get("revocation", {})
    status = envelope.get("status")
    if status not in STATUS_VALUES:
        return _result(False, STATUS_NOT_VALID, f"status {status!r} not in enum", envelope, "status",
                       sorted(STATUS_VALUES), status)
    if status == "revoked" or rev.get("revoked") is True:
        return _result(False, EVIDENCE_REVOKED, "evidence is revoked/superseded", envelope,
                       "revocation.revoked", "not revoked", "revoked")
    if status != "valid":
        return _result(False, STATUS_NOT_VALID, f"status {status!r} does not satisfy the gate",
                       envelope, "status", "valid", status)

    # 6. subject identity binding present + typed
    subj = envelope.get("subject", {})
    for f in _SUBJECT_COMMON:
        if f not in subj or subj.get(f) in (None, ""):
            return _result(False, SCHEMA_MALFORMED, f"subject.{f} missing", envelope, f"subject.{f}",
                           "present", subj.get(f))
    if subj.get("split") not in SPLIT_VALUES:
        return _result(False, SCHEMA_MALFORMED, "subject.split invalid", envelope, "subject.split",
                       sorted(SPLIT_VALUES), subj.get("split"))
    for f in ("scene_digest", "route_plan_digest", "config_digest"):
        if not _DIGEST_RE.match(str(subj.get(f))):
            return _result(False, SCHEMA_MALFORMED, f"subject.{f} not a sha256 digest", envelope,
                           f"subject.{f}", _DIGEST_RE.pattern, subj.get(f))

    # 7. CL_BOUND_XY binding — must equal the watchdog value exactly
    if subj.get("cl_bound_xy") != CL_BOUND_XY:
        return _result(False, BOUND_MISMATCH, "subject.cl_bound_xy != watchdog", envelope,
                       "subject.cl_bound_xy", CL_BOUND_XY, subj.get("cl_bound_xy"))

    # 8. integrity: recompute digests + signature policy
    ig = envelope.get("integrity", {})
    digs = compute_digests(envelope)
    for name in ("subject_digest", "payload_digest", "content_digest"):
        if ig.get(name) != digs[name]:
            return _result(False, DIGEST_MISMATCH, f"integrity.{name} mismatch", envelope,
                           f"integrity.{name}", digs[name], ig.get(name))
    if require_signature and ig.get("verification_status") != "verified":
        return _result(False, SIGNATURE_UNVERIFIED, "signature required but not verified", envelope,
                       "integrity.verification_status", "verified", ig.get("verification_status"))

    # 9. freshness / validity window (§10)
    win = envelope.get("validity_window", {})
    try:
        rt = _parse_ts(review_time)
        obs = _parse_ts(envelope.get("observation_time"))
        iss = _parse_ts(envelope.get("issue_time"))
        nb = _parse_ts(win.get("not_before"))
        na = _parse_ts(win.get("not_after"))
    except ValueError as e:
        return _result(False, SCHEMA_MALFORMED, f"timestamp error: {e}", envelope, "validity_window",
                       "RFC3339 UTC with timezone", str(e))
    skew = int(win.get("clock_skew_seconds", 0) or 0)
    if na <= nb:
        return _result(False, VALIDITY_WINDOW_MISMATCH, "not_after <= not_before", envelope,
                       "validity_window.not_after", "> not_before", win.get("not_after"))
    if iss > na:
        return _result(False, VALIDITY_WINDOW_MISMATCH, "issue_time after not_after", envelope,
                       "issue_time", "<= not_after", envelope.get("issue_time"))
    if obs > iss:
        return _result(False, VALIDITY_WINDOW_MISMATCH, "observation_time after issue_time", envelope,
                       "observation_time", "<= issue_time", envelope.get("observation_time"))
    if rt < nb - _skew_delta(skew):
        return _result(False, EVIDENCE_NOT_YET_VALID, "review_time before validity window", envelope,
                       "validity_window.not_before", win.get("not_before"), review_time)
    if rt > na + _skew_delta(skew):
        return _result(False, EVIDENCE_EXPIRED, "review_time after validity window", envelope,
                       "validity_window.not_after", win.get("not_after"), review_time)
    max_age = win.get("max_age_seconds")
    if max_age is not None and (rt - obs).total_seconds() > int(max_age) + skew:
        return _result(False, EVIDENCE_EXPIRED, "observation older than max_age_seconds", envelope,
                       "validity_window.max_age_seconds", max_age, (rt - obs).total_seconds())

    # 10. expected identity binding (cross-instance / scene / route / config / frame substitution)
    if expected:
        for f, code in _BINDING_REASON.items():
            if f in expected and subj.get(f) != expected[f]:
                return _result(False, code, f"subject.{f} does not match expected", envelope,
                               f"subject.{f}", expected[f], subj.get(f))
        if "cl_bound_xy" in expected and subj.get("cl_bound_xy") != expected["cl_bound_xy"]:
            return _result(False, BOUND_MISMATCH, "cl_bound_xy != expected", envelope,
                           "subject.cl_bound_xy", expected["cl_bound_xy"], subj.get("cl_bound_xy"))

    # 11. type-specific payload
    payload = envelope.get("payload", {})
    fields = _RENDER_PAYLOAD_FIELDS if et == "render_valid" else _DRIVE_PAYLOAD_FIELDS
    for f in fields:
        if f not in payload:
            return _result(False, SCHEMA_MALFORMED, f"payload.{f} missing for {et}", envelope,
                           f"payload.{f}", "present", "absent")
    if et == "drive_valid" and payload.get("degraded") is True:
        return _result(False, STATUS_NOT_VALID, "drive payload degraded result is not valid", envelope,
                       "payload.degraded", False, True)

    return _ok(envelope)


def _skew_delta(skew_seconds):
    from datetime import timedelta
    return timedelta(seconds=int(skew_seconds))


# ── render+drive pairing (§14) ────────────────────────────────────────────────────
_PAIR_SHARED = ("dataset_plan_id", "instance_id", "scene_digest", "route_plan_digest",
                "config_digest", "coordinate_frame", "cl_bound_xy")


def validate_pair(render_env, drive_env, *, review_time, expected=None, seen_ids=None,
                  require_signature=False, production_mode=False) -> dict:
    """Validate a render+drive evidence PAIR (§14). Both must individually pass, share all identity
    bindings, and have sufficiently overlapping validity windows. Fails closed on a missing side."""
    if render_env is None or drive_env is None:
        return _result(False, PAIR_INCOMPLETE, "render+drive pair incomplete", render_env or drive_env,
                       "pair", "both present", "one missing")
    if (render_env.get("evidence_type"), drive_env.get("evidence_type")) != ("render_valid",
                                                                             "drive_valid"):
        return _result(False, EVIDENCE_TYPE_INVALID, "pair types must be (render_valid, drive_valid)",
                       render_env, "evidence_type",
                       ("render_valid", "drive_valid"),
                       (render_env.get("evidence_type"), drive_env.get("evidence_type")))
    ids = set(seen_ids or ())
    r = validate_envelope(render_env, review_time=review_time, expected=expected, seen_ids=ids,
                          require_signature=require_signature, production_mode=production_mode)
    if not r["accepted"]:
        return r
    ids.add(render_env.get("evidence_id"))
    d = validate_envelope(drive_env, review_time=review_time, expected=expected, seen_ids=ids,
                          require_signature=require_signature, production_mode=production_mode)
    if not d["accepted"]:
        return d
    rs, ds = render_env.get("subject", {}), drive_env.get("subject", {})
    for f in _PAIR_SHARED:
        if rs.get(f) != ds.get(f):
            return _result(False, PAIR_BINDING_MISMATCH, f"pair subject.{f} differs", drive_env,
                           f"subject.{f}", rs.get(f), ds.get(f))
    # validity windows must overlap
    rn, rx = _parse_ts(render_env["validity_window"]["not_before"]), \
        _parse_ts(render_env["validity_window"]["not_after"])
    dn, dx = _parse_ts(drive_env["validity_window"]["not_before"]), \
        _parse_ts(drive_env["validity_window"]["not_after"])
    if max(rn, dn) >= min(rx, dx):
        return _result(False, PAIR_WINDOW_DISJOINT, "pair validity windows do not overlap", drive_env,
                       "validity_window", "overlapping", "disjoint")
    return _result(True, ACCEPTED, "render+drive pair satisfies the H8 conformance contract", drive_env)


# ── synthetic fixture builders (§17) — clearly-marked NON-RUNTIME test evidence ────
def _seal(envelope: dict) -> dict:
    """Fill the integrity digests for a synthetic fixture so it is internally consistent."""
    digs = compute_digests(envelope)
    envelope["integrity"].update(digs)
    return envelope


def synthetic_render_evidence(instance_id="sfork_00", *, split="train",
                              scene_digest="sha256:" + "a" * 64,
                              route_plan_digest="sha256:" + "b" * 64,
                              config_digest="sha256:" + "c" * 64, verified=False, **overrides) -> dict:
    """Build a self-consistent SYNTHETIC render-valid envelope. NOT runtime evidence; producer identity
    is the fixture sentinel so production mode rejects it."""
    env = {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": f"h8ev-render-{instance_id.replace('_', '')}-0001",
        "evidence_type": "render_valid",
        "status": "valid",
        "subject": {
            "dataset_plan_id": "h8-synthetic-fork-v1", "instance_id": instance_id, "split": split,
            "scene_id": "synthetic_diagnostic_fork", "scene_digest": scene_digest,
            "route_id": f"{instance_id}_N", "route_plan_digest": route_plan_digest,
            "config_digest": config_digest, "cl_bound_xy": CL_BOUND_XY,
            "coordinate_frame": "hospital_world",
            "sim_context": {"simulator": "isaac-sim", "version": "5.1"},
        },
        "context": {"route_family": "N_vs_W_90", "claim_boundary": "SYNTHETIC_DIAGNOSTIC_ONLY",
                    "capture_mode": "recorded"},
        "producer": {"component": FIXTURE_PRODUCER, "version": "1.0.0", "method": "synthetic",
                     "key_id": None},
        "observation_time": "2026-07-16T00:00:00Z",
        "issue_time": "2026-07-16T00:00:01Z",
        "validity_window": {"not_before": "2026-07-16T00:00:00Z", "not_after": "2026-07-23T00:00:00Z",
                            "max_age_seconds": 1209600, "clock_source": "utc", "clock_skew_seconds": 5},
        "integrity": {"canonicalization": CANONICALIZATION, "digest_algorithm": DIGEST_ALGORITHM,
                      "subject_digest": "", "payload_digest": "", "content_digest": "",
                      "signature": None, "signature_algorithm": None, "key_id": None,
                      "verification_status": "verified" if verified else "unsigned"},
        "provenance": {"producer_component": FIXTURE_PRODUCER, "producer_version": "1.0.0",
                       "source_commit": "unknown", "run_id": "synthetic-0001", "host_label": "ci",
                       "method_id": "synthetic-render-fixture", "scene_source": "synthetic",
                       "config_source": "synthetic", "parent_evidence_id": None,
                       "generated_at": "2026-07-16T00:00:01Z", "review_state": "none"},
        "revocation": {"revoked": False, "revoked_at": None, "reason": None, "authority": None,
                       "replacement_evidence_id": None, "supersedes": None},
        "payload": {"scene_loaded": True, "camera_present": True, "camera_transform_matches": True,
                    "resolution": [640, 480], "encoding": "rgb8", "frame_nonempty": True,
                    "frame_not_constant": True, "required_geometry_visible": True,
                    "no_invalid_render_condition": True, "validation_method": "synthetic-check",
                    "thresholds": {"min_nonconstant_std": 3.0}, "diagnostic_ref": "synthetic://render"},
    }
    _apply_overrides(env, overrides)
    return _seal(env) if overrides.get("_reseal", True) else env


def synthetic_drive_evidence(instance_id="sfork_00", *, split="train",
                             scene_digest="sha256:" + "a" * 64,
                             route_plan_digest="sha256:" + "b" * 64,
                             config_digest="sha256:" + "c" * 64, verified=False, **overrides) -> dict:
    """Build a self-consistent SYNTHETIC drive-valid envelope. NOT runtime evidence."""
    env = {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": f"h8ev-drive-{instance_id.replace('_', '')}-0001",
        "evidence_type": "drive_valid",
        "status": "valid",
        "subject": {
            "dataset_plan_id": "h8-synthetic-fork-v1", "instance_id": instance_id, "split": split,
            "scene_id": "synthetic_diagnostic_fork", "scene_digest": scene_digest,
            "route_id": f"{instance_id}_N", "route_plan_digest": route_plan_digest,
            "config_digest": config_digest, "cl_bound_xy": CL_BOUND_XY,
            "coordinate_frame": "hospital_world",
            "sim_context": {"simulator": "isaac-sim", "version": "5.1"},
        },
        "context": {"route_family": "N_vs_W_90", "claim_boundary": "SYNTHETIC_DIAGNOSTIC_ONLY",
                    "capture_mode": "recorded"},
        "producer": {"component": FIXTURE_PRODUCER, "version": "1.0.0", "method": "synthetic",
                     "key_id": None},
        "observation_time": "2026-07-16T00:00:00Z",
        "issue_time": "2026-07-16T00:00:01Z",
        "validity_window": {"not_before": "2026-07-16T00:00:00Z", "not_after": "2026-07-23T00:00:00Z",
                            "max_age_seconds": 1209600, "clock_source": "utc", "clock_skew_seconds": 5},
        "integrity": {"canonicalization": CANONICALIZATION, "digest_algorithm": DIGEST_ALGORITHM,
                      "subject_digest": "", "payload_digest": "", "content_digest": "",
                      "signature": None, "signature_algorithm": None, "key_id": None,
                      "verification_status": "verified" if verified else "unsigned"},
        "provenance": {"producer_component": FIXTURE_PRODUCER, "producer_version": "1.0.0",
                       "source_commit": "unknown", "run_id": "synthetic-0001", "host_label": "ci",
                       "method_id": "synthetic-drive-fixture", "scene_source": "synthetic",
                       "config_source": "synthetic", "parent_evidence_id": None,
                       "generated_at": "2026-07-16T00:00:01Z", "review_state": "none"},
        "revocation": {"revoked": False, "revoked_at": None, "reason": None, "authority": None,
                       "replacement_evidence_id": None, "supersedes": None},
        "payload": {"start_bound_to_instance": True, "goal_bound_to_instance": True,
                    "within_spatial_bounds": True, "collision_feasible": True, "min_clearance_m": 0.42,
                    "clearance_threshold_m": 0.30, "avoids_prohibited_geometry": True,
                    "route_length_m": 7.5, "waypoint_count": 24, "coordinate_frame": "hospital_world",
                    "validation_method": "synthetic-overlap-check", "planner_version": "synthetic-1.0",
                    "sim_context": {"simulator": "isaac-sim", "version": "5.1"}, "degraded": False,
                    "diagnostic_ref": "synthetic://drive"},
    }
    _apply_overrides(env, overrides)
    return _seal(env) if overrides.get("_reseal", True) else env


def _apply_overrides(env: dict, overrides: dict):
    """Apply dotted-path overrides (e.g. {"status": "invalid", "subject.scene_id": "other"}) so a
    negative fixture can be derived from a valid one. A `_reseal=False` override skips digest sealing so
    a digest-mismatch fixture can be built."""
    for dotted, val in overrides.items():
        if dotted == "_reseal":
            continue
        node = env
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = val


def synthetic_paired_evidence(**kwargs):
    """A matched render+drive pair sharing all identity bindings."""
    return synthetic_render_evidence(**kwargs), synthetic_drive_evidence(**kwargs)
