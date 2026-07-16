"""tests/gnm/test_h8_trust_envelope.py

G2A — canonical dependency-evidence envelope: schema, JCS canonicalisation and fixture-only interoperability.

Implements/verifies the committed spec docs/research/H8_G2A_CANONICAL_ENVELOPE_SPEC.md (23d95c8): the
`payload`+`signature_block` envelope, the 4-stage canonical-byte pipeline (strict parse → schema validation →
JCS+NFC canonicalisation → SHA-256 digest), the absent/null/UNAVAILABLE tri-state, non-waivable
`verification_requirements`, and the two G2A-owned failure codes (`TRUST_ENVELOPE_SCHEMA_INVALID`,
`TRUST_CANONICALISATION_FAILED`).

They do NOT establish signature authenticity, trusted time, revocation, origin or any runtime/capture fact.
No key/certificate/signature/trusted-timestamp/revocation record is created. No Isaac/ROS/capture.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "gnm" / "h8_trust_envelope.py"
_spec = importlib.util.spec_from_file_location("h8_trust_envelope", _MOD_PATH)
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "h8_trust_envelope"
_DIG = "sha256:" + "a" * 64
SI = T.TRUST_ENVELOPE_SCHEMA_INVALID


# ── builders (mirror the committed spec §3) ──────────────────────────────────────────
def _dep(did, klass, path, scheme):
    return {
        "dependency_id": did, "dependency_class": klass, "path": path,
        "git_blob_oid": "1" * 40, "git_content_digest": _DIG,
        "semantic_identity_profile": {"scheme": scheme, "id": did, "version": "1.0.0", "digest": _DIG},
        "required": True,
    }


def build_payload(full=False) -> dict:
    p = {
        "envelope_version": "h8-trust-envelope/1.0.0",
        "envelope_type": "resolver-report",
        "report_schema_version": "h8-resolver-report/1.0.0",
        "resolver_id": "h8-git-dependency-resolver",
        "resolver_version": "h8-git-dependency-resolver/1.0.0",
        "resolver_trust_policy_version": "h8-dependency-policy/1.0.0",
        "repository_policy_id": "h8-repo-policy/1.0.0",
        "repository_identity": {"canonical_name": "gnm-vlnverse-baseline",
                                "root_commit": "67b038385629658096ed5f656cd1a29d1592f165"},
        "head_commit": "efa671abc18bde1e6c1f942360cb8d957db60729",
        "head_tree_oid": "2" * 40,
        "reference_resolution": "commit",
        "canonical_manifest_path": "configs/gnm/h8_dependency_manifest.json",
        "canonical_manifest_digest": _DIG,
        "manifest_schema_version": "h8-dependency-manifest/1.0.0",
        "manifest_schema_digest": _DIG,
        "closure_digest": _DIG,
        "attributes_closure_digest": _DIG,
        "git_env_policy_version": "h8-git-env-policy/1.0.0",
        "git_version": "2.34.1",
        "mandatory_dependency_count": 2,
        "accepted_count": 2,
        "rejected_count": 0,
        "unresolved_count": 0,
        "per_dependency_identity_commitments": [
            _dep("h8-resolver", "module", "scripts/gnm/h8_git_dependency_resolver.py", "mod"),
            _dep("h8-dependency-manifest", "dependency-manifest", "configs/gnm/h8_dependency_manifest.json", "man"),
        ],
        "digest_algorithm": "sha-256",
        "signature_algorithm": "ed25519",
        "signing_key_id": "UNAVAILABLE",
        "observation_time": "2026-07-16T00:00:00Z",
        "issue_time": "2026-07-16T00:00:00Z",
        "validity_start": "2026-07-16T00:00:00Z",
        "expiry": "2026-07-16T01:00:00Z",
        "report_id": "h8-report:fixture:0001",
        "nonce": "u4gLptR0Rj2b8xq1nX3zAA",
        "intended_use": "preflight-document",
        "assurance_claims": ["content-equivalent"],
        "verification_requirements": {k: True for k in T.VERIFICATION_REQUIREMENT_KEYS},
        "critical_extensions": [],
    }
    if full:
        p["observed_remote_origins"] = "UNAVAILABLE"
        p["reference_input"] = "refs/tags/pilot"
        p["trusted_timestamp_reference"] = "UNAVAILABLE"
        p["revocation_snapshot_reference"] = "UNAVAILABLE"
        p["origin_attestation_reference"] = "UNAVAILABLE"
        p["extensions"] = {"x-note": {"note": "non-critical forward growth"}}
    return p


def build_env(full=False) -> dict:
    return {"payload": build_payload(full),
            "signature_block": {"signing_key_id": "UNAVAILABLE", "signature_algorithm": "UNAVAILABLE",
                                "signature": "UNAVAILABLE", "timestamp_proof": "UNAVAILABLE"}}


def _dep0(env):
    return env["payload"]["per_dependency_identity_commitments"][0]


def _reason(x):
    return T.evaluate_envelope(x)["reason_code"]


# ═══════════════════ 1. positive conformance ═══════════════════
def test_minimal_valid():
    res = T.evaluate_envelope(build_env(False))
    assert res["document_conformant"] is True
    assert res["reason_code"] == T.TRUST_OK
    assert res["canonical_digest"].startswith("sha256:")
    assert res["classification"] == "fixture_only"


def test_full_valid():
    assert T.evaluate_envelope(build_env(True))["document_conformant"] is True


def test_validate_envelope_returns_ok():
    assert T.validate_envelope(build_env(True)) == T.TRUST_OK


def test_canonical_bytes_cover_payload_only():
    env = build_env(True)
    base = T.canonicalise_payload(env)
    env["signature_block"]["signature"] = "UNAVAILABLE"   # unchanged sentinel
    assert T.canonicalise_payload(env) == base


# ═══════════════════ 2. determinism ═══════════════════
def test_repeat_canonicalisation_identical():
    env = build_env(True)
    a = T.canonicalise_payload(env)
    b = T.canonicalise_payload(copy.deepcopy(env))
    assert a == b and T.compute_digest(a) == T.compute_digest(b)


def test_reordered_payload_identical_digest():
    env = build_env(True)
    env2 = build_env(True)
    env2["payload"] = dict(reversed(list(env2["payload"].items())))
    assert T.canonicalise_payload(env) == T.canonicalise_payload(env2)


def test_nested_reorder_identical():
    env = build_env(True)
    env2 = build_env(True)
    env2["payload"]["repository_identity"] = dict(reversed(list(env2["payload"]["repository_identity"].items())))
    assert T.canonicalise_payload(env) == T.canonicalise_payload(env2)


def test_machine_root_independent(tmp_path, monkeypatch):
    env = build_env(True)
    before = T.canonicalise_payload(env)
    monkeypatch.chdir(tmp_path)
    assert T.canonicalise_payload(env) == before


def test_jcs_key_sort_and_escaping():
    assert T.canonicalise({"b": 1, "a": 2, "Z": 3}) == b'{"Z":3,"a":2,"b":1}'
    out = T.canonicalise({"s": "a/b\t\"\\\b\f\r"}).decode()
    assert '"s":"a/b\\t\\"\\\\\\b\\f\\r"' in out
    assert T.canonicalise({"z": 0, "neg": -7, "big": 10 ** 25}) == b'{"big":10000000000000000000000000,"neg":-7,"z":0}'


def test_utf16_codeunit_key_order():
    out = T.canonicalise({"\U0001f600": 1, "￿": 2, "a": 3}).decode()
    assert out.index('"a"') < out.index("\U0001f600") < out.index("￿")


# ═══════════════════ 3. NFC normalisation (spec §4.3, vector 4) ═══════════════════
def test_nfd_equals_nfc_digest():
    nfc = build_env(True); nfc["payload"]["reference_input"] = "café-ref"   # composed
    nfd = build_env(True); nfd["payload"]["reference_input"] = "café-ref"   # decomposed
    assert T.canonicalise_payload(nfc) == T.canonicalise_payload(nfd)


def test_canonicalise_normalises_keys_and_values():
    assert T.canonicalise({"café": 1}) == T.canonicalise({"café": 1})   # NFC key == NFD key


# ═══════════════════ 4. absent vs null vs UNAVAILABLE (spec §5) ═══════════════════
def test_null_differs_from_absent():
    absent = build_env(False)
    nulled = build_env(False); nulled["payload"]["reference_input"] = None
    assert T.canonicalise_payload(absent) != T.canonicalise_payload(nulled)


def test_absent_optional_not_in_bytes():
    env = build_env(False)
    assert b"reference_input" not in T.canonicalise_payload(env)


def test_unavailable_sentinel_present_in_bytes():
    env = build_env(True)
    assert b"UNAVAILABLE" in T.canonicalise_payload(env)


# ═══════════════════ 5. strict parse (raw) ═══════════════════
@pytest.mark.parametrize("raw", [
    b'{"payload":{},"payload":{}}',
    b'{"payload":{"nonce":"a","nonce":"b"},"signature_block":{}}',
    b'{"payload":{"accepted_count":1.5}}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}',
    b"\xef\xbb\xbf{}", b'{"a":"\xff"}', b"[1,2,3]", b"not json",
])
def test_strict_parse_rejects(raw):
    assert _reason(raw) == SI


def test_parse_requires_bytes():
    with pytest.raises(T.TrustEnvelopeError) as ei:
        T.parse_envelope_strict("a string")  # type: ignore[arg-type]
    assert ei.value.reason_code == SI


# ═══════════════════ 6. schema rejections (all → TRUST_ENVELOPE_SCHEMA_INVALID) ═══════════════════
def test_unknown_top_field():
    env = build_env(False); env["surprise"] = 1
    assert _reason(env) == SI


def test_unknown_payload_field():
    env = build_env(False); env["payload"]["surprise"] = 1
    assert _reason(env) == SI


def test_missing_payload_field():
    env = build_env(False); env["payload"].pop("nonce")
    assert _reason(env) == SI


def test_missing_signature_block():
    env = build_env(False); env.pop("signature_block")
    assert _reason(env) == SI


def test_unsupported_version_no_unknown_accept():
    env = build_env(False); env["payload"]["envelope_version"] = "h8-trust-envelope/9.9.9"
    assert _reason(env) == SI


@pytest.mark.parametrize("field,val", [
    ("envelope_type", "other"),
    ("reference_resolution", "branch"),
    ("digest_algorithm", "sha-1"),
    ("signature_algorithm", "rsa"),      # downgrade / unknown algorithm
    ("intended_use", "capture"),
    ("intended_use", "runtime"),
])
def test_bad_enums(field, val):
    env = build_env(False); env["payload"][field] = val
    assert _reason(env) == SI


def test_bad_dependency_class():
    env = build_env(False); _dep0(env)["dependency_class"] = "mystery"
    assert _reason(env) == SI


def test_bad_oid():
    env = build_env(False); _dep0(env)["git_blob_oid"] = "XYZ"
    assert _reason(env) == SI


def test_bad_digest():
    env = build_env(False); env["payload"]["closure_digest"] = "sha256:short"
    assert _reason(env) == SI


@pytest.mark.parametrize("bad", ["/etc/passwd", "a\\b", "configs/../x", "./x", "a//b"])
def test_bad_paths(bad):
    env = build_env(False); _dep0(env)["path"] = bad
    assert _reason(env) == SI


@pytest.mark.parametrize("ts", [
    "2026-07-16 00:00:00", "2026-07-16T00:00:00", "2026-07-16T00:00:00+00:00",
    "2026-07-16T00:00:00.5Z", "2026-13-01T00:00:00Z", "not-a-time",
])
def test_bad_timestamp(ts):
    env = build_env(False); env["payload"]["issue_time"] = ts
    assert _reason(env) == SI


def test_bad_interval():
    env = build_env(False); env["payload"]["expiry"] = "2026-07-15T00:00:00Z"
    assert _reason(env) == SI


def test_dup_dependency_id():
    env = build_env(False)
    env["payload"]["per_dependency_identity_commitments"].append(copy.deepcopy(_dep0(env)))
    assert _reason(env) == SI


def test_oversized_string():
    env = build_env(False); env["payload"]["nonce"] = "x" * 600
    assert _reason(env) == SI


def test_carriage_return_rejected():
    env = build_env(False); env["payload"]["nonce"] = "abc\rdef"
    assert _reason(json.dumps(env).encode()) == SI


def test_bool_coercion():
    env = build_env(False); _dep0(env)["required"] = "true"
    assert _reason(env) == SI


def test_int_given_bool():
    env = build_env(False); env["payload"]["accepted_count"] = True
    assert _reason(env) == SI


# ═══════════════════ 7. UNAVAILABLE sentinels / no fabricated signature ═══════════════════
def test_signing_key_must_be_unavailable():
    env = build_env(False); env["payload"]["signing_key_id"] = "key-1"
    assert _reason(env) == SI


@pytest.mark.parametrize("field", ["signing_key_id", "signature_algorithm", "signature", "timestamp_proof"])
def test_signature_block_must_be_all_unavailable(field):
    env = build_env(False); env["signature_block"][field] = "something"
    assert _reason(env) == SI


def test_optional_deferred_ref_must_be_absent_or_unavailable():
    env = build_env(False); env["payload"]["trusted_timestamp_reference"] = "https://tsa.example"
    assert _reason(env) == SI


def test_deferred_ref_unavailable_accepted():
    env = build_env(False); env["payload"]["revocation_snapshot_reference"] = "UNAVAILABLE"
    assert T.evaluate_envelope(env)["document_conformant"] is True


# ═══════════════════ 8. non-waivable requirements / assurance / intended-use ═══════════════════
@pytest.mark.parametrize("key", list(T.VERIFICATION_REQUIREMENT_KEYS))
def test_verification_requirements_non_waivable(key):
    env = build_env(False); env["payload"]["verification_requirements"][key] = False
    assert _reason(env) == SI


def test_verification_requirements_unknown_key():
    env = build_env(False); env["payload"]["verification_requirements"]["require_magic"] = True
    assert _reason(env) == SI


@pytest.mark.parametrize("claims", [
    ["resolver-authenticated"], ["runtime-authorised"], ["content-equivalent", "release-attested"],
    [], ["release-attested"],
])
def test_assurance_escalation_rejected(claims):
    env = build_env(False); env["payload"]["assurance_claims"] = claims
    assert _reason(env) == SI


def test_only_content_equivalent_accepted():
    env = build_env(False); env["payload"]["assurance_claims"] = ["content-equivalent"]
    assert T.evaluate_envelope(env)["document_conformant"] is True


def test_intended_use_must_be_preflight_document():
    env = build_env(False); env["payload"]["intended_use"] = "preflight_resolution"
    assert _reason(env) == SI


# ═══════════════════ 9. extensions / critical extensions ═══════════════════
def test_critical_extension_rejected():
    env = build_env(False)
    env["payload"]["critical_extensions"] = ["x-must"]
    env["payload"]["extensions"] = {"x-must": {"v": 1}}
    assert _reason(env) == SI


def test_critical_extension_naming_absent_rejected():
    env = build_env(False); env["payload"]["critical_extensions"] = ["x-absent"]
    assert _reason(env) == SI


def test_noncritical_extension_accepted():
    env = build_env(False); env["payload"]["extensions"] = {"x-note": {"v": "hi"}}
    assert T.evaluate_envelope(env)["document_conformant"] is True


def test_extension_changes_canonical_bytes():
    env = build_env(False)
    base = T.canonicalise_payload(env)
    env["payload"]["extensions"] = {"x-note": {"v": "hi"}}
    assert T.canonicalise_payload(env) != base


# ═══════════════════ 10. one-byte mutation / semantic sensitivity ═══════════════════
def test_changed_closure_digest_changes_digest():
    env = build_env(False)
    base = T.evaluate_envelope(env)["canonical_digest"]
    env["payload"]["closure_digest"] = "sha256:" + "d" * 64
    assert T.evaluate_envelope(env)["canonical_digest"] != base


def test_changed_commitment_changes_digest():
    env = build_env(False)
    base = T.evaluate_envelope(env)["canonical_digest"]
    _dep0(env)["git_blob_oid"] = "3" * 40
    assert T.evaluate_envelope(env)["canonical_digest"] != base


# ═══════════════════ 11. no-authorisation result model (spec §9) ═══════════════════
def test_schema_valid_non_authorising():
    res = T.evaluate_envelope(build_env(True))
    for k in ("signature_verified", "signer_authorised", "timestamp_verified", "fresh",
              "repository_attested", "release_approved", "semantic_identity_verified",
              "attributes_binding_verified", "preflight_eligible", "runtime_eligible", "capture_eligible"):
        assert res[k] is False, k
    assert res["not_revoked"] == "unverified"


def test_invalid_also_non_authorising():
    res = T.evaluate_envelope(b'{"broken":true}')
    assert res["document_conformant"] is False
    for k in ("runtime_eligible", "capture_eligible", "signature_verified", "preflight_eligible"):
        assert res[k] is False


def test_module_exposes_no_sign_or_authorise():
    for forbidden in ("sign", "verify_signature", "authorise", "authorize"):
        assert not hasattr(T, forbidden)


def test_no_crypto_signing_imports():
    src = _MOD_PATH.read_text()
    for lib in ("cryptography", "nacl", "ecdsa", "jwt", "jose", "OpenSSL", "Crypto"):
        assert f"import {lib}" not in src and f"from {lib}" not in src


# ═══════════════════ 12. committed fixture corpus ═══════════════════
def _catalogue():
    return json.loads((FIXTURES / "envelope_vectors" / "catalogue.json").read_text())


def test_catalogue_nonempty():
    c = _catalogue()
    assert len(c["positive"]) >= 5 and len(c["negative"]) >= 25


@pytest.mark.parametrize("entry", _catalogue()["positive"], ids=lambda e: e["id"])
def test_positive_vectors(entry):
    raw = (FIXTURES / entry["file"]).read_bytes()
    res = T.evaluate_envelope(raw)
    assert res["document_conformant"] is True
    assert res["reason_code"] == "TRUST_OK"
    assert res["canonical_digest"] == entry["expected_canonical_digest"]


@pytest.mark.parametrize("entry", _catalogue()["negative"], ids=lambda e: e["id"])
def test_negative_vectors(entry):
    raw = (FIXTURES / entry["file"]).read_bytes()
    res = T.evaluate_envelope(raw)
    assert res["document_conformant"] is False
    assert res["reason_code"] == entry["expected_reason_code"]


def test_positive_reordered_equals_full():
    c = _catalogue()
    full = next(e for e in c["positive"] if e["id"] == "valid_full")["expected_canonical_digest"]
    reordered = next(e for e in c["positive"] if e["id"] == "reordered_full")["expected_canonical_digest"]
    assert full == reordered


def test_positive_nfc_equals_nfd_vector():
    c = _catalogue()
    a = next(e for e in c["positive"] if e["id"] == "unicode_nfc")["expected_canonical_digest"]
    b = next(e for e in c["positive"] if e["id"] == "unicode_nfd")["expected_canonical_digest"]
    assert a == b


# ═══════════════════ 13. cross-language canonicalisation vectors ═══════════════════
def _canon_vectors():
    return json.loads((FIXTURES / "canonical_vectors.json").read_text())["vectors"]


@pytest.mark.parametrize("vec", _canon_vectors(), ids=lambda v: v["id"])
def test_canonical_vectors(vec):
    obj = json.loads(vec["input_json"])
    cb = T.canonicalise(obj)
    assert cb.hex() == vec["canonical_utf8_hex"]
    assert "sha256:" + hashlib.sha256(cb).hexdigest() == vec["canonical_sha256"]


def test_canonical_vectors_scheme():
    assert json.loads((FIXTURES / "canonical_vectors.json").read_text())["scheme"] == "JCS/RFC8785"


# ═══════════════════ 14. taxonomy hygiene ═══════════════════
def test_only_two_reject_codes():
    assert T.TRUST_REASON_CODES == frozenset({T.TRUST_OK, T.TRUST_ENVELOPE_SCHEMA_INVALID,
                                              T.TRUST_CANONICALISATION_FAILED})
    assert len(T.TRUST_REJECT_CODES) == 2


def test_resolver_reason_codes_unchanged_and_disjoint():
    import importlib.util as u
    rp = _MOD_PATH.parent / "h8_git_dependency_resolver.py"
    spec = u.spec_from_file_location("h8_git_dependency_resolver", rp)
    R = u.module_from_spec(spec); spec.loader.exec_module(R)
    assert len(R.REASON_CODES) == 41
    assert T.TRUST_REASON_CODES.isdisjoint(R.REASON_CODES)


def test_canonicalise_float_is_canonicalisation_failed():
    with pytest.raises(T.TrustEnvelopeError) as ei:
        T.canonicalise({"x": 1.5})
    assert ei.value.reason_code == T.TRUST_CANONICALISATION_FAILED
