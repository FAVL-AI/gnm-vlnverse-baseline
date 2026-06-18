# Metric-Provenance Runtime Stopping Paper Draft

This folder contains the ICRA/IEEE-style paper draft for the GNM-VLNVerse Track A stopping-reliability study.

## Core claim

This paper studies a specific termination reliability failure mode: the baseline GNM-style policy enters the goal region more often than it successfully completes the episode.

The baseline result is now backed by per-episode provenance:

- 15 validation episodes
- success radius: 3.0 m
- final successes: 3 / 15
- oracle successes: 7 / 15
- SR: 20.0%
- OSR: 46.7%
- NE: 6.51 m

## Claim boundary

This paper does not claim global superiority over GNM, ViNT, NoMaD, or SaferPath.

It also does not claim:

- valid Yahboom episode_001 rosbag2 recording
- Yahboom rosbag2 to GNM dataset conversion
- GNM fine-tuning on validated Yahboom data
- physical Yahboom closed-loop deployment
- completed Track B language grounding

Those claims remain blocked by the research claim validation ledger until evidence exists.
