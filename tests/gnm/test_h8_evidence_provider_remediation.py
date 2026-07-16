"""tests/gnm/test_h8_evidence_provider_remediation.py

Adversarial regression tests for the H8 evidence-provider trust-boundary remediation
(H8-PREV-F-001..005). Prove that: production acceptance requires a POSITIVELY authorised producer (not
the absence of a fixture marker); renaming/removing individual fixture indicators cannot launder a
fixture into production; the runtime observer must satisfy a typed contract (truthiness is rejected);
dirty-tree enforcement is mandatory; and the previously unused reason codes are now reachable or
explicitly reserved. Pure, no-Isaac, no-capture; document_only preflight still never authorises capture.
"""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm import h8_evidence_provider as prov  # noqa: E402
from scripts.gnm import h8_evidence_schema as es  # noqa: E402

RT = "2026-07-16T12:30:00Z"
CLK = lambda: "2026-07-16T12:00:00Z"  # noqa: E731
TREE = lambda: {"commit": "abc123", "dependency_dirty": False}  # noqa: E731


def _P(mode="preflight", **kw):
    kw.setdefault("clock", CLK)
    kw.setdefault("tree_state", TREE)
    return prov.H8EvidenceProvider(mode=mode, **kw)


def _fixture(**over):
    env = copy.deepcopy(es.synthetic_render_evidence())
    for dotted, val in over.items():
        node = env
        parts = dotted.split(".")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = val
    return es._seal(env)


def _scrub_fixture(producer="unregistered-producer"):
    """A fixture with EVERY known fixture indicator removed except the producer id, which is set to an
    unregistered non-fixture value. Used to prove positive-trust rejection (not fixture-marker reliance)."""
    env = copy.deepcopy(es.synthetic_render_evidence())
    env["producer"]["component"] = producer
    env["producer"]["method"] = "real"
    env["provenance"].update({"producer_component": producer, "run_id": "prod-run-1",
                              "method_id": "real-method", "scene_source": "real", "config_source": "real"})
    env["payload"]["diagnostic_ref"] = "real://render"
    return es._seal(env)


def _prod(env, policy=None):
    return es.validate_envelope(env, review_time=RT, production_mode=True, trust_policy=policy)


# ── §21 fixture-mutation matrix: every mutation still rejected in production ─────────
def test_f001_original_fixture_marker_rejected():
    assert _prod(es.synthetic_render_evidence())["reason_code"] == es.FIXTURE_IN_PRODUCTION


def test_f001_renamed_marker_rejected():
    assert _prod(_fixture(**{"producer.component": "acme-real"}))["reason_code"] == \
        es.FIXTURE_IN_PRODUCTION


def test_f001_removed_marker_rejected():
    assert _prod(_fixture(**{"producer.component": ""}))["reason_code"] == es.FIXTURE_IN_PRODUCTION


def test_f001_run_id_only_changed_rejected():
    assert _prod(_fixture(**{"provenance.run_id": "prod-123"}))["reason_code"] == \
        es.FIXTURE_IN_PRODUCTION


def test_f001_diagnostic_ref_only_changed_rejected():
    assert _prod(_fixture(**{"payload.diagnostic_ref": "real://x"}))["reason_code"] == \
        es.FIXTURE_IN_PRODUCTION


def test_f001_single_indicator_remaining_rejected():
    # scrub everything except provenance.producer_component sentinel -> still caught
    env = _scrub_fixture()
    env["provenance"]["producer_component"] = es.FIXTURE_PRODUCER
    env = es._seal(env)
    assert _prod(env)["reason_code"] == es.FIXTURE_IN_PRODUCTION


def test_f001_all_indicators_scrubbed_but_unregistered_rejected():
    assert _prod(_scrub_fixture())["reason_code"] == es.PRODUCER_NOT_AUTHORISED


def test_f001_valid_looking_unregistered_producer_rejected():
    assert _prod(_scrub_fixture(producer="totally-legit-corp"))["reason_code"] == \
        es.PRODUCER_NOT_AUTHORISED


def test_f001_self_declared_trust_class_ignored():
    # evidence cannot self-promote: an injected producer.trust_class is never consulted
    env = _scrub_fixture()
    env["producer"]["trust_class"] = es.TRUST_RUNTIME_AUTHORISED  # ignored by policy
    env = es._seal(env)
    assert _prod(env)["reason_code"] == es.PRODUCER_NOT_AUTHORISED


