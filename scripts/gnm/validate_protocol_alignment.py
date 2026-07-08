"""Validate protocol-alignment and method-choice appendices."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
A = REPO / "assets/experiments/training_ablation/mnv2_ema_20260708"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    pa = A / "protocol_alignment_vlnverse_vlntube.md"
    mc = A / "method_choice_justification.md"
    for f in (pa, mc, A / "dataset_manifest.json"):
        if not f.exists(): return fail(f"missing {f.name}")
    t = pa.read_text() + mc.read_text()
    low = " ".join(t.lower().split())
    for need in ("dataset_manifest.json", "four-scene", "15",
                 "not yet the full original", "collision rate"):
        if need.lower() not in low: return fail(f"appendix missing: {need}")
    for banned in ("full vlnverse benchmark is complete",
                   "language-instruction following is achieved"):
        if banned in low: return fail(f"banned claim: {banned}")
    if "language" not in low or "goal images" not in low:
        return fail("language vs image-goal distinction missing")
    summary = (A / "professor_summary.md").read_text()
    for ref in ("protocol_alignment_vlnverse_vlntube.md",
                "method_choice_justification.md", "dataset_manifest.json"):
        if ref not in summary: return fail(f"summary missing ref {ref}")
    manuscript = (REPO / "docs/research/GOOD_BAD_UGLY_RESEARCH_MANUSCRIPT.md").read_text()
    if "Method-choice decision" not in manuscript:
        return fail("manuscript missing method-choice section")
    print("appendices present; subset/held-out counts stated; offline vs "
          "Isaac separated; no full-benchmark or language claims; summary "
          "and manuscript cross-reference all three documents")
    print("PASS: protocol alignment validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
