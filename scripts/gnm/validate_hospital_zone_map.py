"""Validate the hospital safety-zone map."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
D = REPO / "assets/datasets/isaac_hospital_navgen_v0"

def fail(m): print(f"FAIL: {m}"); return False

def main():
    z = json.loads((D / "safety_zones.json").read_text())
    kinds = {x["zone"] for x in z["zones"]}
    if kinds != {"red", "amber", "green"}: return fail(f"zones {kinds}")
    for x in z["zones"]:
        poly = x["polygon"]
        if len(poly) < 3: return fail(f"{x['name']}: degenerate polygon")
        for px, py in poly:
            if abs(px) > 6 or abs(py) > 6:
                return fail(f"{x['name']}: outside safety envelope")
    pol = z["policy"]
    if "forbidden" not in pol["red"] or "cost" not in pol["amber"]:
        return fail("zone policy semantics missing")
    print(f"zone map valid: {len(z['zones'])} zones (red/amber/green), all "
          "inside the +/-6 m envelope, policy semantics present")
    print("PASS: hospital zone map validated")
    return True

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
