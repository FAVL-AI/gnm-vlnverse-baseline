"""scripts/gnm/h8_trust_envelope.py

H8 G2A — CANONICAL DEPENDENCY-EVIDENCE ENVELOPE (implementation of the committed G2A spec).

Implements the schema, strict parser, JCS (RFC 8785) canonicaliser and non-authenticating digest for the
`h8-trust-envelope/1.0.0` envelope, EXACTLY as specified in
docs/research/H8_G2A_CANONICAL_ENVELOPE_SPEC.md (committed at 23d95c8), which itself details
docs/research/H8_G2_CRYPTOGRAPHIC_TRUST_ARCHITECTURE.md §8/§9 (640ddd0). The committed spec is authoritative;
this module conforms to it.

ENVELOPE SHAPE (spec §3): exactly two top-level members — `payload` (the signed content) and
`signature_block` (the DETACHED signature, OUTSIDE the signed bytes). Signing/verification (a future gate)
operate on the canonical bytes of `payload` only.

WHAT THIS MODULE DOES (G2A-implementation scope):
  * strict parse of the envelope (duplicate keys / BOM / NaN / Infinity / floats rejected, spec §4.1);
  * schema validation of `payload` + `signature_block` (spec §3, §4.2) — exact-version binding, no
    unknown-version acceptance, unknown-field rejection, enum/allow-list checks, bounds, CR rejection,
    non-waivable `verification_requirements`, `intended_use` const, assurance ≤ content-equivalent;
  * the fixed 4-stage canonical-byte pipeline with JCS + Unicode NFC NORMALISATION (spec §4.3);
  * a NON-AUTHENTICATING SHA-256 digest of the canonical `payload` bytes (spec §4.4);
  * the absent / null / "UNAVAILABLE" tri-state (spec §5), where deferred fields use the explicit
    "UNAVAILABLE" sentinel and are NEVER fabricated.

BOUNDARY — this module does NOT and CANNOT (deferred to later gates G2B..G2H):
  * create, hold or use ANY key, certificate, token, signature or trusted timestamp;
  * connect to a KMS, timestamp authority, transparency log, certificate authority or revocation service;
  * verify a signature, verify freshness, verify revocation or attest repository origin;
  * launch Isaac Sim / Omniverse / ROS 2, render, drive, capture, run inference or train.
A schema-valid envelope here is signature-UNVERIFIED, freshness-UNVERIFIED, revocation-UNVERIFIED, and is
runtime-INELIGIBLE and capture-INELIGIBLE. The module exposes no sign()/verify_signature()/authorise().
The `signature_block` is present only as sentinels; no signature exists.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

# ── envelope identity (spec §3, §6) ─────────────────────────────────────────────────
ENVELOPE_VERSION = "h8-trust-envelope/1.0.0"
SUPPORTED_ENVELOPE_VERSIONS = frozenset({ENVELOPE_VERSION})   # exact match; NO accept-unknown-version
ENVELOPE_TYPE = "resolver-report"
ALLOWED_ENVELOPE_TYPES = frozenset({ENVELOPE_TYPE})

CANONICALISATION_SCHEME = "JCS/RFC8785"          # spec §4.3 (floats prohibited; NFC-normalised)
ALLOWED_DIGEST_ALGORITHMS = frozenset({"sha-256"})           # spec §6 (explicit signed field)
ALLOWED_SIGNATURE_ALGORITHMS = frozenset({"ed25519"})        # spec §3.1 allow-list (verification = G2B)
DIGEST_PREFIX = "sha256:"                                     # digest-string form (spec §6)

INTENDED_USE_G2A = "preflight-document"                       # spec §3.1: const at G2A (never runtime/capture)
ASSURANCE_G2A = ("content-equivalent",)                      # spec §3.1: only claim permitted at G2A
SENTINEL_UNAVAILABLE = "UNAVAILABLE"                          # spec §5: explicit deferred-field sentinel

REFERENCE_RESOLUTIONS = frozenset({"commit", "annotated_tag", "lightweight_tag", "none"})
DEP_CLASSES = frozenset({
    "dataset-config", "dependency-manifest", "manifest-schema", "evidence-schema", "trust-policy",
    "module", "expected-routes", "scene", "level1-drive-manifest", "cl-bound",
    "canonicalisation-impl", "capture-validator",
})
VERIFICATION_REQUIREMENT_KEYS = (
    "require_signature", "require_authorised_signer", "require_trusted_timestamp", "require_not_revoked",
    "require_repository_attestation", "require_semantic_identity", "require_attributes_binding",
    "require_intended_use_match",
)

# ── strict-syntax limits (spec §4.2 bounds) ─────────────────────────────────────────
MAX_STRING_LEN = 512
MAX_ARRAY_LEN = 4096
_RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")   # no offset, no sub-second (spec §6)
_OID = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")                    # 40 (SHA-1) or 64 (SHA-256) hex
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

# ── G2A-owned failure codes (spec §8) ───────────────────────────────────────────────
# The ONLY two codes G2A owns/emits. They live in THIS module and are intentionally NOT added to the Git
# resolver's REASON_CODES (which remains 41). Signature/key/time/revocation/attestation codes are design-only
# (architecture §24) and are NOT defined here. All structural/schema failures collapse to
# TRUST_ENVELOPE_SCHEMA_INVALID; canonicalisation-stage failures to TRUST_CANONICALISATION_FAILED.
TRUST_OK = "TRUST_OK"                                        # schema-conformant (NOT trust acceptance)
TRUST_ENVELOPE_SCHEMA_INVALID = "TRUST_ENVELOPE_SCHEMA_INVALID"
TRUST_CANONICALISATION_FAILED = "TRUST_CANONICALISATION_FAILED"
TRUST_REASON_CODES = frozenset({TRUST_OK, TRUST_ENVELOPE_SCHEMA_INVALID, TRUST_CANONICALISATION_FAILED})
TRUST_REJECT_CODES = TRUST_REASON_CODES - frozenset({TRUST_OK})


class TrustEnvelopeError(ValueError):
    """A schema or canonicalisation failure carrying one of the two G2A TRUST_* codes.

    `detail` preserves the granular reason for debugging while the emitted `reason_code` stays coarse
    (spec §8): TRUST_ENVELOPE_SCHEMA_INVALID or TRUST_CANONICALISATION_FAILED.
    """

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _schema_invalid(detail: str) -> TrustEnvelopeError:
    return TrustEnvelopeError(TRUST_ENVELOPE_SCHEMA_INVALID, detail)


# ── strict parsing (spec §4.1) ──────────────────────────────────────────────────────
def _no_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict:
    seen: set[str] = set()
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise _schema_invalid(f"duplicate object key {key!r}")
        seen.add(key)
        obj[key] = value
    return obj


def _reject_float(_literal: str):
    raise _schema_invalid("floating-point number prohibited (integers only)")


def _reject_constant(literal: str):
    raise _schema_invalid(f"non-finite/JSON constant prohibited: {literal}")


def parse_envelope_strict(raw: bytes) -> dict:
    """Parse raw envelope bytes into a dict, failing CLOSED on structural ambiguity (spec §4.1).

    Rejects: non-bytes, a UTF-8 BOM, non-UTF-8, duplicate keys at any depth, floats, NaN/Infinity.
    All rejections use TRUST_ENVELOPE_SCHEMA_INVALID.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise _schema_invalid("raw envelope must be bytes")
    if raw[:3] == b"\xef\xbb\xbf":
        raise _schema_invalid("UTF-8 BOM is not permitted (RFC 8785)")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _schema_invalid(f"invalid UTF-8: {exc}") from None
    try:
        obj = json.loads(text, object_pairs_hook=_no_duplicate_pairs,
                         parse_float=_reject_float, parse_constant=_reject_constant)
    except TrustEnvelopeError:
        raise
    except json.JSONDecodeError as exc:
        raise _schema_invalid(f"malformed JSON: {exc}") from None
    if not isinstance(obj, dict):
        raise _schema_invalid("envelope root must be a JSON object")
    return obj


