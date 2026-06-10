# Scene Freeze Policy

## Purpose

Reproducibility in navigation benchmarking requires that the same scene
definition produces identical results across labs and over time.
This policy defines how scenes are specified, frozen, and versioned.

---

## Canonical scene set

The canonical scene set for benchmark version 0.1.0 is defined in:

```
benchmarks/scenes/canonical/SCENESET_v0.1.yaml
```

This file is immutable once published (first paper submission that uses it).

---

## Scene definition completeness

A fully specified canonical scene includes:

| Field | Required |
|---|---|
| `scene_id` | Yes |
| `scene_version` | Yes |
| `frozen: true` | Yes |
| `start_goal_pairs` with `optimal_path_m` | Yes |
| `obstacles` (positions + radii) | Yes (empty list if none) |
| `dynamic_agents` (position function + velocity) | Yes (empty list if none) |
| `walls` (segment list) | Yes |
| `seed_policy` | Yes |
| `hash` | Placeholder before first submission; SHA256 after |

---

## Freezing a scene

A scene is frozen when:

1. Its YAML definition is complete (all required fields populated).
2. `frozen: true` is set.
3. The scene has been run through the benchmark pipeline at least once with
   the mock backend and all transparency checks pass.
4. The `hash` field is computed from the serialised scene definition
   and written to the YAML.

**Computing the hash:**

```bash
python - <<'EOF'
import hashlib, json, yaml
with open("benchmarks/scenes/canonical/SCENESET_v0.1.yaml") as f:
    data = yaml.safe_load(f)
scene = next(s for s in data["scenes"] if s["scene_id"] == "straight_corridor")
canon = json.dumps(scene, sort_keys=True, ensure_ascii=True)
print(hashlib.sha256(canon.encode()).hexdigest())
EOF
```

---

## Scene change policy

### Before first publication

Scenes may be modified. `frozen: true` must be removed before modification
and restored after. The `hash` field must be recomputed.

### After first publication

Scenes must not be modified. To change a scene:

1. Increment `SCENESET_VERSION` (MINOR bump).
2. Create a new scene entry with a new `scene_version`.
3. Run the new scene set through the full pipeline.
4. Results from the old scene version are not comparable to results
   from the new scene version for the affected scenes.

### Adding a new scene

A new scene may be added without modifying existing scenes (MINOR bump).
Existing results are not affected.

---

## Dynamic agent specification

Dynamic agents must specify a deterministic position function:

```yaml
dynamic_agents:
  - agent_id: dynamic_agent_0
    start_position: [4.0, -1.5]
    velocity: [0.0, 0.3]       # constant velocity (m/s)
    radius_m: 0.15
    crossing_time_s: 5.0       # after this, agent is considered past
```

Position at time `t` (seconds):

```
pos(t) = start_position + velocity × min(t, crossing_time_s)
```

This is the same formula used in `_MockSimState.step()`. The MuJoCo and
Isaac Lab backends must replicate this behaviour exactly.

---

## Scene integrity checks

`scripts/visualnav/validate_benchmark_artifact.py` verifies:

1. The `sceneset_version` in `metadata.yaml` matches the frozen scene set.
2. The scene names in `metadata.yaml → scenes` are a subset of the canonical
   scene set for that version.

Any result produced with a scene that is not in the canonical set for the
claimed `sceneset_version` is invalid.
