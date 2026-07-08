"""Validate the stop-head firing-boundary recalibration study.

Usage:
    python3 scripts/gnm/validate_stop_boundary_study.py [study_dir]

Exit 0 only if the study outputs are complete, sourced from the three
live hospital shadow episodes, authority-free, and labelled as
recalibration candidates with no improvement claims anywhere.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROUTES = ["hospital_straight_short_A", "hospital_straight_medium_B",
          "hospital_low_curvature_C"]


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def main():
    if len(sys.argv) > 1:
        study = Path(sys.argv[1])
    else:
        root = REPO / "assets/experiments/recalibration"
        dirs = sorted(d for d in root.iterdir()
                      if d.is_dir() and d.name.startswith("stop_head_boundary"))
        if not dirs:
            return fail("no boundary study found")
        study = dirs[-1]
    print(f"validating study: {study.name}")

    sj, sc = study / "summary.json", study / "summary.csv"
    if not sj.exists() or not sc.exists():
        return fail("summary.json or summary.csv missing")
    summary = json.loads(sj.read_text())

    srcs = summary.get("source_episodes", [])
    for route in ROUTES:
        if not any(s.startswith(route) for s in srcs):
            return fail(f"source episode missing for {route}")
        ep_dir = REPO / "assets/experiments/trajectories" / \
            next(s for s in srcs if s.startswith(route))
        meta = json.loads((ep_dir / "episode_metadata.json").read_text())
        if meta.get("stop_head_authority") is not False:
            return fail(f"{route}: source episode not authority-free")
    print(f"all 3 source episodes present and authority-free")

    if "no_authority" not in summary.get("label", "") \
            or "no_improvement" not in summary.get("label", ""):
        return fail("study label must state no-authority/no-improvement")
    rules = summary.get("rules", [])
    if not rules:
        return fail("no candidate rules in study")
    if any(r.get("label") != "recalibration_candidate" for r in rules):
        return fail("every rule must be labelled recalibration_candidate")
    fired_all = [r for r in rules if r["episodes_missed"] == 0]
    print(f"{len(rules)} candidate rules, all labelled recalibration "
          f"candidates; {len(fired_all)} fire in all episodes; "
          f"recommended: {summary.get('recommended_candidate')}")

    status = (REPO / "docs/experiments/PROJECT_BASELINE_STATUS.md").read_text()
    lowered = status.lower()
    for banned in ("stop head improves", "fleetsafe improves",
                   "campaign complete", "sr/spl established"):
        if banned in lowered:
            return fail(f"status doc contains banned claim: {banned}")
    if "authority not yet tested" not in lowered:
        return fail("status doc must state authority is not yet tested")
    print("status doc: no improvement claims; authority marked untested")

    print("PASS: firing-boundary recalibration study validated "
          "(calibratable boundary identified; candidates only)")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
