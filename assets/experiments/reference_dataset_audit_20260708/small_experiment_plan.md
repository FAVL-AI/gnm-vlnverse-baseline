# Small experiment plan — training-data study

**Experiment A (done):** original VLNTube train only — 191/12/50;
frozen-test result SR 32.0 / OSR 56.0 / NE 5.58 / SPL 0.315.

**Experiment B (Stage 4/5, running):** 191 original + 130 generated
top-down episodes (321 train), same val policy, same frozen
kujiale_0271, ONE final test evaluation. RQ-D2.

**Experiment C (diagnostic only, future):** load ONE public GNM-style
dataset sample (candidate: GoStanford2 modified — indoor, closest
regime) through a new adapter; report format, camera convention,
trajectory/action schema and adapter effort as a compatibility score.
No training, no performance claim. RQ-D3.

Fair-comparison ladder: Level 1 internal data comparison (now) →
Level 2 architecture comparison under one evaluator → Level 3
dataset-regime comparison → Level 4 full matched-protocol benchmark.
Never claim "we beat GNM/ViNT/NoMaD" from Level 1 evidence.