# ── JCS (RFC 8785) canonicalisation with NFC normalisation (spec §4.3) ──────────────
_JCS_SHORT_ESCAPE = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r",
                     0x22: '\\"', 0x5C: "\\\\"}


def _canon_string(value: str) -> str:
    # NFC-normalise the string value (spec §4.3: NFD input yields the same canonical bytes as its NFC twin).
    value = unicodedata.normalize("NFC", value)
    out = ['"']
    for ch in value:
        code = ord(ch)
        esc = _JCS_SHORT_ESCAPE.get(code)
        if esc is not None:
            out.append(esc)
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _canon_value(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)                       # shortest decimal, no leading zeros
    if isinstance(value, float):
        raise TrustEnvelopeError(TRUST_CANONICALISATION_FAILED, "floats prohibited in canonical payload")
    if isinstance(value, str):
        return _canon_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canon_value(v) for v in value) + "]"
    if isinstance(value, dict):
        # NFC-normalise keys, then sort by UTF-16 code units (RFC 8785 §3.2.3).
        normalised: dict[str, Any] = {}
        for key, val in value.items():
            if not isinstance(key, str):
                raise TrustEnvelopeError(TRUST_CANONICALISATION_FAILED, "object keys must be strings")
            nkey = unicodedata.normalize("NFC", key)
            if nkey in normalised:
                raise TrustEnvelopeError(TRUST_CANONICALISATION_FAILED, f"key collision after NFC: {nkey!r}")
            normalised[nkey] = val
        items = [_canon_string(k) + ":" + _canon_value(normalised[k])
                 for k in sorted(normalised, key=lambda k: k.encode("utf-16-be"))]
        return "{" + ",".join(items) + "}"
    raise TrustEnvelopeError(TRUST_CANONICALISATION_FAILED, f"uncanonicalisable type: {type(value).__name__}")


