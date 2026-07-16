"""scripts/gnm/h8_evidence_provider.py

H8 NON-CAPTURING render/drive evidence PROVIDER.

Deterministically builds real, schema-conforming evidence envelopes (see `h8_evidence_schema.py`) from
repository-controlled artefacts — the committed dataset config, the derived dataset plan, the committed
scene `.usda`, and a config-derived route representation. It computes REAL canonical digests and identity
bindings, records observation/issue timestamps from an INJECTED clock, and separates what was actually
observed (artefact identity/digest/config/route STRUCTURE) from what was NOT (Isaac render / robot drive).

BOUNDARY — this provider does NOT and CANNOT:
  * launch Isaac Sim, render a frame, drive the robot, access a camera, or invoke ROS 2;
  * perform dataset capture, write RGB/trajectories/rosbags, run a model, or train;
  * assert runtime render/drive validity. Preflight evidence uses `status="indeterminate"` and lists the
    unobserved runtime checks explicitly. It is a well-formed evidence *document* but NEVER authorises
    capture (schema `document_only` distinction, H8-DCP-023).

Everything is injected (clock, reader, tree-state, digest, sink, runtime observer) so the provider is
deterministic and testable with no filesystem, git, or Isaac dependency. The runtime observer is absent
in this gate; requesting runtime-valid status without it fails closed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.gnm import h8_evidence_schema as es

PROVIDER_VERSION = "h8-evidence-provider/1.0.0"

REPO = Path(__file__).resolve().parents[2]
DATASET_CONFIG_REL = "configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml"
PREFLIGHT_NAMESPACE = "assets/evidence/h8/preflight"
RUNTIME_NAMESPACE = "assets/evidence/h8/runtime"          # reserved for a FUTURE runtime provider
DATASET_PLAN_ID = "h8-synthetic-fork-v1"
COORDINATE_FRAME = "synthetic_fork_world"                 # provider-declared frame (not read from cfg)
SCENE_ID = "synthetic_diagnostic_fork"

# the exact set of tracked artefacts this provider's evidence depends on (dirty-tree policy scope)
EVIDENCE_DEPENDENCY_PATHS = (
    DATASET_CONFIG_REL,
    "assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda",
    "scripts/gnm/h8_evidence_schema.py",
    "scripts/gnm/h8_evidence_provider.py",
)

# ── modes ──────────────────────────────────────────────────────────────────────────
MODE_FIXTURE = "fixture"
MODE_PREFLIGHT = "preflight"
MODE_PRODUCTION = "production"
MODES = frozenset({MODE_FIXTURE, MODE_PREFLIGHT, MODE_PRODUCTION})

# ── provider result taxonomy (§21) ─────────────────────────────────────────────────
PROVIDER_OK_PREFLIGHT = "PROVIDER_OK_PREFLIGHT"
PROVIDER_OK_FIXTURE = "PROVIDER_OK_FIXTURE"
PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING = "PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING"
PROVIDER_FIXTURE_REJECTED = "PROVIDER_FIXTURE_REJECTED"
PROVIDER_ARTIFACT_MISSING = "PROVIDER_ARTIFACT_MISSING"
PROVIDER_ARTIFACT_DIGEST_FAILED = "PROVIDER_ARTIFACT_DIGEST_FAILED"
PROVIDER_DIRTY_TREE = "PROVIDER_DIRTY_TREE"
PROVIDER_SCHEMA_REJECTED = "PROVIDER_SCHEMA_REJECTED"
PROVIDER_BINDING_MISMATCH = "PROVIDER_BINDING_MISMATCH"
PROVIDER_OUTPUT_CONFLICT = "PROVIDER_OUTPUT_CONFLICT"
PROVIDER_SIGNATURE_REQUIRED = "PROVIDER_SIGNATURE_REQUIRED"
PROVIDER_CLOCK_UNTRUSTED = "PROVIDER_CLOCK_UNTRUSTED"
PROVIDER_INSTANCE_UNKNOWN = "PROVIDER_INSTANCE_UNKNOWN"
PROVIDER_OBSERVER_INVALID = "PROVIDER_OBSERVER_INVALID"   # typed observer contract (H8-PREV-F-002)
PROVIDER_MODE_INVALID = "PROVIDER_MODE_INVALID"
PROVIDER_INTERNAL_ERROR = "PROVIDER_INTERNAL_ERROR"

PROVIDER_REASON_CODES = frozenset({
    PROVIDER_OK_PREFLIGHT, PROVIDER_OK_FIXTURE, PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING,
    PROVIDER_FIXTURE_REJECTED, PROVIDER_ARTIFACT_MISSING, PROVIDER_ARTIFACT_DIGEST_FAILED,
    PROVIDER_DIRTY_TREE, PROVIDER_SCHEMA_REJECTED, PROVIDER_BINDING_MISMATCH, PROVIDER_OUTPUT_CONFLICT,
    PROVIDER_SIGNATURE_REQUIRED, PROVIDER_CLOCK_UNTRUSTED, PROVIDER_INSTANCE_UNKNOWN,
    PROVIDER_OBSERVER_INVALID, PROVIDER_MODE_INVALID, PROVIDER_INTERNAL_ERROR,
})
# Active codes are triggerable by tests; reserved codes are defensive guards not counted as coverage
# (H8-PREV-F-004 / H8-DCP-033). PROVIDER_MODE_INVALID is unreachable — the constructor rejects bad modes.
PROVIDER_RESERVED_CODES = frozenset({PROVIDER_MODE_INVALID})
PROVIDER_ACTIVE_CODES = PROVIDER_REASON_CODES - PROVIDER_RESERVED_CODES

# ── runtime-observer capability contract (H8-PREV-F-002) ──────────────────────────
# A runtime observer must satisfy an explicit typed capability contract AND be authorised by policy —
# generic truthiness is NOT proof of capability. NO observer is authorised in this gate.
_OBSERVER_REQUIRED_ATTRS = ("observer_id", "observer_version", "supported_evidence_types",
                            "supported_schema_versions", "available")
_OBSERVER_REQUIRED_METHODS = ("observe_render", "observe_drive")
AUTHORISED_OBSERVER_IDS = frozenset()   # none authorised this gate (real observer is a future gate)


def validate_runtime_observer(obj, *, evidence_type=None, schema_version=None) -> tuple:
    """Return (ok, reason). Rejects None/truthy-non-observer/partial/unsupported/unauthorised observers.
    In this gate AUTHORISED_OBSERVER_IDS is empty, so every observer fails closed."""
    if obj is None:
        return False, "no runtime observer"
    for a in _OBSERVER_REQUIRED_ATTRS:
        if not hasattr(obj, a):
            return False, f"observer missing required attribute {a!r}"
    for m in _OBSERVER_REQUIRED_METHODS:
        if not callable(getattr(obj, m, None)):
            return False, f"observer missing required method {m!r}"
    if getattr(obj, "available", False) is not True:
        return False, "observer not marked available"
    ev = tuple(getattr(obj, "supported_evidence_types", ()) or ())
    if evidence_type is not None and evidence_type not in ev:
        return False, f"observer does not support evidence_type {evidence_type!r}"
    sv = tuple(getattr(obj, "supported_schema_versions", ()) or ())
    if schema_version is not None and schema_version not in sv:
        return False, "observer does not support this schema version"
    oid = getattr(obj, "observer_id", None)
    if oid not in AUTHORISED_OBSERVER_IDS:
        return False, f"observer {oid!r} not authorised by policy"
    return True, "observer authorised"

# runtime checks this provider CANNOT observe (recorded explicitly in every preflight envelope)
_RENDER_UNOBSERVED = ("scene_loaded", "camera_present", "camera_transform_matches", "frame_nonempty",
                      "frame_not_constant", "required_geometry_visible", "no_invalid_render_condition")
_DRIVE_UNOBSERVED = ("within_spatial_bounds", "collision_feasible", "avoids_prohibited_geometry",
                     "min_clearance_m", "route_length_m", "runtime_odometry_consistent")


# ── injectable defaults ─────────────────────────────────────────────────────────────
def default_reader(rel_path):
    """Read a repository-relative artefact as bytes. Refuses absolute paths and path traversal."""
    p = Path(rel_path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe artefact path: {rel_path!r}")
    fp = (REPO / p).resolve()
    if REPO not in fp.parents and fp != REPO:
        raise ValueError(f"artefact escapes repository: {rel_path!r}")
    return fp.read_bytes()


def default_digest(data: bytes) -> str:
    """SHA-256 over raw bytes → 'sha256:<64 lowercase hex>'. No truncation."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("digest input must be bytes")
    return "sha256:" + hashlib.sha256(bytes(data)).hexdigest()