def test_f001_registered_preflight_producer_not_production_authorised():
    prf = _P().emit_evidence("sfork_00", kind="render")["evidence"]["render_valid"]
    # the real preflight producer is registered but preflight-class -> not production-authorised
    assert _prod(prf)["reason_code"] == es.PRODUCER_NOT_AUTHORISED


def test_f001_disabled_producer_rejected():
    pol = copy.deepcopy(es.DEFAULT_PRODUCER_POLICY)
    pol["producers"]["runtime-x"] = {"trust_class": es.TRUST_RUNTIME_AUTHORISED,
                                     "permitted_modes": ("production",),
                                     "permitted_evidence_types": ("render_valid",),
                                     "permitted_schema_versions": (es.SCHEMA_VERSION,),
                                     "runtime_observer_allowed": True, "signature_requirement": "none",
                                     "enabled": False}
    pol["production_trust_classes"] = (es.TRUST_RUNTIME_AUTHORISED,)
    env = _scrub_fixture(producer="runtime-x")
    env["status"] = "valid"
    env = es._seal(env)
    assert _prod(env, pol)["reason_code"] == es.PRODUCER_NOT_AUTHORISED


def test_f001_registered_producer_disallowed_schema_and_type():
    base = {"trust_class": es.TRUST_RUNTIME_AUTHORISED, "permitted_modes": ("production",),
            "permitted_evidence_types": ("render_valid",), "permitted_schema_versions": (es.SCHEMA_VERSION,),
            "runtime_observer_allowed": True, "signature_requirement": "none", "enabled": True}
    # disallowed schema
    pol = copy.deepcopy(es.DEFAULT_PRODUCER_POLICY)
    pol["producers"]["runtime-x"] = {**base, "permitted_schema_versions": ("h8-evidence/9.9.9",)}
    pol["production_trust_classes"] = (es.TRUST_RUNTIME_AUTHORISED,)
    env = _scrub_fixture(producer="runtime-x"); env["status"] = "valid"; env = es._seal(env)
    assert _prod(env, pol)["reason_code"] == es.PRODUCER_NOT_AUTHORISED
    # disallowed evidence type (render_valid not permitted)
    pol2 = copy.deepcopy(es.DEFAULT_PRODUCER_POLICY)
    pol2["producers"]["runtime-x"] = {**base, "permitted_evidence_types": ("drive_valid",)}
    pol2["production_trust_classes"] = (es.TRUST_RUNTIME_AUTHORISED,)
    assert _prod(env, pol2)["reason_code"] == es.PRODUCER_NOT_AUTHORISED


def test_f001_positive_path_accepts_authorised_producer():
    # PROOF the positive policy works: an authorised runtime producer with status=valid IS accepted.
    # (test-only injected policy; the DEFAULT policy authorises no production producer.)
    pol = copy.deepcopy(es.DEFAULT_PRODUCER_POLICY)
    pol["producers"]["runtime-x"] = {"trust_class": es.TRUST_RUNTIME_AUTHORISED,
                                     "permitted_modes": ("production",),
                                     "permitted_evidence_types": ("render_valid", "drive_valid"),
                                     "permitted_schema_versions": (es.SCHEMA_VERSION,),
                                     "runtime_observer_allowed": True, "signature_requirement": "none",
                                     "enabled": True}
    pol["production_trust_classes"] = (es.TRUST_RUNTIME_AUTHORISED,)
    env = _scrub_fixture(producer="runtime-x")
    env["status"] = "valid"
    env = es._seal(env)
    r = es.validate_envelope(env, review_time=RT, production_mode=True, trust_policy=pol)
    assert r["accepted"] is True and r["reason_code"] == es.ACCEPTED


# ── §18 document_only preserved under trust ────────────────────────────────────────
def test_document_only_preflight_still_blocks_capture():
    prf = _P().emit_evidence("sfork_00", kind="both")["evidence"]
    exp = {k: prf["render_valid"]["subject"][k] for k in es._SUBJECT_COMMON}
    # valid DOCUMENT under preflight validation
    assert es.validate_envelope(prf["render_valid"], review_time=RT, expected=exp,
                                document_only=True)["accepted"] is True
    # NEVER authorises capture
    assert es.validate_pair(prf["render_valid"], prf["drive_valid"], review_time=RT, expected=exp,
                            document_only=False)["reason_code"] == es.STATUS_NOT_VALID
    # and a preflight producer is not production-authorised even as a document
    assert es.validate_envelope(prf["render_valid"], review_time=RT, production_mode=True,
                                document_only=True)["reason_code"] == es.PRODUCER_NOT_AUTHORISED


