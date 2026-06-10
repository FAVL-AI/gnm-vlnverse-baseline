# Explainability Metrics — FleetSafe VisualNav Benchmark v0.1

These metrics quantify the quality and completeness of the explainability layer.
They are computed from the `ExplainabilityStepRecord` list and written to
`aggregate_metrics.json` under `explainability_metrics`.

---

## explanation_coverage

**Formula:**
```
explanation_coverage = #{steps with non-empty natural_language} / total_steps
```

**Units:** dimensionless [0, 1]

**Direction:** higher is better

**Edge cases:**
- A step with `natural_language = "Normal operation."` counts as covered.
- A step with `natural_language = ""` does not count as covered.
- If total_steps = 0: undefined; report as N/A.

**CI method:** 95% bootstrap

**Publication allowed:** Yes

**Interpretation:** Measures what fraction of episode steps have a human-readable
explanation. A value of 1.0 means every step is explained.

---

## intervention_explanation_rate

**Formula:**
```
intervention_steps = #{steps where causal_event_type in {cbf_intervention, estop}}
explained_intervention_steps = #{intervention steps with non-empty natural_language}
intervention_explanation_rate = explained_intervention_steps / max(1, intervention_steps)
```

**Units:** dimensionless [0, 1]

**Direction:** higher is better

**Edge cases:**
- If no interventions occur (baseline run or no obstacles): rate = 1.0 by convention
  (vacuously true; report with note "no interventions").
- Both `cbf_intervention` and `estop` event types count.

**CI method:** 95% bootstrap

**Publication allowed:** Yes

**Interpretation:** The critical metric for the no-black-box claim. A rate of 1.0
means every FleetSafe action modification has a causal explanation.

---

## counterfactual_validity_rate

**Formula:**
```
cbf_steps = #{steps where causal_event_type == cbf_intervention}
valid_cf_steps = #{cbf steps where distance_shift_m > 0}
counterfactual_validity_rate = valid_cf_steps / max(1, cbf_steps)
```

**Units:** dimensionless [0, 1]

**Direction:** higher is better

**Edge cases:**
- `distance_shift_m = 0` means the obstacle was already beyond the safety margin
  when the intervention was triggered — this can occur if the intervention was
  caused by a wz correction only. These steps are not counted as valid
  counterfactuals.
- If no CBF interventions: rate = 1.0 by convention.

**CI method:** 95% bootstrap

**Publication allowed:** Yes

**Interpretation:** Measures what fraction of CBF interventions have a geometrically
valid counterfactual (i.e., the computed shift would satisfy the CBF constraint).
A rate of 1.0 means all counterfactuals are analytically grounded.

---

## causal_graph_size_mean

**Formula:**
```
graph_size_step_t = |nodes_t| + |edges_t|
causal_graph_size_mean = (1/T) Σ_t graph_size_step_t
```

**Units:** count (nodes + edges)

**Direction:** informational (larger graphs indicate richer scene structure)

**Edge cases:**
- An empty graph (no obstacles) has size = 2 (robot + goal nodes).
- Waypoint nodes are included in the count.

**CI method:** standard deviation reported alongside mean

**Publication allowed:** Yes (informational)

---

## explanation_latency_ms_mean

**Formula:**
```
explanation_latency_ms_mean = (1/T) Σ_t latency_ms_t
```

Where `latency_ms_t` is the wall-clock time to build the scene graph, run causal
reasoning, generate the counterfactual, and produce the natural language explanation.

**Units:** milliseconds

**Direction:** lower is better

**Edge cases:**
- Latency includes only the explainability pipeline, not the policy inference.
- At 4 Hz control, 250 ms per cycle budget; explanation must not consume >50 ms.

**CI method:** p95 reported alongside mean

**Publication allowed:** Yes (informational)

---

## Explainability coverage summary

An episode passes the explainability coverage check if:

- `explanation_coverage >= 1.0`
- `intervention_explanation_rate >= 1.0`
- `counterfactual_validity_rate >= 1.0` (for any CBF episodes)

These three conditions together constitute the "no-black-box guarantee" for
a single episode.
