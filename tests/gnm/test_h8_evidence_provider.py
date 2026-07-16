"""tests/gnm/test_h8_evidence_provider.py

Tests for the H8 NON-CAPTURING evidence provider (scripts/gnm/h8_evidence_provider.py).

Pure, no-Isaac, no-capture: the provider is driven with an injected fixed clock, an in-memory sink and
the real committed artefacts (config, scene, derived plan/route). Tests prove real digests + identity
binding, fail-closed behaviour, fixture/production separation, and the critical boundary that a preflight
document is schema-valid yet NEVER authorises capture. NO Isaac, ROS 2, camera, robot, model, dataset,
image, trajectory or rosbag.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.gnm import h8_evidence_provider as prov  # noqa: E402
from scripts.gnm import h8_evidence_schema as es  # noqa: E402
from scripts.gnm import h8_synthetic_fork_recorded_mode as rm  # noqa: E402

CLK = "2026-07-16T12:00:00Z"
RT = "2026-07-16T12:30:00Z"
CONFIG_REL = "configs/gnm/h8_synthetic_fork_recorded_mode_dataset.yaml"
SCENE_REL = "assets/scenes/synthetic_diagnostic_fork/synthetic_diagnostic_fork.usda"
DRYRUN_DIR = REPO / "assets/experiments/hospital_h8_track_b_synthetic_fork_recorded_mode_dataset_dryrun"
_L1_HASHES = {
    "dataset_dryrun_manifest.json": "3833714d5dbf20a9", "dataset_plan_schema.json": "915e34f0430b6213",
    "dataset_split_validation_dryrun.json": "de70f96f74cd2d79",
    "dataset_leakage_audit_dryrun.json": "84eaea5277b7b1af", "dataset_dryrun_report.md": "02ce0c17fe2bf889",
}


def _clock():
    return CLK


def _clean_tree():
    return {"commit": "abc1234def", "dependency_dirty": False}


def _provider(mode="preflight", **kw):
    kw.setdefault("clock", _clock)
    kw.setdefault("tree_state", _clean_tree)
    return prov.H8EvidenceProvider(mode=mode, **kw)


def _emit(instance="sfork_00", kind="both", **kw):
    return _provider(**kw).emit_evidence(instance, kind=kind)


def _expected(env):
    return {k: env["subject"][k] for k in es._SUBJECT_COMMON}


# ── 1–11 real bindings/digests ──────────────────────────────────────────────────────
def test_01_real_config_digest():
    r = _emit(kind="render")
    cfg_bytes = (REPO / CONFIG_REL).read_bytes()
    assert r["evidence"]["render_valid"]["subject"]["config_digest"] == prov.default_digest(cfg_bytes)


def test_02_real_plan_digest():
    r = _emit(kind="render")
    cfg = rm.load_dataset_config(REPO / CONFIG_REL)
    plan = rm.build_dataset_plan(cfg)
    assert r["evidence"]["render_valid"]["provenance"]["plan_digest"] == \
        prov.default_digest(es.canonical_bytes(plan))


def test_03_real_route_digest():
    p = _provider()
    cfg = rm.load_dataset_config(REPO / CONFIG_REL)
    inst = p.resolve_instance(cfg, "sfork_00")
    route = p.build_route_representation(inst)
    r = _emit(kind="drive")
    assert r["evidence"]["drive_valid"]["subject"]["route_plan_digest"] == \
        prov.default_digest(es.canonical_bytes(route))


def test_04_real_scene_digest():
    r = _emit(kind="render")
    assert r["evidence"]["render_valid"]["subject"]["scene_digest"] == \
        prov.default_digest((REPO / SCENE_REL).read_bytes())


def test_05_deterministic_content_digest():
    a = _emit(kind="render")["evidence"]["render_valid"]["integrity"]["content_digest"]
    b = _emit(kind="render")["evidence"]["render_valid"]["integrity"]["content_digest"]
    assert a == b


def test_06_changed_artifact_changes_digest():
    real = (REPO / CONFIG_REL).read_bytes()

    def mutated_reader(rel):
        if rel == CONFIG_REL:
            return real + b"\n# extra byte\n"
        return prov.default_reader(rel)
    r0 = _emit(kind="render")
    r1 = _provider(reader=mutated_reader).emit_evidence("sfork_00", kind="render")
    d0 = r0["evidence"]["render_valid"]["subject"]["config_digest"]
    d1 = r1["evidence"]["render_valid"]["subject"]["config_digest"]
    assert d0 != d1


def test_07_instance_binding():
    assert _emit(kind="render")["evidence"]["render_valid"]["subject"]["instance_id"] == "sfork_00"


def test_08_scene_binding():
    assert _emit(kind="render")["evidence"]["render_valid"]["subject"]["scene_id"] == prov.SCENE_ID


def test_09_route_binding():
    assert _emit(kind="drive")["evidence"]["drive_valid"]["subject"]["route_id"] == "sfork_00_N"


def test_10_config_binding_present():
    subj = _emit(kind="render")["evidence"]["render_valid"]["subject"]
    assert es._DIGEST_RE.match(subj["config_digest"])


def test_11_cl_bound_is_six():
    assert _emit(kind="render")["evidence"]["render_valid"]["subject"]["cl_bound_xy"] == 6.0


# ── 12–16 fail-closed inputs ────────────────────────────────────────────────────────
def test_12_unknown_instance_rejected():
    r = _emit("sfork_99")
    assert r["ok"] is False and r["provider_code"] == prov.PROVIDER_INSTANCE_UNKNOWN


def test_13_empty_plan_rejected():
    real = (REPO / CONFIG_REL).read_bytes()

    def no_instances(rel):
        if rel == CONFIG_REL:
            import yaml
            c = yaml.safe_load(real)
            c["instance_plan"]["instances"] = []
            return yaml.safe_dump(c).encode()
        return prov.default_reader(rel)
    r = _provider(reader=no_instances).emit_evidence("sfork_00")
    assert r["ok"] is False


def test_14_missing_scene_rejected():
    def no_scene(rel):
        if rel == SCENE_REL:
            raise FileNotFoundError(rel)
        return prov.default_reader(rel)
    r = _provider(reader=no_scene).emit_evidence("sfork_00")
    assert r["ok"] is False and r["provider_code"] == prov.PROVIDER_ARTIFACT_MISSING


def test_15_missing_route_rejected():
    real = (REPO / CONFIG_REL).read_bytes()

    def no_offset(rel):
        if rel == CONFIG_REL:
            import yaml
            c = yaml.safe_load(real)
            for i in c["instance_plan"]["instances"]:
                i.pop("coord_offset", None)
            return yaml.safe_dump(c).encode()
        return prov.default_reader(rel)
    r = _provider(reader=no_offset).emit_evidence("sfork_00")
    assert r["ok"] is False and r["provider_code"] == prov.PROVIDER_ARTIFACT_MISSING


def test_16_dirty_tree_rejected():
    p = _provider(tree_state=lambda: {"commit": "x", "dependency_dirty": True})
    r = p.emit_evidence("sfork_00")
    assert r["ok"] is False and r["provider_code"] == prov.PROVIDER_DIRTY_TREE


# ── 17–19 fixture / production separation ───────────────────────────────────────────
def test_17_fixture_mode_permits_fixture_only():
    ok = prov.H8EvidenceProvider(mode="fixture", clock=_clock,
                                 sink=prov.InMemorySink("tests/fixture")).emit_evidence("sfork_00")
    assert ok["provider_code"] == prov.PROVIDER_OK_FIXTURE
    bad = prov.H8EvidenceProvider(mode="fixture", clock=_clock,
                                  sink=prov.InMemorySink("assets/evidence/h8/preflight")
                                  ).emit_evidence("sfork_00")
    assert bad["provider_code"] == prov.PROVIDER_FIXTURE_REJECTED


def test_18_production_rejects_fixture_sentinel():
    fx = es.synthetic_render_evidence()
    res = es.validate_envelope(fx, review_time=RT, production_mode=True)
    assert res["accepted"] is False and res["reason_code"] == es.FIXTURE_IN_PRODUCTION


def test_19_production_rejects_fixture_producer():
    fx = es.synthetic_drive_evidence()
    assert fx["producer"]["component"] == es.FIXTURE_PRODUCER
    res = es.validate_envelope(fx, review_time=RT, production_mode=True)
    assert res["reason_code"] == es.FIXTURE_IN_PRODUCTION


# ── 20–22 no runtime overclaim ──────────────────────────────────────────────────────
def test_20_preflight_cannot_emit_runtime_valid_render():
    r = _provider().emit_evidence("sfork_00", kind="render", want_runtime_valid=True)
    assert r["ok"] is False and r["provider_code"] == prov.PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING


def test_21_preflight_cannot_emit_runtime_valid_drive():
    r = _provider().emit_evidence("sfork_00", kind="drive", want_runtime_valid=True)
    assert r["ok"] is False and r["provider_code"] == prov.PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING


def test_22_production_without_observer_fails_closed():
    r = _provider(mode="production").emit_evidence("sfork_00")
    assert r["ok"] is False and r["provider_code"] == prov.PROVIDER_BLOCKED_RUNTIME_OBSERVER_MISSING


# ── 23–24 preflight evidence is explicitly non-runtime ──────────────────────────────
def test_23_render_preflight_indeterminate_nonruntime():
    env = _emit(kind="render")["evidence"]["render_valid"]
    assert env["status"] == "indeterminate"
    assert env["payload"]["runtime_observed"] is False
    assert set(env["payload"]["unobserved_runtime_checks"]) == set(prov._RENDER_UNOBSERVED)


def test_24_drive_preflight_indeterminate_nonruntime():
    env = _emit(kind="drive")["evidence"]["drive_valid"]
    assert env["status"] == "indeterminate"
    assert env["payload"]["degraded"] is True
    assert env["payload"]["runtime_observed"] is False


# ── 25–26 document vs capture-gate ──────────────────────────────────────────────────
def test_25_pairing_accepts_preflight_pair_as_documents():
    r = _emit(kind="both")["evidence"]
    res = es.validate_pair(r["render_valid"], r["drive_valid"], review_time=RT,
                           expected=_expected(r["render_valid"]), document_only=True)
    assert res["accepted"] is True


def test_26_pairing_does_not_authorise_capture():
    r = _emit(kind="both")["evidence"]
    res = es.validate_pair(r["render_valid"], r["drive_valid"], review_time=RT,
                           expected=_expected(r["render_valid"]), document_only=False)
    assert res["accepted"] is False and res["reason_code"] == es.STATUS_NOT_VALID
    # and the provider's explicit boundary helper agrees
    auth, info = prov.preflight_satisfies_capture_gate(r["render_valid"], review_time=RT,
                                                       expected=_expected(r["render_valid"]))
    assert auth is False and info["is_valid_document"] is True


# ── 27–31 integrity / version / replay ──────────────────────────────────────────────
def test_27_digest_mismatch_rejected():
    env = _emit(kind="render")["evidence"]["render_valid"]
    env["subject"]["scene_id"] = "tampered"
    assert es.validate_envelope(env, review_time=RT, document_only=True)["reason_code"] == \
        es.DIGEST_MISMATCH


def test_28_unsupported_schema_version_rejected():
    env = _emit(kind="render")["evidence"]["render_valid"]
    env["schema_version"] = "h8-evidence/0.0.1"
    assert es.validate_envelope(env, review_time=RT, document_only=True)["reason_code"] == \
        es.SCHEMA_VERSION_UNSUPPORTED


def test_29_duplicate_evidence_id_rejected():
    env = _emit(kind="render")["evidence"]["render_valid"]
    res = es.validate_envelope(env, review_time=RT, seen_ids={env["evidence_id"]}, document_only=True)
    assert res["reason_code"] == es.DUPLICATE_EVIDENCE_ID


def test_30_same_id_changed_content_conflict():
    sink = prov.InMemorySink()
    prov.H8EvidenceProvider(mode="preflight", clock=lambda: CLK, tree_state=_clean_tree,
                            sink=sink).emit_evidence("sfork_00", kind="render")
    # same instance/kind -> same evidence_id, but a different clock -> different content
    r2 = prov.H8EvidenceProvider(mode="preflight", clock=lambda: "2026-07-16T13:00:00Z",
                                 tree_state=_clean_tree, sink=sink).emit_evidence("sfork_00",
                                                                                  kind="render")
    assert r2["ok"] is False and r2["provider_code"] == prov.PROVIDER_OUTPUT_CONFLICT


def test_31_idempotent_regeneration_ok():
    sink = prov.InMemorySink()
    a = _provider(sink=sink).emit_evidence("sfork_00", kind="render")
    b = _provider(sink=sink).emit_evidence("sfork_00", kind="render")   # identical inputs
    assert a["ok"] and b["ok"] and b["provider_code"] == prov.PROVIDER_OK_PREFLIGHT


# ── 32–33 output discipline ─────────────────────────────────────────────────────────
def test_32_failed_validation_no_output():
    real = (REPO / CONFIG_REL).read_bytes()

    def bad_bound(rel):
        if rel == CONFIG_REL:
            import yaml
            c = yaml.safe_load(real)
            c["cl_bound_xy"] = 7.0
            return yaml.safe_dump(c).encode()
        return prov.default_reader(rel)
    sink = prov.InMemorySink()
    r = prov.H8EvidenceProvider(mode="preflight", clock=_clock, tree_state=_clean_tree, reader=bad_bound,
                                sink=sink).emit_evidence("sfork_00")
    assert r["ok"] is False and r["provider_code"] == prov.PROVIDER_BINDING_MISMATCH
    assert sink.store == {} and sink.atomic_ops == 0


def test_33_atomic_write_on_success():
    sink = prov.InMemorySink()
    r = _provider(sink=sink).emit_evidence("sfork_00", kind="both")
    assert r["ok"] and sink.atomic_ops == 2 and len(sink.store) == 2


# ── 34 provider reason-code stability ───────────────────────────────────────────────
def test_34_provider_reason_codes_stable():
    for r in (_emit(), _emit("sfork_99"), _provider(mode="production").emit_evidence("sfork_00")):
        assert r["provider_code"] in prov.PROVIDER_REASON_CODES
        assert r["provider_version"] == prov.PROVIDER_VERSION


# ── 35–38 no forbidden imports ──────────────────────────────────────────────────────
def test_35_38_no_forbidden_imports():
    src = (REPO / "scripts/gnm/h8_evidence_provider.py").read_text()
    for token in ("import omni", "from omni", "isaacsim", "SimulationApp", "rclpy", "import torch",
                  "import cv2", "sensor_msgs"):
        assert token not in src, f"forbidden token {token!r} in provider"
    for mod in ("omni", "isaacsim", "rclpy", "torch", "cv2"):
        assert mod not in sys.modules, f"{mod} unexpectedly imported"


# ── 39 no dataset / capture output ──────────────────────────────────────────────────
def test_39_no_dataset_or_capture_output():
    sink = prov.InMemorySink()
    _provider(sink=sink).emit_evidence("sfork_00", kind="both")
    assert not (REPO / "assets/experiments/"
                "hospital_h8_track_b_synthetic_fork_recorded_mode_dataset").exists()
    # InMemorySink means nothing was written to the real evidence namespace either
    assert not (REPO / "assets/evidence/h8/runtime").exists()


# ── 40–44 regression / preservation ─────────────────────────────────────────────────
def test_40_schema_conformance_valid_path_intact():
    fx = es.synthetic_render_evidence()
    assert es.validate_envelope(fx, review_time=RT, expected=_expected(fx))["accepted"] is True


def test_41_42_recorded_mode_and_dry_run_intact():
    cfg = rm.load_dataset_config(REPO / CONFIG_REL)
    res = rm.dataset_dry_run_checks(cfg)
    assert res["all_pass"] is True and res["n_total"] == 25 and res["n_pass"] == 25


def test_43_level1_hashes_unchanged():
    for name, prefix in _L1_HASHES.items():
        assert hashlib.sha256((DRYRUN_DIR / name).read_bytes()).hexdigest()[:16] == prefix


def test_44_pilot_path_unchanged():
    assert rm.select_capture_mode({"mode": "pilot_capture_config_only"}) == "pilot"
    for sym in ("validate_pilot_config", "pilot_capture_plan", "_run_pilot_capture"):
        assert hasattr(rm, sym)


# ── extra: schema document_only extension behaves ───────────────────────────────────
def test_extra_document_only_extension():
    # a valid envelope passes both document and gate checks
    fx = es.synthetic_render_evidence()
    assert es.validate_envelope(fx, review_time=RT, document_only=True)["accepted"] is True
    assert es.validate_envelope(fx, review_time=RT, document_only=False)["accepted"] is True
    # an indeterminate preflight envelope is a document but not a gate pass
    env = _emit(kind="render")["evidence"]["render_valid"]
    assert es.validate_envelope(env, review_time=RT, document_only=True)["accepted"] is True
    assert es.validate_envelope(env, review_time=RT, document_only=False)["accepted"] is False
    # revoked is rejected in BOTH modes
    rv = es.synthetic_render_evidence(**{"revocation.revoked": True})
    assert es.validate_envelope(rv, review_time=RT, document_only=True)["reason_code"] == \
        es.EVIDENCE_REVOKED