# ── §22 observer adversarial matrix ─────────────────────────────────────────────────
class _StubObserver:
    """Test-only stub that satisfies the observer SHAPE but is NOT policy-authorised."""
    observer_id = "stub-observer"
    observer_version = "0.0.1"
    supported_evidence_types = ("render_valid", "drive_valid")
    supported_schema_versions = (es.SCHEMA_VERSION,)
    available = True

    def observe_render(self, *a, **k):
        return {}

    def observe_drive(self, *a, **k):
        return {}


class _PartialObserver:
    observer_id = "partial"
    available = True  # missing version/types/methods


def test_f002_truthiness_observers_rejected():
    for bad in (True, 1, {"x": 1}, object(), (lambda: None), _PartialObserver()):
        ok, why = prov.validate_runtime_observer(bad)
        assert ok is False, f"observer {bad!r} wrongly accepted: {why}"


def test_f002_well_formed_stub_not_authorised():
    ok, why = prov.validate_runtime_observer(_StubObserver())
    assert ok is False and "not authorised" in why


def test_f002_unavailable_observer_rejected():
    obs = _StubObserver()
    obs.available = False
    assert prov.validate_runtime_observer(obs)[0] is False


def test_f002_provider_production_with_object_observer_invalid():
    assert _P(mode="production", runtime_observer=object()).emit_evidence("sfork_00")["provider_code"] \
        == prov.PROVIDER_OBSERVER_INVALID


def test_f002_provider_production_with_stub_observer_invalid():
    assert _P(mode="production", runtime_observer=_StubObserver()).emit_evidence("sfork_00")[
        "provider_code"] == prov.PROVIDER_OBSERVER_INVALID


def test_f002_provider_none_observer_blocked():
    assert _P(mode="production").emit_evidence("sfork_00")["provider_code"] == \
        prov.PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING


def test_f002_want_runtime_valid_in_preflight_rejected():
    r = _P().emit_evidence("sfork_00", want_runtime_valid=True)
    assert r["ok"] is False and r["provider_code"] in (
        prov.PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING, prov.PROVIDER_OBSERVER_INVALID)


# ── §23 dirty-tree adversarial matrix ──────────────────────────────────────────────
def test_f003_no_tree_state_fails_closed():
    assert prov.H8EvidenceProvider(mode="preflight", clock=CLK).emit_evidence("sfork_00")[
        "provider_code"] == prov.PROVIDER_DIRTY_TREE


def test_f003_dirty_dependency_fails_closed():
    assert _P(tree_state=lambda: {"dependency_dirty": True}).emit_evidence("sfork_00")[
        "provider_code"] == prov.PROVIDER_DIRTY_TREE


def test_f003_tree_state_raises_fails_closed():
    def boom():
        raise RuntimeError("git unavailable")
    assert _P(tree_state=boom).emit_evidence("sfork_00")["provider_code"] == prov.PROVIDER_DIRTY_TREE


def test_f003_tree_state_non_dict_fails_closed():
    assert _P(tree_state=lambda: "clean").emit_evidence("sfork_00")["provider_code"] == \
        prov.PROVIDER_DIRTY_TREE


def test_f003_dependency_dirty_missing_or_none_fails_closed():
    assert _P(tree_state=lambda: {"commit": "x"}).emit_evidence("sfork_00")["provider_code"] == \
        prov.PROVIDER_DIRTY_TREE
    assert _P(tree_state=lambda: {"dependency_dirty": None}).emit_evidence("sfork_00")[
        "provider_code"] == prov.PROVIDER_DIRTY_TREE


def test_f003_affirmatively_clean_proceeds():
    assert _P(tree_state=lambda: {"commit": "x", "dependency_dirty": False}).emit_evidence(
        "sfork_00")["ok"] is True


# ── §16 reason-code taxonomy: F-004 codes now reachable; MODE_INVALID reserved ──────
def test_f004_artifact_digest_failed_reachable():
    def raising(_b):
        raise RuntimeError("digest boom")
    assert _P(digest_fn=raising).emit_evidence("sfork_00")["provider_code"] == \
        prov.PROVIDER_ARTIFACT_DIGEST_FAILED


def test_f004_clock_untrusted_reachable():
    assert _P(clock=lambda: "not-a-timestamp").emit_evidence("sfork_00")["provider_code"] == \
        prov.PROVIDER_CLOCK_UNTRUSTED


def test_f004_schema_rejected_reachable():
    # a 64-hex-no-prefix digest passes the id hex-slice but fails subject digest format -> SCHEMA_REJECTED
    def hexonly(b):
        return hashlib.sha256(b).hexdigest()
    assert _P(digest_fn=hexonly).emit_evidence("sfork_00")["provider_code"] == \
        prov.PROVIDER_SCHEMA_REJECTED


