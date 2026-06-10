#!/usr/bin/env bash
# Bootstrap the lightweight proof/review virtual environment.
# Usage:  bash scripts/gnm/bootstrap_demo_env.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="$REPO_ROOT/.venv"
REQS="$REPO_ROOT/requirements-demo.txt"

echo "=== GNM-VLNVerse Baseline: bootstrap demo environment ==="
echo "Repository : $REPO_ROOT"
echo "Virtual env: $VENV"
echo ""

# Create venv if absent
if [ ! -d "$VENV" ]; then
    echo "[1/4] Creating virtual environment ..."
    python3 -m venv "$VENV"
else
    echo "[1/4] Virtual environment already exists — skipping creation."
fi

# Upgrade pip
echo "[2/4] Upgrading pip ..."
"$VENV/bin/python" -m pip install --upgrade pip --quiet

# Install proof dependencies
echo "[3/4] Installing $REQS ..."
"$VENV/bin/pip" install -r "$REQS" --quiet

# Verify imports
echo "[4/4] Verifying imports ..."
"$VENV/bin/python" - <<'EOF'
import importlib, sys
failures = []
for mod in ("numpy", "PIL", "matplotlib", "yaml", "cv2", "pytest"):
    try:
        importlib.import_module(mod)
    except ImportError:
        failures.append(mod)
if failures:
    print(f"FAIL: missing modules: {', '.join(failures)}")
    sys.exit(1)
print("PASS: all required modules importable")
EOF

echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Activate the environment:"
echo "  source .venv/bin/activate"
echo ""
echo "Then link the VLNVerse dataset:"
echo "  bash scripts/gnm/link_vlntube_data.sh /path/to/vlntube"
echo ""
echo "Check readiness:"
echo "  python3 scripts/gnm/check_demo_ready.py"
echo ""
echo "Proof commands:"
echo "  python3 scripts/gnm/replay_gnm_demo.py --prove-dataset"
echo "  python3 scripts/gnm/replay_gnm_demo.py --list-scenes"
echo "  python3 scripts/gnm/replay_gnm_demo.py --export-live-dashboard"
echo "  python3 scripts/gnm/manual_testdrive.py --dry-run"
echo "  python3 -m pytest tests/gnm -q"
