"""Isaac-Hospital-NavGen verifier (Stage 5).

Usage: python3 scripts/datasets/hospital_navgen_verify_episode.py <episodes_root>
"""

import json
import pickle
import sys
from pathlib import Path

import numpy as np

root = Path(sys.argv[1])
sem = json.loads(Path("assets/datasets/isaac_hospital_navgen_v0/"
                      "scene_semantics.json").read_text())
known = {lm["name"] for lm in sem["landmarks"]} | {"main lobby"}
ok = bad = 0
for ep in sorted(d for d in root.iterdir() if d.is_dir()):
    errs = []
    m = json.loads((ep / "metadata.json").read_text())
    n = len(list(ep.glob("[0-9]*.jpg")))
    t = pickle.loads((ep / "traj_data.pkl").read_bytes())
    if t["position"].shape != (n, 2):
        errs.append("traj/frame mismatch")
    if m["red_steps"] > 0:
        errs.append("red-zone steps on a standard route")
    if not (ep / "goal.png").exists():
        errs.append("goal image missing")
    else:
        from PIL import Image
        g = np.array(Image.open(ep / "goal.png").convert("L"))
        if g.std() < 8:
            errs.append(f"goal image featureless (std {g.std():.1f})")
    ins = json.loads((ep / "instruction.json").read_text())
    for name in (ins["grounding"]["start_landmark"],
                 ins["grounding"]["goal_landmark"]):
        if name not in known:
            errs.append(f"instruction references unknown landmark {name}")
    if ins["grounding"]["amber_on_route"] != (m["amber_steps"] > 0):
        errs.append("instruction grounding disagrees with zone trace")
    if "front-facing" not in m["camera"]["convention"]:
        errs.append("camera convention wrong")
    if "not real-robot" not in m["claim"]:
        errs.append("claim boundary missing")
    if errs:
        bad += 1
        print(f"FAIL {ep.name}: {errs}")
    else:
        ok += 1
print(f"verified: {ok} OK, {bad} failed")
sys.exit(1 if bad else 0)
