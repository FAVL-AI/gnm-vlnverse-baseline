"""tests/gnm/test_hospital_resolution_gate.py

H8 fail-closed camera-resolution conformity for the hospital scene-identity gate.

Proves that `verify_hospital_scene(..., enforce_resolution=True)` REJECTS a capture
whose observed recorded resolution differs from the declared target (the H7/H7R
condition: 640x480 recorded vs 1280x720 declared), records BOTH values, and that with
the default `enforce_resolution=False` the historical H7/H7R verdict is unchanged
(the resolution check stays purely declarative — no new failing check appears).

No Isaac/ROS/capture: a minimal fake USD stage isolates the resolution check by making
every other scene-identity check pass. This test does NOT establish scene realism,
dataset admission, training readiness, or any physical-hospital fact.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "gnm" / "hospital_scene_identity_gate.py"
_spec = importlib.util.spec_from_file_location("hospital_scene_identity_gate", _MOD_PATH)
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

DECLARED = [1280, 720]   # what the manifests expected
OBSERVED = [640, 480]    # what the H7/H7R stream actually recorded


# ── minimal fake USD stage: every non-resolution check passes ────────────────────────
class _Ref:
    def __init__(self, asset):
        self.assetPath = asset


class _RefList:
    def __init__(self, items):
        self.prependedItems = items
        self.explicitItems = []
        self.addedItems = []


class _Spec:
    def __init__(self, ref_list):
        self.referenceList = ref_list


class _Prim:
    def __init__(self, path, valid=True, stack=None):
        self._path = path
        self._name = path.rsplit("/", 1)[-1]
        self._valid = valid
        self._stack = stack or []

    def IsValid(self):
        return self._valid

    def GetPath(self):
        return self._path

    def GetName(self):
        return self._name

    def GetPrimStack(self):
        return self._stack


class _Stage:
    """Hospital reference authored, >=MIN prims, no forbidden landmarks, camera present."""

    def __init__(self, cam_path):
        root_stack = [_Spec(_RefList([_Ref(G.HOSPITAL_USD)]))]
        self._root = _Prim(G.HOSPITAL_ROOT, valid=True, stack=root_stack)
        # enough clean child prims to clear the prim-count threshold
        self._children = [
            _Prim(f"{G.HOSPITAL_ROOT}/mesh_{i}") for i in range(G.MIN_HOSPITAL_PRIMS + 50)
        ]
        self._cam = _Prim(cam_path, valid=True)
        self._by_path = {G.HOSPITAL_ROOT: self._root, cam_path: self._cam}

    def GetPrimAtPath(self, path):
        return self._by_path.get(path, _Prim(path, valid=False))

    def Traverse(self):
        return [self._root] + self._children


CAM = "/World/M3Pro/camera_link/rgb_camera"


def _run(resolution, *, enforce, declared=DECLARED):
    return G.verify_hospital_scene(
        _Stage(CAM), scene_mode="hospital", front_cam_path=CAM,
        resolution=resolution, declared_resolution=declared,
        enforce_resolution=enforce,
    )


def test_fake_stage_baseline_all_other_checks_pass():
    """Sanity: with a matching resolution and enforcement ON, the gate PASSES —
    confirms the fake stage isolates the resolution check (nothing else fails)."""
    r = _run(DECLARED, enforce=True)
    assert r["pass"] is True, r["reasons"]
    assert r["checks"]["resolution_matches_declared"] is True


def test_enforced_mismatch_is_rejected_and_records_both():
    """NEGATIVE: 640x480 observed vs 1280x720 declared, enforcement ON -> fail closed."""
    r = _run(OBSERVED, enforce=True)
    assert r["pass"] is False
    assert r["checks"]["resolution_matches_declared"] is False
    assert r["observed"]["declared_resolution"] == DECLARED
    assert r["observed"]["observed_resolution"] == OBSERVED
    assert any("!= declared" in reason for reason in r["reasons"])


def test_default_is_declarative_h7_verdict_unchanged():
    """Backward-compat: default (enforce OFF) does NOT add the strict check, so the
    historical H7/H7R 640x480 capture still passes exactly as recorded."""
    r = _run(OBSERVED, enforce=False)
    assert r["pass"] is True, r["reasons"]
    assert "resolution_matches_declared" not in r["checks"]
    assert r["checks"]["resolution_declared"] is True
    assert "declared_resolution" not in r["observed"]


def test_declared_defaults_to_expected_resolution_constant():
    """When declared_resolution is omitted under enforcement, the module's
    EXPECTED_RESOLUTION is the target; a non-matching observed size is rejected."""
    r = G.verify_hospital_scene(
        _Stage(CAM), scene_mode="hospital", front_cam_path=CAM,
        resolution=OBSERVED, enforce_resolution=True,
    )
    assert r["checks"]["resolution_matches_declared"] is False
    assert r["observed"]["declared_resolution"] == G.EXPECTED_RESOLUTION
