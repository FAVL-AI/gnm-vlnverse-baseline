"""
Pre-flight readiness check for the GNM/VLNVerse proof pipeline.

Run from the repository root:
    python3 scripts/gnm/check_demo_ready.py

Prints a PASS/FAIL table and exits 1 if any required check fails.
PyTorch is optional; its absence is reported but does not affect the result.
"""

import importlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _check(label: str, ok: bool, detail: str = "") -> tuple[bool, str, str, str]:
    status = "PASS" if ok else "FAIL"
    return ok, label, status, detail


checks = []
notes = []  # informational lines printed after the table

# Required Python imports (proof pipeline)
for mod in ("numpy", "PIL", "matplotlib", "yaml", "cv2"):
    try:
        importlib.import_module(mod)
        checks.append(_check(f"import {mod}", True))
    except ImportError:
        checks.append(_check(f"import {mod}", False, "not installed"))

# Dataset symlinks
for split in ("train", "val"):
    p = REPO / "datasets" / "vlntube" / split
    checks.append(_check(
        f"datasets/vlntube/{split}",
        p.exists(),
        "" if p.exists() else "symlink missing or broken",
    ))

# Key scripts
for script in (
    "scripts/gnm/replay_gnm_demo.py",
    "scripts/gnm/manual_testdrive.py",
    "scripts/gnm/replay_manual_testdrive.py",
    "scripts/gnm/convert_manual_testdrive_to_gnm.py",
):
    p = REPO / script
    checks.append(_check(script, p.exists(), "" if p.exists() else "file missing"))

# Review documents
for doc in (
    "results/bo_reviewer_packet/03_success_rate_breakdown.md",
    "results/bo_reviewer_packet/BO_RUI_FULL_IMPLEMENTATION_PROOF.md",
    "results/bo_reviewer_packet/DEMO_SCRIPT_BO_RUI.md",
):
    p = REPO / doc
    checks.append(_check(doc, p.exists(), "" if p.exists() else "file missing"))

# No generated dashboard files tracked by Git
try:
    result = subprocess.run(
        ["git", "ls-files", "results/bo_reviewer_packet/live_dashboard/"],
        capture_output=True, text=True, cwd=REPO,
    )
    tracked_dashboard = result.stdout.strip()
    checks.append(_check(
        "no dashboard PNGs tracked by Git",
        tracked_dashboard == "",
        tracked_dashboard if tracked_dashboard else "",
    ))
except Exception as exc:
    checks.append(_check("no dashboard PNGs tracked by Git", False, str(exc)))

# Optional: torch (informational only — does not affect overall result)
try:
    importlib.import_module("torch")
    notes.append("torch optional: installed; training and model tests will run")
except ImportError:
    notes.append(
        "torch optional: not installed; "
        "training tests will be skipped (install requirements-ml.txt for ML work)"
    )

# Print table
col_label = max(len(c[1]) for c in checks) + 2
header = f"{'Check':<{col_label}}  {'Status':<6}  {'Detail'}"
print(header)
print("-" * len(header))
for ok, label, status, detail in checks:
    print(f"{label:<{col_label}}  {status:<6}  {detail}")

print()
for note in notes:
    print(note)

all_pass = all(c[0] for c in checks)
print()
if all_pass:
    print("Overall: PASS — ready to run the proof pipeline.")
else:
    n_fail = sum(1 for c in checks if not c[0])
    print(f"Overall: FAIL — {n_fail} check(s) did not pass.")
    sys.exit(1)
