"""H8-S1R — order-independent forbidden-import testing (closes H8-S1REV-F-004).

Proves both controls behave correctly and that neither depends on what unrelated tests imported
earlier in the pytest session.
"""
from __future__ import annotations

import contextlib
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from h8_import_isolation import (  # noqa: E402
    FORBIDDEN_RUNTIME_MODULES,
    FORBIDDEN_SOURCE_TOKENS,
    REPO,
    assert_module_runtime_clean,
    forbidden_modules_introduced_by,
    forbidden_tokens_in_source,
    modules_introduced_by,
)

GNM = REPO / "scripts" / "gnm"

#: Targets that must stay free of Isaac / Omniverse / ROS / model runtimes.
CLEAN_TARGETS = [
    ("scripts.gnm.h8_evidence_provider", REPO, GNM / "h8_evidence_provider.py"),
    ("scripts.gnm.h8_evidence_schema", REPO, GNM / "h8_evidence_schema.py"),
    ("h8_s1_reason_codes", GNM, GNM / "h8_s1_reason_codes.py"),
    ("h8_time_alignment", GNM, GNM / "h8_time_alignment.py"),
    ("h8_episode_validator", GNM, GNM / "h8_episode_validator.py"),
    ("build_h8_dataset_root", GNM, GNM / "build_h8_dataset_root.py"),
]


# --- 1. clean targets pass both controls ------------------------------------------------------
@pytest.mark.parametrize("mod,syspath,src", CLEAN_TARGETS, ids=[t[0] for t in CLEAN_TARGETS])
def test_01_clean_target_passes_both_controls(mod, syspath, src):
    out = assert_module_runtime_clean(mod, src, syspath)
    assert out["static_scan"] == "CLEAN"
    assert out["runtime_backstop"] == "CLEAN"


# --- 2/3. synthetic violations are caught ------------------------------------------------------
def test_02_synthetic_literal_forbidden_import_fails_static_scan(tmp_path):
    p = tmp_path / "evil_literal.py"
    p.write_text("import torch\nVALUE = 1\n")
    assert "import torch" in forbidden_tokens_in_source(p)


def test_03_synthetic_dynamic_forbidden_import_fails_runtime_backstop(tmp_path):
    """A dynamic import is invisible to the source scan - the backstop must catch it."""
    p = tmp_path / "evil_dynamic.py"
    p.write_text('M = __import__("tor" + "ch")\n')
    assert forbidden_tokens_in_source(p) == [], "dynamic import evades the static scan by design"
    assert "torch" in forbidden_modules_introduced_by("evil_dynamic", tmp_path)


# --- 4/5. preloaded unrelated modules must not fail a clean target -----------------------------
@contextlib.contextmanager
def _temporarily_preloaded(*names: str):
    """Inject stub modules for the duration of one test, then remove them.

    These tests must simulate a polluted session WITHOUT becoming a source of pollution
    themselves - leaking a stub would break sibling suites that still assert absolute absence
    (e.g. test_h8_synthetic_fork_recorded_mode.py::test_L_...), which is the very defect
    H8-S1REV-F-004 is about.
    """
    injected = [n for n in names if n not in sys.modules]
    for n in injected:
        sys.modules[n] = types.ModuleType(n)
    try:
        yield
    finally:
        for n in injected:
            sys.modules.pop(n, None)


def test_04_preloaded_torch_does_not_fail_a_clean_target():
    """The exact condition that broke the old backstop: torch present in the parent session."""
    with _temporarily_preloaded("torch"):
        assert "torch" in sys.modules
        assert forbidden_modules_introduced_by("h8_time_alignment", GNM) == []


def test_05_preloaded_rclpy_does_not_fail_a_clean_target():
    with _temporarily_preloaded("rclpy"):
        assert "rclpy" in sys.modules
        assert forbidden_modules_introduced_by("scripts.gnm.h8_evidence_schema", REPO) == []


