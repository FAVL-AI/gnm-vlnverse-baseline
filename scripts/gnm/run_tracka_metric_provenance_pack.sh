#!/usr/bin/env bash
# One-command Track A metric provenance pack.
# Runs all 9 steps: generate, verify, per-scene, paired, robustness, expanded,
# claim ledger, and paper compile.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Track A metric provenance pack (9 steps) ==="
echo ""

echo "[1/9] Generating all-methods per-episode provenance (75 rows)..."
python3 scripts/gnm/generate_all_methods_provenance.py

echo ""
echo "[2/9] Verifying baseline per-episode provenance..."
python3 scripts/gnm/verify_tracka_metric_provenance.py

echo ""
echo "[3/9] Verifying all-methods per-episode provenance (with bootstrap CIs)..."
python3 scripts/gnm/verify_tracka_all_methods_metric_provenance.py

echo ""
echo "[4/9] Per-scene breakdown (5 methods × 4 scenes, 15-episode val)..."
python3 scripts/gnm/compute_tracka_per_scene_breakdown.py

echo ""
echo "[5/9] Paired comparison and bootstrap seed stability..."
python3 scripts/gnm/compute_tracka_paired_comparison.py

echo ""
echo "[6/9] Robustness summary..."
python3 scripts/gnm/compute_tracka_robustness_summary.py

echo ""
echo "[7/9] Expanded 253-episode provenance (baseline + oracle, all train+val)..."
python3 scripts/gnm/generate_expanded_tracka_provenance.py
python3 scripts/gnm/verify_expanded_tracka_provenance.py

echo ""
echo "[8/9] Updating research claim ledger..."
python3 scripts/gnm/check_research_claim_gates.py

echo ""
echo "[9/9] Compiling ICRA paper (two passes)..."
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
echo "  results/research_audit/tracka_all_methods_per_episode_metric_provenance.csv  (75 rows)"
echo "  results/research_audit/tracka_all_methods_metric_provenance_report.md"
echo "  results/research_audit/tracka_per_scene_breakdown.csv                        (20 rows)"
echo "  results/research_audit/tracka_paired_comparison.md"
echo "  results/research_audit/tracka_bootstrap_seed_stability.md"
echo "  results/research_audit/tracka_robustness_summary.md"
echo "  results/research_audit/tracka_expanded_253ep_baseline_oracle_provenance.csv  (506 rows)"
echo "  results/research_audit/tracka_expanded_provenance_report.md"
echo "  results/research_audit/tracka_expanded_methodology_note.md"
echo "  results/research_audit/tracka_metric_provenance_report.md"
echo "  results/research_audit/research_claim_validation_ledger.md"
echo "  paper/icra_metric_provenance_stopping/main.pdf  (if pdflatex available)"
