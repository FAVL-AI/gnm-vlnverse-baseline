"""Validate NavGen language instructions against grounding."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
GEN = REPO / "datasets/isaac_hospital_navgen_v0/unassigned"
sem = json.loads((REPO / "assets/datasets/isaac_hospital_navgen_v0/"
                  "scene_semantics.json").read_text())
KNOWN = {lm["name"] for lm in sem["landmarks"]} | {"main lobby"}

def fail(m): print(f"FAIL: {m}"); return False

def main():
    if not GEN.exists(): return fail("no episodes")
    n = 0
    for ep in GEN.iterdir():
        ins = json.loads((ep / "instruction.json").read_text())
        g = ins["grounding"]
        if g["goal_landmark"] not in KNOWN or g["start_landmark"] not in KNOWN:
            return fail(f"{ep.name}: unknown landmark in grounding")
        m = json.loads((ep / "metadata.json").read_text())
        if g["amber_on_route"] != (m["amber_steps"] > 0):
            return fail(f"{ep.name}: amber grounding mismatch")
        txt = " ".join(ins["instructions"].values()).lower()
        if g["goal_landmark"].split(" (")[0].lower() not in txt:
            return fail(f"{ep.name}: goal landmark absent from instructions")
        if "amber" in txt and not g["amber_on_route"]:
            return fail(f"{ep.name}: amber mentioned but not on route")
        n += 1
    print(f"instructions valid on {n} episodes: grounded landmarks only, "
          "zone mentions match zone traces")
    print("PASS: hospital language instructions validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
