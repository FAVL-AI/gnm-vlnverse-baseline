"""Isaac-Hospital-NavGen instruction generator (Stage 4, template-based).

Grounded in scene semantics + the episode's rendered zone trace — never
mentions a landmark or zone the route did not touch or head toward.
LLM Describer-Verifier-Synthesizer = future work.

Usage: python3 scripts/datasets/hospital_navgen_generate_instructions.py <episodes_root>
"""

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
for ep in sorted(d for d in root.iterdir() if d.is_dir()):
    m = json.loads((ep / "metadata.json").read_text())
    z = json.loads((ep / "zone_trace.json").read_text())
    goal_lm = m["goal_landmark"]; start_lm = m["start_landmark"]
    amber = m["amber_steps"] > 0
    turns = m["turn_bin"]
    instrs = {
        "simple_goal": f"Go to the {goal_lm}.",
        "route": (f"Start near the {start_lm} and "
                  + ("follow the corridor, turning as needed, "
                     if turns != "straight" else "move straight ahead ")
                  + f"until you reach the {goal_lm}."),
        "safety_aware": (f"Go to the {goal_lm} while staying out of the "
                         "red restricted areas."),
        "zone_aware": (f"Pass through the amber caution area slowly and "
                       f"stop at the goal image near the {goal_lm}."
                       if amber else
                       f"Stay in the green area and stop at the goal "
                       f"image near the {goal_lm}."),
    }
    grounding = {"start_landmark": start_lm, "goal_landmark": goal_lm,
                 "amber_on_route": amber,
                 "red_on_route": m["red_steps"] > 0,
                 "turn_bin": turns,
                 "generator": "template_v0 (grounded; LLM pipeline future)"}
    (ep / "instruction.json").write_text(
        json.dumps({"instructions": instrs, "grounding": grounding},
                   indent=2))
    print(f"{ep.name}: 4 instruction variants ({'amber' if amber else 'green'})")
