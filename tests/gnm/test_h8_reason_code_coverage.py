"""H8-S1R — machine-checked reason-code taxonomy and coverage consistency."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GNM = ROOT / "scripts" / "gnm"
TESTS = ROOT / "tests" / "gnm"

sys.path.insert(0, str(GNM))

from h8_s1_reason_codes import (  # noqa: E402
    ACTIVE_REASON_CODES,
    ALL_CODES,
    INACTIVE_REASON_CODES,
    REASON_CODE_STATUS,
    REASON_CODE_STATUS_COUNTS,
    ReasonCodeStatus,
)

H8_LITERAL = re.compile(r"^H8_[A-Z0-9_]+$")


def _codes_used_inside_test_functions() -> dict[str, set[str]]:
    """Return active reason-code uses grouped by pytest function name.

    The coverage file itself is excluded so importing the taxonomy cannot
    satisfy its own coverage check.
    """
    uses: dict[str, set[str]] = {}

    for source in sorted(TESTS.glob("test_*.py")):
        if source.resolve() == Path(__file__).resolve():
            continue

        tree = ast.parse(
            source.read_text(encoding="utf-8"),
            filename=str(source),
        )

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue

            referenced: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id in ACTIVE_REASON_CODES:
                    referenced.add(child.id)
                elif (
                    isinstance(child, ast.Constant)
                    and isinstance(child.value, str)
                    and child.value in ACTIVE_REASON_CODES
                ):
                    referenced.add(child.value)

            for code in referenced:
                uses.setdefault(code, set()).add(
                    f"{source.relative_to(ROOT)}::{node.name}"
                )

    return uses


S1_REASON_CODE_SOURCES = (
    GNM / "h8_episode_validator.py",
    GNM / "h8_time_alignment.py",
    GNM / "build_h8_dataset_root.py",
)


def _implementation_h8_literals() -> dict[str, set[str]]:
    """Return literal H8_* reason-code strings from S1 reason-emitting modules.

    The repository also contains unrelated H8-prefixed environment variables
    and handoff identifiers in older Track-B scripts. Those are not validation
    reason codes and therefore do not belong to this taxonomy.
    """
    literals: dict[str, set[str]] = {}

    for source in S1_REASON_CODE_SOURCES:
        assert source.is_file(), f"missing S1 reason-code source: {source}"

        tree = ast.parse(
            source.read_text(encoding="utf-8"),
            filename=str(source),
        )

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and H8_LITERAL.fullmatch(node.value)
            ):
                literals.setdefault(node.value, set()).add(
                    f"{source.relative_to(ROOT)}:{node.lineno}"
                )

    return literals


def test_every_declared_code_has_exactly_one_status():
    assert len(ALL_CODES) == len(set(ALL_CODES)) == 56
    assert set(REASON_CODE_STATUS) == set(ALL_CODES)


def test_reason_code_status_counts_are_locked():
    assert REASON_CODE_STATUS_COUNTS == {
        ReasonCodeStatus.ACTIVE_REACHABLE: 54,
        ReasonCodeStatus.RESERVED_NOT_ACTIVE: 0,
        ReasonCodeStatus.DEPRECATED_UNUSED: 1,
        ReasonCodeStatus.DEFERRED_TO_LATER_IMPLEMENTATION: 1,
    }
    assert len(ACTIVE_REASON_CODES) == 54
    assert len(INACTIVE_REASON_CODES) == 2


def test_every_active_reason_code_is_used_by_a_deterministic_test():
    uses = _codes_used_inside_test_functions()
    missing = sorted(ACTIVE_REASON_CODES - set(uses))

    assert not missing, (
        "ACTIVE_REACHABLE reason code(s) have no permanent pytest use: "
        + ", ".join(missing)
    )


def test_inactive_codes_are_not_counted_as_active():
    assert INACTIVE_REASON_CODES == {
        "H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR",
        "H8_METRIC_INPUT_UNAVAILABLE",
    }

    assert (
        REASON_CODE_STATUS["H8_CONTACT_TELEMETRY_ZERO_WITHOUT_DETECTOR"]
        is ReasonCodeStatus.DEFERRED_TO_LATER_IMPLEMENTATION
    )
    assert (
        REASON_CODE_STATUS["H8_METRIC_INPUT_UNAVAILABLE"]
        is ReasonCodeStatus.DEPRECATED_UNUSED
    )


def test_implementation_contains_no_undeclared_h8_literal():
    literals = _implementation_h8_literals()
    undeclared = {
        code: locations
        for code, locations in literals.items()
        if code not in ALL_CODES
    }

    assert not undeclared, f"undeclared H8 reason-code literal(s): {undeclared}"