def canonicalise(obj: dict) -> bytes:
    """Return the JCS (RFC 8785) + NFC canonical byte serialisation of `obj` (spec §4.3)."""
    if not isinstance(obj, dict):
        raise TrustEnvelopeError(TRUST_CANONICALISATION_FAILED, "canonical root must be an object")
    return _canon_value(obj).encode("utf-8")


def canonicalise_payload(envelope: dict) -> bytes:
    """Canonical bytes over `envelope['payload']` ONLY (the signed content, spec §3, §4)."""
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), dict):
        raise TrustEnvelopeError(TRUST_CANONICALISATION_FAILED, "envelope.payload must be an object")
    return canonicalise(envelope["payload"])


def compute_digest(canonical_bytes: bytes) -> str:
    """NON-AUTHENTICATING SHA-256 digest of canonical bytes (spec §4.4). Not a signature."""
    if not isinstance(canonical_bytes, (bytes, bytearray)):
        raise TrustEnvelopeError(TRUST_CANONICALISATION_FAILED, "canonical bytes required")
    return DIGEST_PREFIX + hashlib.sha256(bytes(canonical_bytes)).hexdigest()


# ── field helpers (all failures → TRUST_ENVELOPE_SCHEMA_INVALID) ────────────────────
def _require(obj: dict, key: str, path: str):
    if key not in obj:
        raise _schema_invalid(f"missing {path}.{key}")
    return obj[key]


def _reject_unknown(obj: dict, allowed: set[str], path: str) -> None:
    for key in obj:
        if key not in allowed:
            raise _schema_invalid(f"unknown field {path}.{key}")


def _check_str(value: Any, path: str, *, max_len: int = MAX_STRING_LEN) -> str:
    if not isinstance(value, str):
        raise _schema_invalid(f"{path} must be a string")
    if value == "":
        raise _schema_invalid(f"{path} must be non-empty")
    if len(value) > max_len:
        raise _schema_invalid(f"{path} exceeds {max_len} chars")
    if "\r" in value:                       # spec §7 vector 5: CR/CRLF rejected (LF-only in canonical strings)
        raise _schema_invalid(f"{path} must not contain a carriage return")
    return value


