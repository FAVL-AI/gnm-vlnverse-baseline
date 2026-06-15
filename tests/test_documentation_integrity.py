"""Documentation integrity tests.

Validates that committed documentation is internally consistent, link-correct,
and free of prohibited content.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "data/track_b_annotations/generated_language_manifest.jsonl"
SHA_FILE = REPO / "data/track_b_annotations/generated_language_manifest.sha256"

MARKDOWN_DOCS = [
    REPO / "README.md",
    REPO / "QUICKSTART.md",
    REPO / "docs/USAGE.md",
    REPO / "data/track_b_annotations/DATASET_CARD.md",
]

REQUIRED_FILES = [
    REPO / "README.md",
    REPO / "QUICKSTART.md",
    REPO / "COPYRIGHT.md",
    REPO / "THIRD_PARTY_NOTICES.md",
    REPO / "docs/USAGE.md",
    REPO / "docs/legal/LICENSING_STATUS.md",
    REPO / "data/track_b_annotations/DATASET_CARD.md",
    REPO / "data/track_b_annotations/generated_language_manifest.jsonl",
    REPO / "data/track_b_annotations/generated_language_manifest.sha256",
    REPO / "configs/gnm/track_b_route_prior_diagnostic.yaml",
]

REQUIRED_SCRIPTS = [
    REPO / "scripts/gnm/audit_track_b_language_data.py",
    REPO / "scripts/gnm/audit_instruction_target_exposure.py",
    REPO / "scripts/gnm/dev_set_method_selection.py",
    REPO / "scripts/gnm/language_dependence_controls.py",
    REPO / "scripts/gnm/evaluate_track_b.py",
]

# Patterns whose presence in committed files is prohibited.
# Built dynamically to avoid literal matches in the source file itself.
def _build_prohibited_patterns():
    _C = "cla" + "ude"
    _A = "ant" + "hropic"
    return [
        (re.compile(_C + r"\s+code", re.I), "tool-name attribution"),
        (re.compile(r"generated\s+with\s+" + _C, re.I), "generated-with notice"),
        (re.compile(r"generated\s+by\s+" + _C, re.I), "generated-by notice"),
        (re.compile(r"noreply@" + _A, re.I), "vendor noreply email"),
    ]

_PROHIBITED_PAIRS = _build_prohibited_patterns()
_PROHIBITED_RE    = [p for p, _ in _PROHIBITED_PAIRS]
_PROHIBITED       = [label for _, label in _PROHIBITED_PAIRS]

# Co-authored-by lines that name a bot/tool
_COAUTHOR_BOT_RE = re.compile(
    r'co-authored-by.*?(' + ("cla" + "ude") + '|' + ("ant" + "hropic") + r'|bot)', re.I
)

# Patterns indicating unsupported language-grounding claims
_UNSUPPORTED_CLAIMS = [
    re.compile(r'language[- ]grounding\s+(is\s+)?demonstrated', re.I),
    re.compile(r'clip_route\s+is\s+the\s+(validated|selected|locked)\s+language', re.I),
]


# ── Required files ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", REQUIRED_FILES, ids=[p.name for p in REQUIRED_FILES])
def test_required_file_exists(path: Path) -> None:
    assert path.exists(), f"Required file missing: {path.relative_to(REPO)}"


@pytest.mark.parametrize("path", REQUIRED_SCRIPTS, ids=[p.name for p in REQUIRED_SCRIPTS])
def test_required_script_exists(path: Path) -> None:
    assert path.exists(), f"Required script missing: {path.relative_to(REPO)}"


# ── Manifest integrity ────────────────────────────────────────────────────────

def test_manifest_total_count() -> None:
    records = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    assert len(records) == 253, f"Expected 253 episodes, got {len(records)}"


def test_manifest_train_count() -> None:
    records = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    n_train = sum(1 for r in records if r.get("split") == "train")
    assert n_train == 238, f"Expected 238 train episodes, got {n_train}"


def test_manifest_val_count() -> None:
    records = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    n_val = sum(1 for r in records if r.get("split") == "val")
    assert n_val == 15, f"Expected 15 val episodes, got {n_val}"


def test_manifest_sha256_matches() -> None:
    actual = hashlib.sha256(MANIFEST.read_bytes()).hexdigest()
    expected = SHA_FILE.read_text().strip().split()[0]
    assert actual == expected, (
        f"Manifest SHA-256 mismatch: expected {expected[:16]}..., got {actual[:16]}..."
    )


def test_manifest_instruction_text_not_empty() -> None:
    records = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    empty = [r["episode_id"] for r in records if not r.get("instruction_text", "").strip()]
    assert not empty, f"Episodes with empty instruction_text: {empty[:5]}"


def test_manifest_instruction_sha256_consistent() -> None:
    records = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    mismatches = []
    for r in records:
        text = r.get("instruction_text", "")
        sha  = r.get("instruction_sha256", "")
        if sha and hashlib.sha256(text.encode()).hexdigest() != sha:
            mismatches.append(r["episode_id"])
    assert not mismatches, f"Instruction SHA-256 mismatches in: {mismatches[:5]}"


def test_manifest_gate_b_decision() -> None:
    records = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    wrong = [
        r["episode_id"] for r in records
        if r.get("gate_b_decision") != "READY_FOR_GENERATED_LANGUAGE_BENCHMARK_EVALUATION"
    ]
    assert not wrong, f"Episodes with wrong gate_b_decision: {wrong[:5]}"


def test_manifest_no_train_val_episode_overlap() -> None:
    records = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    train_ids = {r["episode_id"] for r in records if r.get("split") == "train"}
    val_ids   = {r["episode_id"] for r in records if r.get("split") == "val"}
    overlap   = train_ids & val_ids
    assert not overlap, f"Train/val episode overlap: {overlap}"


# ── Markdown fences ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc", MARKDOWN_DOCS, ids=[p.name for p in MARKDOWN_DOCS])
def test_markdown_fences_balanced(doc: Path) -> None:
    if not doc.exists():
        pytest.skip(f"{doc.name} not found")
    lines  = doc.read_text().splitlines()
    depth  = 0
    for line in lines:
        if line.strip().startswith("```"):
            depth = 1 - depth
    assert depth == 0, f"{doc.name}: unbalanced code fences"


# ── Local links ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc", MARKDOWN_DOCS, ids=[p.name for p in MARKDOWN_DOCS])
def test_markdown_local_links_exist(doc: Path) -> None:
    if not doc.exists():
        pytest.skip(f"{doc.name} not found")
    text    = doc.read_text()
    broken  = []
    for m in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', text):
        href = m.group(2)
        if href.startswith("http") or href.startswith("#"):
            continue
        target = (doc.parent / href).resolve()
        if not target.exists():
            broken.append(href)
    assert not broken, f"{doc.name}: broken local links: {broken}"


# ── Prohibited attribution ────────────────────────────────────────────────────

def _source_files_to_check() -> list[Path]:
    files = list((REPO / "gnm_vlnverse").rglob("*.py"))
    files += [p for p in (REPO / "scripts").rglob("*.py")
              if p.name != "validate_documentation.py"]
    return files


@pytest.mark.parametrize("path", _source_files_to_check(),
                          ids=[p.name for p in _source_files_to_check()])
def test_no_prohibited_attribution_in_source(path: Path) -> None:
    if path.name == "test_documentation_integrity.py":
        pytest.skip("self-referential")
    text = path.read_text()
    hits = [label for pat, label in zip(_PROHIBITED_RE, _PROHIBITED) if pat.search(text)]
    hits += ["co-authored-by bot"] if _COAUTHOR_BOT_RE.search(text) else []
    assert not hits, f"{path.name}: prohibited attribution: {hits}"


@pytest.mark.parametrize("doc", MARKDOWN_DOCS, ids=[p.name for p in MARKDOWN_DOCS])
def test_no_prohibited_attribution_in_docs(doc: Path) -> None:
    if not doc.exists():
        pytest.skip(f"{doc.name} not found")
    text = doc.read_text()
    hits = [label for pat, label in zip(_PROHIBITED_RE, _PROHIBITED) if pat.search(text)]
    hits += ["co-authored-by bot"] if _COAUTHOR_BOT_RE.search(text) else []
    assert not hits, f"{doc.name}: prohibited attribution: {hits}"


# ── Unsupported claims ────────────────────────────────────────────────────────

@pytest.mark.parametrize("doc", MARKDOWN_DOCS, ids=[p.name for p in MARKDOWN_DOCS])
def test_no_unsupported_language_grounding_claim(doc: Path) -> None:
    if not doc.exists():
        pytest.skip(f"{doc.name} not found")
    text = doc.read_text()
    for pattern in _UNSUPPORTED_CLAIMS:
        assert not pattern.search(text), (
            f"{doc.name}: unsupported claim matched by {pattern.pattern!r}"
        )


# ── Copyright notices ─────────────────────────────────────────────────────────

def test_copyright_md_exists_and_names_author() -> None:
    cr = REPO / "COPYRIGHT.md"
    assert cr.exists()
    text = cr.read_text()
    assert "Frank Asante Van Laarhoven" in text
    assert "All rights reserved" in text


def test_third_party_notices_exists() -> None:
    assert (REPO / "THIRD_PARTY_NOTICES.md").exists()


def test_licensing_status_exists() -> None:
    assert (REPO / "docs/legal/LICENSING_STATUS.md").exists()


def test_pyproject_not_mit() -> None:
    pyproject = REPO / "pyproject.toml"
    assert pyproject.exists()
    text = pyproject.read_text()
    # MIT should not be declared as the licence text
    assert 'license = { text = "MIT" }' not in text, (
        "pyproject.toml still declares MIT licence; no formal licence has been selected"
    )
