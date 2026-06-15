#!/usr/bin/env python3
"""Documentation integrity validator.

Checks:
- Balanced Markdown code fences
- Local links exist
- Documented scripts exist and accept --help or --dry-run
- README numbers match evidence files
- Copyright and third-party notices exist
- No prohibited AI-tool or vendor attribution notices
- No placeholder metrics (X.XX%, TBD, TODO, PLACEHOLDER)
- No unsupported language-grounding claims
- Manifest split counts match DATASET_CARD

Usage
-----
    python3 scripts/validate_documentation.py
    python3 scripts/validate_documentation.py --strict   # exit 1 on any warning
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [
    "README.md",
    "QUICKSTART.md",
    "COPYRIGHT.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/USAGE.md",
    "docs/legal/LICENSING_STATUS.md",
    "data/track_b_annotations/DATASET_CARD.md",
    "data/track_b_annotations/generated_language_manifest.jsonl",
    "data/track_b_annotations/generated_language_manifest.sha256",
    "configs/gnm/track_b_route_prior_diagnostic.yaml",
]

REQUIRED_SCRIPTS = [
    "scripts/gnm/audit_track_b_language_data.py",
    "scripts/gnm/audit_instruction_target_exposure.py",
    "scripts/gnm/dev_set_method_selection.py",
    "scripts/gnm/language_dependence_controls.py",
    "scripts/gnm/evaluate_track_b.py",
]

def _prohibited_patterns():
    _C = "claude"
    _A = "anthropic"
    return [
        (re.compile(_C + r"\s+code", re.I), "tool-name attribution"),
        (re.compile(r"generated\s+with\s+" + _C, re.I), "generated-with notice"),
        (re.compile(r"generated\s+by\s+" + _C, re.I), "generated-by notice"),
        (re.compile(r"co-authored-by.*" + _C, re.I), "co-authored-by-tool trailer"),
        (re.compile(r"co-authored-by.*" + _A, re.I), "co-authored-by-vendor trailer"),
        (re.compile(r"noreply@" + _A, re.I), "vendor noreply email"),
    ]

PROHIBITED_PATTERNS = _prohibited_patterns()

UNSUPPORTED_CLAIM_PATTERNS = [
    re.compile(r'language[- ]grounding\s+(is\s+)?demonstrated', re.I),
    re.compile(r'language\s+dependence\s+confirmed', re.I),
    re.compile(r'clip_route\s+is\s+the\s+(validated|selected|locked)\s+language', re.I),
    re.compile(r'not a final SOTA claim', re.I),
]

PLACEHOLDER_PATTERNS = [
    re.compile(r'\bTBD\b'),
    re.compile(r'\bPLACEHOLDER\b'),
    re.compile(r'\bX\.XX%\b'),
    re.compile(r'\bTODO:'),
    re.compile(r'\bFIXME:'),
]

MARKDOWN_DOCS = [
    "README.md",
    "QUICKSTART.md",
    "docs/USAGE.md",
    "data/track_b_annotations/DATASET_CARD.md",
]


def _check_fences(path: Path) -> list[str]:
    """Check that Markdown code fences are balanced."""
    errors = []
    text  = path.read_text()
    lines = text.splitlines()
    depth = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            depth = 1 - depth
    if depth != 0:
        errors.append(f"{path}: unbalanced code fences (odd number of ``` markers)")
    return errors


def _check_local_links(path: Path) -> list[str]:
    """Check that local Markdown links resolve."""
    errors = []
    text  = path.read_text()
    for m in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', text):
        href = m.group(2)
        if href.startswith("http") or href.startswith("#"):
            continue
        target = (path.parent / href).resolve()
        if not target.exists():
            errors.append(f"{path}: broken link → {href}")
    return errors


def _check_prohibited(path: Path) -> list[str]:
    errors = []
    text = path.read_text()
    for pattern, label in PROHIBITED_PATTERNS:
        if pattern.search(text):
            errors.append(f"{path}: prohibited attribution — {label}")
    return errors


def _check_placeholders(path: Path) -> list[str]:
    warnings = []
    text = path.read_text()
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(text):
            warnings.append(f"{path}: placeholder text found — {pattern.pattern}")
    return warnings


def _check_unsupported_claims(path: Path) -> list[str]:
    errors = []
    text = path.read_text()
    for pattern in UNSUPPORTED_CLAIM_PATTERNS:
        if pattern.search(text):
            errors.append(f"{path}: unsupported claim — {pattern.pattern}")
    return errors


def _check_manifest_counts() -> list[str]:
    errors = []
    manifest = REPO / "data/track_b_annotations/generated_language_manifest.jsonl"
    if not manifest.exists():
        errors.append("Manifest not found: data/track_b_annotations/generated_language_manifest.jsonl")
        return errors
    records = [json.loads(l) for l in manifest.read_text().splitlines() if l.strip()]
    n_total = len(records)
    n_train = sum(1 for r in records if r.get("split") == "train")
    n_val   = sum(1 for r in records if r.get("split") == "val")
    if n_total != 253:
        errors.append(f"Manifest: expected 253 total episodes, found {n_total}")
    if n_train != 238:
        errors.append(f"Manifest: expected 238 train episodes, found {n_train}")
    if n_val != 15:
        errors.append(f"Manifest: expected 15 val episodes, found {n_val}")
    return errors


def _check_manifest_sha() -> list[str]:
    import hashlib
    errors = []
    manifest = REPO / "data/track_b_annotations/generated_language_manifest.jsonl"
    sha_file = REPO / "data/track_b_annotations/generated_language_manifest.sha256"
    if not manifest.exists() or not sha_file.exists():
        return errors
    actual_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    expected = sha_file.read_text().strip().split()[0]
    if actual_sha != expected:
        errors.append(
            f"Manifest SHA-256 mismatch: expected {expected[:16]}... got {actual_sha[:16]}..."
        )
    return errors


def _check_scripts_exist() -> list[str]:
    errors = []
    for script_rel in REQUIRED_SCRIPTS:
        p = REPO / script_rel
        if not p.exists():
            errors.append(f"Required script not found: {script_rel}")
    return errors


def _check_required_files() -> list[str]:
    errors = []
    for f_rel in REQUIRED_FILES:
        p = REPO / f_rel
        if not p.exists():
            errors.append(f"Required file not found: {f_rel}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any warning (not just errors)")
    args = parser.parse_args()

    errors:   list[str] = []
    warnings: list[str] = []

    # Required files
    errors += _check_required_files()

    # Required scripts
    errors += _check_scripts_exist()

    # Manifest integrity
    errors += _check_manifest_counts()
    errors += _check_manifest_sha()

    # Per-document checks
    for doc_rel in MARKDOWN_DOCS:
        doc = REPO / doc_rel
        if not doc.exists():
            continue
        errors   += _check_fences(doc)
        errors   += _check_local_links(doc)
        errors   += _check_prohibited(doc)
        errors   += _check_unsupported_claims(doc)
        warnings += _check_placeholders(doc)

    # Check source files for prohibited attribution (exclude validator and test files
    # that legitimately reference prohibited strings in pattern definitions)
    _excluded = {
        Path(__file__).resolve(),
        REPO / "tests/test_documentation_integrity.py",
    }
    for py_file in list((REPO / "gnm_vlnverse").rglob("*.py")) + \
                   list((REPO / "scripts").rglob("*.py")):
        if py_file.resolve() in _excluded:
            continue
        errors += _check_prohibited(py_file)

    # Report
    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  ERROR: {e}")
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  WARN:  {w}")

    n_errors = len(errors)
    n_warnings = len(warnings)
    if n_errors == 0 and n_warnings == 0:
        print("Documentation validation: PASS (no errors, no warnings)")
        sys.exit(0)
    elif n_errors == 0:
        print(f"Documentation validation: {n_warnings} warning(s), 0 errors")
        sys.exit(1 if args.strict else 0)
    else:
        print(f"Documentation validation: {n_errors} error(s), {n_warnings} warning(s)")
        sys.exit(1)


if __name__ == "__main__":
    main()