def _check_int(value: Any, path: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _schema_invalid(f"{path} must be an integer")
    if value < minimum:
        raise _schema_invalid(f"{path} must be >= {minimum}")
    return value


def _check_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise _schema_invalid(f"{path} must be a boolean")
    return value


def _check_enum(value: Any, allowed, path: str) -> str:
    text = _check_str(value, path)
    if text not in allowed:
        raise _schema_invalid(f"{path} not in allow-list")
    return text


def _check_oid(value: Any, path: str) -> str:
    text = _check_str(value, path)
    if not _OID.fullmatch(text):
        raise _schema_invalid(f"{path} must be a lowercase hex OID (40 or 64)")
    return text


def _check_digest(value: Any, path: str) -> str:
    text = _check_str(value, path)
    if not _DIGEST.fullmatch(text):
        raise _schema_invalid(f"{path} must be 'sha256:<64 hex>'")
    return text


def _check_repo_relative_path(value: Any, path: str) -> str:
    text = _check_str(value, path)
    if text.startswith("/") or "\\" in text or any(s in ("", ".", "..") for s in text.split("/")):
        raise _schema_invalid(f"{path} must be a POSIX repo-relative path (no leading '/', '.', '..')")
    return text


def _check_timestamp(value: Any, path: str) -> tuple:
    text = _check_str(value, path)
    if not _RFC3339_UTC.fullmatch(text):
        raise _schema_invalid(f"{path} must be RFC3339 UTC 'Z' (no offset, no sub-second)")
    y, mo, d, h, mi, s = int(text[0:4]), int(text[5:7]), int(text[8:10]), int(text[11:13]), int(text[14:16]), int(text[17:19])
    if not (1 <= mo <= 12 and 1 <= d <= 31 and h <= 23 and mi <= 59 and s <= 60):
        raise _schema_invalid(f"{path} out-of-range calendar field")
    return (y, mo, d, h, mi, s)


def _check_unavailable(value: Any, path: str) -> str:
    if value != SENTINEL_UNAVAILABLE:
        raise _schema_invalid(f"{path} must be the '{SENTINEL_UNAVAILABLE}' sentinel at G2A")
    return value


# ── payload schema (spec §3.1) ──────────────────────────────────────────────────────
_PAYLOAD_REQUIRED = {
    "envelope_version", "envelope_type", "report_schema_version", "resolver_id", "resolver_version",
    "resolver_trust_policy_version", "repository_policy_id", "repository_identity", "head_commit",
    "head_tree_oid", "reference_resolution", "canonical_manifest_path", "canonical_manifest_digest",
    "manifest_schema_version", "manifest_schema_digest", "closure_digest", "attributes_closure_digest",
    "git_env_policy_version", "git_version", "mandatory_dependency_count", "accepted_count",
    "rejected_count", "unresolved_count", "per_dependency_identity_commitments", "digest_algorithm",
    "signature_algorithm", "signing_key_id", "observation_time", "issue_time", "validity_start",
    "expiry", "report_id", "nonce", "intended_use", "assurance_claims", "verification_requirements",
    "critical_extensions",
}
_PAYLOAD_OPTIONAL = {
    "observed_remote_origins", "reference_input", "trusted_timestamp_reference",
    "revocation_snapshot_reference", "origin_attestation_reference", "extensions",
}
_PAYLOAD_ALLOWED = _PAYLOAD_REQUIRED | _PAYLOAD_OPTIONAL


def _validate_repository_identity(rid: Any) -> None:
    if not isinstance(rid, dict):
        raise _schema_invalid("repository_identity must be an object")
    _reject_unknown(rid, {"canonical_name", "root_commit"}, "repository_identity")
    _check_str(_require(rid, "canonical_name", "repository_identity"), "repository_identity.canonical_name")
    _check_oid(_require(rid, "root_commit", "repository_identity"), "repository_identity.root_commit")


def _validate_semantic_profile(prof: Any, path: str) -> None:
    if not isinstance(prof, dict):
        raise _schema_invalid(f"{path} must be an object")
    _reject_unknown(prof, {"scheme", "id", "version", "digest"}, path)
    for field in ("scheme", "id", "version", "digest"):
        _check_str(_require(prof, field, path), f"{path}.{field}")


def _validate_dependency_commitments(commitments: Any) -> None:
    if not isinstance(commitments, list):
        raise _schema_invalid("per_dependency_identity_commitments must be an array")
    if len(commitments) > MAX_ARRAY_LEN:
        raise _schema_invalid("per_dependency_identity_commitments too large")
    seen: set[str] = set()
    for i, dep in enumerate(commitments):
        path = f"per_dependency_identity_commitments[{i}]"
        if not isinstance(dep, dict):
            raise _schema_invalid(f"{path} must be an object")
        _reject_unknown(dep, {"dependency_id", "dependency_class", "path", "git_blob_oid",
                              "git_content_digest", "semantic_identity_profile", "required"}, path)
        dep_id = _check_str(_require(dep, "dependency_id", path), f"{path}.dependency_id")
        if dep_id in seen:
            raise _schema_invalid(f"{path}.dependency_id duplicate {dep_id!r}")
        seen.add(dep_id)
        _check_enum(_require(dep, "dependency_class", path), DEP_CLASSES, f"{path}.dependency_class")
        _check_repo_relative_path(_require(dep, "path", path), f"{path}.path")
        _check_oid(_require(dep, "git_blob_oid", path), f"{path}.git_blob_oid")
        _check_digest(_require(dep, "git_content_digest", path), f"{path}.git_content_digest")
        _validate_semantic_profile(_require(dep, "semantic_identity_profile", path),
                                   f"{path}.semantic_identity_profile")
        _check_bool(_require(dep, "required", path), f"{path}.required")


def _validate_verification_requirements(vr: Any) -> None:
    if not isinstance(vr, dict):
        raise _schema_invalid("verification_requirements must be an object")
    _reject_unknown(vr, set(VERIFICATION_REQUIREMENT_KEYS), "verification_requirements")
    for key in VERIFICATION_REQUIREMENT_KEYS:
        val = _check_bool(_require(vr, key, "verification_requirements"), f"verification_requirements.{key}")
        if val is not True:
            # A report may not waive its own required checks (spec §3.4).
            raise _schema_invalid(f"verification_requirements.{key} must be true (non-waivable)")


def _validate_assurance(claims: Any) -> None:
    if not isinstance(claims, list):
        raise _schema_invalid("assurance_claims must be an array")
    # G2A permits ONLY ["content-equivalent"] (spec §3.1); stronger claims are self-promotion.
    if [c for c in claims] != list(ASSURANCE_G2A):
        raise _schema_invalid("assurance_claims must be exactly ['content-equivalent'] at G2A")


def _validate_extensions_and_critical(payload: dict) -> None:
    critical = _require(payload, "critical_extensions", "payload")
    if not isinstance(critical, list):
        raise _schema_invalid("critical_extensions must be an array")
    ext = payload.get("extensions")
    if ext is not None and not isinstance(ext, dict):
        raise _schema_invalid("extensions must be an object")
    ext_keys = set(ext.keys()) if isinstance(ext, dict) else set()
    for name in critical:
        _check_str(name, "critical_extensions[]")
        # Every critical extension must be present AND understood; G2A understands none → fail closed.
        if name not in ext_keys:
            raise _schema_invalid(f"critical_extensions names absent extension {name!r}")
        raise _schema_invalid(f"critical extension {name!r} not understood at G2A")


def _validate_optional_reference(payload: dict, key: str) -> None:
    if key not in payload:
        return
    val = payload[key]
    if val == SENTINEL_UNAVAILABLE:
        return
    raise _schema_invalid(f"payload.{key} must be absent or '{SENTINEL_UNAVAILABLE}' at G2A")


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise _schema_invalid("payload must be an object")
    _reject_unknown(payload, _PAYLOAD_ALLOWED, "payload")
    for field in _PAYLOAD_REQUIRED:
        if field not in payload:
            raise _schema_invalid(f"missing payload.{field}")
    # version / type — exact binding, no unknown-version acceptance
    if _check_str(payload["envelope_version"], "payload.envelope_version") not in SUPPORTED_ENVELOPE_VERSIONS:
        raise _schema_invalid("unsupported envelope_version (no accept-unknown-version)")
    _check_enum(payload["envelope_type"], ALLOWED_ENVELOPE_TYPES, "payload.envelope_type")
    for field in ("report_schema_version", "resolver_id", "resolver_version",
                  "resolver_trust_policy_version", "repository_policy_id", "manifest_schema_version",
                  "git_env_policy_version", "git_version", "report_id", "nonce"):
        _check_str(payload[field], f"payload.{field}")
    _validate_repository_identity(payload["repository_identity"])
    _check_oid(payload["head_commit"], "payload.head_commit")
    _check_oid(payload["head_tree_oid"], "payload.head_tree_oid")
    _check_enum(payload["reference_resolution"], REFERENCE_RESOLUTIONS, "payload.reference_resolution")
    # reference_input: optional + NULLABLE (spec §5 null-vs-absent). string | null.
    if "reference_input" in payload and payload["reference_input"] is not None:
        _check_str(payload["reference_input"], "payload.reference_input")
    _check_repo_relative_path(payload["canonical_manifest_path"], "payload.canonical_manifest_path")
    for field in ("canonical_manifest_digest", "manifest_schema_digest", "closure_digest",
                  "attributes_closure_digest"):
        _check_digest(payload[field], f"payload.{field}")
    for field in ("mandatory_dependency_count", "accepted_count", "rejected_count", "unresolved_count"):
        _check_int(payload[field], f"payload.{field}")
    _validate_dependency_commitments(payload["per_dependency_identity_commitments"])
    _check_enum(payload["digest_algorithm"], ALLOWED_DIGEST_ALGORITHMS, "payload.digest_algorithm")
    _check_enum(payload["signature_algorithm"], ALLOWED_SIGNATURE_ALGORITHMS, "payload.signature_algorithm")
    _check_unavailable(payload["signing_key_id"], "payload.signing_key_id")   # UNAVAILABLE at G2A (G2B)
    obs = _check_timestamp(payload["observation_time"], "payload.observation_time")
    issue = _check_timestamp(payload["issue_time"], "payload.issue_time")
    start = _check_timestamp(payload["validity_start"], "payload.validity_start")
    expiry = _check_timestamp(payload["expiry"], "payload.expiry")
    if not (start <= issue <= expiry) or start >= expiry:
        raise _schema_invalid("require validity_start <= issue_time <= expiry and start < expiry")
    _ = obs  # observation_time syntax-validated; freshness never inferred (trusted time = G2C)
    if _check_str(payload["intended_use"], "payload.intended_use") != INTENDED_USE_G2A:
        raise _schema_invalid(f"intended_use must be '{INTENDED_USE_G2A}' at G2A")
    _validate_assurance(payload["assurance_claims"])
    _validate_verification_requirements(payload["verification_requirements"])
    for key in ("observed_remote_origins", "trusted_timestamp_reference",
                "revocation_snapshot_reference", "origin_attestation_reference"):
        _validate_optional_reference(payload, key)
    _validate_extensions_and_critical(payload)


# ── signature_block schema (spec §3.2) ──────────────────────────────────────────────
def _validate_signature_block(block: Any) -> None:
    if not isinstance(block, dict):
        raise _schema_invalid("signature_block must be an object")
    _reject_unknown(block, {"signing_key_id", "signature_algorithm", "signature", "timestamp_proof"},
                    "signature_block")
    for field in ("signing_key_id", "signature_algorithm", "signature", "timestamp_proof"):
        _check_unavailable(_require(block, field, "signature_block"), f"signature_block.{field}")


def validate_envelope(envelope: dict) -> str:
    """Validate the full envelope (payload + signature_block). Returns TRUST_OK or raises.

    Every structural failure is TRUST_ENVELOPE_SCHEMA_INVALID (spec §8). Schema conformance is NOT trust
    acceptance (see evaluate_envelope).
    """
    if not isinstance(envelope, dict):
        raise _schema_invalid("envelope must be an object")
    _reject_unknown(envelope, {"payload", "signature_block"}, "envelope")
    _validate_payload(_require(envelope, "payload", "envelope"))
    _validate_signature_block(_require(envelope, "signature_block", "envelope"))
    return TRUST_OK


# ── no-authorisation result model (spec §9) ─────────────────────────────────────────
def _non_authorising_dimensions() -> dict:
    return {
        "signature_verified": False,
        "signer_authorised": False,
        "timestamp_verified": False,
        "fresh": False,
        "not_revoked": "unverified",
        "repository_attested": False,
        "release_approved": False,
        "semantic_identity_verified": False,
        "attributes_binding_verified": False,
        "preflight_eligible": False,   # no signature verification exists → not even preflight-eligible
        "runtime_eligible": False,
        "capture_eligible": False,
    }


def evaluate_envelope(raw_or_obj: Any) -> dict:
    """Parse (if bytes), schema-validate and canonicalise the `payload`, returning a strict result dict.

    Reports document conformance + canonical payload bytes/digest for deterministic fixture comparison, and
    ALWAYS reports every trust dimension at its fail-closed value. Schema conformance NEVER implies signature
    verification, freshness, revocation status, runtime eligibility or capture eligibility. Never raises for
    a structural problem — returns document_conformant=False with a reason code.
    """
    result = {
        "document_conformant": False,
        "reason_code": None,
        "canonical_bytes_available": False,
        "canonical_digest": None,
        "classification": "invalid",
        "intended_use": None,
        **_non_authorising_dimensions(),
    }
    try:
        env = parse_envelope_strict(raw_or_obj) if isinstance(raw_or_obj, (bytes, bytearray)) else raw_or_obj
        if not isinstance(env, dict):
            raise _schema_invalid("envelope must be an object or bytes")
        validate_envelope(env)
        canonical = canonicalise_payload(env)
        result.update({
            "document_conformant": True,
            "reason_code": TRUST_OK,
            "canonical_bytes_available": True,
            "canonical_digest": compute_digest(canonical),
            "classification": "fixture_only",
            "intended_use": env["payload"].get("intended_use"),
        })
    except TrustEnvelopeError as exc:
        result["reason_code"] = exc.reason_code
    result.update(_non_authorising_dimensions())   # defence in depth: never flip-able to true
    return result
