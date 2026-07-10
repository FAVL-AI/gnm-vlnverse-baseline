"""Validate the hospital episode review tool + latest export."""
import json, subprocess, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]

def fail(m): print(f"FAIL: {m}"); return False

def main():
    r = subprocess.run([sys.executable,
                        "scripts/robots/isaac_hospital_episode_reviewer.py",
                        "--list"], capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0 or "goal=" not in r.stdout:
        return fail("reviewer --list failed")
    n_listed = len(r.stdout.strip().splitlines())
    reviews = sorted(REPO.glob("assets/experiments/hospital_episode_review_*/*"))
    if not reviews: return fail("no review export found")
    out = reviews[-1]
    for f in ("review_manifest.json", "start_state.png", "goal_state.png",
              "final_current_state.png", "start_current_goal_strip.png",
              "telemetry_summary.json", "contact_summary.json",
              "review_notes.md"):
        if not (out / f).exists(): return fail(f"{out.name}: missing {f}")
    man = json.loads((out / "review_manifest.json").read_text())
    if "front-facing RGB" not in man["main_view"]:
        return fail("main view is not the front camera")
    if "not real-robot evidence" not in man["claim_boundary"]:
        return fail("claim boundary missing")
    if "NOT primary evidence" not in man["debug_view"]:
        return fail("debug view not marked secondary")
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"],
                            capture_output=True, text=True, cwd=REPO).stdout
    import re
    if re.search(r"\.(mp4|db3|pt|pth)$", staged, re.M):
        return fail("heavy artifacts staged")
    print(f"episode review valid: {n_listed} episodes listable; latest "
          f"export {out.name} complete (strip + manifest + telemetry + "
          "contacts); front-RGB main view; debug view secondary; claim "
          "boundary present; no heavy artifacts staged")
    print("PASS: hospital episode review validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