class InMemorySink:
    """A test/production-safe sink that records atomic puts in memory. Never touches the filesystem."""

    def __init__(self, namespace=PREFLIGHT_NAMESPACE):
        self.namespace = namespace
        self.store = {}          # rel_path -> bytes
        self.by_id = {}          # evidence_id -> content_digest
        self.atomic_ops = 0

    def existing_digest(self, evidence_id):
        return self.by_id.get(evidence_id)

    def put(self, rel_path, data: bytes, evidence_id, content_digest):
        # atomic contract: caller has already fully validated; we record in one step.
        self.store[rel_path] = data
        self.by_id[evidence_id] = content_digest
        self.atomic_ops += 1
        return rel_path


class AtomicFileSink:
    """Real sink writing small evidence JSON via temp-file + atomic rename under a dedicated namespace.
    Used only when a caller explicitly opts into on-disk output; tests use InMemorySink."""

    def __init__(self, namespace=PREFLIGHT_NAMESPACE, root=REPO):
        self.namespace = namespace
        self.root = Path(root)
        self.by_id = {}

    def existing_digest(self, evidence_id):
        return self.by_id.get(evidence_id)

    def put(self, rel_path, data: bytes, evidence_id, content_digest):
        import os
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)          # atomic rename
        self.by_id[evidence_id] = content_digest
        return str(rel_path)


