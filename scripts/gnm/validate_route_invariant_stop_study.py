"""Validate the route-invariant stop recalibration study.

Usage:
    python3 scripts/gnm/validate_route_invariant_stop_study.py [study_dir]
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALL_SOURCES = ["hospital_straight_short_A", "hospital_straight_medium_B",
               "hospital_low_curvature_C", "authcmp_D_baseline",
               "authcmp_E_baseline", "authcmp_D_stopauth",
               "authcmp_E_stopauth"]
ALLOWED_LABELS = {"recalibration_candidate", "exploratory",
                  "privileged_diagnostic", "REJECTED"}


def fail(msg):
    print(f"FAIL: {msg}")
    return False


def main():
    if len(sys.argv) > 1:
        study = Path(sys.argv[1])
    else:
        root = REPO / "assets/experiments/recalibration"
        dirs = sorted(d for d in root.iterdir()
                      if d.name.startswith("route_invariant_stop"))
        if not dirs:
            return fail("study missing")
        study = dirs[-1]
    print(f"validating study: {study.name}")
    summary = json.loads((study / "summary.json").read_text())
    if not (study / "summary.csv").exists() \
            or not (study / "report.md").exists():
        return fail("summary.csv or report.md missing")

    root = REPO / "assets/experiments/trajectories"
    for prefix in ALL_SOURCES:
        if not any(d.name.startswith(prefix) for d in root.iterdir()):
            return fail(f"source trajectory missing: {prefix}")
    print("all 7 source trajectories present")

    if "held out as validation" not in summary["protocol"]:
        return fail("protocol must declare D/E as held-out validation")
    if "no_authority" not in summary["label"]:
        return fail("study must be labelled no-authority")
    print("protocol: D/E held-out validation, no authority episodes run")

    rules = summary["rules"]
    labels = [r["label"] for r in rules]
    if any(l not in ALLOWED_LABELS for l in labels):
        return fail(f"unexpected labels: {set(labels) - ALLOWED_LABELS}")
    tuned = [r for r in rules if r.get("tuned")]
    invariant = [r for r in tuned if r["label"] == "recalibration_candidate"]
    if len(tuned) < 3:
        return fail("fewer than 3 candidate rules evaluated")
    if not any(r["label"] == "REJECTED"
               and "absolute" in r["family"] for r in rules):
        return fail("absolute-threshold rejection not recorded")
    print(f"{len(tuned)} rules evaluated ({len(invariant)} route-invariant "
          f"candidates); absolute gate marked REJECTED; "
          f"preferred: {summary['preferred_candidate']}")

    report = (study / "report.md").read_text().lower()
    if "no improvement claim" not in report:
        return fail("report must state no improvement claim")
    status = (REPO / "docs/experiments/PROJECT_BASELINE_STATUS.md").read_text()
    lowered = status.lower()
    for banned in ("fleetsafe improves", "campaign complete",
                   "sr/spl established"):
        if banned in lowered:
            return fail(f"status doc banned claim: {banned}")
    if "authority rerun" not in lowered or "pending" not in lowered:
        return fail("status doc must mark the authority rerun as pending")
    print("report + status doc: no improvement claims; "
          "authority rerun pending")
    print("PASS: route-invariant stop recalibration study validated")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