# --- 6/7. a target that really does import them must fail --------------------------------------
def test_06_target_dynamically_importing_torch_fails(tmp_path):
    p = tmp_path / "t_torch.py"
    p.write_text('import importlib\nM = importlib.import_module("torch")\n')
    assert forbidden_modules_introduced_by("t_torch", tmp_path) == ["torch"]


def test_07_target_dynamically_importing_ros_fails(tmp_path):
    """ROS 2 runtime is not installed in the test interpreter, so a stub stands in for it.

    The point under test is the detection mechanism, not the presence of ROS: a target that
    dynamically resolves a forbidden module name must be reported whatever that module contains.
    """
    (tmp_path / "rclpy.py").write_text("VERSION = 'stub'\n")
    p = tmp_path / "t_ros.py"
    p.write_text('import importlib\nM = importlib.import_module("rclpy")\n')
    introduced = forbidden_modules_introduced_by("t_ros", tmp_path)
    assert "rclpy" in introduced


# --- 8/9. determinism -------------------------------------------------------------------------
def test_08_result_is_independent_of_parent_module_state():
    before = forbidden_modules_introduced_by("h8_episode_validator", GNM)
    with _temporarily_preloaded("torch", "rclpy", "cv2", "omni"):
        after = forbidden_modules_introduced_by("h8_episode_validator", GNM)
    assert before == after == []


def test_08b_this_suite_leaves_no_stub_behind():
    """Guards against this suite becoming the next source of session pollution."""
    with _temporarily_preloaded("torch", "rclpy", "cv2", "omni"):
        pass
    leaked = [n for n in ("cv2", "omni", "isaacsim")
              if isinstance(sys.modules.get(n), types.ModuleType)
              and getattr(sys.modules.get(n), "__file__", None) is None]
    assert not leaked, f"stub module(s) leaked into the session: {leaked}"


def test_09_repeated_runs_are_deterministic():
    runs = [tuple(modules_introduced_by("h8_time_alignment", GNM)["introduced"]) for _ in range(3)]
    assert len(set(runs)) == 1, f"non-deterministic module set across runs: {runs}"


# --- 10. contracts ----------------------------------------------------------------------------
def test_10_forbidden_set_is_not_weakened():
    """Every module the previous backstop guarded must still be guarded."""
    for legacy in ("omni", "isaacsim", "rclpy", "torch", "cv2"):
        assert legacy in FORBIDDEN_RUNTIME_MODULES
    for legacy_token in ("import omni", "from omni", "isaacsim", "SimulationApp", "import torch",
                         "import cv2", "sensor_msgs"):
        assert legacy_token in FORBIDDEN_SOURCE_TOKENS


def test_11_unimportable_target_raises_rather_than_passing_silently(tmp_path):
    p = tmp_path / "broken.py"
    p.write_text("raise RuntimeError('boom')\n")
    with pytest.raises(AssertionError, match="could not be imported in isolation"):
        forbidden_modules_introduced_by("broken", tmp_path)


def test_12_subprocess_reports_a_real_module_delta():
    res = modules_introduced_by("h8_episode_validator", GNM)
    assert res["status"] == "OK"
    assert res["n_after"] > res["n_before"]
    assert "h8_episode_validator" in res["introduced"]


def test_preload_helper_preserves_existing_module():
    """The helper must not replace or remove a genuine pre-existing module."""
    existing = types.ModuleType("torch")
    previous = sys.modules.get("torch")
    sys.modules["torch"] = existing

    try:
        with _temporarily_preloaded("torch"):
            assert sys.modules["torch"] is existing

        assert sys.modules["torch"] is existing
    finally:
        if previous is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = previous


def test_preload_helper_removes_only_injected_module():
    """A synthetic module inserted by the helper must be removed afterwards."""
    previous = sys.modules.pop("rclpy", None)

    try:
        with _temporarily_preloaded("rclpy"):
            assert "rclpy" in sys.modules

        assert "rclpy" not in sys.modules
    finally:
        if previous is not None:
            sys.modules["rclpy"] = previous
