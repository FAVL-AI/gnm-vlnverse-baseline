#!/usr/bin/env bash
# FleetSafe-VLNVerse+ one-command demo
# Runs all setup steps, starts the command center, and opens the project page.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[demo]${NC} $*"; }
ok()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[✗]${NC} $*"; }
sep()   { echo -e "${CYAN}────────────────────────────────────────${NC}"; }

sep
echo -e "${CYAN}  FleetSafe-VLNVerse+ Demo${NC}"
echo -e "  VLN Hub · Project Page · Safety Certificates"
sep

# ── Step 1: IAmGoodNavigator ─────────────────────────────────────────────────
info "Step 1/7 — IAmGoodNavigator setup"
if [[ -f "external/IAmGoodNavigator/demo.py" ]]; then
    ok "IAmGoodNavigator already cloned"
else
    bash scripts/setup_iamgoodnavigator.sh
fi

# ── Step 2: VLNTube ─────────────────────────────────────────────────────────
info "Step 2/7 — VLNTube setup"
if [[ -f "external/VLNTube/scene_graph/__init__.py" ]] || \
   [[ -d "external/VLNTube/scene_graph" ]]; then
    ok "VLNTube already cloned"
else
    bash scripts/setup_vlntube.sh
fi

# ── Step 3: Yahboom assets ───────────────────────────────────────────────────
info "Step 3/7 — Yahboom M3 Pro asset check"
if [[ -f "assets/robots/yahboom_m3_pro/asset_report.json" ]]; then
    ok "Asset report already present"
else
    bash scripts/setup_yahboom_m3_assets.sh || warn "Yahboom URDF not found — Isaac demo blocked (expected)"
fi

# ── Step 4: Download VLNTube HF assets ──────────────────────────────────────
info "Step 4/7 — VLNTube HuggingFace data"
if [[ -f "datasets/vlntube/asset_download_report.json" ]]; then
    ok "HF assets already downloaded"
else
    warn "Downloading minimal HuggingFace assets (requires huggingface_hub)..."
    bash scripts/download_vlntube_minimal_assets.sh || warn "HF download skipped (optional)"
fi

# ── Step 5: Re-run indexers ──────────────────────────────────────────────────
info "Step 5/7 — Re-index VLNVerse and VLNTube"
python -m fleetsafe_vln.benchmark.vlnverse_indexer 2>/dev/null && ok "VLNVerse indexed" || warn "VLNVerse indexer failed"
python -m fleetsafe_vln.datagen.vlntube_indexer   2>/dev/null && ok "VLNTube indexed"  || warn "VLNTube indexer failed"

# ── Step 6: Paper draft ──────────────────────────────────────────────────────
info "Step 6/7 — Paper draft"
if [[ -f "docs/paper/FleetSafe_VLN_Paper_Draft.md" ]]; then
    ok "Paper draft present: docs/paper/FleetSafe_VLN_Paper_Draft.md"
else
    fail "Paper draft missing — expected at docs/paper/FleetSafe_VLN_Paper_Draft.md"
fi

# ── Step 7: Command Center ───────────────────────────────────────────────────
info "Step 7/7 — Command Center"
BACKEND_RUNNING="false"
if curl -s --max-time 2 http://localhost:8000/api/vln-hub/status >/dev/null 2>&1; then
    ok "Backend already running on :8000"
    BACKEND_RUNNING="true"
else
    warn "Backend not running. Start with:"
    echo "    cd command-center && python -m uvicorn backend.main:app --reload --port 8000"
fi

FRONTEND_RUNNING="false"
if curl -s --max-time 2 http://localhost:3000 >/dev/null 2>&1; then
    ok "Frontend already running on :3000"
    FRONTEND_RUNNING="true"
else
    warn "Frontend not running. Start with:"
    echo "    cd command-center/frontend && npm run dev -- --port 3000"
fi

sep

echo ""
echo -e "${GREEN}FleetSafe-VLNVerse+ Demo Ready${NC}"
echo ""
echo "  Project page:  http://localhost:3000/project"
echo "  VLN Hub:       http://localhost:3000/dashboard/vln-hub"
echo "  Evidence:      http://localhost:3000/dashboard/evidence"
echo "  API live:      http://localhost:8000/api/vln-hub/live"
echo "  API project:   http://localhost:8000/api/vln-hub/project-page"
echo "  API pipeline:  http://localhost:8000/api/vln-hub/vlntube-pipeline"
echo "  API paper:     http://localhost:8000/api/vln-hub/paper"
echo ""
echo "  Isaac Sim episode (requires Isaac Sim):"
echo "    bash scripts/run_iamgoodnavigator_episode.sh fine 0"
echo "    # Then in Isaac: Perspective → Cameras → FloatingCamera"
echo ""
echo "  Yahboom URDF (requires physical robot):"
echo "    bash scripts/pull_yahboom_assets_from_robot.sh yahboom@<ROBOT_IP>"
echo ""
echo "  Acceptance check:"
echo "    bash scripts/check_fleetsafe_vlnverse_plus_demo.sh"
echo ""
sep

# Open project page if desktop available
if command -v xdg-open >/dev/null 2>&1 && "${FRONTEND_RUNNING}"; then
    xdg-open "http://localhost:3000/project" 2>/dev/null || true
fi