def test_f004_active_codes_all_triggerable_and_mode_invalid_reserved():
    triggered = set()
    triggered.add(_P().emit_evidence("sfork_00")["provider_code"])                      # OK_PREFLIGHT
    triggered.add(prov.H8EvidenceProvider(mode="fixture", clock=CLK,
                  sink=prov.InMemorySink("tests/fixture")).emit_evidence("sfork_00")["provider_code"])
    triggered.add(_P(mode="production").emit_evidence("sfork_00")["provider_code"])      # BLOCKED
    triggered.add(_P(mode="production", runtime_observer=object()).emit_evidence("sfork_00")[
        "provider_code"])                                                                # OBSERVER_INVALID
    triggered.add(prov.H8EvidenceProvider(mode="fixture", clock=CLK,
                  sink=prov.InMemorySink("assets/x")).emit_evidence("sfork_00")["provider_code"])  # FIX_REJ
    triggered.add(_P(reader=lambda r: (_ for _ in ()).throw(FileNotFoundError())
                     ).emit_evidence("sfork_00")["provider_code"])                       # ARTIFACT_MISSING
    triggered.add(_P(digest_fn=lambda b: (_ for _ in ()).throw(ValueError())).emit_evidence(
        "sfork_00")["provider_code"])                                                    # DIGEST_FAILED
    triggered.add(_P(tree_state=lambda: {"dependency_dirty": True}).emit_evidence("sfork_00")[
        "provider_code"])                                                                # DIRTY_TREE
    triggered.add(_P(digest_fn=lambda b: hashlib.sha256(b).hexdigest()).emit_evidence("sfork_00")[
        "provider_code"])                                                                # SCHEMA_REJECTED
    triggered.add(_P(clock=lambda: "bad").emit_evidence("sfork_00")["provider_code"])    # CLOCK_UNTRUSTED
    triggered.add(_P().emit_evidence("sfork_99")["provider_code"])                       # INSTANCE_UNKNOWN
    triggered.add(_P(require_signature=True).emit_evidence("sfork_00")["provider_code"])  # SIGNATURE_REQ
    # INTERNAL_ERROR: malformed config YAML passes the non-empty precheck then fails to parse
    triggered.add(_P(reader=lambda r: (b"{[bad" if r == prov.DATASET_CONFIG_REL
                                       else prov.default_reader(r))).emit_evidence("sfork_00")[
        "provider_code"])
    # BINDING_MISMATCH: config with cl_bound_xy != 6.0
    import yaml
    _cfgb = prov.default_reader(prov.DATASET_CONFIG_REL)

    def _bad_bound(r):
        if r == prov.DATASET_CONFIG_REL:
            c = yaml.safe_load(_cfgb); c["cl_bound_xy"] = 7.0
            return yaml.safe_dump(c).encode()
        return prov.default_reader(r)
    triggered.add(_P(reader=_bad_bound).emit_evidence("sfork_00")["provider_code"])       # BINDING_MISMATCH
    # OUTPUT_CONFLICT: same id, different content into one sink
    _sink = prov.InMemorySink()
    _P(sink=_sink).emit_evidence("sfork_00", kind="render")
    triggered.add(prov.H8EvidenceProvider(mode="preflight", clock=lambda: "2026-07-16T13:00:00Z",
                  tree_state=TREE, sink=_sink).emit_evidence("sfork_00", kind="render")["provider_code"])
    # OK_FIXTURE
    triggered.add(prov.H8EvidenceProvider(mode="fixture", clock=CLK,
                  sink=prov.InMemorySink("tests/fixture")).emit_evidence("sfork_00")["provider_code"])
    missing = prov.PROVIDER_ACTIVE_CODES - triggered
    assert missing == set(), f"active codes not triggered: {missing}"
    assert prov.PROVIDER_MODE_INVALID in prov.PROVIDER_RESERVED_CODES


# ── §19 capture-authorisation invariant: no backend for blocked/fixture cases ──────
def test_no_output_on_any_rejection():
    sink = prov.InMemorySink()
    for p in (_P(mode="production", sink=sink), _P(tree_state=lambda: {"dependency_dirty": True}, sink=sink),
              prov.H8EvidenceProvider(mode="preflight", clock=CLK, sink=sink)):
        p.emit_evidence("sfork_00")
    assert sink.store == {} and sink.atomic_ops == 0
