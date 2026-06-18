#!/usr/bin/env bash
# One-command Track A metric provenance pack.
# Regenerates all-methods per-episode CSV, verifies all five methods,
# produces per-scene breakdown, paired comparison, robustness summary,
# updates the claim ledger, and compiles the paper.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Track A metric provenance pack ==="
echo ""

echo "[1/8] Generating all-methods per-episode provenance..."
python3 scripts/gnm/generate_all_methods_provenance.py

echo ""
echo "[2/8] Verifying baseline per-episode provenance..."
python3 scripts/gnm/verify_tracka_metric_provenance.py

echo ""
echo "[3/8] Verifying all-methods per-episode provenance (with bootstrap CIs)..."
python3 scripts/gnm/verify_tracka_all_methods_metric_provenance.py

echo ""
echo "[4/8] Per-scene breakdown (all 5 methods × 4 scenes)..."
python3 scripts/gnm/compute_tracka_per_scene_breakdown.py

echo ""
echo "[5/8] Paired comparison and bootstrap seed stability..."
python3 scripts/gnm/compute_tracka_paired_comparison.py

echo ""
echo "[6/8] Robustness summary..."
python3 scripts/gnm/compute_tracka_robustness_summary.py

echo ""
echo "[7/8] Updating research claim ledger..."
python3 scripts/gnm/check_research_claim_gates.py

echo ""
echo "[8/8] Compiling ICRA paper (two passes)..."
if command -v pdflatex &>/dev/null; then
    (
        cd paper/icra_metric_provenance_stopping
        pdflatex -interaction=nonstopmode main.tex > /dev/null 2>&1
        pdflatex -interaction=nonstopmode main.tex > /dev/null 2>&1
        PAGES=$(pdfinfo main.pdf 2>/dev/null | awk '/Pages/{print $2}' || echo "?")
        echo "[OK] Paper compiled: main.pdf (${PAGES} pages)"
    )
else
    echo "[SKIP] pdflatex not found — paper compile skipped"
fi

echo ""
echo "=== Pack complete ==="
echo ""
echo "Key outputs:"
echo "  results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv"
echo "  results/research_audit/tracka_all_methods_metric_provenance_report.md"
echo "  results/research_audit/tracka_per_scene_breakdown.csv"
echo "  results/research_audit/tracka_per_scene_breakdown.md"
echo "  results/research_audit/tracka_paired_comparison.md"
echo "  results/research_audit/tracka_bootstrap_seed_stability.md"
echo "  results/research_audit/tracka_robustness_summary.md"
echo "  results/research_audit/tracka_metric_provenance_report.md"
echo "  results/research_audit/research_claim_validation_ledger.md"
echo "  paper/icra_metric_provenance_stopping/main.pdf  (if pdflatex available)"
