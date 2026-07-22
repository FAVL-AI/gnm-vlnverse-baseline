"""tests/gnm/h8_import_isolation.py

H8-S1R — ORDER-INDEPENDENT FORBIDDEN-IMPORT TESTING (closes H8-S1REV-F-004).

The H8 gates promise that specific modules never pull in an Isaac, Omniverse, ROS or model runtime.
Two complementary controls enforce that promise:

  Control A - STATIC SOURCE SCAN (primary, unchanged in strength)
      Scan the module's own source text for literal prohibited tokens. Order-independent, cheap,
      and catches the overwhelmingly common case. This control is not weakened here.

  Control B - RUNTIME BACKSTOP (repaired here)
      Catch a *dynamic* import that the source scan cannot see (`__import__`, `importlib`, a lazy
      import inside a function). The previous implementation asserted that forbidden modules were
      simply absent from `sys.modules`. That is process-global, so it failed whenever pytest
      *collection* imported unrelated suites - `test_gnm_model.py`, `test_baseline_contract.py` and
      `test_visualnav_adapters.py` pull in `torch`; `test_fleetsafe_perception_node.py` pulls in
      `rclpy` - all before the first test executes. The independent review classified that as a
      pre-existing test-isolation defect.

      The repair narrows the question from "is this module loaded anywhere in the interpreter?" to
      "did *this target module* introduce it?". Each target is imported in a FRESH SUBPROCESS which
      snapshots `sys.modules`, imports only the target, and reports the difference. Unrelated
      imports in the parent pytest session cannot reach the child, so the result is deterministic
      regardless of collection or execution order.

The forbidden set is NOT weakened, and the backstop is NOT removed - it is made answerable.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Runtime modules an H8 validation/evidence module must never pull in, directly or transitively.
FORBIDDEN_RUNTIME_MODULES: tuple[str, ...] = (
    "omni", "isaacsim", "isaacsim.core", "pxr", "carb",       # Isaac / Omniverse
    "rclpy", "rosbag2_py", "sensor_msgs", "geometry_msgs", "nav_msgs",  # ROS 2 runtime
    "torch", "torchvision", "tensorflow", "jax",              # model runtimes
    "cv2",                                                    # capture / vision runtime
)

#: Literal tokens the static scan rejects in module source.
FORBIDDEN_SOURCE_TOKENS: tuple[str, ...] = (
    "import omni", "from omni", "isaacsim", "SimulationApp",
    "import rclpy", "from rclpy", "import torch", "from torch",
    "import cv2", "from cv2", "sensor_msgs",
)

_CHILD = r"""
import json, sys
before = set(sys.modules)
sys.path.insert(0, {syspath!r})
status, error = "OK", None
try:
    import importlib
    importlib.import_module({module!r})
except BaseException as exc:
    status, error = "IMPORT_FAILED", "%s: %s" % (type(exc).__name__, exc)
after = set(sys.modules)
introduced = sorted({{m.split(".")[0] for m in (after - before)}})
print("H8_ISOLATION_RESULT " + json.dumps(
    {{"status": status, "error": error, "introduced": introduced,
      "n_before": len(before), "n_after": len(after)}}))
"""


def modules_introduced_by(module_name: str, syspath: str | Path, timeout: float = 120.0) -> dict:
    """Import `module_name` in a fresh subprocess and report the modules it introduced.

    Returns ``{"status", "error", "introduced", "n_before", "n_after"}``. The parent interpreter's
    already-loaded modules are irrelevant to the result by construction.
    """
    code = _CHILD.format(syspath=str(syspath), module=module_name)
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],   # -I: isolated, ignores env and user site
        capture_output=True, text=True, timeout=timeout, cwd=str(REPO),
    )
    for line in proc.stdout.splitlines():
        if line.startswith("H8_ISOLATION_RESULT "):
            return json.loads(line[len("H8_ISOLATION_RESULT "):])
    return {"status": "NO_RESULT", "error": (proc.stderr or proc.stdout)[-400:],
            "introduced": [], "n_before": 0, "n_after": 0}


def forbidden_modules_introduced_by(
    module_name: str, syspath: str | Path, forbidden: tuple[str, ...] = FORBIDDEN_RUNTIME_MODULES
) -> list[str]:
    """Forbidden modules that `module_name` itself introduces. Empty list means clean."""
    res = modules_introduced_by(module_name, syspath)
    if res["status"] != "OK":
        raise AssertionError(
            f"target module {module_name!r} could not be imported in isolation: {res['error']}"
        )
    roots = {f.split(".")[0] for f in forbidden}
    return sorted(set(res["introduced"]) & roots)


def forbidden_tokens_in_source(
    path: str | Path, tokens: tuple[str, ...] = FORBIDDEN_SOURCE_TOKENS
) -> list[str]:
    """Literal forbidden tokens present in a module's source. Empty list means clean."""
    src = Path(path).read_text()
    return [t for t in tokens if t in src]


def assert_module_runtime_clean(module_name: str, source_path: str | Path,
                                syspath: str | Path) -> dict:
    """Apply both controls to one module. Raises AssertionError on either failure."""
    tokens = forbidden_tokens_in_source(source_path)
    assert not tokens, f"static scan: forbidden token(s) {tokens} in {source_path}"
    introduced = forbidden_modules_introduced_by(module_name, syspath)
    assert not introduced, (
        f"runtime backstop: {module_name!r} itself introduced forbidden module(s) {introduced}"
    )
    return {"module": module_name, "static_scan": "CLEAN", "runtime_backstop": "CLEAN"}