def _provider_result(code, *, ok=False, **extra):
    r = {"provider_code": code, "ok": bool(ok), "provider_version": PROVIDER_VERSION}
    r.update(extra)
    return r


# ── the provider ────────────────────────────────────────────────────────────────────
class H8EvidenceProvider:
    """Deterministic, non-capturing evidence provider. All external effects are injected."""

    def __init__(self, *, mode, clock, reader=default_reader, digest_fn=default_digest,
                 tree_state=None, sink=None, runtime_observer=None, config_rel=DATASET_CONFIG_REL,
                 require_signature=False):
        if mode not in MODES:
            raise ValueError(f"invalid provider mode {mode!r}")
        self.mode = mode
        self.clock = clock                      # () -> RFC3339 UTC string
        self.reader = reader                    # (rel_path) -> bytes
        self.digest_fn = digest_fn              # (bytes) -> 'sha256:...'
        self.tree_state = tree_state            # () -> {"commit": str, "dependency_dirty": bool}
        self.sink = sink if sink is not None else InMemorySink()
        self.runtime_observer = runtime_observer  # MUST be None in this gate
        self.config_rel = config_rel
        self.require_signature = require_signature

    # -- artefact loading -----------------------------------------------------------
    def load_configuration(self):
        raw = self.reader(self.config_rel)
        import yaml
        return yaml.safe_load(raw), raw

    def load_plan(self, cfg):
        from scripts.gnm import h8_synthetic_fork_recorded_mode as rm
        return rm.build_dataset_plan(cfg)

    def resolve_instance(self, cfg, instance_id):
        insts = (cfg.get("instance_plan", {}) or {}).get("instances", []) or []
        for i in insts:
            if i.get("id") == instance_id:
                return i
        return None

    def build_route_representation(self, instance):
        """Deterministic, config-derived route-plan REPRESENTATION (structural, not runtime-executed).
        Start/goal mirror the committed `build_dataset_plan` coordinates for the primary N branch."""
        off = instance.get("coord_offset") or [0, 0]
        ox, oy = float(off[0]), float(off[1])
        return {
            "route_id": f"{instance.get('id')}_N", "route_family": "N_vs_W_90",
            "coordinate_frame": COORDINATE_FRAME, "branch": "N",
            "start": {"xy": [ox, oy], "yaw": 0.0}, "goal": {"xy": [ox, oy + 3.0], "yaw": 0.0},
            "waypoints": [[ox, oy], [ox, oy + 3.0]], "cl_bound_xy": es.CL_BOUND_XY,
            "note": "config-derived structural route representation; NOT a runtime-executed route",
        }

    # -- bindings -------------------------------------------------------------------
    def build_subject_binding(self, instance, *, config_digest, scene_digest, route_digest):
        return {
            "dataset_plan_id": DATASET_PLAN_ID, "instance_id": instance.get("id"),
            "split": instance.get("split"), "scene_id": SCENE_ID, "scene_digest": scene_digest,
            "route_id": f"{instance.get('id')}_N", "route_plan_digest": route_digest,
            "config_digest": config_digest, "cl_bound_xy": es.CL_BOUND_XY,
            "coordinate_frame": COORDINATE_FRAME,
            "sim_context": {"simulator": "none-preflight", "version": "n/a"},
        }

    def build_provenance(self, *, plan_digest):
        ts = self.tree_state() if self.tree_state else {"commit": "unknown", "dependency_dirty": False}
        run_id = "preflight-" + self.digest_fn(f"{ts.get('commit')}::{plan_digest}".encode())[7:19]
        return {
            "producer_component": "h8-evidence-provider", "producer_version": PROVIDER_VERSION,
            "source_commit": ts.get("commit", "unknown"), "run_id": run_id, "host_label": "local",
            "method_id": "preflight-static-binding", "scene_source": "committed-usda",
            "config_source": self.config_rel, "parent_evidence_id": None,
            "generated_at": self.clock(), "review_state": "none", "plan_digest": plan_digest,
        }

    def _evidence_id(self, kind, instance_id):
        short = kind.split("_")[0]        # render_valid -> render, drive_valid -> drive (regex-safe)
        slug = str(instance_id).replace("_", "")
        seq = int(self.digest_fn(f"{kind}:{instance_id}".encode())[7:15], 16) % 10000
        return f"h8ev-{short}-{slug}-{seq:04d}"

    def _seal(self, env):
        env["integrity"].update(es.compute_digests(env))
        return env

    def _envelope_skeleton(self, kind, instance, subject, provenance):
        now = self.clock()
        return {
            "schema_version": es.SCHEMA_VERSION,
            "evidence_id": self._evidence_id(kind, instance.get("id")),
            "evidence_type": kind, "status": "indeterminate", "subject": subject,
            "context": {"route_family": "N_vs_W_90", "claim_boundary": "SYNTHETIC_DIAGNOSTIC_ONLY",
                        "capture_mode": "preflight"},
            "producer": {"component": "h8-evidence-provider", "version": PROVIDER_VERSION,
                         "method": "preflight-static-binding", "key_id": None},
            "observation_time": now, "issue_time": now,
            "validity_window": {"not_before": now, "not_after": _plus_days(now, 7),
                                "max_age_seconds": 604800, "clock_source": "utc",
                                "clock_skew_seconds": 5},
            "integrity": {"canonicalization": es.CANONICALIZATION, "digest_algorithm": es.DIGEST_ALGORITHM,
                          "subject_digest": "", "payload_digest": "", "content_digest": "",
                          "signature": None, "signature_algorithm": None, "key_id": None,
                          "verification_status": "unsigned"},
            "provenance": provenance,
            "revocation": {"revoked": False, "revoked_at": None, "reason": None, "authority": None,
                           "replacement_evidence_id": None, "supersedes": None},
            "payload": {},
        }

    def build_render_preflight_evidence(self, instance, subject, provenance):
        env = self._envelope_skeleton("render_valid", instance, subject, provenance)
        env["payload"] = {
            # runtime facts are NOT observed at preflight → recorded as not-established (False)
            "scene_loaded": False, "camera_present": False, "camera_transform_matches": False,
            "resolution": [640, 480], "encoding": "rgb8", "frame_nonempty": False,
            "frame_not_constant": False, "required_geometry_visible": False,
            "no_invalid_render_condition": False, "validation_method": "preflight-static-binding",
            "thresholds": {}, "diagnostic_ref": f"preflight://render/{instance.get('id')}",
            # explicit preflight annotations (extra fields; permitted by the schema payload)
            "runtime_observed": False, "unobserved_runtime_checks": list(_RENDER_UNOBSERVED),
            "preflight_observations": {
                "scene_file_digest_verified": True, "scene_file_readable": True,
                "config_consistent": True, "camera_config_declared_not_verified": True,
                "instance_bound": True, "resolution_encoding_declared_not_observed": True},
        }
        return self._seal(env)

    def build_drive_preflight_evidence(self, instance, subject, provenance):
        env = self._envelope_skeleton("drive_valid", instance, subject, provenance)
        env["payload"] = {
            "start_bound_to_instance": True, "goal_bound_to_instance": True,
            # runtime/geometric facts NOT observed at preflight
            "within_spatial_bounds": False, "collision_feasible": False, "min_clearance_m": 0.0,
            "clearance_threshold_m": 0.30, "avoids_prohibited_geometry": False, "route_length_m": 0.0,
            "waypoint_count": 2, "coordinate_frame": COORDINATE_FRAME,
            "validation_method": "preflight-static-binding", "planner_version": "none-preflight",
            "sim_context": {"simulator": "none-preflight", "version": "n/a"},
            "degraded": True,                       # uncertain — no runtime observation
            "diagnostic_ref": f"preflight://drive/{instance.get('id')}",
            "runtime_observed": False, "unobserved_runtime_checks": list(_DRIVE_UNOBSERVED),
            "preflight_observations": {
                "route_representation_digest_verified": True, "start_present": True, "goal_present": True,
                "coordinate_frame_declared": True, "cl_bound_is_6": subject["cl_bound_xy"] == 6.0,
                "instance_bound": True},
        }
        return self._seal(env)

    # -- orchestration --------------------------------------------------------------
    def _preflight_prechecks(self):
        """Fail-closed prechecks common to preflight/production. Returns a provider_result on failure,
        else None."""
        # H8-PREV-F-003: cleanliness enforcement is MANDATORY for preflight/production — an absent,
        # failing, or non-affirmatively-clean tree-state resolver fails closed (no permissive default,
        # no allow_dirty override). `dependency_dirty` must be explicitly False to proceed.
        if self.tree_state is None:
            return _provider_result(PROVIDER_DIRTY_TREE,
                                    reason="no tree-state resolver — repository cleanliness cannot be "
                                           "verified; failing closed")
        try:
            ts = self.tree_state()
        except Exception as e:
            return _provider_result(PROVIDER_DIRTY_TREE, reason=f"tree-state resolver failed: {e}")
        if not isinstance(ts, dict) or ts.get("dependency_dirty") is not False:
            return _provider_result(PROVIDER_DIRTY_TREE,
                                    reason="evidence-dependency cleanliness not affirmatively verified "
                                           "(dependency_dirty must be exactly False)")
        # every dependency artefact must be readable
        for rel in EVIDENCE_DEPENDENCY_PATHS:
            try:
                if not self.reader(rel):
                    return _provider_result(PROVIDER_ARTIFACT_MISSING, reason=f"empty artefact {rel}")
            except Exception as e:
                return _provider_result(PROVIDER_ARTIFACT_MISSING, reason=f"{rel}: {e}")
        return None

    def emit_evidence(self, instance_id, *, kind="both", want_runtime_valid=False):
        """Build and (if valid) emit preflight evidence for one instance. `kind` ∈ {render, drive, both}.
        `want_runtime_valid=True` demands runtime-valid status — blocked here (no runtime observer)."""
        try:
            if self.mode == MODE_FIXTURE:
                return self._emit_fixture(instance_id, kind)
            if self.mode not in (MODE_PREFLIGHT, MODE_PRODUCTION):
                return _provider_result(PROVIDER_MODE_INVALID, reason=self.mode)

            # H8-PREV-F-002: production/preflight must never fall back to fixtures or fabricate runtime
            # validity. A runtime-valid request requires an observer that (a) is present, (b) satisfies
            # the typed capability contract, and (c) is authorised by policy — generic truthiness is not
            # accepted. No observer is authorised this gate, so every runtime-valid request fails closed.
            if want_runtime_valid or self.mode == MODE_PRODUCTION:
                if self.runtime_observer is None:
                    return _provider_result(PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING,
                                            reason="runtime-valid status requires an authorised runtime "
                                                   "observer, which is absent in this gate")
                obs_ok, obs_why = validate_runtime_observer(self.runtime_observer)
                # present but invalid/unauthorised → reject explicitly (never silently accept truthiness)
                return _provider_result(PROVIDER_OBSERVER_INVALID, reason=obs_why)
            if self.require_signature:
                return _provider_result(PROVIDER_SIGNATURE_REQUIRED,
                                        reason="signature required but no production signer is available")

            # H8-PREV-F-004: an untrusted/malformed clock fails closed as PROVIDER_CLOCK_UNTRUSTED
            try:
                es._parse_ts(self.clock())
            except Exception as e:
                return _provider_result(PROVIDER_CLOCK_UNTRUSTED, reason=f"clock unusable: {e}")

            pre = self._preflight_prechecks()
            if pre is not None:
                return pre

            cfg, cfg_bytes = self.load_configuration()
            instance = self.resolve_instance(cfg, instance_id)
            if instance is None:
                return _provider_result(PROVIDER_INSTANCE_UNKNOWN, reason=instance_id)
            if cfg.get("cl_bound_xy") != es.CL_BOUND_XY:
                return _provider_result(PROVIDER_BINDING_MISMATCH,
                                        reason=f"cl_bound_xy != {es.CL_BOUND_XY}")
            if instance.get("coord_offset") is None:
                return _provider_result(PROVIDER_ARTIFACT_MISSING,
                                        reason="instance has no route coord_offset (no route artefact)")

            plan = self.load_plan(cfg)
            if not plan:
                return _provider_result(PROVIDER_ARTIFACT_MISSING, reason="empty plan")
            try:
                scene_bytes = self.reader(
                    "assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda")
            except Exception as e:
                return _provider_result(PROVIDER_ARTIFACT_MISSING, reason=f"scene: {e}")
            route_rep = self.build_route_representation(instance)
            # H8-PREV-F-004: a raising digest implementation fails closed as PROVIDER_ARTIFACT_DIGEST_FAILED
            try:
                plan_digest = self.digest_fn(es.canonical_bytes(plan))
                scene_digest = self.digest_fn(scene_bytes)
                route_digest = self.digest_fn(es.canonical_bytes(route_rep))
                config_digest = self.digest_fn(cfg_bytes)
            except Exception as e:
                return _provider_result(PROVIDER_ARTIFACT_DIGEST_FAILED, reason=f"digest failed: {e}")

            subject = self.build_subject_binding(instance, config_digest=config_digest,
                                                 scene_digest=scene_digest, route_digest=route_digest)
            provenance = self.build_provenance(plan_digest=plan_digest)
            expected = {k: subject[k] for k in es._SUBJECT_COMMON}

            envelopes = {}
            if kind in ("render", "both"):
                envelopes["render_valid"] = self.build_render_preflight_evidence(instance, subject,
                                                                                 provenance)
            if kind in ("drive", "both"):
                envelopes["drive_valid"] = self.build_drive_preflight_evidence(instance, subject,
                                                                               provenance)

            emitted = []
            for et, env in envelopes.items():
                rt = self.clock()
                # (1) it MUST be a well-formed evidence DOCUMENT (production_mode rejects fixtures)
                doc = es.validate_envelope(env, review_time=rt, expected=expected, document_only=True,
                                           production_mode=(self.mode == MODE_PRODUCTION))
                if not doc["accepted"]:
                    return _provider_result(PROVIDER_SCHEMA_REJECTED, reason=doc["reason_code"],
                                            evidence_type=et, detail=doc["explanation"])
                # (2) it MUST NOT satisfy the capture gate (indeterminate preflight)
                gate = es.validate_envelope(env, review_time=rt, expected=expected, document_only=False)
                if gate["accepted"]:
                    return _provider_result(PROVIDER_INTERNAL_ERROR,
                                            reason="preflight evidence unexpectedly satisfied the "
                                                   "capture gate", evidence_type=et)
                # (3) replay/conflict control on the sink
                eid, cdig = env["evidence_id"], env["integrity"]["content_digest"]
                prev = self.sink.existing_digest(eid)
                if prev is not None and prev != cdig:
                    return _provider_result(PROVIDER_OUTPUT_CONFLICT, reason=eid, evidence_type=et)
                emitted.append((et, env, eid, cdig))

            written = []
            for et, env, eid, cdig in emitted:
                rel = f"{self.sink.namespace}/{eid}.json"
                data = (json.dumps(env, sort_keys=True, indent=2) + "\n").encode("utf-8")
                written.append(self.sink.put(rel, data, eid, cdig))

            return _provider_result(PROVIDER_OK_PREFLIGHT, ok=True, instance_id=instance_id, kind=kind,
                                    evidence={et: env for et, env, _, _ in emitted},
                                    evidence_ids=[eid for _, _, eid, _ in emitted], written=written)
        except Exception as e:  # never let an unexpected error masquerade as success
            return _provider_result(PROVIDER_INTERNAL_ERROR, reason=f"{type(e).__name__}: {e}")

    def _emit_fixture(self, instance_id, kind):
        """Fixture mode: return clearly-marked synthetic fixtures ONLY; never write to a production
        namespace."""
        if "fixture" not in self.sink.namespace:
            return _provider_result(PROVIDER_FIXTURE_REJECTED,
                                    reason="fixture mode may not write to a non-fixture namespace")
        out = {}
        if kind in ("render", "both"):
            out["render_valid"] = es.synthetic_render_evidence(instance_id=instance_id)
        if kind in ("drive", "both"):
            out["drive_valid"] = es.synthetic_drive_evidence(instance_id=instance_id)
        return _provider_result(PROVIDER_OK_FIXTURE, ok=True, instance_id=instance_id, kind=kind,
                                evidence=out)


# ── capture-harness boundary (§23) — a DOCUMENT is not capture authorisation ────────
def preflight_satisfies_capture_gate(envelope, *, review_time, expected=None) -> tuple:
    """Return (authorises_capture: bool, reason). Preflight `indeterminate` evidence is a valid
    DOCUMENT but does NOT authorise capture. This never launches Isaac or creates anything."""
    doc = es.validate_envelope(envelope, review_time=review_time, expected=expected, document_only=True)
    gate = es.validate_envelope(envelope, review_time=review_time, expected=expected,
                                document_only=False)
    return bool(gate["accepted"]), {"is_valid_document": bool(doc["accepted"]),
                                     "authorises_capture": bool(gate["accepted"]),
                                     "gate_reason": gate["reason_code"]}


def _plus_days(rfc3339, days):
    """Add whole days to an RFC 3339 timestamp (deterministic; no wall-clock)."""
    from datetime import timedelta
    dt = es._parse_ts(rfc3339) + timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
